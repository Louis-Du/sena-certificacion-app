import hashlib
from unittest.mock import MagicMock, patch

import pytest

from app.services import sheets_sync
from app.services.sheets_sync import (
    build_export_url,
    config_to_status,
    download_sheet,
    extract_sheet_id,
    get_config,
    run_sync,
    save_config,
)


def test_extract_sheet_id_from_edit_url():
    url = "https://docs.google.com/spreadsheets/d/ABC123xyz/edit#gid=0"
    assert extract_sheet_id(url) == "ABC123xyz"


def test_extract_sheet_id_from_other_path():
    url = "https://docs.google.com/spreadsheets/d/ID456/viewform"
    assert extract_sheet_id(url) == "ID456"


def test_extract_sheet_id_returns_none_for_invalid():
    assert extract_sheet_id("https://example.com/foo") is None
    assert extract_sheet_id("") is None


def test_build_export_url():
    assert (
        build_export_url("SHEETID")
        == "https://docs.google.com/spreadsheets/d/SHEETID/export?format=xlsx"
    )


def test_download_sheet_permission_error_mock_httpx():
    fake_response = MagicMock()
    fake_response.status_code = 403
    fake_response.content = b"<html>login</html>"
    with patch("app.services.sheets_sync.httpx.get", return_value=fake_response):
        with pytest.raises(PermissionError):
            download_sheet("SHEETID")


def test_download_sheet_html_login_mock_httpx():
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.content = b"<!doctype html><html><body>Sign in to Google</body></html>"
    with patch("app.services.sheets_sync.httpx.get", return_value=fake_response):
        with pytest.raises(PermissionError):
            download_sheet("SHEETID")


def test_save_config_and_status(client):
    response = client.post(
        "/api/sheets/sync",
        json={
            "url": "https://docs.google.com/spreadsheets/d/ID123/edit",
            "information_type": "actas_completo",
            "interval_seconds": 60,
            "enabled": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is True
    assert data["enabled"] is True
    assert data["url"] == "https://docs.google.com/spreadsheets/d/ID123/edit"


def test_interval_minimum(client):
    response = client.post(
        "/api/sheets/sync",
        json={
            "url": "https://docs.google.com/spreadsheets/d/ID123/edit",
            "interval_seconds": 5,
        },
    )
    assert response.status_code == 400


def test_run_permission_error(client):
    client.post(
        "/api/sheets/sync",
        json={"url": "https://docs.google.com/spreadsheets/d/ID123/edit"},
    )
    fake_response = MagicMock()
    fake_response.status_code = 403
    fake_response.content = b"<html>forbidden</html>"
    with patch("app.services.sheets_sync.httpx.get", return_value=fake_response):
        response = client.post("/api/sheets/sync/run")
    assert response.status_code == 200
    data = response.json()
    assert data["last_status"] == "error"
    assert "permisos" in (data["last_message"] or "").lower() or "pública" in (data["last_message"] or "").lower()


def test_run_unchanged_path(db_session):
    url = "https://docs.google.com/spreadsheets/d/ID999/edit"
    config = save_config(db_session, url)
    content = b"some-sheet-bytes"
    config.last_hash = hashlib.sha256(content).hexdigest()
    db_session.commit()

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.content = content
    with patch("app.services.sheets_sync.httpx.get", return_value=fake_response):
        run_sync(db_session)

    refreshed = get_config(db_session)
    assert refreshed.last_status == "unchanged"


def test_run_validation_error_path(db_session):
    url = "https://docs.google.com/spreadsheets/d/ID888/edit"
    save_config(db_session, url)
    content = b"not-a-valid-xlsx"

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.content = content
    with patch("app.services.sheets_sync.httpx.get", return_value=fake_response):
        run_sync(db_session)

    refreshed = get_config(db_session)
    assert refreshed.last_status == "error"


def test_patch_and_delete(client):
    client.post(
        "/api/sheets/sync",
        json={"url": "https://docs.google.com/spreadsheets/d/ID777/edit"},
    )
    r = client.patch("/api/sheets/sync", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    r2 = client.delete("/api/sheets/sync")
    assert r2.status_code == 200
    assert r2.json()["configured"] is False


def test_status_not_configured(client):
    r = client.get("/api/sheets/sync")
    assert r.status_code == 200
    assert r.json()["configured"] is False


def test_preview_then_confirm_imports_with_conflict_resolution(client):
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    content = (
        Path(__file__).parents[1]
        / "archivos_prueba"
        / "incorrectos"
        / "ACTAS_2026_incorrecto_conflictos_y_meses.xlsx"
    ).read_bytes()
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.content = content

    with patch("app.services.sheets_sync.httpx.get", return_value=fake_response):
        response = client.post(
            "/api/sheets/sync/preview",
            json={"url": "https://docs.google.com/spreadsheets/d/PREVIEW1/edit"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["preview"]["coherence_conflicts"]
    assert client.get("/api/imports/history").json()["items"] == []

    resolutions = [
        {"identification": item["identification"], "status": "CERTIFICADOS"}
        for item in data["preview"]["coherence_conflicts"]
    ]
    confirm = client.post(
        "/api/sheets/sync/confirm",
        json={
            "validation_id": data["validation_id"],
            "conflict_resolutions": resolutions,
            "accept_missing_complementaria": True,
        },
    )
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "imported"
    history = client.get("/api/imports/history").json()["items"]
    assert len(history) == 1


def test_preview_unchanged_does_not_stage(client):
    from unittest.mock import MagicMock, patch

    url = "https://docs.google.com/spreadsheets/d/UNCHANGED1/edit"
    content = b"same-sheet-content"
    client.post("/api/sheets/sync", json={"url": url})
    # Force the stored hash to match the mocked download.
    from app.services.sheets_sync import get_config

    with client.session_factory() as session:
        config = get_config(session)
        config.last_hash = hashlib.sha256(content).hexdigest()
        session.commit()

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.content = content
    with patch("app.services.sheets_sync.httpx.get", return_value=fake_response):
        response = client.post("/api/sheets/sync/preview", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "unchanged"
    assert "validation_id" not in response.json()


# ---------------------------------------------------------------------------
# Issue #85: conflictos pendientes, notificacion unica y resolucion diferida
# ---------------------------------------------------------------------------
from io import BytesIO
from pathlib import Path

from app.services.sheets_sync import (
    _fingerprint_conflicts,
    mark_notified,
    pending_conflicts_payload,
    resolve_pending,
)

CONFLICT_XLSX = (
    Path(__file__).parents[1]
    / "archivos_prueba"
    / "incorrectos"
    / "ACTAS_2026_incorrecto_conflictos_y_meses.xlsx"
)
CONFLICT_URL = "https://docs.google.com/spreadsheets/d/CONFLICT85/edit"


def _fake_download(content: bytes):
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.content = content
    return patch("app.services.sheets_sync.httpx.get", return_value=fake_response)


def _run_conflict_sync(client) -> bytes:
    content = CONFLICT_XLSX.read_bytes()
    client.post("/api/sheets/sync", json={"url": CONFLICT_URL})
    with _fake_download(content):
        response = client.post("/api/sheets/sync/run")
    assert response.status_code == 200
    assert response.json()["last_status"] == "conflict_pending"
    return content


def _resolutions(conflicts: list[dict]) -> list[dict]:
    return [
        {"identification": item["identification"], "status": "CERTIFICADOS"}
        for item in conflicts
    ]


def test_conflict_fingerprint_is_stable_and_order_independent():
    first = [{"identification": "2"}, {"identification": "1"}]
    second = [{"identification": "1"}, {"identification": "2"}, {"identification": "1"}]

    assert _fingerprint_conflicts(first) == _fingerprint_conflicts(second)
    assert _fingerprint_conflicts(first) != _fingerprint_conflicts([{"identification": "3"}])
    assert _fingerprint_conflicts([]) is None


def test_run_conflict_pending_persists_recoverable_state(db_session):
    content = CONFLICT_XLSX.read_bytes()
    save_config(db_session, CONFLICT_URL)

    with _fake_download(content):
        run_sync(db_session)

    config = get_config(db_session)
    status = config_to_status(config)
    assert config.last_status == "conflict_pending"
    # El hash de la hoja NO se actualiza: el lote sigue pendiente de resolver.
    assert config.last_hash is None
    assert config.pending_hash == hashlib.sha256(content).hexdigest()
    assert config.pending_validation_id
    assert config.pending_conflict_count >= 1
    assert config.pending_conflict_fingerprint
    assert config.pending_content
    assert config.pending_conflicts_json
    assert config.pending_preview_json
    assert config.notified_at is None
    assert status["conflict_pending"] is True
    assert status["notification_pending"] is True
    assert status["pending_conflict_count"] == config.pending_conflict_count


def test_same_pending_conflict_does_not_renotify_or_change_hash(db_session):
    content = CONFLICT_XLSX.read_bytes()
    save_config(db_session, CONFLICT_URL)
    with _fake_download(content):
        run_sync(db_session)

    config = get_config(db_session)
    validation_id = config.pending_validation_id
    fingerprint = config.pending_conflict_fingerprint
    mark_notified(db_session, fingerprint)
    config = get_config(db_session)
    notified_at = config.notified_at
    assert notified_at is not None

    # El worker vuelve a correr cada 60 s con el mismo contenido.
    with _fake_download(content):
        run_sync(db_session)

    config = get_config(db_session)
    assert config.last_status == "conflict_pending"
    assert config.pending_validation_id == validation_id
    assert config.pending_conflict_fingerprint == fingerprint
    assert config.notified_at == notified_at
    assert config.last_hash is None
    assert config_to_status(config)["notification_pending"] is False


def test_new_sheet_content_with_same_conflicts_keeps_notification_mark(db_session):
    from openpyxl import load_workbook

    content = CONFLICT_XLSX.read_bytes()
    save_config(db_session, CONFLICT_URL)
    with _fake_download(content):
        run_sync(db_session)

    config = get_config(db_session)
    fingerprint = config.pending_conflict_fingerprint
    mark_notified(db_session, fingerprint)
    notified_at = get_config(db_session).notified_at

    # Nueva version del archivo (hoja extra) con el mismo conjunto de
    # documentos en conflicto: la huella no cambia y no se debe re-notificar.
    workbook = load_workbook(BytesIO(content))
    workbook.create_sheet("EXTRA")
    buffer = BytesIO()
    workbook.save(buffer)
    updated_content = buffer.getvalue()

    with _fake_download(updated_content):
        run_sync(db_session)

    config = get_config(db_session)
    assert config.last_status == "conflict_pending"
    assert config.pending_hash == hashlib.sha256(updated_content).hexdigest()
    assert config.pending_conflict_fingerprint == fingerprint
    assert config.notified_at == notified_at
    assert config_to_status(config)["notification_pending"] is False


def test_pending_conflicts_endpoint_and_notification_mark(client):
    _run_conflict_sync(client)

    status = client.get("/api/sheets/sync").json()
    assert status["conflict_pending"] is True
    assert status["pending_conflict_count"] >= 1
    assert status["notification_pending"] is True

    pending = client.get("/api/sheets/sync/pending-conflicts").json()
    assert pending["status"] == "conflict_pending"
    assert pending["conflict_pending"] is True
    assert pending["validation_id"] == status["pending_validation_id"]
    assert pending["fingerprint"] == status["pending_conflict_fingerprint"]
    assert pending["preview"]["coherence_conflicts"] == pending["conflicts"]
    assert pending["conflicts"]

    marked = client.post(
        "/api/sheets/sync/notified",
        json={"fingerprint": pending["fingerprint"]},
    ).json()
    assert marked["status"] == "notified"
    assert marked["config"]["notification_pending"] is False

    stale = client.post(
        "/api/sheets/sync/notified",
        json={"fingerprint": "otra-huella"},
    ).json()
    assert stale["status"] == "stale"


def test_resolve_pending_imports_lot_and_clears_state(client):
    content = _run_conflict_sync(client)
    pending = client.get("/api/sheets/sync/pending-conflicts").json()

    response = client.post(
        "/api/sheets/sync/resolve",
        json={
            "conflict_resolutions": _resolutions(pending["conflicts"]),
            "accept_missing_complementaria": True,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "imported"
    assert data["config"]["conflict_pending"] is False
    assert data["config"]["last_hash"] == hashlib.sha256(content).hexdigest()

    status = client.get("/api/sheets/sync").json()
    assert status["last_status"] == "imported"
    assert status["conflict_pending"] is False
    assert status["pending_conflict_count"] == 0
    assert status["pending_validation_id"] is None
    assert status["notification_pending"] is False

    assert client.get("/api/sheets/sync/pending-conflicts").json()["status"] == "none"
    history = client.get("/api/imports/history").json()["items"]
    assert len(history) == 1

    # La base quedo limpia: nada de contenido ni huellas pendientes.
    with client.session_factory() as session:
        config = get_config(session)
        assert config.pending_validation_id is None
        assert config.pending_content is None
        assert config.pending_conflicts_json is None
        assert config.pending_preview_json is None
        assert config.notified_at is None


def test_resolve_requires_every_conflict_resolution(client):
    _run_conflict_sync(client)

    response = client.post(
        "/api/sheets/sync/resolve",
        json={"conflict_resolutions": [], "accept_missing_complementaria": True},
    )
    assert response.status_code == 400
    status = client.get("/api/sheets/sync").json()
    assert status["conflict_pending"] is True
    assert status["last_status"] == "conflict_pending"


def test_resolution_recovers_staged_lot_after_restart(client):
    from app.services.imports import _staged_imports

    _run_conflict_sync(client)
    # Simula reinicio de la aplicacion: la memoria de staged se pierde.
    _staged_imports.clear()

    pending = client.get("/api/sheets/sync/pending-conflicts").json()
    assert pending["staged_available"] is True
    assert pending["preview"]["coherence_conflicts"]

    response = client.post(
        "/api/sheets/sync/resolve",
        json={
            "conflict_resolutions": _resolutions(pending["conflicts"]),
            "accept_missing_complementaria": True,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "imported"
    assert client.get("/api/sheets/sync").json()["conflict_pending"] is False


def test_service_pending_payload_without_config(db_session):
    payload = pending_conflicts_payload(db_session)
    assert payload["status"] == "none"
    assert payload["conflict_pending"] is False
    assert payload["conflicts"] == []


def test_pending_conflict_cleared_when_sheet_reverts_to_imported_hash(db_session):
    content = CONFLICT_XLSX.read_bytes()
    previous_content = b"previous-imported-sheet"
    save_config(db_session, CONFLICT_URL)
    config = get_config(db_session)
    config.last_hash = hashlib.sha256(previous_content).hexdigest()
    db_session.commit()

    with _fake_download(content):
        run_sync(db_session)
    assert get_config(db_session).last_status == "conflict_pending"

    with _fake_download(previous_content):
        run_sync(db_session)

    config = get_config(db_session)
    assert config.last_status == "unchanged"
    assert config.pending_validation_id is None
    assert config.pending_conflict_fingerprint is None
    assert config.pending_content is None
    assert config.notified_at is None


def test_manual_preview_reuses_pending_lot_and_keeps_state(client):
    content = _run_conflict_sync(client)
    before = client.get("/api/sheets/sync").json()

    with _fake_download(content):
        response = client.post("/api/sheets/sync/preview", json={"url": CONFLICT_URL})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["validation_id"] == before["pending_validation_id"]
    assert data["preview"]["coherence_conflicts"]
    after = client.get("/api/sheets/sync").json()
    assert after["conflict_pending"] is True
    assert after["pending_validation_id"] == before["pending_validation_id"]

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from app.models import Learner
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
    requirement_resolutions = _requirement_resolutions(
        data["preview"]["requirement_conflicts"]
    )
    confirm = client.post(
        "/api/sheets/sync/confirm",
        json={
            "validation_id": data["validation_id"],
            "conflict_resolutions": resolutions,
            "requirement_conflict_resolutions": requirement_resolutions,
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


def _requirement_resolutions(
    requirements: list[dict], status: str | None = None
) -> list[dict]:
    """Decisiones para los requisitos que no se resuelven por regla automática."""
    return [
        {
            "identification": item["identification"],
            "requirement_type": item["requirement_type"],
            "status": status or item.get("suggested_status") or "Pendiente",
            "source": "bulk",
            "conflict_fingerprint": item["fingerprint"],
        }
        for item in requirements
        if not item.get("auto_resolved")
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
            "requirement_conflict_resolutions": _requirement_resolutions(
                pending["requirement_conflicts"]
            ),
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


def test_resolve_records_manual_sheets_cleanup_acknowledgement(client):
    """El acuse del modal es solo trazabilidad; no dispara escritura remota."""
    _run_conflict_sync(client)
    pending = client.get("/api/sheets/sync/pending-conflicts").json()

    response = client.post(
        "/api/sheets/sync/resolve",
        json={
            "conflict_resolutions": _resolutions(pending["conflicts"]),
            "requirement_conflict_resolutions": _requirement_resolutions(
                pending["requirement_conflicts"]
            ),
            "accept_missing_complementaria": True,
            "sheets_manual_cleanup_acknowledged": True,
        },
    )
    assert response.status_code == 200, response.text

    history = client.get("/api/imports/history").json()["items"]
    assert len(history) == 1
    assert "corrección manual" in history[0]["message"]
    assert "Google Sheets" in history[0]["message"]


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
            "requirement_conflict_resolutions": _requirement_resolutions(
                pending["requirement_conflicts"]
            ),
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


# ---------------------------------------------------------------------------
# Desempate condicional: solo aplica mientras el documento siga en la
# interseccion CERTIFICADOS/PENDIENTES.
# ---------------------------------------------------------------------------
def _with_extra_sheet(content: bytes) -> bytes:
    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(content))
    workbook.create_sheet("EXTRA")
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _content_without_document(content: bytes, sheet: str, document: str) -> bytes:
    import unicodedata
    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(content))
    worksheet = workbook[sheet]
    document_column = None
    for cell in worksheet[1]:
        text = unicodedata.normalize("NFKD", str(cell.value or ""))
        text = text.encode("ascii", "ignore").decode("ascii").lower()
        if "numero de documento" in text:
            document_column = cell.column
            break
    assert document_column is not None

    for row in range(worksheet.max_row, 1, -1):
        value = str(worksheet.cell(row=row, column=document_column).value or "").strip()
        if value == document:
            worksheet.delete_rows(row)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _resolve_all_pending(client, status: str = "CERTIFICADOS") -> dict:
    pending = client.get("/api/sheets/sync/pending-conflicts").json()
    response = client.post(
        "/api/sheets/sync/resolve",
        json={
            "conflict_resolutions": [
                {"identification": item["identification"], "status": status}
                for item in pending["conflicts"]
            ],
            "requirement_conflict_resolutions": _requirement_resolutions(
                pending["requirement_conflicts"]
            ),
            "accept_missing_complementaria": True,
        },
    )
    assert response.status_code == 200, response.text
    return pending


def test_next_scan_reuses_saved_resolution_without_intervencion(client):
    content = _run_conflict_sync(client)
    pending = _resolve_all_pending(client, "CERTIFICADOS")
    document = pending["conflicts"][0]["identification"]

    # Cambia el archivo (hoja extra) pero el cruce sigue siendo el mismo.
    updated = _with_extra_sheet(content)
    with _fake_download(updated):
        response = client.post("/api/sheets/sync/run")

    assert response.status_code == 200
    status = response.json()
    assert status["last_status"] == "imported"
    assert status["conflict_pending"] is False
    assert status["notification_pending"] is False
    assert status["last_hash"] == hashlib.sha256(updated).hexdigest()

    with client.session_factory() as session:
        learner = session.query(Learner).filter_by(identification=document).one()
        assert learner.conflict_resolution == "CERTIFICADOS"
        assert learner.last_conflict_resolution == "CERTIFICADOS"
        assert learner.certification_status == "CERTIFICADOS"


def test_document_leaving_intersection_clears_tiebreak_and_follows_sheet(client):
    content = _run_conflict_sync(client)
    pending = _resolve_all_pending(client, "PENDIENTE")
    document = pending["conflicts"][0]["identification"]

    # La hoja corrige el cruce: el documento queda solo en CERTIFICADOS.
    only_certificados = _content_without_document(content, "PENDIENTES", document)
    with _fake_download(only_certificados):
        response = client.post("/api/sheets/sync/run")

    assert response.status_code == 200
    assert response.json()["last_status"] == "imported"
    with client.session_factory() as session:
        learner = session.query(Learner).filter_by(identification=document).one()
        assert learner.certification_status == "CERTIFICADOS"
        # El desempate condicional ya no aplica...
        assert learner.conflict_resolution is None
        # ...pero la ultima decision queda como historial.
        assert learner.last_conflict_resolution == "PENDIENTE"

    # Si el cruce reaparece, se reaplica la ultima decision sin interrumpir.
    with _fake_download(content):
        response = client.post("/api/sheets/sync/run")

    assert response.status_code == 200
    status = response.json()
    assert status["last_status"] == "imported"
    assert status["conflict_pending"] is False
    assert status["notification_pending"] is False
    with client.session_factory() as session:
        learner = session.query(Learner).filter_by(identification=document).one()
        assert learner.certification_status == "PENDIENTE"
        assert learner.conflict_resolution == "PENDIENTE"


def test_new_conflict_after_resolved_one_only_requests_the_new_document(client):
    from openpyxl import load_workbook

    content = _run_conflict_sync(client)
    pending = _resolve_all_pending(client, "CERTIFICADOS")
    resolved_document = pending["conflicts"][0]["identification"]

    # Agrega un segundo documento a ambas hojas: solo ese exige intervencion.
    workbook = load_workbook(BytesIO(content))
    for sheet_name in ("CERTIFICADOS", "PENDIENTES"):
        worksheet = workbook[sheet_name]
        document_column = None
        for cell in worksheet[1]:
            if "documento" in str(cell.value or "").lower():
                document_column = cell.column
                break
        assert document_column is not None
        source_row = None
        for row in range(2, worksheet.max_row + 1):
            value = str(
                worksheet.cell(row=row, column=document_column).value or ""
            ).strip()
            if value == resolved_document:
                source_row = row
                break
        assert source_row is not None
        target_row = worksheet.max_row + 1
        for column in range(1, worksheet.max_column + 1):
            worksheet.cell(
                row=target_row,
                column=column,
                value=worksheet.cell(row=source_row, column=column).value,
            )
        worksheet.cell(row=target_row, column=document_column, value="9999999999")
    buffer = BytesIO()
    workbook.save(buffer)
    updated = buffer.getvalue()

    with _fake_download(updated):
        response = client.post("/api/sheets/sync/run")

    assert response.status_code == 200
    assert response.json()["last_status"] == "conflict_pending"
    pending_after = client.get("/api/sheets/sync/pending-conflicts").json()
    documents = {item["identification"] for item in pending_after["conflicts"]}
    assert "9999999999" in documents
    assert resolved_document not in documents
    assert pending_after["pending_conflict_count"] == len(documents)


def test_pending_lot_imports_when_resolution_is_already_saved(client):
    """Aunque el hash no cambie, un cruce ya decidido no debe quedar bloqueado."""
    from app.models import RequirementStatusHistory

    content = _run_conflict_sync(client)
    pending = client.get("/api/sheets/sync/pending-conflicts").json()
    document = pending["conflicts"][0]["identification"]

    with client.session_factory() as session:
        learner = session.query(Learner).filter_by(identification=document).one_or_none()
        if learner is None:
            learner = Learner(identification=document, name="Aprendiz en conflicto")
            session.add(learner)
            session.flush()
        learner.conflict_resolution = "CERTIFICADOS"
        learner.last_conflict_resolution = "CERTIFICADOS"
        # Las decisiones de requisitos guardadas también se reaplican sin
        # intervención: el lote no debe quedar bloqueado por ellas.
        for item in pending["requirement_conflicts"]:
            requirement_learner = session.query(Learner).filter_by(
                identification=item["identification"]
            ).one_or_none()
            if requirement_learner is None:
                requirement_learner = Learner(
                    identification=item["identification"],
                    name=item.get("name") or "Aprendiz en conflicto",
                )
                session.add(requirement_learner)
                session.flush()
            session.add(
                RequirementStatusHistory(
                    learner_id=requirement_learner.id,
                    requirement_type=item["requirement_type"],
                    status=item.get("suggested_status") or "Pendiente",
                    source="conflict:requirement",
                    decision_source="user",
                    conflict_fingerprint=item["fingerprint"],
                )
            )
        session.commit()

    with _fake_download(content):
        response = client.post("/api/sheets/sync/run")

    assert response.status_code == 200
    status = response.json()
    assert status["last_status"] == "imported"
    assert status["conflict_pending"] is False
    assert status["notification_pending"] is False
    assert status["last_hash"] == hashlib.sha256(content).hexdigest()


def test_resolved_lot_is_unchanged_on_next_scan(client):
    """Tras resolver e importar, el mismo contenido no reabre el conflicto."""
    content = _run_conflict_sync(client)
    pending = _resolve_all_pending(client, "CERTIFICADOS")
    resolved_document = pending["conflicts"][0]["identification"]

    with client.session_factory() as session:
        learner = session.query(Learner).filter_by(identification=resolved_document).one()
        assert learner.conflict_resolution == "CERTIFICADOS"

    # Reimportar el mismo lote no vuelve a abrir la resolucion.
    with _fake_download(content):
        response = client.post("/api/sheets/sync/run")
    assert response.json()["last_status"] == "unchanged"
    assert response.json()["conflict_pending"] is False

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

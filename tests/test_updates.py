"""Pruebas del servicio de actualizaciones y de sus endpoints."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from app.services import updates


def _release(version: str = "0.4.0", notes: str = "- feat: novedades\n- fix: corrección"):
    return {
        "version": version,
        "update_available": updates.is_newer(version),
        "notes": notes,
        "notes_items": updates.notes_items(notes),
        "setup_url": (
            "https://github.com/Louis-Du/sena-certificacion-app/releases/download/"
            f"v{version}/SENACertificacion-Setup-{version}.exe"
        ),
        "sha256": "a" * 64,
        "published_at": "2026-11-17T12:00:00Z",
        "release_url": (
            "https://github.com/Louis-Du/sena-certificacion-app/releases/tag/"
            f"v{version}"
        ),
        "source": "version.json",
    }


@pytest.fixture(autouse=True)
def reset_update_cache():
    updates.reset_cache()
    yield
    updates.reset_cache()


def test_parse_and_compare_versions():
    assert updates.parse_version("v0.3.0") == (0, 3)
    assert updates.parse_version("1.2.3") == (1, 2, 3)
    assert updates.is_newer("0.4.0", "0.3.0")
    assert updates.is_newer("0.3.1", "0.3.0")
    assert not updates.is_newer("0.3.0", "0.3.0")
    assert not updates.is_newer("0.2.9", "0.3.0")
    assert not updates.is_newer("", "0.3.0")


def test_notes_items_cleans_markdown_and_release_metadata():
    notes = """## SENA Certificación 0.4.0

### Cambios

- feat: agregar **autoupdate**
- fix: [descarga](https://example.com) de informes

**Instalador:** [setup.exe](https://example.com/setup.exe)
**SHA-256:** `abc`
"""

    items = updates.notes_items(notes)

    assert "feat: agregar autoupdate" in items
    assert "fix: descarga de informes" in items
    assert not any(item.lower().startswith("instalador:") for item in items)
    assert not any(item.lower().startswith("sha-256:") for item in items)


def test_check_for_update_detects_new_release(monkeypatch):
    monkeypatch.setattr(updates, "_fetch_latest", lambda: _release("0.4.0"))

    result = updates.check_for_update(force=True)

    assert result["current_version"] == "0.3.0"
    assert result["latest_version"] == "0.4.0"
    assert result["update_available"] is True
    assert result["notes_items"][0] == "feat: novedades"
    assert result["can_self_update"] is False
    assert result["error"] is None


def test_check_for_update_ignores_same_version(monkeypatch):
    monkeypatch.setattr(updates, "_fetch_latest", lambda: _release("0.3.0"))

    result = updates.check_for_update(force=True)

    assert result["update_available"] is False
    assert result["latest_version"] == "0.3.0"


def test_check_for_update_reports_network_error(monkeypatch):
    def fail():
        raise updates.UpdateError("sin conexión")

    monkeypatch.setattr(updates, "_fetch_latest", fail)

    result = updates.check_for_update(force=True)

    assert result["update_available"] is False
    assert "sin conexión" in result["error"]


def test_dismiss_version_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("SENA_DATA_DIR", str(tmp_path))

    updates.dismiss_version("v0.4.0")

    assert updates.dismissed_version() == "0.4.0"
    assert (tmp_path / "updates" / "state.json").is_file()


def test_cached_result_refreshes_dismissed_version(monkeypatch, tmp_path):
    monkeypatch.setenv("SENA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(updates, "_fetch_latest", lambda: _release("0.4.0"))

    first = updates.check_for_update(force=True)
    assert first["dismissed_version"] == ""

    updates.dismiss_version("0.4.0")
    cached = updates.check_for_update(force=False)

    assert cached["cached"] is True
    assert cached["dismissed_version"] == "0.4.0"


def test_apply_update_in_dev_mode_does_not_launch_installer(monkeypatch):
    monkeypatch.setattr(updates, "is_frozen", lambda: False)
    monkeypatch.setattr(updates, "_fetch_latest", lambda: _release("0.4.0"))

    result = updates.apply_update()

    assert result["launched"] is False
    assert result["reason"] == "manual"
    assert result["setup_url"].endswith(".exe")


def test_download_installer_verifies_sha(monkeypatch, tmp_path):
    payload = b"instalador de prueba"
    digest = hashlib.sha256(payload).hexdigest()
    info = _release("0.4.0")
    info["sha256"] = digest
    monkeypatch.setenv("SENA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(updates, "_validate_setup_url", lambda url: url)
    monkeypatch.setattr(
        updates.urllib.request,
        "urlopen",
        lambda *args, **kwargs: io.BytesIO(payload),
    )

    installer = updates.download_installer(info)

    assert installer.is_file()
    assert installer.read_bytes() == payload
    assert installer.parent == tmp_path / "updates"


def test_download_installer_rejects_wrong_sha(monkeypatch, tmp_path):
    payload = b"instalador alterado"
    info = _release("0.4.0")
    info["sha256"] = "b" * 64
    monkeypatch.setenv("SENA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(updates, "_validate_setup_url", lambda url: url)
    monkeypatch.setattr(
        updates.urllib.request,
        "urlopen",
        lambda *args, **kwargs: io.BytesIO(payload),
    )

    with pytest.raises(updates.UpdateError):
        updates.download_installer(info)

    assert not (tmp_path / "updates" / "SENACertificacion-Setup-0.4.0.exe").exists()


def test_updates_endpoints(client, monkeypatch, tmp_path):
    monkeypatch.setenv("SENA_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(updates, "_fetch_latest", lambda: _release("0.4.0"))
    updates.reset_cache()

    response = client.get("/api/updates/check?force=1")

    assert response.status_code == 200
    data = response.json()
    assert data["update_available"] is True
    assert data["latest_version"] == "0.4.0"

    dismissed = client.post("/api/updates/dismiss", json={"version": "0.4.0"})
    assert dismissed.status_code == 200
    assert dismissed.json()["version"] == "0.4.0"


def test_apply_endpoint_rejects_requests_without_custom_header(client):
    response = client.post("/api/updates/apply")

    assert response.status_code == 403


def test_setup_url_must_point_to_github():
    with pytest.raises(updates.UpdateError):
        updates._validate_setup_url("https://example.com/instalador.exe")

    assert updates._validate_setup_url(
        "https://github.com/Louis-Du/sena-certificacion-app/releases/download/"
        "v0.4.0/SENACertificacion-Setup-0.4.0.exe"
    ).startswith("https://github.com/")


def test_state_file_is_created_next_to_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("SENA_DATA_DIR", str(tmp_path))

    updates.dismiss_version("0.4.0")

    state = Path(tmp_path) / "updates" / "state.json"
    assert state.read_text(encoding="utf-8")

"""Contrato estático de la UI de actualizaciones y del diálogo de guardado."""

from pathlib import Path

ROOT = Path(__file__).parents[1]
STATIC = ROOT / "app" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
UPDATES_JS = (STATIC / "updates.js").read_text(encoding="utf-8")
UI_JS = (STATIC / "ui-enhancements.js").read_text(encoding="utf-8")
STYLES = (STATIC / "styles.css").read_text(encoding="utf-8")


def test_update_modal_markup_and_script_are_present():
    assert 'id="update-modal"' in INDEX
    assert 'id="update-notes"' in INDEX
    assert 'id="update-apply"' in INDEX
    assert 'id="update-modal-later"' in INDEX
    assert 'id="update-release-link"' in INDEX
    assert "/static/updates.js" in INDEX
    assert 'id="app-version"' in INDEX
    assert '<button class="sidebar-version"' in INDEX


def test_updates_js_checks_releases_and_exposes_bridge():
    assert '"/api/updates/check"' in UPDATES_JS
    assert '"/api/updates/check?force=1"' in UPDATES_JS
    assert '"/api/updates/dismiss"' in UPDATES_JS
    assert '"/api/updates/apply"' in UPDATES_JS
    assert "window.SenaUpdates" in UPDATES_JS
    assert "notify_update" in UPDATES_JS
    assert "open_external" in UPDATES_JS
    assert "pywebviewready" in UPDATES_JS
    assert "POLL_INTERVAL_MS = 6 * 60 * 60 * 1000" in UPDATES_JS
    assert "update_available" in UPDATES_JS


def test_report_download_prefers_native_save_dialog():
    bridge_position = UI_JS.index("bridge.save_file")
    picker_position = UI_JS.index("window.showSaveFilePicker")

    assert bridge_position < picker_position
    assert "function blobToBase64" in UI_JS
    assert "result.cancelled" in UI_JS
    assert "No se pudo abrir el explorador" in UI_JS


def test_update_styles_cover_modal_and_version_badge():
    assert ".update-dialog" in STYLES
    assert ".update-version-row" in STYLES
    assert ".update-notes" in STYLES
    assert ".sidebar-version.has-update" in STYLES
    assert "@keyframes updatePulse" in STYLES

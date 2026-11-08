"""Regresiones de la UI del banner de conflictos Google Sheets (#85).

Estas pruebas no levantan un navegador: verifican el contrato estatico del
markup y del JavaScript que sostiene el flujo de resolucion.
"""

from pathlib import Path

ROOT = Path(__file__).parents[1]
INDEX = (ROOT / "app" / "static" / "index.html").read_text(encoding="utf-8")
APP_JS = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
UI_JS = (ROOT / "app" / "static" / "ui-enhancements.js").read_text(encoding="utf-8")
STYLES = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")


def test_banner_markup_has_resolution_and_dismiss_actions():
    assert 'id="global-conflict-banner"' in INDEX
    assert 'id="global-conflict-resolve"' in INDEX
    assert 'id="global-conflict-later"' in INDEX
    assert "Resolver ahora" in INDEX
    assert "Más tarde" in INDEX


def test_banner_is_fixed_on_top_without_blocking_layout():
    assert ".global-conflict-banner" in STYLES
    assert "position: fixed" in STYLES
    assert "body.has-conflict-banner .shell" in STYLES
    assert "--conflict-banner-height" in STYLES


def test_frontend_polls_and_exposes_bridge_entrypoint():
    assert "CONFLICT_POLL_INTERVAL_MS = 12000" in APP_JS
    assert "window.SenaConflictBanner" in APP_JS
    assert "openResolution: openPendingConflictResolution" in APP_JS
    assert "pywebviewready" in APP_JS


def test_resolution_does_not_depend_on_history_replace_state():
    """Browser Guard lanza 'Breaking Browser Locker Behavior detected'.

    El flujo de resolucion debe seguir abriendo el modal aunque un bloqueador
    intercepte history.replaceState. Por eso solo existe una llamada directa,
    encapsulada en el helper seguro, y la vista se cambia sin actualizar hash.
    """

    assert APP_JS.count("history.replaceState(null") == 1
    assert "function replaceLocationHash(hash)" in APP_JS
    assert 'showView("carga", false);' in APP_JS
    assert "replaceHashSafely" in UI_JS


def test_conflict_panel_only_contains_the_state_decision():
    start = INDEX.index('id="coherence-conflicts"')
    end = INDEX.index("</section>", start)
    panel = INDEX[start:end]

    assert "coherence-conflict-list" in panel
    assert "Certificado" not in panel  # las opciones las construye app.js
    assert "solo lee Google Sheets" not in panel
    assert "sheets-manual-cleanup" not in panel
    assert "corrección manual" not in panel


def test_second_confirmation_modal_has_required_warning_and_actions():
    assert 'id="conflict-confirm-modal"' in INDEX
    assert "Antes de confirmar" in INDEX
    assert (
        "Resolvió conflictos de coherencia en este lote. Esa decisión se guardará "
        "solo en SENA Certificación App."
    ) in INDEX
    assert (
        "Esta aplicación solo lee Google Sheets y los archivos de origen: no puede "
        "modificar, borrar ni actualizar filas en la hoja."
    ) in INDEX
    assert "el cruce permanecerá allí" in INDEX
    assert "corríjala o elimine el registro duplicado de forma manual" in INDEX
    assert "la app tomará ese estado y descartará el desempate anterior" in INDEX
    assert "Ya corregí o eliminé el registro duplicado en Google Sheets" in INDEX
    assert "Solo documental en la app; no modifica Google Sheets." in INDEX
    assert ">Volver</button>" in INDEX
    assert ">Confirmar de todos modos</button>" in INDEX


def test_import_post_waits_for_second_confirmation_when_conflicts_exist():
    assert "function openConflictConfirmModal()" in APP_JS
    assert "resolutions.length > 0 && !conflictConfirmBypass" in APP_JS
    assert "openConflictConfirmModal();" in APP_JS
    assert "conflictConfirmBypass = true;" in APP_JS
    assert "conflictConfirmBypass = false;" in APP_JS
    assert "sheets_manual_cleanup_acknowledged" in APP_JS
    assert "payload.sheets_manual_cleanup_acknowledged" in APP_JS
    assert 'const endpoint = isSheetsResolve' in APP_JS
    assert '? "/api/sheets/sync/resolve"' in APP_JS


def test_warning_modal_escape_does_not_cancel_import_review():
    assert 'getElementById("conflict-confirm-modal")' in UI_JS
    assert 'warningModal?.classList.contains("is-open")' in UI_JS


def test_banner_text_mentions_resolution_and_google_sheets():
    assert "de resolución (Google Sheets)" in APP_JS
    assert "conflictCountLabel(count)" in APP_JS

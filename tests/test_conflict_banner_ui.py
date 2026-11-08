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

"""Contrato de la actualizacion automatica de la UI tras un escaneo de Sheets.

El worker de fondo importa cada ``interval_seconds`` (60 s por defecto), pero eso
solo cambia SQLite. Estas pruebas fijan el contrato del frontend: cuando
``/api/sheets/sync`` reporta una importacion nueva (``last_import_at`` distinto),
la vista abierta se vuelve a consultar sin recargar la aplicacion.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")


def test_sheets_poll_detects_new_import_by_timestamp():
    assert "let sheetsLastImportAt = null;" in APP_JS
    assert "function rememberSheetsImport(data)" in APP_JS
    assert "const importAt = data?.last_import_at || null;" in APP_JS
    assert "if (sheetsLastImportAt === importAt) return false;" in APP_JS
    # Se engancha al polling existente, sin crear otro temporizador.
    assert "const importChanged = rememberSheetsImport(data);" in APP_JS
    assert "if (importChanged) {" in APP_JS
    assert "refreshViewsAfterSheetsImport().catch(() => {});" in APP_JS


def test_sheets_auto_refresh_covers_list_detail_and_indicators():
    assert "async function refreshViewsAfterSheetsImport()" in APP_JS
    # Listado de aprendices y, si la ficha esta abierta, el detalle visible.
    assert "await loadLearners();" in APP_JS
    assert "if (!learnerDetail.hidden && window.currentLearnerId) {" in APP_JS
    assert "await loadLearnerDetail(window.currentLearnerId);" in APP_JS
    # Indicadores y sus metricas complementarias.
    assert "await loadIndicadores();" in APP_JS
    assert "window.SenaUI?.loadIndicadoresExtras?.();" in APP_JS
    # Actas e historial tambien se mantienen al dia.
    assert "await loadActs();" in APP_JS
    assert "if (!actDetail.hidden && currentActId) {" in APP_JS
    assert "await loadActDetail(currentActId);" in APP_JS
    assert "await loadHistory();" in APP_JS


def test_sheets_auto_refresh_is_single_flight_and_reports_to_user():
    assert "let sheetsAutoRefreshInFlight = false;" in APP_JS
    assert (
        "if (sheetsAutoRefreshInFlight) return;\n"
        "  sheetsAutoRefreshInFlight = true;"
    ) in APP_JS
    assert (
        "} finally {\n"
        "    sheetsAutoRefreshInFlight = false;\n"
        "  }"
    ) in APP_JS
    assert "Datos actualizados automáticamente desde Google Sheets." in APP_JS


def test_manual_confirmation_does_not_duplicate_auto_refresh():
    # La confirmacion manual ya recarga las vistas; se registra la marca antes
    # de consultar el estado para que el polling no repita el refresco.
    assert "if (response?.config?.last_import_at) {" in APP_JS
    assert "sheetsLastImportAt = response.config.last_import_at;" in APP_JS


def test_deleting_sheets_config_resets_import_baseline():
    assert (
        "if (!data.configured) {\n"
        "      sheetsLastImportAt = null;"
    ) in APP_JS

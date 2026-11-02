"""E2E de Indicadores: toggle Heatmap | Gráfico y claridad de datos.

Cubre:
* Ambas vistas de actividad usan la misma fuente (la suma semanal coincide con
  los eventos diarios del endpoint del heatmap).
* Cambiar el año refresca la vista activa y muestra el vacío controlado.
* Causas normalizadas + auditoría sin "diferencia de −N".
* Actas del consolidado: columnas de fecha/tipo ocultas si no hay dato y enlace
  al detalle cuando el acta está registrada en el módulo Actas.
"""

from pathlib import Path

CORRECTOS = Path(__file__).resolve().parents[2] / "archivos_prueba" / "correctos"


def _importar_actas(page, app_url):
    page.goto(app_url)
    page.click('.category-option[data-type="actas_completo"]')
    page.set_input_files("#file-input", str(CORRECTOS / "ACTAS_2026_correcto.xlsx"))
    page.click("#validate-button")
    page.wait_for_selector("#confirmation-panel:not([hidden])")
    page.click("#modal-confirm-button")
    page.wait_for_selector("#import-success-banner:not([hidden])")


def _abrir_indicadores(page):
    page.click('a[data-view="indicadores"]')
    page.wait_for_selector("#indicadores-metrics")
    # Las celdas se crean después de cargar /api/activity/heatmap.
    page.wait_for_selector("#indicadores-heatmap .heatmap-cell", state="attached")


def test_activity_toggle_shares_source_and_switches_year(page, app_url):
    _importar_actas(page, app_url)
    _abrir_indicadores(page)

    assert page.locator("#activity-heatmap-panel").is_visible()
    assert page.locator("#activity-chart-panel").is_hidden()
    assert page.locator("#indicadores-heatmap .heatmap-cell").count() >= 365

    page.click("#activity-tab-chart")
    page.wait_for_selector("#activity-chart-panel:not([hidden])")
    assert page.locator("#activity-heatmap-panel").is_hidden()
    page.wait_for_function(
        "() => {"
        " const canvas = document.querySelector('#indicadores-activity-chart');"
        " const chart = window.Chart && window.Chart.getChart(canvas);"
        " return !!(chart && chart.data.datasets[0].data.some((value) => value > 0));"
        "}"
    )

    # Misma fuente: la serie semanal suma exactamente los eventos diarios.
    total_diario = page.request.get(f"{app_url}/api/activity/heatmap?year=2026").json()[
        "total_events"
    ]
    total_grafico = page.evaluate(
        "() => window.Chart"
        ".getChart(document.querySelector('#indicadores-activity-chart'))"
        ".data.datasets[0].data.reduce((sum, value) => sum + value, 0)"
    )
    assert total_grafico == total_diario

    # Cambiar el año refresca la vista activa con los datos de ese año.
    page.select_option("#heatmap-year", "2025")
    total_2025 = page.request.get(f"{app_url}/api/activity/heatmap?year=2025").json()[
        "total_events"
    ]
    page.wait_for_function(
        "(total) => {"
        " const chart = window.Chart.getChart(document.querySelector('#indicadores-activity-chart'));"
        " return chart.data.datasets[0].data.reduce((sum, value) => sum + value, 0) === total;"
        "}",
        arg=total_2025,
    )

    # Año sin datos (se inyecta 2024): vacío controlado en gráfico y heatmap.
    page.evaluate(
        "() => {"
        " const sel = document.querySelector('#heatmap-year');"
        " const opt = document.createElement('option');"
        " opt.value = '2024'; opt.textContent = '2024'; sel.appendChild(opt);"
        " sel.value = '2024';"
        " sel.dispatchEvent(new Event('change', { bubbles: true }));"
        "}"
    )
    page.wait_for_selector("#activity-chart-empty:not([hidden])")
    assert "2024" in page.locator("#activity-chart-empty").text_content()
    page.click("#activity-tab-heatmap")
    page.wait_for_selector("#activity-heatmap-panel:not([hidden])")
    page.wait_for_selector("#heatmap-empty:not([hidden])")

    # La selección se conserva al volver a entrar a Indicadores.
    page.select_option("#heatmap-year", "2026")
    page.click("#activity-tab-chart")
    page.wait_for_selector("#activity-chart-panel:not([hidden])")
    page.click('a[data-view="carga"]')
    page.click('a[data-view="indicadores"]')
    page.wait_for_selector("#activity-chart-panel:not([hidden])")
    assert page.locator("#activity-tab-chart").get_attribute("aria-selected") == "true"


def test_causas_normalizadas_y_auditoria_clara(page, app_url):
    _importar_actas(page, app_url)
    _abrir_indicadores(page)

    page.click("#tab-causas")
    page.wait_for_selector("#panel-causas:not([hidden])")
    page.wait_for_function(
        "() => document.querySelector('#indicadores-causas-table')"
        ".textContent.includes('No anexa TyT')"
    )
    tabla = page.locator("#indicadores-causas-table").text_content()
    assert "No anexa TyT" in tabla
    # La tabla completa vive dentro de <details>; el gráfico solo muestra el top.
    assert page.locator("#panel-causas details").count() == 1
    assert page.locator("#panel-causas details table").count() == 1

    auditoria = page.locator("#indicadores-causas-note").text_content()
    assert "Auditoría de consistencia" in auditoria
    assert "diferencia de" not in auditoria.lower()
    assert "incidencias" in auditoria


def test_actas_sin_columnas_vacias_y_enlace_al_detalle(page, app_url):
    _importar_actas(page, app_url)
    _abrir_indicadores(page)

    page.click("#tab-actas")
    page.wait_for_selector("#panel-actas:not([hidden])")
    page.wait_for_selector("#indicadores-actas-table tr")

    # Sin actas registradas en el módulo: no se muestran columnas vacías.
    assert page.locator("#indicadores-actas-date-th").is_hidden()
    assert page.locator("#indicadores-actas-type-th").is_hidden()
    nota = page.locator("#indicadores-actas-note").text_content()
    assert "no vienen en la hoja CERTIFICADOS" in nota
    assert "No disponible" not in page.locator("#indicadores-actas-table").text_content()

    # Registrar en el módulo Actas un acta con el número del consolidado.
    numero = page.request.get(f"{app_url}/api/indicadores").json()["ultimas_actas"][0][
        "number"
    ]
    creada = page.request.post(
        f"{app_url}/api/acts",
        data={
            "number": numero,
            "act_date": "2026-08-12",
            "act_type": "Certificación",
            "original_file": "acta_demo.pdf",
        },
    )
    assert creada.status == 201

    page.reload()
    _abrir_indicadores(page)
    page.click("#tab-actas")
    page.wait_for_selector("#panel-actas:not([hidden])")

    assert page.locator("#indicadores-actas-date-th").is_visible()
    assert page.locator("#indicadores-actas-type-th").is_visible()
    tabla = page.locator("#indicadores-actas-table").text_content()
    assert "2026-08-12" in tabla
    assert "Certificación" in tabla
    assert "Ver" in tabla

    page.locator("#indicadores-actas-table button[data-act-id]").first.click()
    page.wait_for_selector("#actas-view:not([hidden])")
    page.wait_for_selector("#act-detail:not([hidden])")
    assert numero in page.locator("#act-detail").text_content()

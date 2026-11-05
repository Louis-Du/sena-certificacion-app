"""E2E de Indicadores: certificados por mes y claridad de datos.

Cubre:
* El único gráfico temporal usa el mes de certificación del consolidado.
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
    page.wait_for_selector("#indicadores-certificados-mes-chart", state="attached")


def test_certificados_por_mes_usa_la_fuente_del_consolidado(page, app_url):
    _importar_actas(page, app_url)
    _abrir_indicadores(page)

    assert page.locator('a[href="/api/informes/export"]').is_visible()
    assert page.locator("#activity-tab-heatmap").count() == 0
    assert page.locator("#activity-tab-chart").count() == 0
    assert page.locator("#activity-tab-certificados").count() == 0
    page.wait_for_function(
        "() => {"
        " const canvas = document.querySelector('#indicadores-certificados-mes-chart');"
        " const chart = window.Chart && window.Chart.getChart(canvas);"
        " return !!(chart && chart.data.datasets[0].data.some((value) => value > 0));"
        "}"
    )

    total_grafico = page.evaluate(
        "() => window.Chart.getChart(document.querySelector('#indicadores-certificados-mes-chart'))"
        ".data.datasets[0].data.reduce((sum, value) => sum + value, 0)"
    )
    total_consolidado = page.request.get(
        f"{app_url}/api/indicadores/certificados-por-mes"
    ).json()["total"]
    assert total_grafico == total_consolidado
    assert "No es padrón local ni fecha de importación" in page.locator(
        "#certificados-mes-summary"
    ).text_content()


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

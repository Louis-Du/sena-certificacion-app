"""E2E de Indicadores -> Aprendices y limpieza de copy de prototipo.

Cubre:
* No queda copy de prototipo visible en las vistas principales.
* Las advertencias de Indicadores solo aparecen si el API devuelve alguna.
* Drill-down de pendientes, causa y acta con filtros reales del listado.
* "Quitar filtro" restaura el listado completo.
* Los certificados del consolidado no se enlazan al padron local.
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
    page.wait_for_selector("#indicadores-kpis .panel")


def _texto_visible(page):
    return page.locator("body").inner_text().lower()


def test_no_queda_copy_de_prototipo_en_la_ui(page, app_url):
    page.goto(app_url)
    for vista in ["carga", "indicadores", "aprendices", "actas"]:
        page.click(f'a[data-view="{vista}"]')
        page.wait_for_timeout(250)
        texto = _texto_visible(page)
        for prohibido in ("prototipo", "reglas por confirmar", "ficticios"):
            assert prohibido not in texto, f"Copy de prototipo visible en {vista}: {prohibido}"


def test_advertencias_solo_si_el_api_las_devuelve(page, app_url):
    _importar_actas(page, app_url)
    data = page.request.get(f"{app_url}/api/indicadores").json()
    _abrir_indicadores(page)

    paneles = page.locator("#indicadores-avisos .avisos-panel")
    if data["advertencias"]:
        assert paneles.count() == 1
        assert "Advertencias de cálculo" in paneles.inner_text()
        # El copy genérico de "resultados calculados..." ya no se muestra.
        assert "Resultados calculados con los documentos cargados" not in paneles.inner_text()
    else:
        assert paneles.count() == 0
        assert page.locator("#indicadores-avisos").inner_text().strip() == ""


def test_drilldown_pendientes_y_quitar_filtro(page, app_url):
    _importar_actas(page, app_url)
    _abrir_indicadores(page)

    page.click("#indicadores-kpis [data-drilldown-pendientes]")
    page.wait_for_selector("#aprendices-view:not([hidden])")
    page.wait_for_selector("#learners-drilldown-banner:not([hidden])")
    assert "Pendientes únicos" in page.locator("#learners-drilldown-text").inner_text()
    assert page.locator("#learner-status").input_value().upper() == "PENDIENTE"

    esperado = page.request.get(f"{app_url}/api/learners?status=PENDIENTE").json()["total"]
    resumen = page.locator("#learners-summary").inner_text()
    assert f"{esperado} aprendices" in resumen

    estados = page.locator("#learners-list .status-chip").all_inner_texts()
    assert estados and all("PENDIENTE" in estado.upper() for estado in estados)

    page.click("#learners-drilldown-clear")
    page.wait_for_selector("#learners-drilldown-banner", state="hidden")
    assert page.locator("#learner-status").input_value() == ""
    total = page.request.get(f"{app_url}/api/learners").json()["total"]
    assert f"{total} aprendices" in page.locator("#learners-summary").inner_text()


def test_drilldown_causa_normalizada(page, app_url):
    _importar_actas(page, app_url)
    _abrir_indicadores(page)

    page.click("#tab-causas")
    page.wait_for_selector("#panel-causas:not([hidden])")
    page.click("#panel-causas details summary")
    boton = page.locator(
        "#indicadores-causas-table button[data-causa-index]", has_text="No anexa TyT"
    ).first
    boton.click()

    page.wait_for_selector("#aprendices-view:not([hidden])")
    page.wait_for_selector("#learners-drilldown-banner:not([hidden])")
    assert "No anexa TyT" in page.locator("#learners-drilldown-text").inner_text()

    # La etiqueta normalizada se traduce a las variantes crudas que guarda
    # non_certification_reason; en el fixture la causa es "No anexa T&T".
    esperado = page.request.get(
        f"{app_url}/api/learners", params={"reason": "no anexa t&t"}
    ).json()["total"]
    assert esperado == 1
    assert f"{esperado} aprendiz" in page.locator("#learners-summary").inner_text()


def test_drilldown_acta_y_certificados_sin_enlace(page, app_url):
    _importar_actas(page, app_url)
    _abrir_indicadores(page)

    # El KPI de certificados del consolidado no es perforable.
    assert page.locator("#indicadores-kpis [data-drilldown-pendientes]").count() == 1
    assert page.locator("#indicadores-kpis button.kpi-drilldown").count() == 1

    page.click("#tab-actas")
    page.wait_for_selector("#panel-actas:not([hidden])")
    boton_acta = page.locator("#indicadores-actas-table button[data-acta-number]").first
    numero = boton_acta.inner_text().strip()
    boton_acta.click()

    page.wait_for_selector("#aprendices-view:not([hidden])")
    page.wait_for_selector("#learners-drilldown-banner:not([hidden])")
    assert f"acta {numero}" in page.locator("#learners-drilldown-text").inner_text()

    esperado = page.request.get(
        f"{app_url}/api/learners", params={"act_number": numero}
    ).json()["total"]
    assert esperado >= 1
    etiqueta = "aprendiz" if esperado == 1 else "aprendices"
    assert f"{esperado} {etiqueta}" in page.locator("#learners-summary").inner_text()

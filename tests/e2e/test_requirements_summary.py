import json


def _post_requirement(page, app_url, learner_id, requirement_type, status):
    response = page.request.post(
        f"{app_url}/api/learners/{learner_id}/requirements",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"requirement_type": requirement_type, "status": status}),
    )
    assert response.ok, response.text()


def _open_learners(page, app_url):
    page.goto(app_url)
    page.click('a[data-view="aprendices"]')
    page.wait_for_selector("#learners-list .detail-button")


def test_list_and_detail_prioritize_pending_requirements(page, app_url, seed_df14a):
    seed_df14a(1)
    learner = page.request.get(f"{app_url}/api/learners").json()["items"][0]
    learner_id = learner["id"]
    for requirement_type, status in (
        ("saber_tyt", "Pendiente"),
        ("ape", "Pendiente"),
        ("documento_identidad", "Pendiente"),
        ("carnet", "Pendiente"),
        ("biblioteca", "Cumplido"),
    ):
        _post_requirement(page, app_url, learner_id, requirement_type, status)

    _open_learners(page, app_url)
    pending_cell = page.locator("#learners-list .pending-requirements-cell").first
    pending_text = pending_cell.text_content()
    assert "4" in pending_text
    assert "Saber TyT" in pending_text
    assert "Inscripción APE" in pending_text
    assert "y 2 más" in pending_text
    assert "has-pending" in (pending_cell.get_attribute("class") or "")
    assert pending_cell.locator(".pending-count-badge").text_content() == "4"

    # Error 2: el listado completo se abre con teclado, sin abrir la ficha.
    toggle = pending_cell.locator(".pending-toggle")
    assert toggle.get_attribute("aria-expanded") == "false"
    toggle.focus()
    page.keyboard.press("Enter")
    assert toggle.get_attribute("aria-expanded") == "true"
    panel = pending_cell.locator(".pending-list")
    assert not panel.is_hidden()
    panel_text = panel.text_content()
    for label in (
        "Saber TyT",
        "Inscripción APE",
        "Documento de identidad",
        "Destrucción de carnet",
    ):
        assert label in panel_text
    assert page.locator("#learner-detail").is_hidden()
    page.keyboard.press("Enter")
    assert toggle.get_attribute("aria-expanded") == "false"
    assert panel.is_hidden()

    # Error 3: label estable y nombre accesible completo.
    detail_button = page.locator("#learners-list .detail-button").first
    assert detail_button.text_content().strip() == "Ver detalles"
    assert learner["name"] in (detail_button.get_attribute("aria-label") or "")
    assert not detail_button.evaluate("el => el.scrollWidth > el.clientWidth")
    assert detail_button.bounding_box()["width"] >= 100

    page.click("#learners-list .detail-button")
    page.wait_for_selector("#learner-detail-content:not([hidden])")
    assert page.evaluate("document.activeElement.id") == "learner-detail-title"

    # La tarjeta de resumen bajo el nombre se elimino: los conteos quedan en el
    # subtitulo del panel de requisitos.
    assert page.locator("#learner-requirements-summary").count() == 0
    subtitle = page.locator("#learner-requirements-subtitle")
    subtitle_text = subtitle.text_content()
    assert "4 pendientes" in subtitle_text
    assert "1 cumplido" in subtitle_text
    assert "0 no aplica" in subtitle_text

    first_form = page.locator("#learner-requirements .requirement-editor").first
    assert "is-pending" in (first_form.get_attribute("class") or "")
    assert "Saber TyT" in first_form.text_content()

    first_form.locator("select").select_option("Cumplido")
    first_form.locator("button[type='submit']").click()
    page.wait_for_function(
        "() => document.querySelector('#learner-requirements-subtitle').textContent.includes('3 pendientes')"
    )

    subtitle_text = subtitle.text_content()
    assert "3 pendientes" in subtitle_text
    assert "2 cumplidos" in subtitle_text
    assert "0 no aplica" in subtitle_text

    # Tras guardar, los pendientes siguen primero y el requisito cumplido baja.
    forms = page.locator("#learner-requirements .requirement-editor")
    first_form = forms.first
    assert "Inscripción APE" in first_form.text_content()
    assert "is-pending" in (first_form.get_attribute("class") or "")
    saber_tyt = page.locator(
        "#learner-requirements .requirement-editor", has_text="Saber TyT"
    )
    assert "is-fulfilled" in (saber_tyt.get_attribute("class") or "")


def test_list_distinguishes_missing_matrix_and_exposes_filters(
    page, app_url, seed_df14a
):
    seed_df14a(2)
    learners = page.request.get(f"{app_url}/api/learners").json()["items"]
    empty_learner = learners[0]
    complete_learner = learners[1]
    for requirement_type, status in (("biblioteca", "Cumplido"), ("carnet", "No aplica")):
        _post_requirement(
            page, app_url, complete_learner["id"], requirement_type, status
        )

    _open_learners(page, app_url)

    # Error 1: "sin matriz" y "cero pendientes" no comparten el mismo token.
    empty_row = page.locator("#learners-list tr", has_text=empty_learner["name"]).first
    empty_cell = empty_row.locator(".pending-requirements-cell")
    assert "Sin requisitos registrados" in empty_cell.text_content()
    assert empty_cell.locator(".pending-count-badge").count() == 0

    complete_row = page.locator(
        "#learners-list tr", has_text=complete_learner["name"]
    ).first
    complete_cell = complete_row.locator(".pending-requirements-cell")
    assert "Ninguno" in complete_cell.text_content()
    assert "Sin requisitos registrados" not in complete_cell.text_content()
    assert complete_cell.locator(".pending-count-badge").count() == 0

    # La celda de Origen debe seguir siendo table-cell: si se convierte en flex,
    # su borde inferior no cubre la altura de la fila y la linea se descuadra.
    origin_wrapper = complete_row.locator(".origin-cell-wrapper")
    assert origin_wrapper.evaluate("el => getComputedStyle(el).display") == "table-cell"
    cell_heights = complete_row.locator("td").evaluate_all(
        "cells => cells.map(cell => Math.round(cell.getBoundingClientRect().height))"
    )
    assert len(set(cell_heights)) == 1

    # Error 8: el antiguo "Info" ahora dice qué muestra.
    resumen = complete_row.locator(".info-button")
    assert resumen.text_content().strip() == "Resumen"
    assert "Ver resumen de" in (resumen.get_attribute("aria-label") or "")

    # Error 5: los chips se anuncian como filtros, no como texto decorativo.
    todos_chip = page.locator(
        "#learner-status-chips .status-chip-button", has_text="Todos"
    ).first
    assert "Mostrar todos los estados" in (todos_chip.get_attribute("aria-label") or "")
    assert todos_chip.get_attribute("aria-pressed") == "true"

    # Error 7: el contenedor declara scroll horizontal consciente.
    overflow_x = page.locator("#aprendices-view .learners-table-wrap").evaluate(
        "el => getComputedStyle(el).overflowX"
    )
    assert overflow_x in ("auto", "scroll")

    # Ficha vacia: mensaje controlado, sin inventar conteos.
    empty_row.locator(".detail-button").click()
    page.wait_for_selector("#learner-detail-content:not([hidden])")
    assert "Sin requisitos registrados" in page.locator(
        "#learner-requirements"
    ).text_content()
    assert (
        "Sin requisitos registrados."
        in page.locator("#learner-requirements-subtitle").text_content()
    )
    page.click("#back-to-learners")
    page.wait_for_selector("#learner-detail", state="hidden")

    # Ficha con matriz completa y sin pendientes.
    page.fill("#learner-search", complete_learner["identification"])
    page.wait_for_timeout(300)
    page.wait_for_selector("#learners-list .detail-button")
    page.click("#learners-list .detail-button")
    page.wait_for_selector("#learner-detail-content:not([hidden])")
    subtitle_text = page.locator("#learner-requirements-subtitle").text_content()
    assert "0 pendientes" in subtitle_text
    assert "1 cumplido" in subtitle_text
    assert "1 no aplica" in subtitle_text
    assert page.locator("#learner-requirements .requirement-editor.is-pending").count() == 0
    page.click("#back-to-learners")
    page.wait_for_selector("#learner-detail", state="hidden")

    # Error 9: filtro sin resultados no deja una pagina anterior engañosa.
    page.fill("#learner-search", "NO-EXISTE-999")
    page.wait_for_selector("#learners-list .learners-empty-message")
    assert "No hay aprendices con estos filtros" in page.locator(
        "#learners-list .learners-empty-message"
    ).text_content()
    assert page.locator("#learners-page").text_content() == "Sin resultados"
    assert page.locator("#learners-list .learners-empty-cell button").count() == 1
    page.click("#learners-list .learners-empty-cell button")
    page.wait_for_selector("#learners-list .detail-button")
    assert page.input_value("#learner-search") == ""
    assert page.input_value("#learner-status") == ""

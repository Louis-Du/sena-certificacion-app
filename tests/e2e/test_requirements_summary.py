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
        ("biblioteca", "Cumplido"),
        ("carnet", "No aplica"),
    ):
        _post_requirement(page, app_url, learner_id, requirement_type, status)

    _open_learners(page, app_url)
    pending_cell = page.locator("#learners-list .pending-requirements-cell").first
    pending_text = pending_cell.text_content()
    assert "2" in pending_text
    assert "Saber TyT" in pending_text
    assert "Inscripción APE" in pending_text

    page.click("#learners-list .detail-button")
    page.wait_for_selector("#learner-detail-content:not([hidden])")

    # La tarjeta de resumen bajo el nombre se elimino: los conteos quedan en el
    # subtitulo del panel de requisitos.
    assert page.locator("#learner-requirements-summary").count() == 0
    subtitle = page.locator("#learner-requirements-subtitle")
    subtitle_text = subtitle.text_content()
    assert "2 pendientes" in subtitle_text
    assert "1 cumplido" in subtitle_text
    assert "1 no aplica" in subtitle_text

    first_form = page.locator("#learner-requirements .requirement-editor").first
    assert "is-pending" in (first_form.get_attribute("class") or "")
    assert "Saber TyT" in first_form.text_content()

    first_form.locator("select").select_option("Cumplido")
    first_form.locator("button[type='submit']").click()
    page.wait_for_function(
        "() => document.querySelector('#learner-requirements-subtitle').textContent.includes('1 pendiente')"
    )

    subtitle_text = subtitle.text_content()
    assert "1 pendiente" in subtitle_text
    assert "2 cumplidos" in subtitle_text
    assert "1 no aplica" in subtitle_text

    # Tras guardar, los pendientes siguen primero y el requisito cumplido baja.
    forms = page.locator("#learner-requirements .requirement-editor")
    first_form = forms.first
    assert "Inscripción APE" in first_form.text_content()
    assert "is-pending" in (first_form.get_attribute("class") or "")
    saber_tyt = page.locator(
        "#learner-requirements .requirement-editor", has_text="Saber TyT"
    )
    assert "is-fulfilled" in (saber_tyt.get_attribute("class") or "")


def test_detail_subtitle_reports_complete_and_empty_states(page, app_url, seed_df14a):
    seed_df14a(2)
    learners = page.request.get(f"{app_url}/api/learners").json()["items"]
    complete_learner = learners[1]
    for requirement_type, status in (("biblioteca", "Cumplido"), ("carnet", "No aplica")):
        _post_requirement(
            page, app_url, complete_learner["id"], requirement_type, status
        )

    _open_learners(page, app_url)
    page.click("#learners-list .detail-button")
    page.wait_for_selector("#learner-detail-content:not([hidden])")
    assert "Sin requisitos registrados" in page.locator("#learner-requirements").text_content()
    assert (
        "Sin requisitos registrados."
        in page.locator("#learner-requirements-subtitle").text_content()
    )

    page.click("#back-to-learners")
    page.wait_for_selector("#learner-detail", state="hidden")
    page.fill("#learner-search", complete_learner["identification"])
    page.wait_for_timeout(300)
    page.wait_for_selector("#learners-list .detail-button")

    # En el listado, un aprendiz sin pendientes no inventa un conteo y su
    # procedencia indica documentacion completa.
    pending_text = page.locator(
        "#learners-list .pending-requirements-cell"
    ).first.text_content()
    assert pending_text.strip() == "—"
    row_title = page.locator("#learners-list tr").first.get_attribute("title") or ""
    assert "Documentación completa" in row_title

    page.click("#learners-list .detail-button")
    page.wait_for_selector("#learner-detail-content:not([hidden])")
    subtitle_text = page.locator("#learner-requirements-subtitle").text_content()
    assert "0 pendientes" in subtitle_text
    assert "1 cumplido" in subtitle_text
    assert "1 no aplica" in subtitle_text
    assert page.locator("#learner-requirements .requirement-editor.is-pending").count() == 0

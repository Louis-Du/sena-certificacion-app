import json


def _open_learner_detail(page, app_url):
    page.goto(app_url)
    page.click('a[data-view="aprendices"]')
    page.wait_for_selector("#learners-list .detail-button")
    page.click("#learners-list .detail-button")
    page.wait_for_selector("#learner-detail-content:not([hidden])")


def test_learner_detail_shows_requirement_history(page, app_url, seed_df14a):
    seed_df14a(1)
    learner = page.request.get(f"{app_url}/api/learners").json()["items"][0]
    learner_id = learner["id"]

    _open_learner_detail(page, app_url)
    history = page.locator("#learner-requirement-history")
    assert "Aún no hay cambios de requisitos registrados." in history.text_content()

    created = page.request.post(
        f"{app_url}/api/learners/{learner_id}/requirements",
        headers={"Content-Type": "application/json"},
        data=json.dumps(
            {"requirement_type": "saber_tyt", "status": "Pendiente", "observations": "Cargue inicial."}
        ),
    )
    assert created.ok, created.text()
    requirement_id = created.json()["id"]

    page.reload()
    page.click('a[data-view="aprendices"]')
    page.wait_for_selector("#learners-list .detail-button")
    page.click("#learners-list .detail-button")
    page.wait_for_selector("#learner-requirement-history .requirement-history-row")
    text = page.locator("#learner-requirement-history").text_content()
    assert "Saber TyT" in text
    assert "Pendiente" in text
    assert "Edición manual" in text

    updated = page.request.patch(
        f"{app_url}/api/learners/{learner_id}/requirements/{requirement_id}",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"requirement_type": "saber_tyt", "status": "Cumplido"}),
    )
    assert updated.ok, updated.text()

    page.reload()
    page.click('a[data-view="aprendices"]')
    page.wait_for_selector("#learners-list .detail-button")
    page.click("#learners-list .detail-button")
    page.wait_for_selector("#learner-requirement-history .requirement-history-row")
    rows = page.locator("#learner-requirement-history .requirement-history-row")
    assert rows.count() == 2
    assert "Cumplido" in rows.nth(0).text_content()
    assert "Pendiente" in rows.nth(1).text_content()

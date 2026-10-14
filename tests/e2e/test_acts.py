def _go_to_acts(page, app_url):
    page.goto(app_url)
    page.click('a[data-view="actas"]')
    page.wait_for_selector("#act-form")


def test_create_act_appears_in_list(page, app_url):
    _go_to_acts(page, app_url)
    page.fill('input[name="number"]', "ACT-E2E-01")
    page.fill('input[name="act_date"]', "2026-10-10")
    page.fill('input[name="act_type"]', "Certificacion")
    page.click("#act-form button[type='submit']")
    page.wait_for_function("() => document.querySelector('#acts-list').textContent.includes('ACT-E2E-01')")
    assert "ACT-E2E-01" in page.locator("#acts-list").text_content()


def test_act_detail_and_learner_link_unlink(page, app_url, tmp_path):
    from tests.conftest import csv_bytes

    _go_to_acts(page, app_url)
    page.fill('input[name="number"]', "ACT-E2E-02")
    page.fill('input[name="act_date"]', "2026-10-11")
    page.click("#act-form button[type='submit']")
    page.wait_for_selector("#acts-list tr")

    page.goto(app_url)
    page.click('.type-option[data-type="df14a"]')
    csv_path = tmp_path / "learner.csv"
    csv_path.write_bytes(csv_bytes("identificacion,nombre\n6001,Hugo\n"))
    page.set_input_files("#file-input", str(csv_path))
    page.click("#validate-button")
    page.wait_for_selector("#confirmation-panel:not([hidden])")
    page.click("#confirm-button")
    page.wait_for_selector("#confirm-button", state="hidden")

    _go_to_acts(page, app_url)
    page.click("#acts-list .detail-button")
    page.wait_for_selector("#act-detail-content:not([hidden])")
    page.fill('#act-learner-form input[name="learner_id"]', "1")
    page.click('#act-learner-form button[type="submit"]')
    page.wait_for_selector("#act-learners .detail-list-item")
    assert "Hugo" in page.locator("#act-learners").text_content()

    page.click("#act-learners .cancel-button")
    page.wait_for_selector("#act-learners .detail-list-item", state="detached")
    page.wait_for_function("() => document.querySelector('#act-learners').textContent.includes('Sin aprendices')")
    assert "Sin aprendices asociados" in page.locator("#act-learners").text_content()


def test_act_review_status_filter(page, app_url):
    _go_to_acts(page, app_url)
    page.fill('input[name="number"]', "ACT-E2E-03")
    page.fill('input[name="act_date"]', "2026-10-12")
    page.select_option('select[name="review_status"]', "reviewed")
    page.click("#act-form button[type='submit']")
    page.wait_for_selector("#acts-list tr")

    page.select_option("#act-status", "reviewed")
    page.wait_for_timeout(300)
    assert "ACT-E2E-03" in page.locator("#acts-list").text_content()

    page.select_option("#act-status", "pending")
    page.wait_for_timeout(300)
    assert "ACT-E2E-03" not in page.locator("#acts-list").text_content()


def test_acta_file_import_does_not_create_act_entity(page, app_url, tmp_path):
    from tests.conftest import pdf_bytes

    page.goto(app_url)
    page.click('.type-option[data-type="acta"]')
    pdf_path = tmp_path / "acta.pdf"
    pdf_path.write_bytes(pdf_bytes())
    page.set_input_files("#file-input", str(pdf_path))
    page.click("#validate-button")
    page.wait_for_selector("#confirmation-panel:not([hidden])")
    page.click("#confirm-button")
    page.wait_for_selector("#confirm-button", state="hidden")

    page.click('a[data-view="actas"]')
    page.wait_for_selector("#acts-list")
    assert "No hay actas registradas" in page.locator("#acts-list").text_content()

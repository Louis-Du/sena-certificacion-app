from tests.conftest import csv_bytes


def test_status_chips_control_select_and_clear(page, app_url):
    content = csv_bytes(
        "DOCUMENTO,NOMBRES,FICHA,PROGRAMA,ESTADO_ASPIRANTE\n"
        "8001,Ana,4601,Software,CERTIFICADOS\n"
        "8002,Bruno,4602,Software,PENDIENTE\n"
        "8003,Carla,4603,Software,Por Certificar\n"
        "8004,Dario,4604,Software,\n"
    )
    validated = page.request.post(
        f"{app_url}/api/files/validate",
        multipart={
            "information_type": "df14a",
            "file": {"name": "statuses.csv", "mimeType": "text/csv", "buffer": content},
        },
    )
    assert validated.ok, validated.text()
    confirmed = page.request.post(
        f"{app_url}/api/imports/{validated.json()['validation_id']}/confirm"
    )
    assert confirmed.ok, confirmed.text()

    page.goto(app_url)
    page.click('a[data-view="aprendices"]')
    page.wait_for_selector("#learner-status-chips .status-chip-button:visible")

    chips = page.locator("#learner-status-chips .status-chip-button")
    texts = chips.all_text_contents()
    assert "Todos 4" in texts
    assert "CERTIFICADOS 1" in texts
    assert "PENDIENTE 1" in texts
    assert "Por Certificar 1" in texts
    assert "Sin estado 1" in texts

    page.locator("#learner-status-chips .status-chip-button", has_text="PENDIENTE").click()
    page.wait_for_function(
        "() => document.querySelector('#learner-status').value === 'PENDIENTE'"
    )
    page.wait_for_function(
        "() => document.querySelector('#learners-list').textContent.includes('Bruno')"
    )
    assert "Ana" not in page.locator("#learners-list").text_content()
    assert (
        page.locator("#learner-status-chips .status-chip-button.is-active").text_content()
        == "PENDIENTE 1"
    )

    page.locator("#learner-status-chips .status-chip-button", has_text="PENDIENTE").click()
    page.wait_for_function("() => document.querySelector('#learner-status').value === ''")
    page.wait_for_function(
        "() => document.querySelector('#learners-list').textContent.includes('Ana')"
    )

    page.select_option("#learner-status", "CERTIFICADOS")
    page.wait_for_function(
        "() => document.querySelector('#learners-list').textContent.includes('Ana')"
    )
    assert "Bruno" not in page.locator("#learners-list").text_content()
    assert (
        page.locator("#learner-status-chips .status-chip-button.is-active").text_content()
        == "CERTIFICADOS 1"
    )

    page.fill("#learner-search", "Ana")
    page.click("#learner-missing-requirement summary")
    page.locator(
        "#learner-missing-requirement-options .requirement-option[data-value]:not([data-value=''])"
    ).first.click()
    page.click("#clear-learner-search")
    page.wait_for_function("() => document.querySelector('#learner-status').value === ''")
    page.wait_for_function(
        "() => document.querySelector('#learner-status-chips .status-chip-button.is-active')"
        "?.textContent === 'Todos 4'"
    )
    assert page.input_value("#learner-search") == ""
    assert page.locator("#learner-missing-requirement-summary").text_content() == "Cualquiera"
    assert (
        page.locator("#learner-status-chips .status-chip-button.is-active").text_content()
        == "Todos 4"
    )
    selected_requirements = page.locator(
        "#learner-missing-requirement-options .requirement-option.is-selected"
    )
    assert selected_requirements.count() == 1
    assert selected_requirements.get_attribute("data-value") == ""

from pathlib import Path

from tests.conftest import csv_bytes


def _write_file(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def _validate_csv(page, app_url, tmp_path, content: bytes) -> None:
    page.goto(app_url)
    page.click('.type-option[data-type="df14a"]')
    file_path = _write_file(tmp_path, "df14a.csv", content)
    page.set_input_files("#file-input", str(file_path))
    page.click("#validate-button")
    page.wait_for_selector("#confirmation-panel:not([hidden])")


def test_confirm_import_persists_data(page, app_url, tmp_path):
    _validate_csv(
        page, app_url, tmp_path, csv_bytes("identificacion,nombre,FICHA\n1001,Ana,3001\n")
    )
    page.click("#confirm-button")
    page.wait_for_selector("#confirm-button", state="hidden")
    assert "IMPORTACION COMPLETA" in page.locator("#file-status").text_content()
    history_items = page.locator("#history-list .history-item")
    assert history_items.count() >= 1
    page.click('a[data-view="aprendices"]')
    page.wait_for_selector("#learners-list tr")
    rows = page.locator("#learners-list tr")
    assert rows.count() >= 1


def test_cancel_import_does_not_persist(page, app_url, tmp_path):
    _validate_csv(
        page, app_url, tmp_path, csv_bytes("identificacion,nombre,FICHA\n2001,Bruno,3001\n")
    )
    page.click("#cancel-button")
    page.wait_for_selector("#file-panel", state="hidden")
    assert page.locator("#history-list").text_content() == "Aun no hay importaciones."
    page.click('a[data-view="aprendices"]')
    page.wait_for_selector("#learners-list")
    assert "Aun no hay aprendices" in page.locator("#learners-list").text_content()

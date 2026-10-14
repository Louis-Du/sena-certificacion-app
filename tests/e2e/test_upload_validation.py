from pathlib import Path

import pytest

from tests.conftest import csv_bytes, pdf_bytes


def _write_file(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_select_type_and_validate_compatible_file(page, app_url, tmp_path):
    page.goto(app_url)
    page.click('.type-option[data-type="df14a"]')
    file_path = _write_file(tmp_path, "df14a.csv", csv_bytes("nombre,estado\nAna,Por Certificar\n"))
    page.set_input_files("#file-input", str(file_path))
    page.click("#validate-button")
    page.wait_for_selector("#validation-panel:not([hidden])")
    assert "APTO" in page.locator("#validation-status").text_content()
    assert page.locator("#file-status").text_content() == "VALIDACION COMPLETA"


def test_validate_incompatible_format_shows_error(page, app_url, tmp_path):
    page.goto(app_url)
    page.click('.type-option[data-type="df14a"]')
    file_path = _write_file(tmp_path, "acta.pdf", pdf_bytes())
    page.set_input_files("#file-input", str(file_path))
    feedback = page.locator("#feedback")
    page.wait_for_selector("#feedback.visible")
    assert "no es compatible" in feedback.text_content()
    assert page.locator("#validate-button").is_disabled()


def test_validation_does_not_persist_to_history(page, app_url, tmp_path):
    page.goto(app_url)
    page.click('.type-option[data-type="df14a"]')
    file_path = _write_file(tmp_path, "df14a.csv", csv_bytes("nombre\nAna\n"))
    page.set_input_files("#file-input", str(file_path))
    page.click("#validate-button")
    page.wait_for_selector("#validation-panel:not([hidden])")
    assert page.locator("#history-list").text_content() == "Aun no hay importaciones."


def test_validation_shows_warning_for_duplicate_rows(page, app_url, tmp_path):
    page.goto(app_url)
    page.click('.type-option[data-type="df14a"]')
    file_path = _write_file(
        tmp_path,
        "df14a.csv",
        csv_bytes("nombre,estado\nAna,Por Certificar\nAna,Por Certificar\n"),
    )
    page.set_input_files("#file-input", str(file_path))
    page.click("#validate-button")
    page.wait_for_selector("#validation-panel:not([hidden])")
    assert "ADVERTENCIAS" in page.locator("#validation-status").text_content()

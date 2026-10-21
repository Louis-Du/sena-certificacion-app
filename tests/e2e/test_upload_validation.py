from pathlib import Path

import pytest

from tests.conftest import csv_bytes, pdf_bytes


ROOT = Path(__file__).resolve().parents[2]
INCORRECTOS = ROOT / "archivos_prueba" / "incorrectos"
CORRECTOS = ROOT / "archivos_prueba" / "correctos"


def _write_file(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_select_type_and_validate_compatible_file(page, app_url, tmp_path):
    page.goto(app_url)
    page.click('.type-option[data-type="df14a"]')
    file_path = _write_file(
        tmp_path,
        "df14a.csv",
        csv_bytes("FICHA,nombre,estado\n3001,Ana,Por Certificar\n"),
    )
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
    file_path = _write_file(tmp_path, "df14a.csv", csv_bytes("FICHA\n3001\n"))
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
        csv_bytes(
            "FICHA,nombre,estado\n3001,Ana,Por Certificar\n3001,Ana,Por Certificar\n"
        ),
    )
    page.set_input_files("#file-input", str(file_path))
    page.click("#validate-button")
    page.wait_for_selector("#validation-panel:not([hidden])")
    assert "ADVERTENCIAS" in page.locator("#validation-status").text_content()


def test_requisitos_incorrect_file_uses_requisitos_rules_in_ui(page, app_url):
    page.goto(app_url)
    page.click('.category-option[data-category="requisitos_aprendices"]')
    page.click('.type-option[data-type="requisitos"]')
    page.set_input_files(
        "#file-input",
        str(INCORRECTOS / "Requisitos_incorrecto_sin_columnas_clave.xlsx"),
    )
    page.click("#validate-button")
    page.wait_for_selector("#validation-panel:not([hidden])")

    checks = page.locator("#validation-checks").text_content()
    assert "DOCUMENTO" in checks
    assert "NOMBRES" in checks
    assert "REQUISITO" in checks
    assert "ESTADO" in checks
    assert "CERTIFICADOS" not in checks
    assert "COMPLEMENTARIA" not in checks
    assert "NO APTO" in page.locator("#validation-status").text_content()
    assert page.locator("#confirmation-panel").is_hidden()


def test_unreadable_acta_pdf_is_rejected_in_ui(page, app_url):
    page.goto(app_url)
    page.click('.category-option[data-category="actas_revision"]')
    page.click('.type-option[data-type="acta"]')
    page.set_input_files(
        "#file-input",
        str(INCORRECTOS / "Acta_certificacion_incorrecto_vacio.pdf"),
    )
    page.click("#validate-button")
    page.wait_for_selector("#validation-panel:not([hidden])")

    assert "NO APTO" in page.locator("#validation-status").text_content()
    assert page.locator("#file-status").text_content() == "REVISAR ARCHIVO"
    assert page.locator("#confirmation-panel").is_hidden()


def test_incorrect_actas_preview_shows_ten_records_and_conflict(page, app_url):
    page.goto(app_url)
    page.click('.type-option[data-type="actas_completo"]')
    page.set_input_files(
        "#file-input",
        str(INCORRECTOS / "ACTAS_2026_incorrecto_conflictos_y_meses.xlsx"),
    )
    page.click("#validate-button")
    page.wait_for_selector("#confirmation-panel:not([hidden])")

    assert page.locator("#confirm-importable").text_content() == "10"
    assert page.locator("#confirm-new").text_content() == "10"
    breakdown = page.locator("#confirm-breakdown").text_content()
    assert "Certificados: 4 de 4" in breakdown
    assert "Pendientes: 5 de 5" in breakdown
    assert "Meta: 1 de 1" in breakdown
    warnings = page.locator("#confirm-warnings").text_content()
    assert "figuran simult" in warnings
    assert "No se resuelve automaticamente" in warnings


def test_correct_actas_preview_shows_twenty_one_records(page, app_url):
    page.goto(app_url)
    page.click('.type-option[data-type="actas_completo"]')
    page.set_input_files("#file-input", str(CORRECTOS / "ACTAS_2026_correcto.xlsx"))
    page.click("#validate-button")
    page.wait_for_selector("#confirmation-panel:not([hidden])")

    assert page.locator("#confirm-importable").text_content() == "21"
    breakdown = page.locator("#confirm-breakdown").text_content()
    assert "Certificados: 4 de 4" in breakdown
    assert "Pendientes: 4 de 4" in breakdown
    assert "Complementaria: 12 de 12" in breakdown
    assert "Meta: 1 de 1" in breakdown

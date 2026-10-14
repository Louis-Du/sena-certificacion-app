from app.services.validation import MAX_FILE_SIZE, TYPE_LABELS, validate_file

from tests.conftest import csv_bytes, docx_bytes, pdf_bytes, xlsx_bytes


def test_validate_rejects_unknown_information_type():
    result = validate_file("archivo.csv", csv_bytes("nombre\nAna\n"), "desconocido")

    assert result.status == "error"
    assert "no reconocido" in result.message


def test_validate_rejects_empty_file():
    result = validate_file("df14a.csv", b"", "df14a")

    assert result.status == "error"
    assert "vacio" in result.message


def test_validate_rejects_oversized_file():
    result = validate_file("df14a.csv", b"x" * (MAX_FILE_SIZE + 1), "df14a")

    assert result.status == "error"
    assert "20 MB" in result.message


def test_validate_rejects_incompatible_extension_for_df14a():
    result = validate_file("acta.pdf", pdf_bytes(), "df14a")

    assert result.status == "error"
    assert result.as_dict()["information_type"] == TYPE_LABELS["df14a"]
    assert "no es compatible" in result.message


def test_validate_accepts_csv_and_counts_rows():
    result = validate_file(
        "df14a.csv",
        csv_bytes("nombre,estado\nAna,Por Certificar\nLuis,Certificado\n"),
        "df14a",
    )

    assert result.status == "ready"
    assert result.records_found == 2
    assert result.valid_records == 2
    assert result.inconsistencies == 0
    assert "no se han guardado datos" in result.message


def test_validate_xlsx_df14a_is_ready():
    content = xlsx_bytes(
        [
            {"DOCUMENTO": "1001", "NOMBRES": "Ana", "FICHA": "3001", "PROGRAMA": "Software"},
        ]
    )

    result = validate_file("df14a.xlsx", content, "df14a")

    assert result.status == "ready"
    assert result.records_found == 1


def test_validate_pdf_acta_is_ready():
    result = validate_file("acta.pdf", pdf_bytes(), "acta")

    assert result.status == "ready"
    assert any("PDF" in check["label"] for check in result.checks)


def test_validate_docx_acta_is_ready():
    result = validate_file("acta.docx", docx_bytes(), "acta")

    assert result.status == "ready"
    assert any("Word" in check["label"] for check in result.checks)


def test_validate_unreadable_xlsx_returns_warning_not_error():
    result = validate_file("df14a.xlsx", b"esto no es un excel", "df14a")

    assert result.status == "warning"
    assert "no se pudo leer" in result.message

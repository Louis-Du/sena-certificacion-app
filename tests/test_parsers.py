from io import BytesIO

import pandas as pd

from app.services.parsers import (
    frame_to_records,
    list_excel_sheets,
    parse_acta_docx,
    parse_df14a_xml,
    read_actas_certificados,
    read_actas_pendientes,
    read_complementaria,
)
from app.services.validation import check_required_columns, normalize_column_name
from tests.conftest import docx_bytes


def _multi_sheet_xlsx(sheets: dict[str, list[dict]]) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=name, index=False)
    return buffer.getvalue()


SAMPLE_DF14A_XML = """<?xml version="1.0"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
  <Worksheet ss:Name="Hoja1">
    <Table>
      <Row><Cell><Data ss:Type="String">DF-14A_</Data></Cell></Row>
      <Row><Cell><Data ss:Type="String">MATRICULADOS_RESUMEN_POR_FICHA</Data></Cell></Row>
      <Row><Cell><Data ss:Type="String">23-09-2026</Data></Cell></Row>
      <Row>
        <Cell><Data ss:Type="String">CODIGO_REGIONAL</Data></Cell>
        <Cell><Data ss:Type="String">PROGRAMA</Data></Cell>
        <Cell><Data ss:Type="String">FICHA</Data></Cell>
        <Cell><Data ss:Type="String">POR_CERTIFICAR</Data></Cell>
        <Cell><Data ss:Type="String">CERTIFICADO</Data></Cell>
      </Row>
      <Row>
        <Cell><Data ss:Type="String">13</Data></Cell>
        <Cell><Data ss:Type="String">ADSI</Data></Cell>
        <Cell><Data ss:Type="String">2558701</Data></Cell>
        <Cell><Data ss:Type="String">3</Data></Cell>
        <Cell><Data ss:Type="String">12</Data></Cell>
      </Row>
    </Table>
  </Worksheet>
</Workbook>"""


def test_parse_df14a_xml_extracts_header_and_data_rows():
    frame = parse_df14a_xml(SAMPLE_DF14A_XML.encode("utf-8"))

    assert list(frame.columns) == ["CODIGO_REGIONAL", "PROGRAMA", "FICHA", "POR_CERTIFICAR", "CERTIFICADO"]
    assert len(frame) == 1
    assert frame.iloc[0]["FICHA"] == "2558701"
    assert frame.iloc[0]["POR_CERTIFICAR"] == "3"


def test_parse_df14a_xml_returns_empty_for_invalid():
    frame = parse_df14a_xml(b"<not><valid/></not>")
    assert frame.empty


def test_list_excel_sheets_detects_multiple_sheets():
    content = _multi_sheet_xlsx(
        {
            "CERTIFICADOS": [{"NÚMERO DE DOCUMENTO": "1", "NOMBRE": "Ana"}],
            "PENDIENTES": [{"NÚMERO DE DOCUMENTO": "2", "NOMBRE": "Luis"}],
        }
    )
    sheets = list_excel_sheets(content)
    assert "CERTIFICADOS" in sheets
    assert "PENDIENTES" in sheets


def test_read_actas_certificados_reads_correct_sheet():
    content = _multi_sheet_xlsx(
        {
            "CERTIFICADOS": [
                {"NÚMERO DE DOCUMENTO": "111", "NOMBRE": "Ana", "FICHA": "3001"},
            ],
            "PENDIENTES": [
                {"NÚMERO DE DOCUMENTO": "222", "NOMBRE": "Luis", "FICHA": "3002"},
            ],
        }
    )
    frame = read_actas_certificados(content)
    assert len(frame) == 1
    assert frame.iloc[0]["NÚMERO DE DOCUMENTO"] == 111
    assert frame.iloc[0]["NOMBRE"] == "Ana"


def test_read_actas_pendientes_reads_correct_sheet():
    content = _multi_sheet_xlsx(
        {
            "CERTIFICADOS": [{"NÚMERO DE DOCUMENTO": "111", "NOMBRE": "Ana"}],
            "PENDIENTES": [{"NÚMERO DE DOCUMENTO": "222", "NOMBRE": "Luis", "FICHA": "3002"}],
        }
    )
    frame = read_actas_pendientes(content)
    assert len(frame) == 1
    assert frame.iloc[0]["NOMBRE"] == "Luis"


def test_read_complementaria_reads_correct_sheet():
    content = _multi_sheet_xlsx(
        {
            "COMPLEMENTARIA": [{"FECHA": "2026-01-15", "N° DE CERTIFICADOS": 44}],
        }
    )
    frame = read_complementaria(content)
    assert len(frame) == 1
    assert frame.iloc[0]["N° DE CERTIFICADOS"] == 44


def test_parse_acta_docx_extracts_table_records():
    from docx import Document

    document = Document()
    document.add_paragraph("ACTA DE CERTIFICACIÓN No. 23")
    table = document.add_table(rows=3, cols=4)
    table.cell(0, 0).text = "No."
    table.cell(0, 1).text = "Documento"
    table.cell(0, 2).text = "Nombre"
    table.cell(0, 3).text = "Ficha"
    table.cell(1, 0).text = "1"
    table.cell(1, 1).text = "1043000100"
    table.cell(1, 2).text = "LAURA SOFÍA PÉREZ"
    table.cell(1, 3).text = "2558701"
    table.cell(2, 0).text = "2"
    table.cell(2, 1).text = "1043000237"
    table.cell(2, 2).text = "CARLOS ANDRÉS RODRÍGUEZ"
    table.cell(2, 3).text = "2558702"
    buffer = BytesIO()
    document.save(buffer)
    result = parse_acta_docx(buffer.getvalue())

    assert result["tables_count"] == 1
    assert result["header"] == ["No.", "Documento", "Nombre", "Ficha"]
    assert len(result["records"]) == 2
    assert result["records"][0]["Documento"] == "1043000100"
    assert result["records"][0]["Ficha"] == "2558701"
    assert any("ACTA DE CERTIFICACIÓN" in p for p in result["paragraphs"])


def test_frame_to_records_strips_nan_values():
    frame = pd.DataFrame(
        [
            {"nombre": "Ana", "ficha": None, "estado": "Certificado"},
            {"nombre": None, "ficha": None, "estado": None},
        ]
    )
    records = frame_to_records(frame)

    assert len(records) == 1
    assert records[0] == {"nombre": "Ana", "estado": "Certificado"}


def test_normalize_column_name_handles_accents_and_case():
    assert normalize_column_name("NÚMERO DE DOCUMENTO") == "numero de documento"
    assert normalize_column_name("Ficha ") == "ficha"
    assert normalize_column_name("MES_DE_CERTIFICACIÓN") == "mes de certificacion"


def test_check_required_columns_detects_missing_and_extra():
    missing, extra = check_required_columns(
        "certificados",
        ["NÚMERO DE DOCUMENTO", "NOMBRE", "FICHA", "COLUMNA_EXTRA"],
    )
    assert missing == []
    assert "COLUMNA_EXTRA" in extra


def test_check_required_columns_reports_missing():
    missing, extra = check_required_columns(
        "certificados",
        ["NOMBRE", "FICHA"],
    )
    assert "NÚMERO DE DOCUMENTO" in missing

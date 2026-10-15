from __future__ import annotations

from io import BytesIO
from typing import Any
from xml.etree import ElementTree as ET

import pandas as pd

SS = "{urn:schemas-microsoft-com:office:spreadsheet}"

ACTAS_SHEETS = ("CERTIFICADOS", "PENDIENTES", "COMPLEMENTARIA")


def parse_df14a_xml(content: bytes) -> pd.DataFrame:
    root = ET.fromstring(content)
    worksheet = None
    for ws in root.iter(SS + "Worksheet"):
        name = ws.get(SS + "Name", "")
        if name and name != "Hoja2" and name != "Hoja3":
            worksheet = ws
            break
    if worksheet is None:
        worksheet = root.find(f".//{SS}Worksheet")
    if worksheet is None:
        return pd.DataFrame()

    table = worksheet.find(SS + "Table")
    if table is None:
        return pd.DataFrame()

    rows = table.findall(SS + "Row")
    if not rows:
        return pd.DataFrame()

    header_idx = _find_header_row(rows)
    headers = _row_values(rows[header_idx]) if header_idx is not None else []
    if not headers:
        return pd.DataFrame()

    data_rows = rows[header_idx + 1 :] if header_idx is not None else rows
    records: list[dict[str, Any]] = []
    for row in data_rows:
        values = _row_values(row)
        if not values or all(v is None or str(v).strip() == "" for v in values):
            continue
        record = {headers[i]: values[i] for i in range(min(len(headers), len(values)))}
        records.append(record)
    return pd.DataFrame(records)


def _find_header_row(rows: list[ET.Element]) -> int | None:
    for idx, row in enumerate(rows[:15]):
        values = _row_values(row)
        text_values = {str(v).strip().upper() for v in values if v is not None}
        if "FICHA" in text_values:
            return idx
    return None


def _row_values(row: ET.Element) -> list[Any]:
    values: list[Any] = []
    last_index = 0
    for cell in row.findall(SS + "Cell"):
        index_attr = cell.get(SS + "Index")
        if index_attr and index_attr.isdigit():
            target = int(index_attr) - 1
            while last_index < target:
                values.append(None)
                last_index += 1
        data = cell.find(SS + "Data")
        values.append(data.text if data is not None else None)
        last_index += 1
    return values


def list_excel_sheets(content: bytes) -> list[str]:
    try:
        return pd.ExcelFile(BytesIO(content)).sheet_names
    except Exception:
        return []


def read_actas_sheet(content: bytes, sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(BytesIO(content), sheet_name=sheet_name)


def read_actas_certificados(content: bytes) -> pd.DataFrame:
    return read_actas_sheet(content, "CERTIFICADOS")


def read_actas_pendientes(content: bytes) -> pd.DataFrame:
    return read_actas_sheet(content, "PENDIENTES")


def read_complementaria(content: bytes) -> pd.DataFrame:
    return read_actas_sheet(content, "COMPLEMENTARIA")


def read_requisitos(content: bytes) -> pd.DataFrame:
    return pd.read_excel(BytesIO(content))


def parse_acta_docx(content: bytes) -> dict[str, Any]:
    from docx import Document

    document = Document(BytesIO(content))
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    table_rows: list[list[str]] = []
    for table in document.tables:
        for row in table.rows:
            table_rows.append([cell.text.strip() for cell in row.cells])

    header = table_rows[0] if table_rows else []
    records: list[dict[str, str]] = []
    for row in table_rows[1:]:
        if not any(row):
            continue
        record = {header[i]: row[i] for i in range(min(len(header), len(row)))}
        records.append(record)

    return {
        "paragraphs": paragraphs,
        "header": header,
        "records": records,
        "tables_count": len(document.tables),
    }


def frame_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.where(pd.notna(frame), None)
    return [
        {str(key): value for key, value in row.items() if value is not None}
        for row in clean.to_dict(orient="records")
        if any(value is not None for value in row.values())
    ]

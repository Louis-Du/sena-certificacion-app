"""Generacion de informes en formato Word (.docx) a partir de la plantilla institucional."""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

from docx import Document

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "informe_gestion_administrativa.docx"


def _replace_in_paragraph(paragraph, replacements: dict[str, str]) -> None:
    full = paragraph.text
    for key, value in replacements.items():
        if key in full:
            full = full.replace(key, value)
    if paragraph.text != full:
        style = None
        if paragraph.runs:
            style = paragraph.runs[0].style
        paragraph.text = full
        if style is not None and paragraph.runs:
            paragraph.runs[0].style = style


def generate_report_docx(
    year: int | None = None,
    quarter: int | None = None,
    cutoff: date | None = None,
    summary: dict | None = None,
) -> bytes:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Plantilla no encontrada: {TEMPLATE_PATH}")

    doc = Document(str(TEMPLATE_PATH))

    year = year or date.today().year
    quarter = quarter or 2
    cutoff = cutoff or date.today()

    roman = {1: "I", 2: "II", 3: "III", 4: "IV"}.get(quarter, str(quarter))

    replacements = {
        "Junio 30 de 2026": cutoff.strftime("%B %d de %Y").capitalize(),
        "Trimestre II de": f"Trimestre {roman} de",
        "trimestre II 2026": f"trimestre {roman} {year}",
        "II 2026": f"{roman} {year}",
    }

    for p in doc.paragraphs:
        _replace_in_paragraph(p, replacements)

    # Reemplazar valores historicos de la tabla de indicadores por "Pendiente"
    # porque no existe fuente confiable para metas/porcentajes oficiales.
    for table in doc.tables:
        for row in table.rows:
            # saltar encabezado
            if row.cells and row.cells[0].text.strip().upper() in ("INDICADOR", "PROCESO"):
                continue
            for idx, cell in enumerate(row.cells):
                if idx == 0:
                    continue
                for p in cell.paragraphs:
                    if p.text.strip():
                        p.text = "Pendiente (sin fuente confiable)"

    # Agregar resumen de datos reales al final (antes de anexos) si existe
    if summary:
        doc.add_paragraph("RESUMEN DE DATOS DISPONIBLES (SQLite)", style=None)
        for k, v in summary.items():
            doc.add_paragraph(f"- {k}: {v}")

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
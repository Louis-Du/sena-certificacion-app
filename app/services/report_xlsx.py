"""Generacion del libro XLSX del informe administrativo.

El libro completo tiene siete secciones funcionales:

1. Resumen ejecutivo
2. Resultados por categoría
3. Evolución mensual
4. Análisis de pendientes
5. Gestión documental
6. Anexo aprendices
7. Anexo pendientes y trazabilidad

Todas las cifras provienen de ``report_data.consolidate_report_dataset``. Este
modulo solo las presenta; no recalcula indicadores. Los valores ``None`` se
dejan vacios en las celdas numéricas (con una nota de "No calculable" cuando
corresponde) y nunca se convierten en cero.
"""

from __future__ import annotations

import math
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, DoughnutChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.series import DataPoint
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins
from openpyxl.worksheet.properties import PageSetupProperties

from app.services.report_data import INCIDENCE_NOTE, INCIDENCE_NOTE_SHORT


# ---------------------------------------------------------------------------
# Paleta institucional y utilidades de presentacion
# ---------------------------------------------------------------------------

DARK_GREEN = "14532D"
GREEN = "15803D"
GREEN_SOFT = "DCFCE7"
TEAL = "0F766E"
BLUE = "1E3A5F"
BLUE_SOFT = "E2E8F0"
GRAY = "475569"
GRAY_SOFT = "F1F5F9"
GRAY_LINE = "CBD5E1"
AMBER = "B45309"
AMBER_SOFT = "FEF3C7"
RED = "B91C1C"
RED_SOFT = "FEE2E2"
WHITE = "FFFFFF"

THIN = Side(style="thin", color=GRAY_LINE)
MEDIUM = Side(style="medium", color=GRAY_LINE)


def _fill(color: str) -> PatternFill:
    return PatternFill("solid", fgColor=color)


def _font(
    size: int = 10,
    *,
    bold: bool = False,
    color: str = "1F2937",
    italic: bool = False,
) -> Font:
    return Font(name="Calibri", size=size, bold=bold, color=color, italic=italic)


def _align(
    horizontal: str = "left",
    vertical: str = "center",
    *,
    wrap: bool = True,
) -> Alignment:
    return Alignment(horizontal=horizontal, vertical=vertical, wrap_text=wrap)


def _style_range(
    ws,
    min_row: int,
    max_row: int,
    min_col: int,
    max_col: int,
    *,
    fill: PatternFill | None = None,
    font: Font | None = None,
    alignment: Alignment | None = None,
    border: Border | None = None,
) -> None:
    for row in ws.iter_rows(
        min_row=min_row, max_row=max_row, min_col=min_col, max_col=max_col
    ):
        for cell in row:
            if fill is not None:
                cell.fill = fill
            if font is not None:
                cell.font = font
            if alignment is not None:
                cell.alignment = alignment
            if border is not None:
                cell.border = border


def _merged(
    ws,
    row1: int,
    col1: int,
    row2: int,
    col2: int,
    value: Any,
    *,
    fill: PatternFill | None = None,
    font: Font | None = None,
    alignment: Alignment | None = None,
    border: Border | None = None,
) -> None:
    _style_range(
        ws,
        row1,
        row2,
        col1,
        col2,
        fill=fill,
        font=font,
        alignment=alignment,
        border=border,
    )
    ws.merge_cells(
        start_row=row1, start_column=col1, end_row=row2, end_column=col2
    )
    ws.cell(row=row1, column=col1, value=value)


def _title(ws, row: int, text: str, subtitle: str, last_col: int = 12) -> int:
    _merged(
        ws,
        row,
        1,
        row,
        last_col,
        text,
        fill=_fill(DARK_GREEN),
        font=_font(18, bold=True, color=WHITE),
        alignment=_align("left", "center"),
    )
    ws.row_dimensions[row].height = 28
    _merged(
        ws,
        row + 1,
        1,
        row + 1,
        last_col,
        subtitle,
        fill=_fill(GRAY_SOFT),
        font=_font(9, color=GRAY),
        alignment=_align("left", "center"),
    )
    ws.row_dimensions[row + 1].height = 18
    return row + 2


def _section(ws, row: int, text: str, last_col: int = 12, color: str = BLUE) -> int:
    _merged(
        ws,
        row,
        1,
        row,
        last_col,
        text,
        fill=_fill(color),
        font=_font(11, bold=True, color=WHITE),
        alignment=_align("left", "center"),
    )
    ws.row_dimensions[row].height = 20
    return row + 1


def _note(
    ws,
    row: int,
    text: str,
    last_col: int = 12,
    *,
    kind: str = "info",
    chars_per_line: int = 118,
) -> int:
    palette = {
        "info": (GRAY_SOFT, GRAY, GRAY_LINE),
        "warning": (AMBER_SOFT, "92400E", "F59E0B"),
        "alert": (RED_SOFT, RED, RED),
        "success": (GREEN_SOFT, DARK_GREEN, GREEN),
    }
    fill_color, font_color, border_color = palette.get(kind, palette["info"])
    lines = sum(
        max(1, math.ceil(len(line) / max(chars_per_line, 20)))
        for line in str(text or "").splitlines()
    )
    lines = max(1, lines)
    height = max(20, lines * 14 + 6)
    _merged(
        ws,
        row,
        1,
        row,
        last_col,
        text,
        fill=_fill(fill_color),
        font=_font(9, color=font_color),
        alignment=_align("left", "top"),
    )
    # El borde izquierdo se aplica a la primera celda del rango fusionado.
    ws.cell(row=row, column=1).border = Border(
        left=Side(style="thick", color=border_color),
        top=Side(style="thin", color=border_color),
        bottom=Side(style="thin", color=border_color),
        right=Side(style="thin", color=border_color),
    )
    ws.row_dimensions[row].height = height
    return row + 1


def _card(
    ws,
    row: int,
    col: int,
    *,
    title: str,
    value: Any,
    note: str,
    accent: str = DARK_GREEN,
    background: str = WHITE,
    span: int = 3,
) -> None:
    end_col = col + span - 1
    border = Border(
        left=Side(style="thin", color=accent),
        right=Side(style="thin", color=accent),
        top=Side(style="thin", color=accent),
        bottom=Side(style="thin", color=accent),
    )
    _merged(
        ws,
        row,
        col,
        row,
        end_col,
        title.upper(),
        fill=_fill(background),
        font=_font(8, bold=True, color=GRAY),
        alignment=_align("left", "center"),
        border=border,
    )
    _merged(
        ws,
        row + 1,
        col,
        row + 1,
        end_col,
        value,
        fill=_fill(background),
        font=_font(20, bold=True, color=accent),
        alignment=_align("left", "center"),
        border=border,
    )
    _merged(
        ws,
        row + 2,
        col,
        row + 2,
        end_col,
        note,
        fill=_fill(background),
        font=_font(8, color=GRAY),
        alignment=_align("left", "top"),
        border=border,
    )
    ws.row_dimensions[row].height = 16
    ws.row_dimensions[row + 1].height = 24
    ws.row_dimensions[row + 2].height = 20


def _cards(ws, row: int, items: list[dict[str, Any]], span: int = 3) -> int:
    if not items:
        return row
    for index, item in enumerate(items):
        card_row = row + (index // 4) * 4
        card_col = 1 + (index % 4) * span
        _card(
            ws,
            card_row,
            card_col,
            title=item.get("title", ""),
            value=item.get("value", "No calculable"),
            note=item.get("note", ""),
            accent=item.get("accent", DARK_GREEN),
            background=item.get("background", WHITE),
            span=span,
        )
    rows_used = ((len(items) - 1) // 4 + 1) if items else 0
    return row + rows_used * 4 + 1


def _num(value: Any) -> str:
    if value is None:
        return "No calculable"
    if isinstance(value, (int, float)):
        return f"{value:,.0f}".replace(",", ".")
    return str(value)


def _pct(value: Any) -> str:
    if value is None:
        return "No calculable"
    if isinstance(value, (int, float)):
        return f"{value:.1f}%".replace(".", ",")
    return str(value)


def _table(
    ws,
    row: int,
    headers: list[str],
    rows: list[list[Any]],
    *,
    widths: list[int] | None = None,
    number_formats: dict[int, str] | None = None,
    blank_columns: set[int] | None = None,
    none_text: str = "No calculable",
    freeze: bool = True,
    auto_filter: bool = True,
    highlight_status: int | None = None,
) -> int:
    """Escribe una tabla con encabezado, filtros y formatos numericos."""
    header_row = row
    last_col = len(headers)
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col, value=header)
        cell.fill = _fill(BLUE)
        cell.font = _font(9, bold=True, color=WHITE)
        cell.alignment = _align("center", "center")
        cell.border = Border(bottom=Side(style="medium", color=WHITE))
    ws.row_dimensions[header_row].height = 24

    blank_columns = blank_columns or set()
    number_formats = number_formats or {}
    for index, values in enumerate(rows, start=1):
        data_row = header_row + index
        for col, value in enumerate(values, start=1):
            if value is None and col in blank_columns:
                display_value = None
            elif value is None:
                display_value = none_text
            else:
                display_value = value
            cell = ws.cell(row=data_row, column=col, value=display_value)
            cell.font = _font(9, color="1F2937")
            cell.alignment = _align(
                "left" if col == 1 else "center", "center"
            )
            cell.border = Border(bottom=THIN)
            if index % 2 == 0:
                cell.fill = _fill(GRAY_SOFT)
            if col in number_formats and isinstance(value, (int, float)):
                cell.number_format = number_formats[col]
            if highlight_status is not None and col == highlight_status:
                _status_style(cell, value)
    last_row = header_row + len(rows)
    if last_row == header_row:
        last_row = header_row + 1
        ws.cell(row=last_row, column=1, value="Sin registros disponibles.")
        ws.cell(row=last_row, column=1).font = _font(9, italic=True, color=GRAY)
        ws.merge_cells(
            start_row=last_row,
            start_column=1,
            end_row=last_row,
            end_column=last_col,
        )
    if widths:
        for col, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(col)].width = width
    if auto_filter and rows:
        ws.auto_filter.ref = (
            f"A{header_row}:{get_column_letter(last_col)}{last_row}"
        )
    if freeze:
        ws.freeze_panes = f"A{header_row + 1}"
    return last_row


def _status_style(cell, value: Any) -> None:
    text = str(value or "").strip()
    if text == "Certificado":
        cell.fill = _fill(GREEN_SOFT)
        cell.font = _font(9, bold=True, color=DARK_GREEN)
    elif text == "Pendiente":
        cell.fill = _fill(AMBER_SOFT)
        cell.font = _font(9, bold=True, color=AMBER)
    elif text == "Sin estado informado" or text == "Estado no reconocido":
        cell.fill = _fill(RED_SOFT)
        cell.font = _font(9, bold=True, color=RED)
    elif text == "Sin motivo informado":
        cell.fill = _fill(AMBER_SOFT)
        cell.font = _font(9, bold=True, color=AMBER)


def _print_setup(
    ws,
    *,
    last_col: int,
    last_row: int,
    orientation: str = "landscape",
    title_rows: str | None = None,
    header: str = "Informe consolidado de certificación 2026",
) -> None:
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 90
    ws.page_setup.orientation = orientation
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_margins = PageMargins(
        left=0.4, right=0.4, top=0.6, bottom=0.6, header=0.25, footer=0.25
    )
    ws.print_area = f"A1:{get_column_letter(last_col)}{last_row}"
    if title_rows:
        ws.print_title_rows = title_rows
    ws.oddHeader.center.text = header
    ws.oddHeader.center.size = 9
    ws.oddHeader.center.font = "Calibri,Bold"
    ws.oddFooter.left.text = "SENA Certificación · Documento administrativo"
    ws.oddFooter.left.size = 8
    ws.oddFooter.right.text = "Página &P de &N"
    ws.oddFooter.right.size = 8


def _bar_chart(
    ws,
    *,
    values_col: int,
    labels_col: int,
    header_row: int,
    last_row: int,
    title: str,
    anchor: str,
    horizontal: bool = False,
    height: float = 8.0,
    width: float = 13.0,
    percent: bool = False,
    legend: bool = False,
) -> None:
    if last_row <= header_row:
        return
    chart = BarChart()
    chart.type = "bar" if horizontal else "col"
    chart.style = 10
    chart.title = title
    chart.height = height
    chart.width = width
    chart.dispBlanksAs = "gap"
    values = Reference(
        ws,
        min_col=values_col,
        min_row=header_row,
        max_row=last_row,
    )
    labels = Reference(
        ws,
        min_col=labels_col,
        min_row=header_row + 1,
        max_row=last_row,
    )
    chart.add_data(values, titles_from_data=True)
    chart.set_categories(labels)
    chart.dataLabels = DataLabelList()
    chart.dataLabels.showVal = True
    chart.dataLabels.showSerName = False
    chart.dataLabels.showCatName = False
    chart.dataLabels.showLegendKey = False
    chart.dataLabels.showPercent = False
    chart.dataLabels.showBubbleSize = False
    chart.dataLabels.numFmt = '0.0"%"' if percent else "0"
    chart.legend = None
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    if percent:
        chart.y_axis.scaling.min = 0
        chart.y_axis.scaling.max = 100
    if horizontal:
        chart.x_axis.scaling.orientation = "maxMin"
    if legend:
        chart.legend = None
    ws.add_chart(chart, anchor)


def _clustered_chart(
    ws,
    *,
    header_row: int,
    last_row: int,
    first_value_col: int,
    last_value_col: int,
    labels_col: int,
    title: str,
    anchor: str,
    height: float = 8.0,
    width: float = 13.0,
) -> None:
    if last_row <= header_row:
        return
    chart = BarChart()
    chart.type = "col"
    chart.grouping = "clustered"
    chart.style = 10
    chart.title = title
    chart.height = height
    chart.width = width
    chart.dispBlanksAs = "gap"
    values = Reference(
        ws,
        min_col=first_value_col,
        max_col=last_value_col,
        min_row=header_row,
        max_row=last_row,
    )
    labels = Reference(
        ws,
        min_col=labels_col,
        min_row=header_row + 1,
        max_row=last_row,
    )
    chart.add_data(values, titles_from_data=True)
    chart.set_categories(labels)
    chart.dataLabels = DataLabelList()
    chart.dataLabels.showVal = True
    chart.dataLabels.showSerName = False
    chart.dataLabels.showCatName = False
    chart.dataLabels.showLegendKey = False
    chart.dataLabels.showPercent = False
    chart.dataLabels.showBubbleSize = False
    chart.legend.position = "b"
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    ws.add_chart(chart, anchor)


def _doughnut_chart(
    ws,
    *,
    labels_col: int,
    values_col: int,
    header_row: int,
    last_row: int,
    title: str,
    anchor: str,
) -> None:
    if last_row < header_row + 2:
        return
    chart = DoughnutChart()
    chart.title = title
    chart.height = 10.0
    chart.width = 9.0
    chart.style = 10
    data = Reference(
        ws, min_col=values_col, min_row=header_row, max_row=last_row
    )
    labels = Reference(
        ws, min_col=labels_col, min_row=header_row + 1, max_row=last_row
    )
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(labels)
    chart.dataLabels = DataLabelList()
    chart.dataLabels.showVal = True
    chart.dataLabels.showCatName = False
    chart.dataLabels.showSerName = False
    chart.dataLabels.showPercent = False
    chart.dataLabels.showLegendKey = False
    if chart.series:
        chart.series[0].data_points = [
            DataPoint(idx=0, spPr=GraphicalProperties(solidFill=GREEN)),
            DataPoint(idx=1, spPr=GraphicalProperties(solidFill=AMBER)),
        ]
    ws.add_chart(chart, anchor)


# ---------------------------------------------------------------------------
# Hojas
# ---------------------------------------------------------------------------


def _sheet_summary(wb: Workbook, dataset: dict[str, Any]) -> None:
    ws = wb.create_sheet("Resumen ejecutivo")
    summary = dataset.get("resumen_ejecutivo") or {}
    local = dataset.get("universo_local") or {}
    trace = dataset.get("trazabilidad") or {}
    row = 1
    row = _title(
        ws,
        row,
        "Informe consolidado de certificación 2026",
        f"Periodo {dataset.get('periodo') or 'No disponible'} · Universo institucional "
        f"ACTAS 2026 · Generado {str(dataset.get('generated_at') or '')[:10]}",
        last_col=12,
    )
    source = (
        f"Fuente: consolidado del lote vigente"
        f"{' · ' + str(dataset.get('file_name')) if dataset.get('file_name') else ''}"
        f" · Metas: {dataset.get('fuente_metas') or 'No disponible'}"
    )
    row = _note(ws, row, source, last_col=12, kind="info", chars_per_line=130)
    row += 1

    row = _section(ws, row, "Indicadores principales", last_col=12, color=DARK_GREEN)
    cards = [
        {
            "title": "Meta institucional",
            "value": _num(summary.get("meta_total")),
            "note": "Aprendices proyectados por la meta anual",
            "accent": BLUE,
        },
        {
            "title": "Certificados personas",
            "value": _num(summary.get("certificados_personas")),
            "note": "Personas únicas del consolidado en el periodo",
            "accent": DARK_GREEN,
            "background": GREEN_SOFT,
        },
        {
            "title": "Pendientes personas",
            "value": _num(summary.get("pendientes_personas")),
            "note": "Personas únicas pendientes; no incluye complementaria",
            "accent": AMBER,
            "background": AMBER_SOFT,
        },
        {
            "title": "Avance global",
            "value": _pct(summary.get("avance_global")),
            "note": "Certificados (personas + complementaria) / meta",
            "accent": DARK_GREEN,
            "background": GREEN_SOFT,
        },
        {
            "title": "Certificados complementaria",
            "value": _num(summary.get("certificados_complementaria")),
            "note": "Certificados agregados; no son personas",
            "accent": TEAL,
        },
        {
            "title": "Efectividad de personas",
            "value": _pct(summary.get("efectividad_global")),
            "note": "Personas certificadas / (certificadas + pendientes)",
            "accent": DARK_GREEN,
        },
        {
            "title": "Brecha",
            "value": _num(summary.get("brecha_total")),
            "note": "Meta - certificados; 0 si la meta está cumplida",
            "accent": AMBER,
        },
        {
            "title": "Alertas de calidad",
            "value": _num(summary.get("alertas_total")),
            "note": f"{summary.get('alertas_alta', 0)} de severidad alta",
            "accent": RED if summary.get("alertas_alta") else GREEN,
        },
    ]
    row = _cards(ws, row, cards)
    row = _section(ws, row, "Avance global frente a la meta", last_col=12)
    chart_header = row
    ws.cell(row=chart_header, column=1, value="Concepto")
    ws.cell(row=chart_header, column=2, value="Valor")
    for col in (1, 2):
        cell = ws.cell(row=chart_header, column=col)
        cell.fill = _fill(BLUE)
        cell.font = _font(9, bold=True, color=WHITE)
        cell.alignment = _align("center")
    chart_rows = [
        ("Certificados (personas + complementaria)", summary.get("total_certificados")),
        ("Brecha", summary.get("brecha_total")),
        ("Meta institucional", summary.get("meta_total")),
    ]
    for index, (label, value) in enumerate(chart_rows, start=1):
        data_row = chart_header + index
        ws.cell(row=data_row, column=1, value=label).font = _font(9)
        value_cell = ws.cell(
            row=data_row,
            column=2,
            value=value if isinstance(value, (int, float)) else None,
        )
        value_cell.font = _font(9, bold=True)
        value_cell.number_format = "#,##0"
        value_cell.alignment = _align("center")
    if isinstance(summary.get("total_certificados"), (int, float)) and isinstance(
        summary.get("brecha_total"), (int, float)
    ):
        _doughnut_chart(
            ws,
            labels_col=1,
            values_col=2,
            header_row=chart_header,
            last_row=chart_header + 2,
            title="Cumplimiento de la meta",
            anchor=f"D{chart_header}",
        )
    else:
        row = _note(
            ws,
            chart_header + 4,
            "No se puede representar el cumplimiento porque falta la meta o la "
            "brecha. El dato no se reemplaza por cero.",
            last_col=6,
            kind="warning",
            chars_per_line=58,
        )
    # La fila 36 deja espacio para el grafico, que flota sobre las columnas D:G.
    row = max(row, 36)
    row = _section(ws, row, "Alertas de calidad de la información", last_col=12, color=AMBER)
    alerts = (dataset.get("calidad") or {}).get("alertas") or []
    alert_headers = ["Severidad", "Alerta", "Universo", "Cantidad", "Porcentaje"]
    alert_rows = []
    for item in alerts[:8]:
        alert_rows.append(
            [
                str(item.get("severidad") or "").capitalize(),
                item.get("titulo") or "",
                "Institucional" if item.get("universo") == "consolidado_institucional" else "Local",
                item.get("cantidad") if item.get("cantidad") is not None else "No calculable",
                _pct(item.get("porcentaje")),
            ]
        )
    last_alert_row = _table(
        ws,
        row,
        alert_headers,
        alert_rows,
        widths=[16, 28, 20, 12, 12],
        none_text="No calculable",
        freeze=False,
        auto_filter=False,
    )
    row = last_alert_row + 2
    row = _section(ws, row, "Conciliación de universos (no comparables)", last_col=12, color=BLUE)
    reconciliation = (trace.get("conciliacion_certificados") or {})
    recon_rows = [
        ["Certificados locales (padrón)", _num(reconciliation.get("certificados_locales"))],
        ["Certificados institucionales (periodo)", _num(reconciliation.get("certificados_institucionales"))],
        ["Diferencia (local - institucional)", _num(reconciliation.get("diferencia"))],
        ["Certificados excluidos del periodo", _num(reconciliation.get("certificados_excluidos_periodo"))],
    ]
    last_recon = _table(
        ws,
        row,
        ["Concepto", "Valor"],
        recon_rows,
        widths=[48, 18],
        freeze=False,
        auto_filter=False,
    )
    row = last_recon + 1
    row = _note(
        ws,
        row,
        str(reconciliation.get("explicacion") or "No hay información de conciliación."),
        last_col=12,
        kind="info",
        chars_per_line=120,
    )
    row = _note(
        ws,
        row,
        "El universo local (aprendices, requisitos, actas y seguimiento) no se suma "
        "al universo institucional (ACTAS 2026). Las cifras se presentan separadas.",
        last_col=12,
        kind="warning",
        chars_per_line=120,
    )
    row += 1
    row = _note(
        ws,
        row,
        INCIDENCE_NOTE_SHORT,
        last_col=12,
        kind="warning",
        chars_per_line=120,
    )
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 16
    for col in range(4, 13):
        ws.column_dimensions[get_column_letter(col)].width = 12
    _print_setup(ws, last_col=12, last_row=row, header="Informe consolidado · Resumen ejecutivo")


def _sheet_categories(wb: Workbook, dataset: dict[str, Any]) -> None:
    ws = wb.create_sheet("Resultados por categoría")
    metrics = dataset.get("desglose_por_categoria") or []
    row = 1
    row = _title(
        ws,
        row,
        "Resultados por categoría",
        "Metas, certificados, pendientes, avance, brecha y efectividad del universo institucional.",
        last_col=12,
    )
    row = _note(
        ws,
        row,
        "La formación complementaria es un universo agregado: no aporta personas "
        "pendientes y queda fuera de la efectividad. «No calculable» significa que "
        "falta la meta o el dato de pendientes; nunca se reemplaza por cero.",
        last_col=9,
        kind="info",
        chars_per_line=105,
    )
    row += 1
    row = _section(ws, row, "Tabla de resultados", last_col=12, color=DARK_GREEN)
    headers = [
        "Categoría",
        "Universo",
        "Meta",
        "Certificados",
        "Pendientes",
        "Avance %",
        "Brecha",
        "Efectividad %",
        "Estado del cálculo",
    ]
    table_rows = []
    for item in metrics:
        estado = "Calculado"
        if item.get("meta") is None:
            estado = "No calculable: meta no disponible"
        elif item.get("pendientes") is None:
            estado = "No calculable: pendientes no disponibles"
        table_rows.append(
            [
                item.get("category_label") or item.get("category"),
                "Personas" if item.get("universo") == "personas" else "Complementaria",
                item.get("meta"),
                item.get("certificados"),
                item.get("pendientes"),
                item.get("avance"),
                item.get("brecha"),
                item.get("efectividad"),
                estado,
            ]
        )
    header_row = row
    last_row = _table(
        ws,
        row,
        headers,
        table_rows,
        widths=[28, 15, 12, 13, 12, 12, 12, 13, 34],
        number_formats={
            3: "#,##0",
            4: "#,##0",
            5: "#,##0",
            6: '0.0"%"',
            7: "#,##0",
            8: '0.0"%"',
        },
        blank_columns={3, 4, 5, 6, 7, 8},
        freeze=False,
    )
    # Resaltar la mayor brecha y las categorias que cumplen la meta.
    brechas = [
        (index, value)
        for index, value in enumerate(
            [item.get("brecha") for item in metrics], start=1
        )
        if isinstance(value, (int, float))
    ]
    if brechas:
        max_index, _ = max(brechas, key=lambda item: item[1])
        for col in range(1, 10):
            cell = ws.cell(row=header_row + max_index, column=col)
            cell.fill = _fill(AMBER_SOFT)
            cell.font = _font(9, bold=True, color=AMBER)
    for index, item in enumerate(metrics, start=1):
        avance = item.get("avance")
        if isinstance(avance, (int, float)) and avance >= 100:
            for col in range(1, 10):
                ws.cell(row=header_row + index, column=col).fill = _fill(GREEN_SOFT)
    row = last_row + 2
    row = _section(ws, row, "Lectura rápida", last_col=9, color=BLUE)
    total_meta = dataset.get("resumen_ejecutivo", {}).get("meta_total")
    total_cert = dataset.get("resumen_ejecutivo", {}).get("total_certificados")
    total_brecha = dataset.get("resumen_ejecutivo", {}).get("brecha_total")
    biggest = None
    if brechas:
        biggest = metrics[max_index - 1].get("category_label") if max_index else None
    lines = [
        f"Meta institucional total: {_num(total_meta)}.",
        f"Certificados del periodo (personas + complementaria): {_num(total_cert)}.",
        f"Brecha total: {_num(total_brecha)}.",
        f"Categoría con mayor brecha: {biggest or 'No calculable'}.",
    ]
    for line in lines:
        _merged(
            ws,
            row,
            1,
            row,
            9,
            line,
            fill=_fill(WHITE),
            font=_font(9, color="1F2937"),
            alignment=_align("left", "top"),
        )
        ws.row_dimensions[row].height = 18
        row += 1
    _bar_chart(
        ws,
        values_col=6,
        labels_col=1,
        header_row=header_row,
        last_row=last_row,
        title="Avance por categoría (%)",
        anchor="K12",
        horizontal=True,
        height=8.0,
        width=12.5,
        percent=True,
    )
    _clustered_chart(
        ws,
        header_row=header_row,
        last_row=last_row,
        first_value_col=3,
        last_value_col=4,
        labels_col=1,
        title="Meta frente a certificados",
        anchor="K24",
        height=8.5,
        width=12.5,
    )
    for col in range(1, 10):
        ws.column_dimensions[get_column_letter(col)].width = [28, 15, 12, 13, 12, 12, 12, 13, 34][col - 1]
    _print_setup(
        ws,
        last_col=22,
        last_row=46,
        header="Informe consolidado · Resultados por categoría",
    )


def _sheet_monthly(wb: Workbook, dataset: dict[str, Any]) -> None:
    ws = wb.create_sheet("Evolución mensual")
    monthly = dataset.get("certificados_por_mes") or {}
    months = monthly.get("meses") or []
    resumen = monthly.get("resumen") or {}
    row = 1
    row = _title(
        ws,
        row,
        "Evolución mensual de certificados",
        f"Certificados de personas por mes de certificación · {dataset.get('periodo') or 'No disponible'}",
        last_col=12,
    )
    row = _note(
        ws,
        row,
        "Serie descriptiva del consolidado. No se infieren causas ni relaciones "
        "causales a partir de los cambios entre meses.",
        last_col=9,
        kind="info",
        chars_per_line=105,
    )
    row += 1
    row = _section(ws, row, "Indicadores del periodo", last_col=12, color=DARK_GREEN)
    mayor = resumen.get("mes_mayor") or {}
    menor = resumen.get("mes_menor") or {}
    cards = [
        {
            "title": "Total del periodo",
            "value": _num(monthly.get("total")),
            "note": "Certificados de personas en Ene–Sep 2026",
            "accent": DARK_GREEN,
            "background": GREEN_SOFT,
        },
        {
            "title": "Mes con mayor cantidad",
            "value": mayor.get("mes") or "No calculable",
            "note": f"{_num(mayor.get('certificados'))} certificados",
            "accent": BLUE,
        },
        {
            "title": "Mes con menor cantidad",
            "value": menor.get("mes") or "No calculable",
            "note": f"{_num(menor.get('certificados'))} certificados",
            "accent": AMBER,
        },
        {
            "title": "Meses con certificados",
            "value": _num(resumen.get("meses_con_certificados")),
            "note": "Meses con al menos un certificado",
            "accent": TEAL,
        },
    ]
    row = _cards(ws, row, cards)
    row = _section(ws, row, "Serie mensual", last_col=9, color=BLUE)
    headers = ["Mes", "Certificados", "% del periodo", "Acumulado"]
    table_rows = [
        [
            item.get("etiqueta") or item.get("mes"),
            item.get("certificados"),
            item.get("porcentaje"),
            item.get("acumulado"),
        ]
        for item in months
    ]
    header_row = row
    last_row = _table(
        ws,
        row,
        headers,
        table_rows,
        widths=[18, 16, 16, 16],
        number_formats={2: "#,##0", 3: '0.0"%"', 4: "#,##0"},
        blank_columns={2, 3, 4},
        freeze=False,
    )
    row = last_row + 2
    row = _section(ws, row, "Observaciones descriptivas", last_col=9, color=BLUE)
    observations = []
    if mayor:
        tie = " (empate)" if len(mayor.get("empates") or []) > 1 else ""
        observations.append(
            f"El mes con mayor cantidad fue {mayor.get('mes')} con "
            f"{_num(mayor.get('certificados'))} certificados{tie}."
        )
    if menor:
        tie = " (empate)" if len(menor.get("empates") or []) > 1 else ""
        observations.append(
            f"El mes con menor cantidad fue {menor.get('mes')} con "
            f"{_num(menor.get('certificados'))} certificados{tie}."
        )
    observations.append(
        f"El total del periodo es {_num(monthly.get('total'))} certificados de personas."
    )
    observations.append(
        "La serie no permite afirmar por sí sola por qué cambió la certificación "
        "entre meses; se requiere cruzar con las causas y la gestión documental."
    )
    for line in observations:
        _merged(
            ws,
            row,
            1,
            row,
            9,
            line,
            fill=_fill(WHITE),
            font=_font(9, color="1F2937"),
            alignment=_align("left", "top"),
        )
        ws.row_dimensions[row].height = 20
        row += 1
    _bar_chart(
        ws,
        values_col=2,
        labels_col=1,
        header_row=header_row,
        last_row=last_row,
        title="Certificados por mes",
        anchor=f"A{row + 1}",
        horizontal=False,
        height=9.5,
        width=13.0,
        percent=False,
    )
    for col in range(1, 10):
        ws.column_dimensions[get_column_letter(col)].width = [18, 16, 16, 16, 4, 14, 14, 14, 14][col - 1]
    _print_setup(
        ws,
        last_col=14,
        last_row=row + 1,
        header="Informe consolidado · Evolución mensual",
    )


def _sheet_causes(wb: Workbook, dataset: dict[str, Any]) -> None:
    ws = wb.create_sheet("Análisis de pendientes")
    causes = dataset.get("causas_no_certificacion") or {}
    row = 1
    row = _title(
        ws,
        row,
        "Análisis de pendientes y causas",
        "Universo institucional · Hoja PENDIENTES del consolidado ACTAS 2026.",
        last_col=12,
    )
    row = _note(
        ws,
        row,
        "Las causas se cuentan sobre personas únicas del consolidado. Una persona "
        "puede registrar varias causas: la suma de las filas es el total de "
        "incidencias (asociaciones persona-causa) y puede superar a las personas "
        "pendientes. Los pendientes sin motivo se conservan y se muestran aparte.",
        last_col=9,
        kind="info",
        chars_per_line=105,
    )
    row = _section(ws, row, "Indicadores de pendientes", last_col=12, color=DARK_GREEN)
    cards = [
        {
            "title": "Personas pendientes únicas",
            "value": _num(causes.get("aprendices_pendientes_unicos")),
            "note": "Personas con estado Pendiente",
            "accent": AMBER,
            "background": AMBER_SOFT,
        },
        {
            "title": "Total incidencias",
            "value": _num(causes.get("total_incidencias")),
            "note": "Asociaciones persona-causa; una persona puede sumar varias",
            "accent": BLUE,
        },
        {
            "title": "Personas sin motivo informado",
            "value": _num(causes.get("aprendices_sin_motivo")),
            "note": "No se les asigna una causa artificial",
            "accent": AMBER,
            "background": AMBER_SOFT,
        },
        {
            "title": "% sin motivo",
            "value": _pct(causes.get("porcentaje_sin_motivo")),
            "note": "Sobre personas pendientes registradas en PENDIENTES",
            "accent": AMBER,
        },
    ]
    row = _cards(ws, row, cards)
    row = _section(ws, row, "Causas principales", last_col=9, color=BLUE)
    headers = ["Causa", "Personas asociadas", "% sobre pendientes", "% sobre incidencias"]
    table_rows = [
        [
            item.get("motivo"),
            item.get("personas"),
            item.get("porcentaje_personas"),
            item.get("porcentaje_incidencias"),
        ]
        for item in causes.get("motivos") or []
    ]
    header_row = row
    last_row = _table(
        ws,
        row,
        headers,
        table_rows,
        widths=[42, 18, 18, 18],
        number_formats={2: "#,##0", 3: '0.0"%"', 4: '0.0"%"'},
        blank_columns={2, 3, 4},
        freeze=False,
        auto_filter=False,
    )
    if table_rows:
        # Fila de calidad: no es una causa, es ausencia de motivo.
        quality_row = last_row + 1
        ws.cell(row=quality_row, column=1, value="Sin motivo informado")
        ws.cell(
            row=quality_row,
            column=2,
            value=causes.get("aprendices_sin_motivo")
            if causes.get("aprendices_sin_motivo") is not None
            else None,
        )
        ws.cell(
            row=quality_row,
            column=3,
            value=causes.get("porcentaje_sin_motivo")
            if causes.get("porcentaje_sin_motivo") is not None
            else None,
        )
        ws.cell(row=quality_row, column=4, value=None)
        for col in range(1, 5):
            cell = ws.cell(row=quality_row, column=col)
            cell.fill = _fill(AMBER_SOFT)
            cell.font = _font(9, bold=True, color=AMBER)
            cell.border = Border(bottom=THIN)
            cell.alignment = _align("left", "center")
        ws.cell(row=quality_row, column=2).number_format = "#,##0"
        ws.cell(row=quality_row, column=3).number_format = '0.0"%"'
        last_row = quality_row
    if table_rows:
        ws.auto_filter.ref = f"A{header_row}:D{last_row}"
    row = last_row + 1
    row = _note(
        ws,
        row,
        INCIDENCE_NOTE,
        last_col=9,
        kind="warning",
        chars_per_line=105,
    )
    if causes.get("total_incidencias") and causes.get("personas_pendientes_registradas") and (
        causes.get("total_incidencias") != causes.get("personas_pendientes_registradas")
    ):
        row = _note(
            ws,
            row,
            "Diferencia esperada: el total de incidencias puede ser mayor o menor "
            "que las personas pendientes registradas porque una persona puede tener "
            "varias causas y porque hay pendientes sin motivo.",
            last_col=9,
            kind="info",
            chars_per_line=105,
        )
    chart_last_row = header_row + len(table_rows) if table_rows else header_row
    if table_rows and causes.get("aprendices_sin_motivo") is not None:
        chart_last_row += 1
    _bar_chart(
        ws,
        values_col=2,
        labels_col=1,
        header_row=header_row,
        last_row=chart_last_row,
        title="Principales causas (personas asociadas)",
        anchor=f"A{row + 1}",
        horizontal=True,
        height=max(8.0, (chart_last_row - header_row + 1) * 0.55),
        width=18.0,
        percent=False,
    )
    for col in range(1, 10):
        ws.column_dimensions[get_column_letter(col)].width = [42, 18, 18, 18, 4, 14, 14, 14, 14][col - 1]
    _print_setup(
        ws,
        last_col=14,
        last_row=row + 1,
        header="Informe consolidado · Análisis de pendientes",
    )


def _sheet_acts(wb: Workbook, dataset: dict[str, Any]) -> None:
    ws = wb.create_sheet("Gestión documental")
    actas = dataset.get("actas") or {}
    items = actas.get("items") or []
    row = 1
    row = _title(
        ws,
        row,
        "Gestión documental y actas",
        "Actas del periodo, aprendices asociados y disponibilidad de metadatos.",
        last_col=12,
    )
    row = _note(
        ws,
        row,
        "La hoja CERTIFICADOS solo informa el número de acta. La fecha y el tipo se "
        "muestran únicamente cuando existen en el módulo de Actas; si faltan, se "
        "indica «No disponible». No se construyen fechas a partir del número de acta.",
        last_col=9,
        kind="info",
        chars_per_line=105,
    )
    row += 1
    row = _section(ws, row, "Indicadores documentales", last_col=12, color=DARK_GREEN)
    cards = [
        {
            "title": "Actas distintas",
            "value": _num(actas.get("total")),
            "note": "Actas con certificados en el periodo",
            "accent": BLUE,
        },
        {
            "title": "Certificados asociados",
            "value": _num(actas.get("certificados_asociados")),
            "note": "Personas únicas asociadas a actas",
            "accent": DARK_GREEN,
            "background": GREEN_SOFT,
        },
        {
            "title": "Actas con fecha y tipo",
            "value": _num(
                max(0, (actas.get("total") or 0) - (actas.get("sin_metadatos") or 0))
                if actas.get("total") is not None
                else None
            ),
            "note": "Metadatos completos en el módulo de Actas",
            "accent": TEAL,
        },
        {
            "title": "Actas sin metadatos",
            "value": _num(actas.get("sin_metadatos")),
            "note": "Se muestran como «No disponible»",
            "accent": AMBER,
            "background": AMBER_SOFT,
        },
    ]
    row = _cards(ws, row, cards)
    row = _section(ws, row, "Detalle de actas", last_col=9, color=BLUE)
    headers = ["Acta", "Aprendices asociados", "Fecha", "Tipo", "Metadatos", "Registro local", "Observación"]
    table_rows = []
    for item in items:
        has_date = bool(item.get("act_date"))
        has_type = bool(item.get("act_type"))
        if has_date and has_type:
            metadata = "Completos"
        elif has_date or has_type:
            metadata = "Parciales"
        else:
            metadata = "No disponibles"
        table_rows.append(
            [
                item.get("number") or "No disponible",
                item.get("aprendices_count"),
                item.get("act_date") or "No disponible",
                item.get("act_type") or "No disponible",
                metadata,
                "Sí" if item.get("act_id") is not None else "No",
                " · ".join(
                    part
                    for part in [
                        (
                            ""
                            if metadata == "Completos"
                            else "Fecha o tipo no disponibles en el módulo de Actas"
                        ),
                        (
                            "Identificador de acta inválido"
                            if item.get("identificador_invalido")
                            else ""
                        ),
                    ]
                    if part
                ),
            ]
        )
    header_row = row
    last_row = _table(
        ws,
        row,
        headers,
        table_rows,
        widths=[14, 18, 14, 18, 14, 14, 42],
        number_formats={2: "#,##0"},
        blank_columns={2},
        freeze=False,
    )
    row = last_row + 1
    row = _note(
        ws,
        row,
        "Las actas se conservan como vienen del consolidado. La disponibilidad de "
        "metadatos es informativa y no altera el conteo de certificados.",
        last_col=9,
        kind="info",
        chars_per_line=105,
    )
    _bar_chart(
        ws,
        values_col=2,
        labels_col=1,
        header_row=header_row,
        last_row=min(header_row + 10, last_row),
        title="Aprendices asociados por acta (top 10)",
        anchor=f"I{header_row}",
        horizontal=True,
        height=9.5,
        width=11.5,
        percent=False,
    )
    for col in range(1, 10):
        ws.column_dimensions[get_column_letter(col)].width = [14, 18, 14, 18, 14, 14, 42, 4, 14][col - 1]
    _print_setup(
        ws,
        last_col=16,
        last_row=row + 1,
        header="Informe consolidado · Gestión documental",
    )


def _sheet_learners(wb: Workbook, dataset: dict[str, Any], *, title: str | None = None) -> None:
    ws = wb.create_sheet("Anexo aprendices")
    local = dataset.get("universo_local") or {}
    filter_info = local.get("filtro") or {}
    row = 1
    row = _title(
        ws,
        row,
        title or "Anexo de aprendices · Universo local",
        (
            "Padrón local SQLite. No es el consolidado institucional y sus cifras no "
            "se suman a ACTAS 2026."
            + (
                f" · Vista filtrada: búsqueda «{filter_info.get('search') or ''}»"
                f" · estado «{filter_info.get('status') or 'Todos'}»"
                if filter_info.get("aplicado")
                else ""
            )
        ),
        last_col=8,
    )
    row = _note(
        ws,
        row,
        "Los registros sin estado se muestran como «Sin estado informado»; no se "
        "clasifican como certificados ni como pendientes. No se elimina ningún "
        "aprendiz para reducir el documento.",
        last_col=8,
        kind="warning",
        chars_per_line=95,
    )
    row = _section(ws, row, "Resumen del padrón local", last_col=8, color=DARK_GREEN)
    cards = [
        {
            "title": "Aprendices",
            "value": _num(local.get("total_aprendices")),
            "note": "Registros del padrón local",
            "accent": BLUE,
        },
        {
            "title": "Certificados",
            "value": _num(local.get("certificados")),
            "note": "Estado local normalizado",
            "accent": DARK_GREEN,
            "background": GREEN_SOFT,
        },
        {
            "title": "Pendientes",
            "value": _num(local.get("pendientes")),
            "note": "Estado local normalizado",
            "accent": AMBER,
            "background": AMBER_SOFT,
        },
        {
            "title": "Sin estado informado",
            "value": _num(local.get("sin_estado")),
            "note": "Alerta de calidad; no se imputa estado",
            "accent": RED,
            "background": RED_SOFT,
        },
    ]
    # En esta hoja usamos tarjetas de dos columnas para no exceder el ancho de la tabla.
    for index, item in enumerate(cards):
        card_row = row + (index // 2) * 4
        card_col = 1 + (index % 2) * 4
        _card(
            ws,
            card_row,
            card_col,
            title=item["title"],
            value=item["value"],
            note=item["note"],
            accent=item["accent"],
            background=item.get("background", WHITE),
            span=4,
        )
    row = row + ((len(cards) - 1) // 2 + 1) * 4 + 1
    row = _section(ws, row, "Listado de aprendices", last_col=8, color=BLUE)
    headers = ["Documento", "Nombre", "Programa", "Ficha", "Estado", "Acta", "Alerta de calidad"]
    learner_rows = local.get("learners_rows") or []
    table_rows = [
        [
            item.get("Documento"),
            item.get("Nombre"),
            item.get("Programa"),
            item.get("Ficha"),
            item.get("Estado"),
            item.get("Acta"),
            item.get("Alerta de calidad") or "",
        ]
        for item in learner_rows
    ]
    header_row = row
    last_row = _table(
        ws,
        row,
        headers,
        table_rows,
        widths=[18, 32, 32, 14, 20, 14, 26],
        freeze=False,
        highlight_status=5,
    )
    row = last_row + 1
    row = _note(
        ws,
        row,
        "Este anexo es la vista local del padrón. Para los indicadores institucionales "
        "use las hojas de resumen, categorías, evolución y pendientes.",
        last_col=8,
        kind="info",
        chars_per_line=95,
    )
    _print_setup(
        ws,
        last_col=8,
        last_row=row,
        title_rows=f"{header_row}:{header_row}",
        header="Anexo local · Aprendices",
    )


def _sheet_pending_local(wb: Workbook, dataset: dict[str, Any]) -> None:
    ws = wb.create_sheet("Anexo pendientes")
    local = dataset.get("universo_local") or {}
    filter_info = local.get("filtro") or {}
    row = 1
    row = _title(
        ws,
        row,
        "Anexo de pendientes · Universo local",
        (
            "Padrón local SQLite. No es el consolidado institucional."
            + (
                f" · Vista filtrada: búsqueda «{filter_info.get('search') or ''}»"
                f" · estado «{filter_info.get('status') or 'Todos'}»"
                if filter_info.get("aplicado")
                else ""
            )
        ),
        last_col=8,
    )
    row = _note(
        ws,
        row,
        "Los pendientes sin motivo se mantienen y se muestran como «Sin motivo "
        "informado». No se inventan causas. El análisis institucional de causas está "
        "en la hoja «Análisis de pendientes».",
        last_col=8,
        kind="warning",
        chars_per_line=95,
    )
    row += 1
    row = _section(ws, row, "Resumen de pendientes locales", last_col=8, color=DARK_GREEN)
    cards = [
        {
            "title": "Pendientes locales",
            "value": _num(local.get("pendientes")),
            "note": "Personas con estado local Pendiente",
            "accent": AMBER,
            "background": AMBER_SOFT,
        },
        {
            "title": "Sin motivo informado",
            "value": _num(local.get("pendientes_sin_motivo")),
            "note": "Se conservan sin causa asignada",
            "accent": AMBER,
        },
        {
            "title": "% sin motivo",
            "value": _pct(local.get("pendientes_sin_motivo_porcentaje")),
            "note": "Sobre pendientes locales",
            "accent": AMBER,
        },
        {
            "title": "Requisitos pendientes",
            "value": _num(local.get("requisitos_pendientes")),
            "note": "Requisitos locales registrados",
            "accent": BLUE,
        },
    ]
    row = _cards(ws, row, cards, span=2)
    row = _section(ws, row, "Detalle de pendientes locales", last_col=8, color=BLUE)
    headers = ["Documento", "Nombre", "Programa", "Ficha", "Motivo", "Estado", "Alerta de calidad"]
    pending_rows = local.get("pending_rows") or []
    table_rows = [
        [
            item.get("Documento"),
            item.get("Nombre"),
            item.get("Programa"),
            item.get("Ficha"),
            item.get("Motivo"),
            item.get("Estado"),
            item.get("Alerta de calidad") or "",
        ]
        for item in pending_rows
    ]
    header_row = row
    last_row = _table(
        ws,
        row,
        headers,
        table_rows,
        widths=[18, 32, 32, 14, 30, 14, 24],
        freeze=False,
        highlight_status=6,
    )
    row = last_row + 1
    row = _note(
        ws,
        row,
        INCIDENCE_NOTE_SHORT,
        last_col=8,
        kind="warning",
        chars_per_line=95,
    )
    _print_setup(
        ws,
        last_col=8,
        last_row=row,
        title_rows=f"{header_row}:{header_row}",
        header="Anexo local · Pendientes",
    )


def _write_bullets(ws, row: int, title: str, bullets: list[str], last_col: int = 10) -> int:
    row = _section(ws, row, title, last_col=last_col, color=BLUE)
    text = "\n".join(f"• {item}" for item in bullets) if bullets else "Sin registros."
    row = _note(ws, row, text, last_col=last_col, kind="info", chars_per_line=105)
    return row


def _sheet_traceability(wb: Workbook, dataset: dict[str, Any]) -> None:
    ws = wb.create_sheet("Anexo pendientes y trazabilidad")
    local = dataset.get("universo_local") or {}
    trace = dataset.get("trazabilidad") or {}
    row = 1
    row = _title(
        ws,
        row,
        "Anexo de pendientes y trazabilidad",
        "Detalle local de pendientes + fuentes, metodología, exclusiones y limitaciones del informe.",
        last_col=10,
    )
    row = _note(
        ws,
        row,
        "Este anexo reúne el detalle local y la trazabilidad metodológica. Las "
        "advertencias no se esconden en una hoja técnica separada: acompañan a los "
        "datos que las originan.",
        last_col=10,
        kind="warning",
        chars_per_line=110,
    )
    row += 1
    row = _section(ws, row, "Pendientes del padrón local", last_col=10, color=DARK_GREEN)
    headers = ["Documento", "Nombre", "Programa", "Ficha", "Motivo", "Estado", "Alerta de calidad"]
    pending_rows = local.get("pending_rows") or []
    table_rows = [
        [
            item.get("Documento"),
            item.get("Nombre"),
            item.get("Programa"),
            item.get("Ficha"),
            item.get("Motivo"),
            item.get("Estado"),
            item.get("Alerta de calidad") or "",
        ]
        for item in pending_rows
    ]
    header_row = row
    last_row = _table(
        ws,
        row,
        headers,
        table_rows,
        widths=[18, 32, 32, 14, 30, 14, 24],
        freeze=False,
        highlight_status=6,
    )
    row = last_row + 2
    row = _section(ws, row, "Trazabilidad y metodología", last_col=10, color=BLUE)
    row = _write_bullets(
        ws,
        row,
        "Universos de datos",
        [
            f"{item.get('nombre')}: {item.get('descripcion')} Uso: {item.get('uso')}"
            for item in trace.get("universos") or []
        ],
        last_col=10,
    )
    row = _write_bullets(
        ws,
        row,
        "Fuentes de información",
        [
            f"{item.get('nombre')}: {item.get('detalle')}"
            for item in trace.get("fuentes") or []
        ],
        last_col=10,
    )
    period = trace.get("periodo") or {}
    row = _write_bullets(
        ws,
        row,
        "Periodo analizado",
        [
            f"{period.get('etiqueta') or 'No disponible'} ({period.get('inicio') or '?'} a {period.get('fin') or '?'}).",
            period.get("criterio") or "",
        ],
        last_col=10,
    )
    row = _write_bullets(
        ws,
        row,
        "Reglas de deduplicación",
        trace.get("deduplicacion") or [],
        last_col=10,
    )
    row = _write_bullets(
        ws,
        row,
        "Criterios de clasificación",
        trace.get("clasificacion") or [],
        last_col=10,
    )
    row = _write_bullets(
        ws,
        row,
        "Exclusiones",
        trace.get("exclusiones") or [],
        last_col=10,
    )
    row = _section(ws, row, "Conciliación de certificados locales e institucionales", last_col=10)
    reconciliation = trace.get("conciliacion_certificados") or {}
    recon_rows = [
        ["Certificados locales (padrón)", _num(reconciliation.get("certificados_locales"))],
        ["Certificados institucionales (periodo)", _num(reconciliation.get("certificados_institucionales"))],
        ["Diferencia (local - institucional)", _num(reconciliation.get("diferencia"))],
        ["Certificados excluidos del periodo", _num(reconciliation.get("certificados_excluidos_periodo"))],
    ]
    last_recon = _table(
        ws,
        row,
        ["Concepto", "Valor"],
        recon_rows,
        widths=[52, 18],
        freeze=False,
        auto_filter=False,
    )
    row = last_recon + 1
    row = _note(
        ws,
        row,
        str(reconciliation.get("explicacion") or "Sin información de conciliación."),
        last_col=10,
        kind="info",
        chars_per_line=105,
    )
    comparison = trace.get("comparacion_causas") or []
    if comparison:
        row = _section(ws, row, "Comparación informativa de causas (universos distintos)", last_col=10)
        comparison_rows = [
            [
                item.get("Causa"),
                item.get("Personas institucional"),
                item.get("Personas local"),
                item.get("Diferencia (local - institucional)"),
            ]
            for item in comparison
        ]
        last_comparison = _table(
            ws,
            row,
            ["Causa", "Personas institucional", "Personas local", "Diferencia"],
            comparison_rows,
            widths=[42, 22, 22, 24],
            number_formats={2: "#,##0", 3: "#,##0", 4: "#,##0"},
            blank_columns={2, 3, 4},
            freeze=False,
            auto_filter=False,
        )
        row = last_comparison + 1
        row = _note(
            ws,
            row,
            str(trace.get("nota_causas") or ""),
            last_col=10,
            kind="warning",
            chars_per_line=105,
        )
    row = _note(
        ws,
        row,
        str(trace.get("nota_incidencias") or INCIDENCE_NOTE),
        last_col=10,
        kind="warning",
        chars_per_line=105,
    )
    row = _write_bullets(
        ws,
        row,
        "Limitaciones",
        trace.get("limitaciones") or [],
        last_col=10,
    )
    row = _write_bullets(
        ws,
        row,
        "Advertencias del cálculo",
        trace.get("advertencias") or ["Sin advertencias registradas."],
        last_col=10,
    )
    row = _note(
        ws,
        row,
        (trace.get("actas") or {}).get("nota") or "",
        last_col=10,
        kind="info",
        chars_per_line=105,
    )
    for col in range(1, 11):
        ws.column_dimensions[get_column_letter(col)].width = [22, 32, 32, 14, 30, 14, 24, 12, 12, 12][col - 1]
    _print_setup(
        ws,
        last_col=10,
        last_row=row,
        title_rows=f"{header_row}:{header_row}",
        header="Anexo local · Pendientes y trazabilidad",
    )


# ---------------------------------------------------------------------------
# API publica del modulo
# ---------------------------------------------------------------------------


def _new_workbook() -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)
    wb.properties.title = "Informe consolidado de certificación 2026"
    wb.properties.creator = "SENA Certificación"
    wb.properties.description = (
        "Informe administrativo generado desde el consolidado ACTAS 2026 y el padrón local."
    )
    return wb


def _save(wb: Workbook) -> bytes:
    output = BytesIO()
    wb.save(output)
    return output.getvalue()


def build_consolidated_xlsx(dataset: dict[str, Any], *, detail: str = "completo") -> bytes:
    wb = _new_workbook()
    _sheet_summary(wb, dataset)
    _sheet_categories(wb, dataset)
    _sheet_monthly(wb, dataset)
    _sheet_causes(wb, dataset)
    _sheet_acts(wb, dataset)
    if detail == "completo":
        _sheet_learners(wb, dataset)
        _sheet_traceability(wb, dataset)
    wb.active = 0
    return _save(wb)


def build_report_xlsx(
    dataset: dict[str, Any], report_type: str, *, detail: str = "completo"
) -> bytes:
    if report_type in {"consolidado", "general"}:
        return build_consolidated_xlsx(dataset, detail=detail)
    wb = _new_workbook()
    if report_type == "ejecutivo":
        _sheet_summary(wb, dataset)
    elif report_type == "causas":
        _sheet_causes(wb, dataset)
    elif report_type == "actas":
        _sheet_acts(wb, dataset)
    elif report_type == "aprendices":
        _sheet_learners(wb, dataset)
    elif report_type == "pendientes":
        _sheet_causes(wb, dataset)
        _sheet_pending_local(wb, dataset)
    else:
        raise ValueError(f"Tipo de informe no soportado: {report_type}.")
    wb.active = 0
    return _save(wb)

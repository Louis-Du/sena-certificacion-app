"""Generacion del informe PDF editorial 2026.

El PDF no calcula nada por su cuenta: recibe el dataset de
``report_data.consolidate_report_dataset`` y lo presenta con una composicion
pensada para lectura administrativa:

* portada institucional;
* resumen ejecutivo con tarjetas KPI;
* resultados por categoria, evolucion mensual, pendientes y actas;
* fuentes, metodologia, conciliacion, exclusiones y limitaciones;
* anexos locales solo cuando el nivel de detalle es ``completo``.

Los valores ``None`` se presentan como «No calculable». Nunca se convierten en
cero. Las tablas largas repiten el encabezado y el pie lleva paginacion.
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from io import BytesIO
from typing import Any, Callable
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Flowable,
    Frame,
    KeepTogether,
    LongTable,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.services.report_data import INCIDENCE_NOTE


# ---------------------------------------------------------------------------
# Geometria y paleta
# ---------------------------------------------------------------------------

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_X = 42
MARGIN_TOP = 64
MARGIN_BOTTOM = 52
CONTENT_WIDTH = PAGE_WIDTH - (MARGIN_X * 2)

INK = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#64748B")
LINE = colors.HexColor("#CBD5E1")
LINE_SOFT = colors.HexColor("#E2E8F0")
DARK_GREEN = colors.HexColor("#14532D")
GREEN = colors.HexColor("#15803D")
GREEN_SOFT = colors.HexColor("#DCFCE7")
GREEN_PALE = colors.HexColor("#F0FDF4")
BLUE = colors.HexColor("#1E3A5F")
BLUE_SOFT = colors.HexColor("#E2E8F0")
GRAY_SOFT = colors.HexColor("#F8FAFC")
AMBER = colors.HexColor("#B45309")
AMBER_SOFT = colors.HexColor("#FEF3C7")
RED = colors.HexColor("#B91C1C")
RED_SOFT = colors.HexColor("#FEE2E2")
WHITE = colors.white

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------

STYLE_BODY = ParagraphStyle(
    "body",
    fontName=FONT,
    fontSize=9,
    leading=13,
    textColor=INK,
    spaceAfter=3,
)
STYLE_SMALL = ParagraphStyle(
    "small",
    parent=STYLE_BODY,
    fontSize=7.8,
    leading=10.5,
    textColor=MUTED,
)
STYLE_TINY = ParagraphStyle(
    "tiny",
    parent=STYLE_BODY,
    fontSize=6.8,
    leading=9,
    textColor=MUTED,
)
STYLE_KICKER = ParagraphStyle(
    "kicker",
    fontName=FONT_BOLD,
    fontSize=7.4,
    leading=9,
    textColor=GREEN,
    charSpace=1.3,
    spaceAfter=3,
)
STYLE_H1 = ParagraphStyle(
    "h1",
    fontName=FONT_BOLD,
    fontSize=21,
    leading=25,
    textColor=DARK_GREEN,
    spaceAfter=2,
)
STYLE_H2 = ParagraphStyle(
    "h2",
    fontName=FONT_BOLD,
    fontSize=12,
    leading=15,
    textColor=BLUE,
    spaceBefore=8,
    spaceAfter=4,
)
STYLE_KPI_TITLE = ParagraphStyle(
    "kpi_title",
    fontName=FONT_BOLD,
    fontSize=6.4,
    leading=8,
    textColor=MUTED,
    charSpace=0.5,
)
STYLE_KPI_VALUE = ParagraphStyle(
    "kpi_value",
    fontName=FONT_BOLD,
    fontSize=17,
    leading=20,
    textColor=DARK_GREEN,
)
STYLE_KPI_NOTE = ParagraphStyle(
    "kpi_note",
    fontName=FONT,
    fontSize=6.7,
    leading=8.8,
    textColor=MUTED,
)
STYLE_TH = ParagraphStyle(
    "th",
    fontName=FONT_BOLD,
    fontSize=6.9,
    leading=8.4,
    textColor=WHITE,
)
STYLE_TD = ParagraphStyle(
    "td",
    fontName=FONT,
    fontSize=7.3,
    leading=9.2,
    textColor=INK,
)
STYLE_TD_NUM = ParagraphStyle(
    "td_num",
    parent=STYLE_TD,
    alignment=2,
)
STYLE_TD_MUTED = ParagraphStyle(
    "td_muted",
    parent=STYLE_TD,
    textColor=MUTED,
    fontName="Helvetica-Oblique",
)
STYLE_BULLET = ParagraphStyle(
    "bullet",
    parent=STYLE_BODY,
    fontSize=8,
    leading=11,
    leftIndent=14,
    bulletIndent=3,
    bulletFontName=FONT,
    bulletFontSize=7,
    spaceAfter=2,
)


# ---------------------------------------------------------------------------
# Utilidades de formato
# ---------------------------------------------------------------------------

def _num(value: Any) -> str:
    if value is None:
        return "No calculable"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return "No calculable"
        text = f"{value:,.0f}"
        return text.replace(",", ".")
    return str(value)


def _pct(value: Any) -> str:
    if value is None:
        return "No calculable"
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return f"{value:.1f}%".replace(".", ",")
    return str(value)


def _personas(value: Any) -> str:
    count = _num(value)
    if value == 1:
        return f"{count} persona"
    return f"{count} personas"


def _certificados(value: Any) -> str:
    count = _num(value)
    if value == 1:
        return f"{count} certificado"
    return f"{count} certificados"


def _text(value: Any, fallback: str = "No disponible") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback


def _truncate(text: Any, limit: int) -> str:
    value = _text(text, "")
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _bullet(text: str) -> Paragraph:
    return Paragraph(f"<bullet>•</bullet> {escape(str(text))}", STYLE_BULLET)


def _note(text: str, kind: str = "info") -> Table:
    palette = {
        "info": (GRAY_SOFT, BLUE, LINE),
        "warning": (AMBER_SOFT, AMBER, colors.HexColor("#F59E0B")),
        "alert": (RED_SOFT, RED, RED),
        "success": (GREEN_SOFT, DARK_GREEN, GREEN),
    }
    background, border, line_color = palette.get(kind, palette["info"])
    cell = Paragraph(escape(str(text)), STYLE_SMALL)
    table = Table([[cell]], colWidths=[CONTENT_WIDTH])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("LINEBEFORE", (0, 0), (0, -1), 2.6, border),
                ("BOX", (0, 0), (-1, -1), 0.35, line_color),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _section_header(number: str, title: str, subtitle: str | None = None) -> list[Flowable]:
    items: list[Flowable] = [
        Paragraph(f"SECCIÓN {number}", STYLE_KICKER),
        Paragraph(escape(title), STYLE_H1),
    ]
    if subtitle:
        items.append(Paragraph(escape(subtitle), STYLE_SMALL))
    items.append(Spacer(1, 7))
    return items


# ---------------------------------------------------------------------------
# Tarjetas KPI
# ---------------------------------------------------------------------------

def _kpi_card(item: dict[str, Any], width: float) -> Table:
    accent = item.get("accent") or GREEN
    background = item.get("background") or WHITE
    title = Paragraph(escape(_text(item.get("title"), "").upper()), STYLE_KPI_TITLE)
    value_style = ParagraphStyle(
        "kpi_value_custom",
        parent=STYLE_KPI_VALUE,
        textColor=accent,
    )
    value = Paragraph(escape(_text(item.get("value"), "No calculable")), value_style)
    note = Paragraph(escape(_text(item.get("note"), "")), STYLE_KPI_NOTE)
    body = Table(
        [[title], [value], [note]],
        colWidths=[max(20, width - 12)],
    )
    body.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (0, 0), 6),
                ("BOTTOMPADDING", (0, 2), (0, 2), 6),
                ("TOPPADDING", (0, 1), (0, 1), 1),
                ("BOTTOMPADDING", (0, 1), (0, 1), 1),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    card = Table([["", body]], colWidths=[3.6, width - 3.6])
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), accent),
                ("BACKGROUND", (1, 0), (1, 0), background),
                ("BOX", (0, 0), (-1, -1), 0.45, accent),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return card


def _kpi_grid(items: list[dict[str, Any]], per_row: int = 3) -> list[Flowable]:
    if not items:
        return []
    gap = 7
    card_width = (CONTENT_WIDTH - gap * (per_row - 1)) / per_row
    flowables: list[Flowable] = []
    for start in range(0, len(items), per_row):
        chunk = items[start : start + per_row]
        cells: list[Any] = []
        widths: list[float] = []
        for index, item in enumerate(chunk):
            if index:
                cells.append("")
                widths.append(gap)
            cells.append(_kpi_card(item, card_width))
            widths.append(card_width)
        while len(cells) < (per_row * 2 - 1):
            cells.extend(["", ""])
            widths.extend([gap, card_width])
        row = Table([cells], colWidths=widths)
        row.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        flowables.append(row)
        flowables.append(Spacer(1, gap))
    return flowables


# ---------------------------------------------------------------------------
# Tablas
# ---------------------------------------------------------------------------

def _cell(value: Any, formatter: Callable[[Any], str] | None) -> Paragraph:
    if formatter is not None:
        text = formatter(value)
        style = STYLE_TD_NUM if formatter in {_num, _pct} else STYLE_TD
        return Paragraph(escape(text), style if text != "No calculable" else STYLE_TD_MUTED)
    if value is None:
        return Paragraph("No disponible", STYLE_TD_MUTED)
    return Paragraph(escape(str(value)), STYLE_TD)


def _data_table(
    headers: list[str],
    rows: list[list[Any]],
    widths: list[float],
    *,
    formats: dict[int, Callable[[Any], str]] | None = None,
    total_row: list[Any] | None = None,
    total_formats: dict[int, Callable[[Any], str]] | None = None,
    font_note: str | None = None,
) -> Any:
    formats = formats or {}
    scale = CONTENT_WIDTH / float(sum(widths))
    col_widths = [width * scale for width in widths]
    data: list[list[Any]] = [
        [Paragraph(escape(header), STYLE_TH) for header in headers]
    ]
    for row in rows:
        data.append(
            [
                _cell(value, formats.get(index))
                for index, value in enumerate(row)
            ]
        )
    if total_row is not None:
        total_formats = total_formats or formats
        data.append(
            [
                _cell(value, total_formats.get(index))
                for index, value in enumerate(total_row)
            ]
        )
    table = LongTable(
        data,
        colWidths=col_widths,
        repeatRows=1,
        hAlign="LEFT",
    )
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, LINE_SOFT),
    ]
    for index in range(1, len(data)):
        if index % 2 == 0:
            style.append(("BACKGROUND", (0, index), (-1, index), GRAY_SOFT))
    if total_row is not None:
        last = len(data) - 1
        style.extend(
            [
                ("BACKGROUND", (0, last), (-1, last), GREEN_SOFT),
                ("LINEABOVE", (0, last), (-1, last), 0.9, DARK_GREEN),
                ("FONTNAME", (0, last), (-1, last), FONT_BOLD),
            ]
        )
    table.setStyle(TableStyle(style))
    if font_note:
        return [table, Spacer(1, 3), Paragraph(escape(font_note), STYLE_TINY)]
    return table


# ---------------------------------------------------------------------------
# Graficos vectoriales
# ---------------------------------------------------------------------------

def _nice_max(values: list[float], minimum: float = 1) -> float:
    candidates = [value for value in values if isinstance(value, (int, float))]
    top = max(candidates) if candidates else 0
    if top <= 0:
        return minimum
    magnitude = 10 ** int(math.floor(math.log10(top)))
    for step in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        candidate = magnitude * step
        if candidate >= top * 1.08:
            return candidate
    return top * 1.1


def _nice_step(top: float, target: int = 5) -> float:
    if top <= 0:
        return 1
    raw = top / max(1, target)
    magnitude = 10 ** int(math.floor(math.log10(raw)))
    for step in (1, 2, 2.5, 5, 10):
        candidate = magnitude * step
        if candidate >= raw:
            return max(1, candidate)
    return max(1, top / target)


def _bar_drawing(
    items: list[tuple[Any, Any]],
    *,
    horizontal: bool = True,
    color: colors.Color = GREEN,
    percent: bool = False,
    height: float | None = None,
    label_limit: int = 34,
) -> Drawing:
    # ``items`` es una lista de pares (etiqueta, valor) que SIEMPRE se
    # desempaqueta junta. De este modo es imposible perder la correspondencia
    # entre una categoria y su cantidad, incluso al ordenar o invertir.
    labels = [str(pair[0]) for pair in items]
    values = [pair[1] for pair in items]
    count = max(1, len(labels))
    if height is None:
        height = max(130, count * 20 + 34) if horizontal else 190
    drawing = Drawing(CONTENT_WIDTH, height)
    if horizontal:
        # En HorizontalBarChart el primer dato se dibuja abajo; se invierte
        # conjuntamente para que la categoria con mayor valor quede arriba,
        # manteniendo siempre la correspondencia etiqueta-valor.
        labels = list(reversed(labels))
        values = list(reversed(values))
        chart = HorizontalBarChart()
        chart.x = 98
        chart.y = 8
        chart.width = CONTENT_WIDTH - 112
        chart.height = height - 22
        chart.data = [values]
        chart.categoryAxis.categoryNames = [_truncate(label, label_limit) for label in labels]
        chart.categoryAxis.labels.fontName = FONT
        chart.categoryAxis.labels.fontSize = 7
        chart.categoryAxis.labels.dx = -3
        chart.valueAxis.valueMin = 0
        axis_max = 100 if percent else _nice_max(values)
        chart.valueAxis.valueMax = axis_max
        chart.valueAxis.valueStep = 20 if percent else _nice_step(axis_max)
        chart.valueAxis.labelTextFormat = "%d"
        chart.valueAxis.labels.fontName = FONT
        chart.valueAxis.labels.fontSize = 6.6
        chart.bars[0].fillColor = color
        chart.bars[0].strokeColor = color
        chart.useAbsolute = 1
        chart.barWidth = min(13, max(8, (chart.height - 18) / max(1, count) - 4))
        chart.barLabelFormat = "%d"
        chart.barLabelArray = None
        chart.barLabels.fontName = FONT_BOLD
        chart.barLabels.fontSize = 7
        chart.barLabels.fillColor = INK
    else:
        chart = VerticalBarChart()
        chart.x = 34
        chart.y = 26
        chart.width = CONTENT_WIDTH - 52
        chart.height = height - 44
        chart.data = [values]
        chart.categoryAxis.categoryNames = [_truncate(label, 12) for label in labels]
        chart.categoryAxis.labels.fontName = FONT
        chart.categoryAxis.labels.fontSize = 6.8
        chart.categoryAxis.labels.dy = -4
        chart.valueAxis.valueMin = 0
        axis_max = _nice_max(values)
        chart.valueAxis.valueMax = axis_max
        chart.valueAxis.valueStep = _nice_step(axis_max)
        chart.valueAxis.labelTextFormat = "%d"
        chart.valueAxis.labels.fontName = FONT
        chart.valueAxis.labels.fontSize = 6.6
        chart.bars[0].fillColor = color
        chart.bars[0].strokeColor = color
        chart.barWidth = min(26, max(12, chart.width / max(1, count) * 0.55))
        chart.barLabels.fontName = FONT_BOLD
        chart.barLabels.fontSize = 7
        chart.barLabels.dy = 3
        chart.barLabelFormat = '%d'
        chart.barLabelArray = None
        chart.barLabels.fillColor = INK
    chart.valueAxis.strokeColor = LINE
    chart.categoryAxis.strokeColor = LINE
    drawing.add(chart)
    return drawing


# ---------------------------------------------------------------------------
# Documento y plantillas de pagina
# ---------------------------------------------------------------------------

class SectionMarker(Flowable):
    """Cambia el rotulo de seccion antes de la pagina siguiente."""

    def __init__(self, doc: "ReportDocTemplate", title: str):
        super().__init__()
        self.doc = doc
        self.title = title

    def wrap(self, available_width: float, available_height: float) -> tuple[float, float]:
        return 0, 0

    def draw(self) -> None:
        self.doc.current_section = self.title


class NumberedCanvas(pdfcanvas.Canvas):
    """Canvas que agrega «Página X de Y» al pie de cada pagina."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:  # noqa: N802 - API de ReportLab
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)

    def _draw_footer(self, total: int) -> None:
        if self._pageNumber <= 1:
            return
        self.saveState()
        self.setStrokeColor(LINE)
        self.setLineWidth(0.4)
        self.line(MARGIN_X, 38, PAGE_WIDTH - MARGIN_X, 38)
        self.setFont(FONT, 6.8)
        self.setFillColor(MUTED)
        self.drawString(
            MARGIN_X,
            28,
            "SENA Certificación · Documento administrativo · Informe 2026",
        )
        self.drawRightString(
            PAGE_WIDTH - MARGIN_X,
            28,
            f"Página {self._pageNumber} de {total}",
        )
        self.restoreState()


class ReportDocTemplate(BaseDocTemplate):
    def __init__(self, buffer: BytesIO, *, metadata: dict[str, Any]):
        super().__init__(
            buffer,
            pagesize=A4,
            leftMargin=MARGIN_X,
            rightMargin=MARGIN_X,
            topMargin=MARGIN_TOP,
            bottomMargin=MARGIN_BOTTOM,
            title=metadata.get("title") or "Informe de certificación 2026",
            author="SENA Certificación",
            subject=metadata.get("subject") or "Informe administrativo 2026",
            creator="SENA Certificación · módulo de informes",
        )
        self.metadata = metadata
        self.current_section = "Resumen ejecutivo"
        cover_frame = Frame(
            0,
            0,
            PAGE_WIDTH,
            PAGE_HEIGHT,
            id="cover",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        body_frame = Frame(
            MARGIN_X,
            MARGIN_BOTTOM,
            CONTENT_WIDTH,
            PAGE_HEIGHT - MARGIN_TOP - MARGIN_BOTTOM,
            id="body",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        )
        self.addPageTemplates(
            [
                PageTemplate(id="Cover", frames=[cover_frame], onPage=self._draw_cover),
                PageTemplate(id="Body", frames=[body_frame], onPage=self._draw_header),
            ]
        )

    def _draw_cover(self, canv: pdfcanvas.Canvas, doc: "ReportDocTemplate") -> None:
        meta = self.metadata
        canv.saveState()
        canv.setFillColor(DARK_GREEN)
        canv.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
        canv.setFillColor(GREEN)
        canv.rect(0, PAGE_HEIGHT - 7, PAGE_WIDTH, 7, fill=1, stroke=0)
        canv.setFillColor(colors.HexColor("#166534"))
        canv.rect(0, 0, 11, PAGE_HEIGHT, fill=1, stroke=0)

        # Marca y encabezado
        canv.setFillColor(colors.HexColor("#BBF7D0"))
        canv.setFont(FONT_BOLD, 8.5)
        canv.drawString(MARGIN_X, PAGE_HEIGHT - 72, "SENA · CERTIFICACIÓN 2026")
        canv.setStrokeColor(colors.HexColor("#22C55E"))
        canv.setLineWidth(0.8)
        canv.line(MARGIN_X, PAGE_HEIGHT - 86, PAGE_WIDTH - MARGIN_X, PAGE_HEIGHT - 86)

        # Titulo con ajuste de linea
        title = _text(meta.get("title"), "Informe de certificación 2026")
        title_size = 30 if len(title) < 46 else 25
        lines: list[str] = []
        current = ""
        for word in title.split():
            probe = f"{current} {word}".strip()
            if stringWidth(probe, FONT_BOLD, title_size) <= CONTENT_WIDTH - 24:
                current = probe
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        y = PAGE_HEIGHT - 142
        canv.setFillColor(WHITE)
        canv.setFont(FONT_BOLD, title_size)
        for line in lines[:4]:
            canv.drawString(MARGIN_X, y, line)
            y -= title_size * 1.12

        # Subtitulo
        y -= 8
        subtitle = _text(meta.get("subtitle"), "Periodo enero – septiembre de 2026")
        canv.setFillColor(colors.HexColor("#D1FAE5"))
        canv.setFont(FONT, 11.5)
        for line in _wrap_text(subtitle, FONT, 11.5, CONTENT_WIDTH - 70)[:4]:
            canv.drawString(MARGIN_X, y, line)
            y -= 16

        # Universo destacado
        y -= 10
        badge_text = _text(meta.get("universe_label"), "Universo institucional")
        badge_width = stringWidth(badge_text, FONT_BOLD, 7.5) + 20
        canv.setFillColor(colors.HexColor("#166534"))
        canv.roundRect(MARGIN_X, y - 5, badge_width, 18, 8, fill=1, stroke=0)
        canv.setFillColor(colors.HexColor("#DCFCE7"))
        canv.setFont(FONT_BOLD, 7.5)
        canv.drawString(MARGIN_X + 10, y, badge_text.upper())

        # Ficha de metadatos en la parte inferior
        box_top = 205
        canv.setFillColor(colors.HexColor("#0B3D20"))
        canv.roundRect(MARGIN_X, 56, CONTENT_WIDTH, box_top - 56, 6, fill=1, stroke=0)
        canv.setFillColor(colors.HexColor("#86EFAC"))
        canv.setFont(FONT_BOLD, 7)
        canv.drawString(MARGIN_X + 16, box_top - 22, "FICHA DEL DOCUMENTO")

        entries = [
            ("Periodo", _text(meta.get("period"), "Enero – Septiembre 2026")),
            ("Fuente", _text(meta.get("source"), "Consolidado ACTAS 2026")),
            ("Corte", _text(meta.get("generated"), "No disponible")),
            ("Documento", _text(meta.get("code"), "Informe administrativo")),
        ]
        column_width = (CONTENT_WIDTH - 32) / 2
        for index, (label, value) in enumerate(entries):
            col = index % 2
            row = index // 2
            x = MARGIN_X + 16 + col * column_width
            y_text = box_top - 48 - row * 34
            canv.setFillColor(colors.HexColor("#86EFAC"))
            canv.setFont(FONT_BOLD, 6.3)
            canv.drawString(x, y_text, label.upper())
            canv.setFillColor(WHITE)
            canv.setFont(FONT, 8.4)
            canv.drawString(x, y_text - 12, _truncate(value, 46))

        # Sello inferior
        canv.setFillColor(colors.HexColor("#D1FAE5"))
        canv.setFont(FONT, 7.2)
        canv.drawString(
            MARGIN_X,
            30,
            "Documento generado desde el módulo de informes · No modifica la base de datos.",
        )
        # Marca de agua discreta: no se superpone con la ficha del documento.
        canv.setFillColor(colors.HexColor("#166534"))
        canv.setFont(FONT_BOLD, 96)
        canv.drawRightString(PAGE_WIDTH - 30, 232, "2026")
        canv.restoreState()

    def _draw_header(self, canv: pdfcanvas.Canvas, doc: "ReportDocTemplate") -> None:
        if doc.page <= 1:
            return
        canv.saveState()
        canv.setStrokeColor(LINE)
        canv.setLineWidth(0.4)
        canv.line(MARGIN_X, PAGE_HEIGHT - 52, PAGE_WIDTH - MARGIN_X, PAGE_HEIGHT - 52)
        canv.setFont(FONT_BOLD, 6.8)
        canv.setFillColor(MUTED)
        canv.drawString(MARGIN_X, PAGE_HEIGHT - 45, "SENA CERTIFICACIÓN · INFORME ADMINISTRATIVO 2026")
        canv.drawRightString(
            PAGE_WIDTH - MARGIN_X,
            PAGE_HEIGHT - 45,
            _truncate(self.current_section.upper(), 52),
        )
        canv.restoreState()


def _wrap_text(text: str, font: str, size: float, width: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        probe = f"{current} {word}".strip()
        if stringWidth(probe, font, size) <= width:
            current = probe
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ---------------------------------------------------------------------------
# Secciones
# ---------------------------------------------------------------------------

def _summary_section(dataset: dict[str, Any], number: str) -> list[Flowable]:
    summary = dataset.get("resumen_ejecutivo") or {}
    trace = dataset.get("trazabilidad") or {}
    flowables: list[Flowable] = _section_header(
        number,
        "Resumen ejecutivo",
        "Indicadores principales del universo institucional del periodo.",
    )
    cards = [
        {
            "title": "Meta institucional",
            "value": _num(summary.get("meta_total")),
            "note": "Aprendices proyectados por la meta anual.",
            "accent": BLUE,
        },
        {
            "title": "Certificados personas",
            "value": _num(summary.get("certificados_personas")),
            "note": "Personas únicas certificadas en el periodo.",
            "accent": DARK_GREEN,
            "background": GREEN_SOFT,
        },
        {
            "title": "Pendientes personas",
            "value": _num(summary.get("pendientes_personas")),
            "note": "Personas únicas pendientes; no incluye complementaria.",
            "accent": AMBER,
            "background": AMBER_SOFT,
        },
        {
            "title": "Avance global",
            "value": _pct(summary.get("avance_global")),
            "note": "Certificados (personas + complementaria) frente a la meta.",
            "accent": GREEN,
        },
        {
            "title": "Efectividad de personas",
            "value": _pct(summary.get("efectividad_global")),
            "note": "Certificadas / (certificadas + pendientes).",
            "accent": DARK_GREEN,
        },
        {
            "title": "Brecha",
            "value": _num(summary.get("brecha_total")),
            "note": "Meta menos certificados; 0 si la meta está cumplida.",
            "accent": AMBER,
        },
        {
            "title": "Complementaria",
            "value": _num(summary.get("certificados_complementaria")),
            "note": "Certificados agregados; no son personas.",
            "accent": colors.HexColor("#0F766E"),
        },
        {
            "title": "Alertas de calidad",
            "value": _num(summary.get("alertas_total")),
            "note": f"{summary.get('alertas_alta', 0)} de severidad alta.",
            "accent": RED if summary.get("alertas_alta") else GREEN,
            "background": RED_SOFT if summary.get("alertas_alta") else WHITE,
        },
        {
            "title": "Pendientes sin motivo",
            "value": _pct(summary.get("porcentaje_sin_motivo")),
            "note": f"{_personas(summary.get('aprendices_sin_motivo'))} sin causa informada.",
            "accent": AMBER,
            "background": AMBER_SOFT,
        },
    ]
    flowables.extend(_kpi_grid(cards))
    flowables.append(Spacer(1, 5))

    quality_alerts = (dataset.get("calidad") or {}).get("alertas") or []
    if quality_alerts:
        flowables.append(Paragraph("Alertas de calidad", STYLE_H2))
        flowables.append(
            _data_table(
                ["Severidad", "Alerta", "Universo", "Cantidad", "%"],
                [
                    [
                        item.get("severidad"),
                        item.get("titulo"),
                        item.get("universo"),
                        item.get("cantidad"),
                        item.get("porcentaje"),
                    ]
                    for item in quality_alerts
                ],
                widths=[70, 230, 120, 70, 60],
                formats={3: _num, 4: _pct},
            )
        )
        flowables.append(Spacer(1, 5))

    # Evolucion compacta de la meta
    flowables.append(Paragraph("Lectura de la meta", STYLE_H2))
    meta = summary.get("meta_total")
    certificados = summary.get("total_certificados")
    brecha = summary.get("brecha_total")
    if isinstance(meta, (int, float)) and isinstance(certificados, (int, float)):
        flowables.append(
            _data_table(
                ["Concepto", "Valor"],
                [
                    ["Meta institucional", meta],
                    [
                        "Certificados (personas + complementaria)",
                        certificados,
                    ],
                    ["Brecha", brecha],
                ],
                widths=[330, 90],
                formats={1: _num},
            )
        )
    else:
        flowables.append(
            _note(
                "No se puede leer el cumplimiento porque falta la meta o el total "
                "de certificados. El valor no se reemplaza por cero.",
                "warning",
            )
        )

    # Conciliacion de universos
    reconciliation = trace.get("conciliacion_certificados") or {}
    flowables.append(Spacer(1, 9))
    flowables.append(Paragraph("Conciliación de universos", STYLE_H2))
    flowables.append(
        _data_table(
            ["Concepto", "Valor"],
            [
                ["Certificados locales (padrón)", reconciliation.get("certificados_locales")],
                [
                    "Certificados institucionales (periodo)",
                    reconciliation.get("certificados_institucionales"),
                ],
                ["Diferencia (local − institucional)", reconciliation.get("diferencia")],
                [
                    "Certificados excluidos del periodo",
                    reconciliation.get("certificados_excluidos_periodo"),
                ],
            ],
            widths=[330, 90],
            formats={1: _num},
        )
    )
    flowables.append(Spacer(1, 4))
    flowables.append(_note(str(reconciliation.get("explicacion") or ""), "info"))
    flowables.append(Spacer(1, 5))
    flowables.append(
        _note(
            "El universo local y el institucional no se suman ni se presentan como "
            "comparables. Cada uno conserva su propia fuente y su propio alcance.",
            "warning",
        )
    )
    return flowables


def _categories_section(dataset: dict[str, Any], number: str) -> list[Flowable]:
    metrics = dataset.get("desglose_por_categoria") or []
    flowables: list[Flowable] = _section_header(
        number,
        "Resultados por categoría",
        "Metas, certificados, pendientes, avance, brecha y efectividad.",
    )
    rows = []
    labels = []
    chart_labels = []
    avances = []
    for item in metrics:
        rows.append(
            [
                item.get("category_label") or item.get("category") or "Sin categoría",
                "Personas" if item.get("universo") == "personas" else "Complementaria",
                item.get("meta"),
                item.get("certificados"),
                item.get("pendientes"),
                item.get("avance"),
                item.get("brecha"),
                item.get("efectividad"),
            ]
        )
        label = item.get("category_label") or item.get("category") or "Sin categoría"
        labels.append(label)
        chart_labels.append(
            _truncate(re.sub(r"\s*\(.*?\)", "", str(label)).strip(), 28)
        )
        avances.append(
            float(item.get("avance"))
            if isinstance(item.get("avance"), (int, float))
            else 0.0
        )
    if rows:
        flowables.append(
            _data_table(
                [
                    "Categoría",
                    "Universo",
                    "Meta",
                    "Certificados",
                    "Pendientes",
                    "Avance",
                    "Brecha",
                    "Efectividad",
                ],
                rows,
                widths=[120, 62, 48, 58, 55, 48, 48, 56],
                formats={
                    2: _num,
                    3: _num,
                    4: _num,
                    5: _pct,
                    6: _num,
                    7: _pct,
                },
            )
        )
        flowables.append(Spacer(1, 8))
        flowables.append(Paragraph("Avance por categoría", STYLE_H2))
        flowables.append(
            _bar_drawing(
                list(zip(chart_labels, avances)),
                horizontal=True,
                color=GREEN,
                percent=True,
                height=max(140, len(chart_labels) * 22 + 30),
            )
        )
    else:
        flowables.append(_note("No hay categorías disponibles en el lote vigente.", "warning"))
    flowables.append(Spacer(1, 5))
    flowables.append(
        _note(
            "La formación complementaria se informa separada: son certificados "
            "agregados, no personas, y no se usan como denominador de efectividad. "
            "«No calculable» indica que falta la meta o el dato de pendientes.",
            "info",
        )
    )
    return flowables


def _monthly_section(dataset: dict[str, Any], number: str) -> list[Flowable]:
    monthly = dataset.get("certificados_por_mes") or {}
    months = monthly.get("meses") or []
    resumen = monthly.get("resumen") or {}
    mayor = resumen.get("mes_mayor") or {}
    menor = resumen.get("mes_menor") or {}
    flowables: list[Flowable] = _section_header(
        number,
        "Evolución mensual",
        "Certificados de personas por mes de certificación del periodo.",
    )
    cards = [
        {
            "title": "Total del periodo",
            "value": _num(monthly.get("total")),
            "note": "Personas certificadas en enero–septiembre de 2026.",
            "accent": DARK_GREEN,
            "background": GREEN_SOFT,
        },
        {
            "title": "Mes con mayor cantidad",
            "value": _text(mayor.get("mes"), "No calculable"),
            "note": f"{_certificados(mayor.get('certificados'))}.",
            "accent": BLUE,
        },
        {
            "title": "Mes con menor cantidad",
            "value": _text(menor.get("mes"), "No calculable"),
            "note": f"{_certificados(menor.get('certificados'))}.",
            "accent": AMBER,
        },
    ]
    flowables.extend(_kpi_grid(cards))
    flowables.append(Spacer(1, 4))
    if months:
        flowables.append(
            _bar_drawing(
                [
                    (
                        item.get("etiqueta") or item.get("mes") or "",
                        float(item.get("certificados"))
                        if isinstance(item.get("certificados"), (int, float))
                        else 0.0,
                    )
                    for item in months
                ],
                horizontal=False,
                color=colors.HexColor("#0F766E"),
                height=210,
            )
        )
        flowables.append(Spacer(1, 7))
        flowables.append(
            _data_table(
                ["Mes", "Certificados", "% del periodo", "Acumulado"],
                [
                    [
                        item.get("etiqueta") or item.get("mes"),
                        item.get("certificados"),
                        item.get("porcentaje"),
                        item.get("acumulado"),
                    ]
                    for item in months
                ],
                widths=[150, 100, 100, 100],
                formats={1: _num, 2: _pct, 3: _num},
                total_row=[
                    "Total",
                    monthly.get("total"),
                    100.0 if monthly.get("total") is not None else None,
                    monthly.get("total"),
                ],
            )
        )
        flowables.append(Spacer(1, 5))
        flowables.append(
            _note(
                "Serie descriptiva: no se infieren causas ni relaciones causales a "
                "partir de los cambios entre meses. Los certificados fuera del "
                "periodo no se cuentan y se informan en la trazabilidad.",
                "info",
            )
        )
    else:
        flowables.append(_note("No hay certificados del periodo para graficar.", "warning"))
    return flowables


def _causes_section(dataset: dict[str, Any], number: str) -> list[Flowable]:
    causes = dataset.get("causas_no_certificacion") or {}
    motivos = causes.get("motivos") or []
    flowables: list[Flowable] = _section_header(
        number,
        "Análisis de pendientes",
        "Causas de no certificación del universo institucional (hoja PENDIENTES).",
    )
    cards = [
        {
            "title": "Personas pendientes únicas",
            "value": _num(causes.get("aprendices_pendientes_unicos")),
            "note": "Personas con estado Pendiente",
            "accent": AMBER,
            "background": AMBER_SOFT,
        },
        {
            "title": "Total de incidencias",
            "value": _num(causes.get("total_incidencias")),
            "note": "Asociaciones persona-causa; una persona puede sumar varias.",
            "accent": BLUE,
        },
        {
            "title": "Personas sin motivo",
            "value": _num(causes.get("aprendices_sin_motivo")),
            "note": f"{_pct(causes.get('porcentaje_sin_motivo'))} de las personas registradas.",
            "accent": AMBER,
            "background": AMBER_SOFT,
        },
    ]
    flowables.extend(_kpi_grid(cards))
    flowables.append(Spacer(1, 5))
    if motivos:
        flowables.append(
            _data_table(
                [
                    "Causa",
                    "Personas asociadas",
                    "% sobre pendientes",
                    "% sobre incidencias",
                ],
                [
                    [
                        item.get("motivo"),
                        item.get("personas"),
                        item.get("porcentaje_personas"),
                        item.get("porcentaje_incidencias"),
                    ]
                    for item in motivos
                ],
                widths=[250, 90, 90, 90],
                formats={1: _num, 2: _pct, 3: _pct},
            )
        )
        flowables.append(Spacer(1, 8))
        flowables.append(Paragraph("Principales causas", STYLE_H2))
        chart_items = [
            (
                item.get("motivo") or "",
                float(item.get("personas"))
                if isinstance(item.get("personas"), (int, float))
                else 0.0,
            )
            for item in motivos
        ]
        if causes.get("aprendices_sin_motivo") not in (None, 0):
            chart_items.append(
                (
                    "Sin motivo informado",
                    float(causes.get("aprendices_sin_motivo")),
                )
            )
        flowables.append(
            _bar_drawing(
                chart_items,
                horizontal=True,
                color=AMBER,
                height=max(150, len(chart_items) * 23 + 34),
                label_limit=38,
            )
        )
        flowables.append(Spacer(1, 6))
    else:
        flowables.append(_note("No hay causas informadas en el lote vigente.", "warning"))
    flowables.append(
        _note(
            INCIDENCE_NOTE,
            "warning",
        )
    )
    if causes.get("aprendices_sin_motivo") not in (None, 0):
        sin_motivo = causes.get("aprendices_sin_motivo")
        verbo = "no trae" if sin_motivo == 1 else "no traen"
        flowables.append(Spacer(1, 5))
        flowables.append(
            _note(
                f"{_personas(sin_motivo)} "
                f"({_pct(causes.get('porcentaje_sin_motivo'))}) {verbo} motivo de "
                "no certificación. Se conservan como «Sin motivo informado» y no se "
                "les asigna una causa artificial.",
                "warning",
            )
        )
    return flowables


def _acts_section(dataset: dict[str, Any], number: str) -> list[Flowable]:
    actas = dataset.get("actas") or {}
    items = actas.get("items") or []
    flowables: list[Flowable] = _section_header(
        number,
        "Gestión documental y actas",
        "Actas del periodo, aprendices asociados y disponibilidad de metadatos.",
    )
    cards = [
        {
            "title": "Actas distintas",
            "value": _num(actas.get("total")),
            "note": "Actas con certificados en el periodo.",
            "accent": BLUE,
        },
        {
            "title": "Certificados asociados",
            "value": _num(actas.get("certificados_asociados")),
            "note": "Personas únicas asociadas a actas.",
            "accent": DARK_GREEN,
            "background": GREEN_SOFT,
        },
        {
            "title": "Actas sin metadatos",
            "value": _num(actas.get("sin_metadatos")),
            "note": "Fecha o tipo no disponibles en el módulo de Actas.",
            "accent": AMBER,
            "background": AMBER_SOFT,
        },
    ]
    flowables.extend(_kpi_grid(cards))
    flowables.append(Spacer(1, 5))
    if items:
        flowables.append(
            _data_table(
                ["Acta", "Aprendices", "Fecha", "Tipo", "Registro local", "Observación"],
                [
                    [
                        item.get("number"),
                        item.get("aprendices_count"),
                        item.get("act_date"),
                        item.get("act_type"),
                        "Sí" if item.get("act_id") is not None else "No",
                        (
                            "Identificador de acta inválido"
                            if item.get("identificador_invalido")
                            else (
                                ""
                                if (item.get("act_date") and item.get("act_type"))
                                else "Fecha o tipo no disponibles en el módulo de Actas"
                            )
                        ),
                    ]
                    for item in items
                ],
                widths=[70, 70, 85, 130, 85, 120],
                formats={1: _num},
            )
        )
        flowables.append(Spacer(1, 8))
        top = items[:10]
        flowables.append(
            KeepTogether(
                [
                    Paragraph("Aprendices asociados por acta (top 10)", STYLE_H2),
                    _bar_drawing(
                        [
                            (
                                f"Acta {item.get('number')}",
                                float(item.get("aprendices_count"))
                                if isinstance(item.get("aprendices_count"), (int, float))
                                else 0.0,
                            )
                            for item in top
                        ],
                        horizontal=True,
                        color=BLUE,
                        height=max(150, len(top) * 21 + 34),
                        label_limit=24,
                    ),
                ]
            )
        )
        flowables.append(Spacer(1, 5))
    else:
        flowables.append(_note("No hay actas asociadas al periodo.", "warning"))
    flowables.append(
        _note(
            "La hoja CERTIFICADOS solo informa el número de acta. La fecha y el tipo "
            "se muestran únicamente si el acta existe en el módulo de Actas; si "
            "faltan, se indica «No disponible». No se construyen fechas a partir del "
            "número de acta.",
            "info",
        )
    )
    return flowables


def _traceability_section(dataset: dict[str, Any], number: str) -> list[Flowable]:
    trace = dataset.get("trazabilidad") or {}
    flowables: list[Flowable] = _section_header(
        number,
        "Fuentes, metodología y limitaciones",
        "Cómo se construyen las cifras y qué no permite afirmar este informe.",
    )
    flowables.append(Paragraph("Universos de datos", STYLE_H2))
    for item in trace.get("universos") or []:
        flowables.append(
            _bullet(
                f"{_text(item.get('nombre'))}: {_text(item.get('descripcion'))} "
                f"Uso: {_text(item.get('uso'))}"
            )
        )

    flowables.append(Paragraph("Fuentes de información", STYLE_H2))
    for item in trace.get("fuentes") or []:
        flowables.append(
            _bullet(f"{_text(item.get('nombre'))}: {_text(item.get('detalle'))}")
        )

    period = trace.get("periodo") or {}
    flowables.append(Paragraph("Periodo analizado", STYLE_H2))
    flowables.append(
        _bullet(
            f"{_text(period.get('etiqueta'))} ({_text(period.get('inicio'))} a "
            f"{_text(period.get('fin'))})."
        )
    )
    if period.get("criterio"):
        flowables.append(_bullet(str(period["criterio"])))

    flowables.append(Paragraph("Reglas de deduplicación", STYLE_H2))
    for item in trace.get("deduplicacion") or []:
        flowables.append(_bullet(str(item)))

    flowables.append(Paragraph("Criterios de clasificación", STYLE_H2))
    for item in trace.get("clasificacion") or []:
        flowables.append(_bullet(str(item)))

    flowables.append(Paragraph("Exclusiones", STYLE_H2))
    for item in trace.get("exclusiones") or []:
        flowables.append(_bullet(str(item)))

    resoluciones = dataset.get("resoluciones_conflicto") or {}
    if resoluciones:
        flowables.append(Paragraph("Resoluciones de conflictos certificado/pendiente", STYLE_H2))
        flowables.append(
            _data_table(
                ["Documento", "Resolución aplicada", "Fuente"],
                [
                    [
                        doc,
                        "Certificado" if res == "certificados" else "Pendiente",
                        "Learner.conflict_resolution (o nota histórica)",
                    ]
                    for doc, res in sorted(resoluciones.items())
                ],
                widths=[140, 120, 250],
            )
        )

    comparison = trace.get("comparacion_causas") or []
    if comparison:
        flowables.append(Paragraph("Comparación informativa de causas", STYLE_H2))
        flowables.append(
            _note(
                "Los universos son distintos y no comparables. Esta tabla solo "
                "documenta por qué las cifras locales e institucionales pueden "
                "diferir; no se usa para calcular indicadores.",
                "warning",
            )
        )
        flowables.append(Spacer(1, 4))
        flowables.append(
            _data_table(
                ["Causa", "Personas institucional", "Personas local", "Diferencia"],
                [
                    [
                        item.get("Causa"),
                        item.get("Personas institucional"),
                        item.get("Personas local"),
                        item.get("Diferencia (local - institucional)"),
                    ]
                    for item in comparison
                ],
                widths=[220, 100, 90, 90],
                formats={1: _num, 2: _num, 3: _num},
            )
        )
        flowables.append(Spacer(1, 4))
        if trace.get("nota_causas"):
            flowables.append(_note(str(trace["nota_causas"]), "info"))

    flowables.append(Paragraph("Limitaciones", STYLE_H2))
    for item in trace.get("limitaciones") or []:
        flowables.append(_bullet(str(item)))

    flowables.append(Paragraph("Advertencias del cálculo", STYLE_H2))
    advertencias = trace.get("advertencias") or []
    if advertencias:
        for item in advertencias:
            flowables.append(_bullet(str(item)))
    else:
        flowables.append(_bullet("Sin advertencias registradas."))

    if (trace.get("actas") or {}).get("nota"):
        flowables.append(Spacer(1, 4))
        flowables.append(_note(str(trace["actas"]["nota"]), "info"))
    flowables.append(Spacer(1, 4))
    flowables.append(_note(str(trace.get("nota_incidencias") or INCIDENCE_NOTE), "warning"))
    return flowables


def _learners_section(
    dataset: dict[str, Any], number: str, *, title: str = "Anexo de aprendices"
) -> list[Flowable]:
    local = dataset.get("universo_local") or {}
    filter_info = local.get("filtro") or {}
    subtitle = (
        "Padrón local SQLite. No es el consolidado institucional y sus cifras no "
        "se suman a ACTAS 2026."
    )
    if filter_info.get("aplicado"):
        subtitle += (
            f" Vista filtrada: búsqueda «{filter_info.get('search') or ''}» · "
            f"estado «{filter_info.get('status') or 'Todos'}»."
        )
    flowables: list[Flowable] = _section_header(number, title, subtitle)
    cards = [
        {
            "title": "Aprendices",
            "value": _num(local.get("total_aprendices")),
            "note": "Registros del padrón local.",
            "accent": BLUE,
        },
        {
            "title": "Certificados",
            "value": _num(local.get("certificados")),
            "note": "Estado local normalizado.",
            "accent": DARK_GREEN,
            "background": GREEN_SOFT,
        },
        {
            "title": "Pendientes",
            "value": _num(local.get("pendientes")),
            "note": "Estado local normalizado.",
            "accent": AMBER,
            "background": AMBER_SOFT,
        },
        {
            "title": "Sin estado informado",
            "value": _num(local.get("sin_estado")),
            "note": "Se conservan sin imputar estado.",
            "accent": RED,
            "background": RED_SOFT,
        },
    ]
    flowables.extend(_kpi_grid(cards, per_row=2))
    flowables.append(Spacer(1, 5))
    flowables.append(
        _note(
            "Los registros sin estado se muestran como «Sin estado informado»; no "
            "se clasifican como certificados ni como pendientes. No se elimina "
            "ningún aprendiz para reducir el documento.",
            "warning",
        )
    )
    flowables.append(Spacer(1, 8))
    rows = local.get("learners_rows") or []
    if rows:
        flowables.append(
            _data_table(
                ["Documento", "Nombre", "Programa", "Ficha", "Estado", "Acta", "Alerta"],
                [
                    [
                        item.get("Documento"),
                        item.get("Nombre"),
                        item.get("Programa"),
                        item.get("Ficha"),
                        item.get("Estado"),
                        item.get("Acta"),
                        item.get("Alerta de calidad") or "",
                    ]
                    for item in rows
                ],
                widths=[70, 105, 105, 48, 70, 42, 72],
            )
        )
    else:
        flowables.append(_note("El padrón local no tiene aprendices para esta vista.", "info"))
    return flowables


def _pending_section(
    dataset: dict[str, Any], number: str, *, title: str = "Anexo de pendientes"
) -> list[Flowable]:
    local = dataset.get("universo_local") or {}
    filter_info = local.get("filtro") or {}
    subtitle = "Pendientes del padrón local SQLite. No es el consolidado institucional."
    if filter_info.get("aplicado"):
        subtitle += (
            f" Vista filtrada: búsqueda «{filter_info.get('search') or ''}» · "
            f"estado «{filter_info.get('status') or 'Todos'}»."
        )
    flowables: list[Flowable] = _section_header(number, title, subtitle)
    cards = [
        {
            "title": "Pendientes locales",
            "value": _num(local.get("pendientes")),
            "note": "Personas con estado local Pendiente.",
            "accent": AMBER,
            "background": AMBER_SOFT,
        },
        {
            "title": "Sin motivo informado",
            "value": _num(local.get("pendientes_sin_motivo")),
            "note": "Se conservan sin causa asignada.",
            "accent": AMBER,
        },
        {
            "title": "% sin motivo",
            "value": _pct(local.get("pendientes_sin_motivo_porcentaje")),
            "note": "Sobre pendientes locales.",
            "accent": AMBER,
        },
        {
            "title": "Requisitos pendientes",
            "value": _num(local.get("requisitos_pendientes")),
            "note": "Requisitos locales registrados.",
            "accent": BLUE,
        },
    ]
    flowables.extend(_kpi_grid(cards, per_row=2))
    flowables.append(Spacer(1, 5))
    flowables.append(
        _note(
            "Los pendientes sin motivo se mantienen y se muestran como «Sin motivo "
            "informado». No se inventan causas. El análisis institucional de causas "
            "se presenta en su propia sección.",
            "warning",
        )
    )
    flowables.append(Spacer(1, 8))
    rows = local.get("pending_rows") or []
    if rows:
        flowables.append(
            _data_table(
                ["Documento", "Nombre", "Programa", "Ficha", "Motivo", "Estado", "Alerta"],
                [
                    [
                        item.get("Documento"),
                        item.get("Nombre"),
                        item.get("Programa"),
                        item.get("Ficha"),
                        item.get("Motivo"),
                        item.get("Estado"),
                        item.get("Alerta de calidad") or "",
                    ]
                    for item in rows
                ],
                widths=[66, 100, 100, 44, 95, 55, 65],
            )
        )
    else:
        flowables.append(_note("No hay pendientes locales para esta vista.", "info"))
    return flowables


# ---------------------------------------------------------------------------
# Construccion del documento
# ---------------------------------------------------------------------------

REPORT_META = {
    "consolidado": {
        "title": "Informe consolidado de certificación",
        "code": "SENA-CERT-2026-CONS",
        "universe": "institucional y local, separados",
        "universe_label": "Institucional ACTAS 2026 + padrón local",
    },
    "general": {
        "title": "Informe consolidado de certificación",
        "code": "SENA-CERT-2026-CONS",
        "universe": "institucional y local, separados",
        "universe_label": "Institucional ACTAS 2026 + padrón local",
    },
    "ejecutivo": {
        "title": "Informe ejecutivo de certificación",
        "code": "SENA-CERT-2026-EJEC",
        "universe": "institucional",
        "universe_label": "Universo institucional ACTAS 2026",
    },
    "causas": {
        "title": "Análisis de pendientes y causas",
        "code": "SENA-CERT-2026-CAUS",
        "universe": "institucional",
        "universe_label": "Universo institucional ACTAS 2026",
    },
    "actas": {
        "title": "Gestión documental y actas",
        "code": "SENA-CERT-2026-ACTAS",
        "universe": "institucional",
        "universe_label": "Universo institucional ACTAS 2026",
    },
    "aprendices": {
        "title": "Anexo de aprendices",
        "code": "SENA-CERT-2026-APR",
        "universe": "local",
        "universe_label": "Universo local · padrón SQLite",
    },
    "pendientes": {
        "title": "Anexo de pendientes",
        "code": "SENA-CERT-2026-PEND",
        "universe": "local",
        "universe_label": "Universo local · padrón SQLite",
    },
}


def _section_plan(
    report_type: str, detail: str
) -> list[tuple[str, Callable[..., list[Flowable]]]]:
    """Devuelve las secciones en orden, con su constructor."""
    if report_type in {"consolidado", "general"}:
        plan: list[tuple[str, Callable[..., list[Flowable]]]] = [
            ("Resumen ejecutivo", _summary_section),
            ("Resultados por categoría", _categories_section),
            ("Evolución mensual", _monthly_section),
            ("Análisis de pendientes", _causes_section),
            ("Gestión documental y actas", _acts_section),
            ("Fuentes, metodología y limitaciones", _traceability_section),
        ]
        if detail == "completo":
            plan.extend(
                [
                    ("Anexo de aprendices", _learners_section),
                    ("Anexo de pendientes", _pending_section),
                ]
            )
        return plan
    if report_type == "ejecutivo":
        return [
            ("Resumen ejecutivo", _summary_section),
            ("Fuentes, metodología y limitaciones", _traceability_section),
        ]
    if report_type == "causas":
        return [
            ("Análisis de pendientes", _causes_section),
            ("Fuentes, metodología y limitaciones", _traceability_section),
        ]
    if report_type == "actas":
        return [
            ("Gestión documental y actas", _acts_section),
            ("Fuentes, metodología y limitaciones", _traceability_section),
        ]
    if report_type == "aprendices":
        return [
            ("Anexo de aprendices", _learners_section),
            ("Fuentes, metodología y limitaciones", _traceability_section),
        ]
    if report_type == "pendientes":
        return [
            ("Análisis de pendientes", _causes_section),
            ("Anexo de pendientes", _pending_section),
            ("Fuentes, metodología y limitaciones", _traceability_section),
        ]
    raise ValueError(f"Tipo de informe no soportado: {report_type}.")


def _build_meta(dataset: dict[str, Any], report_type: str) -> dict[str, Any]:
    meta = dict(REPORT_META[report_type])
    meta.update(
        {
            "period": dataset.get("periodo") or "No disponible",
            "source": (
                f"Consolidado ACTAS 2026 · {dataset.get('file_name')}"
                if dataset.get("file_name")
                else "Consolidado ACTAS 2026 · lote vigente"
            ),
            "generated": _generated_label(dataset.get("generated_at")),
            "subject": f"{meta['title']} · {dataset.get('periodo') or ''}".strip(" ·"),
        }
    )
    return meta


def _build_story(
    dataset: dict[str, Any],
    report_type: str,
    detail: str,
    doc: ReportDocTemplate,
) -> list[Flowable]:
    story: list[Flowable] = [Spacer(1, 1), NextPageTemplate("Body")]
    plan = _section_plan(report_type, detail)
    for index, (section_title, builder) in enumerate(plan, start=1):
        story.append(SectionMarker(doc, section_title))
        story.append(PageBreak())
        story.extend(builder(dataset, f"{index:02d}"))
    return story


def _generated_label(value: Any) -> str:
    if not value:
        return "No disponible"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%d/%m/%Y %H:%M UTC")
    except ValueError:
        return str(value)[:16]


def build_report_pdf(
    dataset: dict[str, Any],
    report_type: str = "consolidado",
    *,
    detail: str = "completo",
) -> bytes:
    """Genera el PDF editorial del tipo solicitado."""
    if report_type not in REPORT_META:
        raise ValueError(f"Tipo de informe no soportado: {report_type}.")
    if detail not in {"completo", "ejecutivo"}:
        raise ValueError(f"Nivel de detalle no soportado: {detail}.")
    meta = _build_meta(dataset, report_type)
    buffer = BytesIO()
    doc = ReportDocTemplate(buffer, metadata=meta)
    story = _build_story(dataset, report_type, detail, doc)
    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()


def build_consolidated_pdf(dataset: dict[str, Any], *, detail: str = "completo") -> bytes:
    return build_report_pdf(dataset, "consolidado", detail=detail)


__all__ = [
    "REPORT_META",
    "build_consolidated_pdf",
    "build_report_pdf",
]

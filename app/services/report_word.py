"""Generacion de informes Word desde la plantilla institucional y datos cargados."""

from __future__ import annotations

import io
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "informe_gestion_administrativa.docx"
MONTHS_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def _set_paragraph_text(paragraph, text: str) -> None:
    """Replace paragraph content while retaining its paragraph and first-run style."""
    if not text:
        paragraph._p.getparent().remove(paragraph._p)
        return
    first_run = paragraph.runs[0] if paragraph.runs else None
    run_properties = (
        deepcopy(first_run._r.rPr)
        if first_run is not None and first_run._r.rPr is not None
        else None
    )
    for child in list(paragraph._p):
        if child.tag != qn("w:pPr"):
            paragraph._p.remove(child)
    run = paragraph.add_run(text)
    if run_properties is not None:
        run._r.insert(0, run_properties)


def _format_number(value: Any) -> str:
    if value is None:
        return "No disponible"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{int(value):,}".replace(",", ".")


def _format_percent(value: Any) -> str:
    return "No disponible" if value is None else _format_number(value)


def _format_date(value: date) -> str:
    return f"{value.day} de {MONTHS_ES[value.month - 1]} de {value.year}"


def _periodo_contexto(dataset: dict[str, Any]) -> dict[str, Any]:
    """Resume el periodo elegido para redactar el Word sin textos fijos."""
    try:
        trimestre = int(dataset.get("trimestre") or 3)
    except (TypeError, ValueError):
        trimestre = 3
    trimestre = trimestre if trimestre in (1, 2, 3, 4) else 3
    romano = dataset.get("trimestre_romano") or {1: "I", 2: "II", 3: "III", 4: "IV"}[trimestre]
    ordinal = dataset.get("trimestre_ordinal") or {
        1: "primer",
        2: "segundo",
        3: "tercer",
        4: "cuarto",
    }[trimestre]
    anio = dataset.get("year") or dataset.get("anio") or date.today().year
    etiqueta_trimestre = (
        dataset.get("trimestre_etiqueta") or f"Trimestre {romano} {anio}"
    )
    try:
        inicio = date.fromisoformat(str(dataset.get("periodo_inicio")))
    except (TypeError, ValueError):
        inicio = date(int(anio), 1, 1)
    try:
        fin = date.fromisoformat(str(dataset.get("periodo_fin")))
    except (TypeError, ValueError):
        fin = date(int(anio), 9, 30)
    modo = dataset.get("modo") or "acumulado"
    periodo = dataset.get("periodo") or f"{MONTHS_ES[inicio.month - 1].capitalize()} - {MONTHS_ES[fin.month - 1].capitalize()} {anio}"
    modo_texto = (
        "acumulado desde el 1 de enero"
        if modo == "acumulado"
        else "solo los tres meses del trimestre"
    )
    rango_texto = f"del {_format_date(inicio)} al {_format_date(fin)}"
    return {
        "trimestre": trimestre,
        "romano": romano,
        "ordinal": ordinal,
        "anio": anio,
        "etiqueta_trimestre": etiqueta_trimestre,
        "etiqueta_periodo": f"{periodo}, {modo_texto}",
        "modo": modo,
        "modo_texto": modo_texto,
        "periodo": periodo,
        "inicio": inicio,
        "fin": fin,
        "rango_texto": rango_texto,
    }


def _metric_map(dataset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["category"]: item
        for item in dataset.get("metricas", [])
        if item.get("category")
    }


def _sum_known(*values: Any) -> int | None:
    if not values or any(not isinstance(value, (int, float)) for value in values):
        return None
    return int(sum(values))


def _table_rows(dataset: dict[str, Any]) -> dict[int, tuple[Any, Any, Any, Any]]:
    metrics = _metric_map(dataset)
    channels = dataset.get("complementaria_canales") or {}
    channel_metas = dataset.get("metas_canales") or {}
    certificates_available = dataset.get("certificados_disponible", True)
    complementary_available = dataset.get("complementaria_disponible", True)

    def category(key: str) -> tuple[Any, Any, Any, Any]:
        item = metrics.get(key, {})
        available = (
            complementary_available if key == "complementaria" else certificates_available
        )
        if not available:
            return item.get("meta"), None, None, None
        return (
            item.get("meta"),
            item.get("certificados"),
            item.get("brecha"),
            item.get("avance"),
        )

    def channel_row(name: str) -> tuple[Any, Any, Any, Any]:
        meta = channel_metas.get(name)
        certificates = channels.get(name) if complementary_available else None
        if not complementary_available:
            return meta, None, None, None
        pending = (
            max(0, meta - certificates)
            if isinstance(meta, (int, float)) and isinstance(certificates, (int, float))
            else None
        )
        advance = (
            round(certificates * 100 / meta, 1)
            if isinstance(meta, (int, float))
            and meta
            and isinstance(certificates, (int, float))
            else None
        )
        return meta, certificates, pending, advance

    superior = category("superior")
    tecnica = category("tecnica")
    articulacion = category("articulacion")
    complementaria = category("complementaria")

    def total(*parts: tuple[Any, Any, Any, Any]) -> tuple[Any, Any, Any, Any]:
        meta = _sum_known(*(part[0] for part in parts))
        certificates = _sum_known(*(part[1] for part in parts))
        pending = max(0, meta - certificates) if meta is not None and certificates is not None else None
        advance = round(certificates * 100 / meta, 1) if meta and certificates is not None else None
        return meta, certificates, pending, advance

    return {
        1: superior,
        2: tecnica,
        3: articulacion,
        4: total(tecnica, articulacion),
        6: channel_row("campesena"),
        7: channel_row("fullpopular"),
        9: total(superior, tecnica, articulacion),
        # The template vertically merges the value cells for these two rows.
        # Put the shared complementary total there; channel totals remain in
        # the accompanying narrative instead of overwriting one another.
        10: complementaria,
        11: complementaria,
        12: total(superior, tecnica, articulacion, complementaria),
    }


def _write_indicator_table(doc, dataset: dict[str, Any]) -> None:
    if len(doc.tables) < 2:
        return
    table = doc.tables[1]
    for row_index, values in _table_rows(dataset).items():
        if row_index >= len(table.rows):
            continue
        row = table.rows[row_index]
        for column_index, value in enumerate(values, start=1):
            if column_index >= len(row.cells):
                continue
            cell = row.cells[column_index]
            _set_paragraph_text(
                cell.paragraphs[0],
                _format_percent(value) if column_index == 4 else _format_number(value),
            )
            for paragraph in cell.paragraphs[1:]:
                _set_paragraph_text(paragraph, "")


def _category_summary(dataset: dict[str, Any], category: str) -> str:
    summary = dataset.get("resumen_ejecutivo") or {}
    row_index = {
        "superior": 1,
        "tecnica": 2,
        "articulacion": 3,
        "complementaria": 10,
        "total": 12,
    }.get(category)
    meta, certified, pending, advance = (
        _table_rows(dataset)[row_index] if row_index is not None else (None, None, None, None)
    )
    channels_text = ""
    if category == "complementaria":
        channels = dataset.get("complementaria_canales") or {}
        if dataset.get("complementaria_disponible", True):
            channels_text = ", ".join(
                f"{name}: {_format_number(channels.get(name))}"
                for name in ("presencial", "virtual", "campesena", "fullpopular")
                if channels.get(name) is not None
            )
            if channels_text:
                channels_text = f" Desglose por canal: {channels_text}."
    else:
        channels_text = ""
    period_end = dataset.get("periodo_fin")
    try:
        period_text = _format_date(date.fromisoformat(period_end)) if period_end else "periodo disponible"
    except (TypeError, ValueError):
        period_text = "periodo disponible"
    if category == "total" and meta is None:
        meta = summary.get("meta_total")
    advance_text = f"{_format_percent(advance)}%" if advance is not None else "No disponible"
    return (
        f"Al corte del {period_text} se registran "
        f"{_format_number(certified)} certificados, frente a una meta de "
        f"{_format_number(meta)}. Avance: {advance_text}; "
        f"pendientes por cumplir: {_format_number(pending)}.{channels_text}"
    )


def _update_narrative(doc, dataset: dict[str, Any], cutoff: date) -> None:
    contexto = _periodo_contexto(dataset)
    trimestre_etiqueta = contexto["etiqueta_trimestre"]
    etiqueta_periodo = contexto["etiqueta_periodo"]
    rango_texto = contexto["rango_texto"]
    total_summary = _category_summary(dataset, "total")
    replacements = (
        ("Junio 30 de 2026", _format_date(cutoff)),
    )
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        for old, new in replacements:
            if old in text:
                _set_paragraph_text(paragraph, text.replace(old, new))
                text = paragraph.text.strip()

        if text.startswith("Presentar la gestión realizada"):
            _set_paragraph_text(
                paragraph,
                f"Presentar los resultados de certificación registrados en el sistema "
                f"para el {trimestre_etiqueta}, correspondientes al periodo "
                f"{etiqueta_periodo}, con base en las fuentes institucionales cargadas.",
            )
        elif text.startswith("Este informe incluye la gestión realizada"):
            _set_paragraph_text(
                paragraph,
                f"Este informe incluye la gestión realizada en el {trimestre_etiqueta} "
                f"({rango_texto}) en relación con los procesos de certificación, "
                "incluyendo formación titulada y complementaria, en el Centro de "
                "Comercio y Servicios de la Regional Bolívar.",
            )
        elif text.startswith("A continuación, se presenta la gestión llevada"):
            _set_paragraph_text(
                paragraph,
                f"A continuación, se presentan los resultados del {trimestre_etiqueta} "
                f"(periodo {etiqueta_periodo}), calculados a partir de los datos "
                "cargados en el sistema.",
            )
        elif text.startswith("Fuente:"):
            _set_paragraph_text(
                paragraph,
                "Fuente: consolidado ACTAS 2026 y registros institucionales cargados en el sistema.",
            )
        elif (
            text.startswith("¿Cómo fue la gestión en el periodo")
            and "Educación Superior" in text
        ):
            _set_paragraph_text(
                paragraph,
                "Resultados del indicador: Certificación - Educación Superior",
            )
        elif text.startswith("La Meta Anual asignada"):
            _set_paragraph_text(
                paragraph,
                _category_summary(dataset, "superior"),
            )
        elif text.startswith("En el segundo trimestre se identifica"):
            _set_paragraph_text(paragraph, _category_summary(dataset, "superior"))
        elif text.startswith("Dentro de las estrategias establecidas"):
            _set_paragraph_text(
                paragraph,
                "El sistema no almacena estrategias narrativas para este periodo; "
                "por ello, no se agregan actividades no registradas.",
            )
        elif text.startswith("¿Cómo fue la gestión del periodo para el Indicador"):
            _set_paragraph_text(
                paragraph,
                "Resultados del indicador: Certificación - Técnico Laboral y Otros sin "
                f"incluir Media Técnica. {_category_summary(dataset, 'tecnica')}",
            )
        elif text.startswith("Dependencia de las actas de certificación:") or text.startswith(
            "Cantidad de aprendices relacionados en las actas:"
        ):
            _set_paragraph_text(paragraph, "")
        elif text.startswith("Estrategia o Actividades llevadas a cabo: Para avanzar"):
            _set_paragraph_text(
                paragraph,
                "No se registran estrategias o actividades narrativas en las fuentes cargadas.",
            )
        elif text.startswith("Certificación Técnico Laboral y Otros:"):
            _set_paragraph_text(paragraph, "")
        elif text.startswith("Se remiten semanalmente actas") or text.startswith(
            "Con el fin de apoyar en aumentar"
        ):
            _set_paragraph_text(paragraph, "")
        elif text.startswith("El componente de Certificación alcanzó"):
            _set_paragraph_text(paragraph, _category_summary(dataset, "articulacion"))
        elif text.startswith("A través de la Coordinación de programas especiales"):
            _set_paragraph_text(
                paragraph,
                "No se registran actividades narrativas de articulación en las fuentes cargadas.",
            )
        elif (
            text.startswith("¿Cómo fue la gestión en el periodo")
            and "formación Complementaria" in text
        ):
            _set_paragraph_text(paragraph, "Resultados del indicador: Certificación - Formación Complementaria")
        elif text.startswith("Con una meta anual de"):
            _set_paragraph_text(paragraph, _category_summary(dataset, "complementaria"))
        elif text.startswith("▪ Reducción de tiempos") or text.startswith(
            "▪ Dependencia de la valoración"
        ) or text.startswith("▪ Diferencia entre aprendices matriculados") or text.startswith(
            "▪ Dependencia del estado"
        ) or text.startswith("▪ Dependencia del proceso de precertificación") or text.startswith(
            "▪ Intermitencias en los sistemas de información"
        ):
            _set_paragraph_text(paragraph, "")
        elif text.startswith("Con el fin de optimizar el proceso de inscripción"):
            _set_paragraph_text(
                paragraph,
                "No se registran actividades narrativas de formación complementaria en las fuentes cargadas.",
            )
        elif (text.startswith("¿Cómo fue la gestión en el periodo") and "Certificación TOTAL" in text):
            _set_paragraph_text(
                paragraph,
                f"Resultados del indicador: Certificación total - Centros de Formación. "
                f"{total_summary}",
            )
        elif text.startswith("Aprendices con requisitos pendientes para certificación:"):
            pending = (dataset.get("resumen_ejecutivo") or {}).get("pendientes_personas")
            _set_paragraph_text(
                paragraph,
                "El consolidado institucional registra "
                f"{_format_number(pending)} aprendices pendientes. No se infieren "
                "requisitos individuales a partir de este total.",
            )
        elif text.startswith("▪ Dependencia de la oportunidad") or text.startswith(
            "▪ Intermitencias en SOFIA Plus:"
        ) or text.startswith("▪ Procesos de depuración de aprendices:"):
            _set_paragraph_text(paragraph, "")
        elif text.startswith("Estrategia o Actividades llevadas a cabo.  Dentro"):
            _set_paragraph_text(
                paragraph,
                "No se registran estrategias o actividades narrativas en las fuentes cargadas.",
            )
        elif text.startswith("Realizar llamadas, videollamadas chat") or text.startswith(
            "Trabajar de la mano con el Líder"
        ):
            _set_paragraph_text(paragraph, "")
        elif text.startswith("A continuación, se relacionan algunas de las actividades"):
            _set_paragraph_text(
                paragraph,
                "No hay actividades adicionales registradas en el sistema para este periodo.",
            )
        elif text.startswith("Atención al usuario en jornadas") or text.startswith(
            "Coordinación realización de Fase II"
        ) or text.startswith("Matrículas I Convocatoria") or text.startswith(
            "Inducción nuevos aprendices"
        ) or text.startswith("A continuación, se relacionan soportes"):
            _set_paragraph_text(paragraph, "")
        elif text.startswith("Se evidenció la gestión desarrollada"):
            _set_paragraph_text(
                paragraph,
                f"Para el {trimestre_etiqueta}, con base en el consolidado institucional "
                f"disponible, {total_summary[0].lower() + total_summary[1:] if total_summary else 'no hay resultados calculables.'}",
            )
        elif text.startswith(
            (
                "Respecto al indicador Total Técnico Laboral",
                "De igual manera, se verificó",
                "En este sentido, el avance",
                "Si bien desde esta área",
                "Durante la vigencia, se implementaron",
                "Fortaleciendo el control de calidad",
                "Seguimiento permanente y articulado",
            )
        ):
            _set_paragraph_text(paragraph, "")


def _remove_annex_content(doc) -> None:
    body = doc._element.body
    children = list(body)
    annex_index = None
    for index, child in enumerate(children):
        if child.tag != qn("w:p"):
            continue
        text = Paragraph(child, doc._body).text.strip().upper()
        if text == "ANEXOS":
            annex_index = index
            break
    if annex_index is None:
        return
    for child in children[annex_index + 1 :]:
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def generate_report_docx(
    dataset: dict[str, Any],
    year: int | None = None,
    quarter: int | None = None,
    cutoff: date | None = None,
) -> bytes:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Plantilla no encontrada: {TEMPLATE_PATH}")

    doc = Document(str(TEMPLATE_PATH))

    contexto = _periodo_contexto(dataset)
    year = year or int(contexto["anio"])
    if cutoff is None:
        cutoff = contexto["fin"]

    roman = contexto["romano"]
    ordinal = contexto["ordinal"]
    replacements = {
        "Trimestre II de": f"Trimestre {roman} de",
        "Trimestre II 2026": f"Trimestre {roman} {year}",
        "trimestre II 2026": f"trimestre {roman} {year}",
        "II Trimestre 2026": f"{roman} Trimestre {year}",
        "segundo trimestre": f"{ordinal} trimestre",
        "Segundo trimestre": f"{ordinal.capitalize()} trimestre",
        "periodo II": f"periodo {roman}",
        "II 2026": f"{roman} {year}",
    }
    for paragraph in doc.paragraphs:
        text = paragraph.text
        for old, new in replacements.items():
            text = text.replace(old, new)
        if text != paragraph.text:
            _set_paragraph_text(paragraph, text)

    _write_indicator_table(doc, dataset)
    _update_narrative(doc, dataset, cutoff)
    _remove_annex_content(doc)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()

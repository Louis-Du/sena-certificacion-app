"""Generación del informe de gestión desde la plantilla institucional.

La plantilla ``informe_gestion_administrativa.docx`` replica el informe oficial
de la dependencia Administración Educativa. El generador NO reescribe la
estructura ni redacta un informe técnico: solo sustituye el periodo, las fechas
de corte, las cifras de la tabla y las lecturas derivadas de esas cifras.

Las secciones de limitaciones, estrategias, conclusión y anexos conservan la
redacción y el orden del original. Cuando una actividad no está soportada por
los datos del periodo se deja un placeholder institucional neutro; nunca se
menciona el aplicativo ni se habla de "fuentes cargadas".
"""

from __future__ import annotations

import io
import re
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
PLACEHOLDER_ESTRATEGIAS = "Pendiente de registro por la dependencia."
FUENTE_TABLA = (
    "Fuente: Sistema Optimizado para la Formación Integral del Aprendizaje "
    "Activo (SOFIA Plus)."
)


def _set_paragraph_text(paragraph, text: str) -> None:
    """Reemplaza el contenido conservando párrafo, estilo y formato del primer run.

    A diferencia de la versión anterior, un texto vacío NO elimina el párrafo:
    la plantilla institucional mantiene su estructura de bloques y espaciado.
    """
    first_run = paragraph.runs[0] if paragraph.runs else None
    run_properties = (
        deepcopy(first_run._r.rPr)
        if first_run is not None and first_run._r.rPr is not None
        else None
    )
    for child in list(paragraph._p):
        if child.tag != qn("w:pPr"):
            paragraph._p.remove(child)
    if not text:
        return
    run = paragraph.add_run(text)
    if run_properties is not None:
        run._r.insert(0, run_properties)


def _run_properties(run):
    """Copia las propiedades de un run de la plantilla, si existen."""
    if run is None or run._r.rPr is None:
        return None
    return deepcopy(run._r.rPr)


def _first_meaningful_run(paragraph):
    """Primer run con texto suficiente para representar el formato del bloque."""
    for run in paragraph.runs:
        if len(run.text.strip()) >= 2:
            return run
    return paragraph.runs[0] if paragraph.runs else None


def _first_body_run(paragraph):
    """Primer run que no sea título/viñeta y que no esté en negrita."""
    for run in paragraph.runs:
        text = run.text.strip()
        if len(text) >= 2 and not text.startswith("▪") and run.bold is not True:
            return run
    return None


def _first_bullet_run(paragraph):
    for run in paragraph.runs:
        if run.text.strip().startswith("▪"):
            return run
    return None


def _format_flags(run, *, bold: bool) -> dict[str, bool]:
    """Formato explicito para un run, sin heredar negrita en el cuerpo."""
    return {
        "bold": bold,
        "italic": bool(run.italic) if run is not None else False,
        "underline": bool(run.underline) if run is not None else False,
    }


def _narrative_segments(text: str) -> list[tuple[str, str]]:
    """Separa un párrafo en título/rótulo y cuerpo para no heredar negrita.

    La plantilla institucional mezcla en un mismo párrafo títulos en negrita con
    datos en formato normal. Al reconstruir el texto se conserva esa separación;
    el cuerpo nunca recibe el ``bold``/``italic``/``underline`` del título.
    """
    if not text:
        return []

    if text.startswith("¿Cómo fue la gestión"):
        marker = "?: "
        index = text.find(marker)
        if index != -1:
            return [("title", text[: index + 2]), ("body", text[index + 2 :])]
        return [("title", text)]

    strategy_label = "Estrategia o Actividades llevadas a cabo:"
    if text.startswith(strategy_label):
        return [
            ("label", strategy_label),
            ("body", text[len(strategy_label) :]),
        ]

    if text.startswith("▪ "):
        rest = text[2:]
        colon = rest.find(": ")
        if colon != -1:
            return [
                ("bullet", "▪ "),
                ("label", rest[: colon + 1]),
                ("body", rest[colon + 1 :]),
            ]
        return [("bullet", "▪ "), ("label", rest)]

    for label in (
        "Análisis de la ejecución",
        "Dependencia de las actas de certificación:",
        "Cantidad de aprendices relacionados en las actas:",
        "Aprendices con requisitos pendientes para certificación:",
    ):
        if not text.startswith(label):
            continue
        if label.startswith("Análisis") and text.rstrip().endswith(":"):
            return [("label", text)]
        colon = text.find(": ")
        if colon != -1:
            return [("label", text[: colon + 1]), ("body", text[colon + 1 :])]
        return [("label", text)]

    return [("body", text)]


def _add_formatted_run(paragraph, text: str, properties, flags: dict[str, bool]):
    run = paragraph.add_run(text)
    if properties is not None:
        run._r.insert(0, deepcopy(properties))
    run.bold = flags["bold"]
    run.italic = flags["italic"]
    run.underline = flags["underline"]
    return run


def _set_narrative_text(paragraph, text: str) -> None:
    """Reemplaza un párrafo narrativo conservando título y cuerpo separados.

    A diferencia de :func:`_set_paragraph_text`, no copia el formato del primer
    run a todo el texto: los datos de meta/ejecución/% quedan explícitamente en
    formato normal y solo el título o el rótulo corto conserva la negrita de la
    plantilla.
    """
    title_run = _first_meaningful_run(paragraph)
    body_run = _first_body_run(paragraph)
    bullet_run = _first_bullet_run(paragraph)
    title_properties = _run_properties(title_run)
    body_properties = _run_properties(body_run)
    if body_properties is None:
        body_properties = title_properties
    bullet_properties = _run_properties(bullet_run)
    if bullet_properties is None:
        bullet_properties = body_properties

    for child in list(paragraph._p):
        if child.tag != qn("w:pPr"):
            paragraph._p.remove(child)
    if not text:
        return

    for kind, segment in _narrative_segments(text):
        if not segment:
            continue
        if kind == "title":
            _add_formatted_run(
                paragraph,
                segment,
                title_properties,
                _format_flags(title_run, bold=True),
            )
        elif kind == "label":
            _add_formatted_run(
                paragraph,
                segment,
                title_properties,
                _format_flags(title_run, bold=True),
            )
        elif kind == "bullet":
            _add_formatted_run(
                paragraph,
                segment,
                bullet_properties,
                {"bold": False, "italic": False, "underline": False},
            )
        else:
            _add_formatted_run(
                paragraph,
                segment,
                body_properties,
                {"bold": False, "italic": False, "underline": False},
            )


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


def _format_aprendices(value: Any) -> str:
    if value is None:
        return "No disponible"
    if value == 1:
        return "1 aprendiz"
    return f"{_format_number(value)} aprendices"


def _periodo_contexto(dataset: dict[str, Any]) -> dict[str, Any]:
    """Resume el periodo elegido y el prorrateo orientativo de la meta."""
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
    periodo = dataset.get("periodo") or (
        f"{MONTHS_ES[inicio.month - 1].capitalize()} - "
        f"{MONTHS_ES[fin.month - 1].capitalize()} {anio}"
    )
    # Regla de semaforización acordada con el informe original:
    # * acumulado: se compara contra 25 % por cada trimestre transcurrido;
    # * solo_trimestre: se compara contra el 25 % orientativo del trimestre.
    prorrateo = 25 * trimestre if modo == "acumulado" else 25
    return {
        "trimestre": trimestre,
        "romano": romano,
        "ordinal": ordinal,
        "anio": anio,
        "etiqueta_trimestre": etiqueta_trimestre,
        "modo": modo,
        "periodo": periodo,
        "inicio": inicio,
        "fin": fin,
        "fecha_corte": _format_date(fin),
        "prorrateo": prorrateo,
        "rango_texto": f"del {_format_date(inicio)} al {_format_date(fin)}",
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
        # La plantilla fusiona verticalmente estas dos filas: el total de
        # complementaria se escribe una sola vez en ambas celdas.
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


def _indicator_values(
    dataset: dict[str, Any], category: str
) -> tuple[Any, Any, Any, Any]:
    row_index = {
        "superior": 1,
        "tecnica": 2,
        "articulacion": 3,
        "complementaria": 10,
        "total": 12,
    }.get(category)
    return (
        _table_rows(dataset)[row_index]
        if row_index is not None
        else (None, None, None, None)
    )


def _lectura_avance(
    advance: Any, prorrateo: int
) -> tuple[str, str]:
    """Devuelve (calificación, color) según el prorrateo orientativo."""
    if not isinstance(advance, (int, float)):
        return "sin información", "sin semaforización"
    if advance >= prorrateo:
        return "buena", "verde"
    return "baja", "rojo"


def _semaforo(advance: Any, prorrateo: int) -> str:
    calificacion, color = _lectura_avance(advance, prorrateo)
    if calificacion == "sin información":
        return "no se cuenta con información suficiente para calificar la ejecución"
    return (
        f"semaforización en {color}, se entiende que es una ejecución "
        f"{calificacion} al prorratear la meta entre los cuatro trimestres"
    )


def _sentence_superior(dataset: dict[str, Any], contexto: dict[str, Any]) -> str:
    meta, certified, _, advance = _indicator_values(dataset, "superior")
    return (
        "La Meta Anual asignada por la Dirección de formación Profesional "
        f"Integral es de {_format_number(meta)} aprendices; a corte del "
        f"{contexto['fecha_corte']}, se lleva una ejecución de "
        f"{_format_aprendices(certified)}, que equivale al "
        f"{_format_percent(advance)}%; "
        f"{_semaforo(advance, contexto['prorrateo'])}. "
    )


def _sentence_tecnica(dataset: dict[str, Any], contexto: dict[str, Any]) -> str:
    meta, certified, _, advance = _indicator_values(dataset, "tecnica")
    calificacion, _ = _lectura_avance(advance, contexto["prorrateo"])
    return (
        f"¿Cómo fue la gestión del periodo {contexto['romano']} para el "
        "Indicador: “Certificación - Técnico Laboral y Otros sin Incluir Media "
        f"Técnica” ?: La Meta Anual es de {_format_number(meta)}, a corte del "
        f"{contexto['fecha_corte']}, se lleva una ejecución de "
        f"{_format_aprendices(certified)}, que equivale al "
        f"{_format_percent(advance)}%, encontrándose en una ejecución "
        f"{calificacion}. "
    )


def _sentence_articulacion(dataset: dict[str, Any], contexto: dict[str, Any]) -> str:
    _, certified, _, advance = _indicator_values(dataset, "articulacion")
    calificacion, _ = _lectura_avance(advance, contexto["prorrateo"])
    if calificacion == "sin información":
        avance_calificado = "sin información"
    else:
        avance_calificado = "bueno" if calificacion == "buena" else "bajo"
    return (
        "El componente de Certificación alcanzó una ejecución de "
        f"{_format_aprendices(certified)}, equivalente al "
        f"{_format_percent(advance)}% de la meta anual. Si bien este resultado "
        f"representa un avance {avance_calificado} frente al cumplimiento "
        "esperado de la vigencia, su comportamiento responde a las "
        "particularidades propias de la estrategia de Articulación con la Media "
        "Técnica, donde la mayor concentración de certificaciones se genera "
        "durante el último trimestre del año, una vez finaliza el calendario "
        "académico de las instituciones educativas y los aprendices cumplen los "
        "requisitos establecidos para su certificación."
    )


def _sentence_complementaria_titulo(
    dataset: dict[str, Any], contexto: dict[str, Any]
) -> str:
    return (
        f"¿Cómo fue la gestión en el periodo {contexto['romano']} para el "
        "Indicador: “Certificación - formación Complementaria” ?:"
    )


def _sentence_complementaria(dataset: dict[str, Any], contexto: dict[str, Any]) -> str:
    meta, certified, _, advance = _indicator_values(dataset, "complementaria")
    calificacion, _ = _lectura_avance(advance, contexto["prorrateo"])
    return (
        f"Con una meta anual de {_format_number(meta)}, a corte del "
        f"{contexto['fecha_corte']}, se logró certificar "
        f"{_format_aprendices(certified)} entre formación presencial y "
        f"virtual, para una ejecución del {_format_percent(advance)}%, lo que "
        f"representa una ejecución {calificacion}, acorde con la "
        "trimestralización prorrateada."
    )


def _sentence_total(dataset: dict[str, Any], contexto: dict[str, Any]) -> str:
    meta, certified, _, advance = _indicator_values(dataset, "total")
    calificacion, _ = _lectura_avance(advance, contexto["prorrateo"])
    return (
        f"¿Cómo fue la gestión en el periodo {contexto['romano']} para el "
        "Indicador: “Certificación TOTAL - Centros de Formación” ?: La Meta "
        "Anual asignada por la Dirección de formación Profesional Integral es "
        f"de {_format_number(meta)} aprendices certificados, a corte del "
        f"{contexto['fecha_corte']}, se realizó una ejecución de "
        f"{_format_number(certified)} "
        f"{'aprendiz certificado' if certified == 1 else 'aprendices certificados'}, "
        f"para una ejecución del {_format_percent(advance)}%, encontrándose en una "
        f"ejecución {calificacion}."
    )


def _sentence_conclusion(dataset: dict[str, Any], contexto: dict[str, Any]) -> str:
    meta, certified, _, advance = _indicator_values(dataset, "total")
    calificacion, _ = _lectura_avance(advance, contexto["prorrateo"])
    return (
        "De igual manera, se verificó que la totalidad de las actas de "
        "certificación recibidas para trámite fueron gestionadas oportunamente. "
        f"Al corte del {contexto['fecha_corte']}, se registran "
        f"{_format_number(certified)} certificaciones frente a una meta anual "
        f"de {_format_number(meta)}, lo que representa un avance del "
        f"{_format_percent(advance)}% y una ejecución {calificacion} frente al "
        f"{contexto['prorrateo']}% proyectado para el "
        f"{contexto['ordinal']} trimestre en los diferentes indicadores de "
        "certificación."
    )


def _replace_periodo(doc, contexto: dict[str, Any], year: int) -> None:
    """Sustituye únicamente las referencias de periodo del original.

    Se usa una sola pasada de regex para que un reemplazo no vuelva a coincidir
    con otro patrón (por ejemplo, que ``III`` se convierta en ``IIII``).
    """
    roman = contexto["romano"]
    ordinal = contexto["ordinal"]
    fecha_corte = contexto["fecha_corte"]
    patterns = (
        (re.compile(r"Trimestre II de 2026"), f"Trimestre {roman} de {year}"),
        (re.compile(r"Trimestre II 2026"), f"Trimestre {roman} {year}"),
        (re.compile(r"trimestre II 2026"), f"trimestre {roman} {year}"),
        (re.compile(r"II Trimestre 2026"), f"{roman} Trimestre {year}"),
        (re.compile(r"Segundo trimestre"), f"{ordinal.capitalize()} trimestre"),
        (re.compile(r"segundo trimestre"), f"{ordinal} trimestre"),
        (re.compile(r"periodo II"), f"periodo {roman}"),
        (re.compile(r"Junio 30 de 2026"), fecha_corte),
        (re.compile(r"junio 30"), fecha_corte),
        (re.compile(r"II 2026"), f"{roman} {year}"),
    )
    combined = re.compile("|".join(f"(?:{pattern.pattern})" for pattern, _ in patterns))

    def replacement(match: re.Match[str]) -> str:
        token = match.group(0)
        for pattern, value in patterns:
            if pattern.fullmatch(token):
                return value
        return token

    for paragraph in doc.paragraphs:
        text = paragraph.text
        updated = combined.sub(replacement, text)
        if updated != text:
            _set_paragraph_text(paragraph, updated)


def _sanitize_sofia(text: str) -> str:
    """Evita que el informe hable del aplicativo; SOFIA Plus es la fuente oficial."""
    replacements = (
        ("Superado este plazo, el sistema no permite", "Superado este plazo, SOFIA Plus no permite"),
        ("tiempos establecidos por el sistema", "tiempos establecidos por SOFIA Plus"),
        ("habilitados en el sistema", "habilitados en SOFIA Plus"),
        ("en el sistema, esto incluye", "en SOFIA Plus, esto incluye"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def _strip_annex_references(text: str) -> str:
    """Quita referencias a anexos que aún no se generan, sin tocar el listado."""
    cleaned = re.sub(r"\s*ANEXO\s+\d+\.?", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _estrategia_texto(
    estrategias: dict[str, str] | None, seccion: str
) -> str:
    """Texto redactado por la dependencia o el placeholder institucional."""
    if not estrategias:
        return PLACEHOLDER_ESTRATEGIAS
    texto = str(estrategias.get(seccion) or "").strip()
    return texto or PLACEHOLDER_ESTRATEGIAS


def _estrategia_con_rotulo(
    estrategias: dict[str, str] | None, seccion: str
) -> str:
    return (
        "Estrategia o Actividades llevadas a cabo: "
        f"{_estrategia_texto(estrategias, seccion)}"
    )


def _update_narrative(
    doc,
    dataset: dict[str, Any],
    contexto: dict[str, Any],
    estrategias: dict[str, str] | None = None,
) -> None:
    """Actualiza cifras y lecturas manteniendo la redacción institucional.

    Las secciones de estrategia usan el texto guardado para ``(año, trimestre)``.
    Si la sección está vacía se conserva el placeholder institucional. El cuerpo
    se escribe con ``_set_narrative_text`` para no heredar la negrita del rótulo.
    """
    for paragraph in doc.paragraphs:
        text = _sanitize_sofia(paragraph.text.strip())
        if text.upper() == "ANEXOS":
            break

        updated: str | None = None
        if text.startswith("La Meta Anual asignada"):
            updated = _sentence_superior(dataset, contexto)
        elif re.match(r"En el (primer|segundo|tercer|cuarto) trimestre", text):
            _, _, _, advance = _indicator_values(dataset, "superior")
            calificacion, _ = _lectura_avance(advance, contexto["prorrateo"])
            updated = (
                f"En el {contexto['ordinal']} trimestre se identifica el nivel de "
                "cumplimiento de la meta establecida, con la ejecución del "
                f"{_format_percent(advance)}% frente al {contexto['prorrateo']}% "
                f"esperado, lo que permite establecer que es una ejecución "
                f"{calificacion}."
            )
        elif text.startswith("Dentro de las estrategias establecidas"):
            updated = _estrategia_texto(estrategias, "3.1.1")
        elif text.startswith("¿Cómo fue la gestión del periodo para el Indicador"):
            updated = _sentence_tecnica(dataset, contexto)
        elif text.startswith("Estrategia o Actividades llevadas a cabo: Para avanzar"):
            updated = _estrategia_con_rotulo(estrategias, "3.1.2")
        elif text.startswith("Certificación Técnico Laboral y Otros:"):
            updated = ""
        elif text.startswith("Se remiten semanalmente actas"):
            updated = ""
        elif text.startswith("Con el fin de apoyar en aumentar"):
            updated = ""
        elif text.startswith("El componente de Certificación alcanzó"):
            updated = _sentence_articulacion(dataset, contexto)
        elif text.startswith("A través de la Coordinación de programas especiales"):
            updated = _estrategia_texto(estrategias, "3.1.3")
        elif (
            text.startswith("¿Cómo fue la gestión en el periodo")
            and "formación Complementaria" in text
        ):
            updated = _sentence_complementaria_titulo(dataset, contexto)
        elif text.startswith("Con una meta anual de"):
            updated = _sentence_complementaria(dataset, contexto)
        elif text.startswith("Con el fin de optimizar el proceso de inscripción"):
            updated = ""
        elif (
            text.startswith("¿Cómo fue la gestión en el periodo")
            and "Certificación TOTAL" in text
        ):
            updated = _sentence_total(dataset, contexto)
        elif text.startswith("Aprendices con requisitos pendientes para certificación:"):
            # Bloque de limitaciones del original: se conserva completo.
            updated = _strip_annex_references(text)
        elif text.startswith("Estrategia o Actividades llevadas a cabo. En el periodo"):
            updated = _estrategia_con_rotulo(estrategias, "3.1.4")
        elif text.startswith("Estrategia o Actividades llevadas a cabo.  Dentro"):
            updated = _estrategia_con_rotulo(estrategias, "3.1.5")
        elif text.startswith("Realizar llamadas") or text.startswith(
            "Trabajar de la mano con el Líder"
        ):
            updated = ""
        elif text.startswith("Atención al usuario en jornadas"):
            updated = _estrategia_texto(estrategias, "3.2")
        elif text.startswith("Coordinación realización") or text.startswith(
            "Matrículas I Convocatoria"
        ) or text.startswith("Inducción nuevos aprendices"):
            updated = ""
        elif text.startswith("A continuación, se relacionan soportes"):
            updated = ""
        elif text.startswith("De igual manera, se verificó"):
            updated = _sentence_conclusion(dataset, contexto)
        elif text.startswith("Fuente:"):
            updated = FUENTE_TABLA
        elif text.startswith("Cantidad de aprendices relacionados en las actas:"):
            meta, _, _, _ = _indicator_values(dataset, "tecnica")
            updated = re.sub(
                r"meta de\s+[\d.,]+\s+aprendices",
                f"meta de {_format_number(meta)} aprendices",
                text,
            )

        if updated is None:
            updated = _strip_annex_references(text)
        elif updated and updated != text:
            updated = _strip_annex_references(updated)

        if updated != paragraph.text:
            _set_narrative_text(paragraph, updated)


def _remove_duplicate_annex_content(doc) -> None:
    """Conserva el listado y la firma; elimina el contenido de anexos de ejemplo.

    La plantilla original trae dos bloques llamados ANEXOS: el primero es el
    listado oficial y el segundo contiene pantallazos/evidencias del trimestre
    de ejemplo. Como aún no se generan anexos reales, se conserva el listado y
    se retira el segundo bloque para no publicar evidencias de otro periodo.
    """
    body = doc._element.body
    children = list(body)
    annex_positions = []
    for index, child in enumerate(children):
        if child.tag != qn("w:p"):
            continue
        if Paragraph(child, doc._body).text.strip().upper() == "ANEXOS":
            annex_positions.append(index)
    if len(annex_positions) < 2:
        return
    for child in children[annex_positions[1] :]:
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def _trim_trailing_empty_paragraphs(doc) -> None:
    """Retira los párrafos vacíos y el salto de sección que deja el bloque de anexos.

    Al eliminar las evidencias de ejemplo queda un salto de sección después de
    la firma que produce una página en blanco. Se conserva el ``sectPr`` final
    del cuerpo y se eliminan los párrafos vacíos posteriores al último contenido
    visible (texto, imagen u objeto).
    """
    body = doc._element.body
    children = list(body)
    last_content = None
    for index, child in enumerate(children):
        if child.tag == qn("w:sectPr"):
            continue
        if child.tag != qn("w:p"):
            last_content = index
            continue
        paragraph = Paragraph(child, doc._body)
        has_media = any(
            child.findall(".//" + qn(tag))
            for tag in ("w:drawing", "w:pict", "w:object")
        )
        if paragraph.text.strip() or has_media:
            last_content = index
    if last_content is None:
        return
    for child in children[last_content + 1 :]:
        if child.tag != qn("w:sectPr"):
            body.remove(child)


def generate_report_docx(
    dataset: dict[str, Any],
    year: int | None = None,
    quarter: int | None = None,
    cutoff: date | None = None,
    estrategias: dict[str, str] | None = None,
) -> bytes:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Plantilla no encontrada: {TEMPLATE_PATH}")

    doc = Document(str(TEMPLATE_PATH))
    contexto = _periodo_contexto(dataset)
    year = year or int(contexto["anio"])
    if cutoff is not None:
        contexto["fin"] = cutoff
        contexto["fecha_corte"] = _format_date(cutoff)

    _replace_periodo(doc, contexto, year)
    _write_indicator_table(doc, dataset)
    _update_narrative(doc, dataset, contexto, estrategias)
    _remove_duplicate_annex_content(doc)
    _trim_trailing_empty_paragraphs(doc)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()

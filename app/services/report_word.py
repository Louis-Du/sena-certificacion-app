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
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from docx.text.paragraph import Paragraph

from app.services.rich_text import html_to_docx_paragraphs

from app.runtime import resource_root

TEMPLATE_PATH = resource_root() / "app" / "templates" / "informe_gestion_administrativa.docx"
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


# Referencia dentro del cuerpo de una estrategia: ``ANEXO 1``, ``ANEXO 1.`` o
# ``ANEXO  1``. El punto final se conserva dentro del hipervínculo para no
# alterar la redacción guardada por el usuario.
_ANEXO_REFERENCIA_RE = re.compile(
    r"(?<![A-Za-z0-9])ANEXO\s+(\d{1,3})(?!\d)\.?",
    re.IGNORECASE,
)


def _anclas_anexos(anexos: list[dict[str, Any]] | None) -> dict[int, str]:
    """Marcadores ``anexo-1`` … ``anexo-N`` según el orden del periodo."""
    return {
        numero: f"anexo-{numero}"
        for numero in range(1, len(anexos or []) + 1)
    }


def _clonar_run_con_texto(run, texto: str):
    """Crea un ``w:r`` con el mismo formato del run y el texto indicado."""
    nuevo = OxmlElement("w:r")
    if run._r.rPr is not None:
        nuevo.append(deepcopy(run._r.rPr))
    fragmento = OxmlElement("w:t")
    # Los fragmentos pueden empezar o terminar en espacio; Word los recorta
    # si no se marca el espacio como significativo.
    fragmento.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    fragmento.text = texto
    nuevo.append(fragmento)
    return nuevo


def _enlazar_referencias_anexo(paragraphs, anclas: dict[int, str]) -> None:
    """Convierte ``ANEXO N`` del cuerpo de una estrategia en enlace interno.

    El texto visible no cambia. Si el número no existe en el periodo, la
    referencia queda como texto plano (no se rompe la generación).
    """
    if not anclas:
        return
    for paragraph in paragraphs:
        for run in list(paragraph.runs):
            texto = run.text
            if not texto or not _ANEXO_REFERENCIA_RE.search(texto):
                continue
            piezas: list[tuple[str, int | None]] = []
            cursor = 0
            for match in _ANEXO_REFERENCIA_RE.finditer(texto):
                numero = int(match.group(1))
                if numero not in anclas:
                    continue
                if match.start() > cursor:
                    piezas.append((texto[cursor : match.start()], None))
                piezas.append((match.group(0), numero))
                cursor = match.end()
            if cursor < len(texto):
                piezas.append((texto[cursor:], None))
            if not any(numero is not None for _, numero in piezas):
                continue
            parent = run._r.getparent()
            posicion = list(parent).index(run._r)
            parent.remove(run._r)
            insercion = posicion
            for fragmento, numero in piezas:
                if not fragmento:
                    continue
                nuevo_run = _clonar_run_con_texto(run, fragmento)
                if numero is None:
                    elemento = nuevo_run
                else:
                    elemento = OxmlElement("w:hyperlink")
                    elemento.set(qn("w:anchor"), anclas[numero])
                    elemento.set(qn("w:history"), "1")
                    elemento.append(nuevo_run)
                parent.insert(insercion, elemento)
                insercion += 1


# Centinela para los párrafos de ejemplo de la plantilla que la estrategia del
# periodo reemplaza por completo: se eliminan en lugar de quedar como viñetas o
# líneas vacías.
_SUPRIMIR = object()


def _remove_paragraph(paragraph) -> bool:
    """Elimina el párrafo del cuerpo conservando saltos de sección e imágenes."""
    p = paragraph._p
    if p.findall(".//" + qn("w:sectPr")):
        return False
    if any(
        p.findall(".//" + qn(tag))
        for tag in ("w:drawing", "w:pict", "w:object")
    ):
        return False
    parent = p.getparent()
    if parent is None:
        return False
    parent.remove(p)
    return True


ROTULO_ESTRATEGIA = "Estrategia o Actividades llevadas a cabo: "

# Prefijo del párrafo de la plantilla -> (sección, rótulo a anteponer).
# El rótulo solo se antepone donde la plantilla lo trae; 3.1.1, 3.1.3 y 3.2
# sustituyen únicamente el cuerpo redactado.
_ESTRATEGIAS_NARRATIVA: tuple[tuple[str, str, str | None], ...] = (
    ("Dentro de las estrategias establecidas", "3.1.1", None),
    (
        "Estrategia o Actividades llevadas a cabo: Para avanzar",
        "3.1.2",
        ROTULO_ESTRATEGIA,
    ),
    ("A través de la Coordinación de programas especiales", "3.1.3", None),
    (
        "Estrategia o Actividades llevadas a cabo. En el periodo",
        "3.1.4",
        ROTULO_ESTRATEGIA,
    ),
    (
        "Estrategia o Actividades llevadas a cabo.  Dentro",
        "3.1.5",
        ROTULO_ESTRATEGIA,
    ),
    ("Atención al usuario en jornadas", "3.2", None),
)


def _estrategia_por_texto(texto: str) -> tuple[str, str | None] | None:
    """Devuelve ``(sección, rótulo)`` si el párrafo es una estrategia."""
    for prefijo, seccion, rotulo in _ESTRATEGIAS_NARRATIVA:
        if texto.startswith(prefijo):
            return seccion, rotulo
    return None


def _update_narrative(
    doc,
    dataset: dict[str, Any],
    contexto: dict[str, Any],
    estrategias: dict[str, str] | None = None,
    anclas_anexos: dict[int, str] | None = None,
) -> None:
    """Actualiza cifras y lecturas manteniendo la redacción institucional.

    Las secciones de estrategia usan el texto guardado para ``(año, trimestre)``.
    Si la sección está vacía se conserva el placeholder institucional. El cuerpo
    se escribe con ``_set_narrative_text`` para no heredar la negrita del rótulo.
    Las referencias ``ANEXO N`` del cuerpo se enlazan al detalle post-firma.
    """
    for paragraph in doc.paragraphs:
        text = _sanitize_sofia(paragraph.text.strip())
        if text.upper() == "ANEXOS":
            break

        estrategia = _estrategia_por_texto(text)
        if estrategia is not None:
            # Las estrategias se insertan como HTML restringido -> párrafos y
            # runs con negrita/cursiva/listas. El placeholder se aplica cuando
            # la sección no tiene contenido.
            seccion, rotulo = estrategia
            body_run = _first_body_run(paragraph)
            body_properties = _run_properties(body_run)
            if body_properties is None:
                body_properties = _run_properties(
                    _first_meaningful_run(paragraph)
                )
            creados = html_to_docx_paragraphs(
                paragraph,
                (estrategias or {}).get(seccion) or "",
                placeholder=PLACEHOLDER_ESTRATEGIAS,
                prefix=rotulo,
                body_properties=body_properties,
            )
            _enlazar_referencias_anexo(creados, anclas_anexos or {})
            continue

        updated: str | object | None = None
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
        elif text.startswith("¿Cómo fue la gestión del periodo para el Indicador"):
            updated = _sentence_tecnica(dataset, contexto)
        elif text.startswith("Certificación Técnico Laboral y Otros:"):
            updated = _SUPRIMIR
        elif text.startswith("Se remiten semanalmente actas"):
            updated = _SUPRIMIR
        elif text.startswith("Con el fin de apoyar en aumentar"):
            updated = _SUPRIMIR
        elif text.startswith("El componente de Certificación alcanzó"):
            updated = _sentence_articulacion(dataset, contexto)
        elif (
            text.startswith("¿Cómo fue la gestión en el periodo")
            and "formación Complementaria" in text
        ):
            updated = _sentence_complementaria_titulo(dataset, contexto)
        elif text.startswith("Con una meta anual de"):
            updated = _sentence_complementaria(dataset, contexto)
        elif text.startswith("Con el fin de optimizar el proceso de inscripción"):
            updated = _SUPRIMIR
        elif (
            text.startswith("¿Cómo fue la gestión en el periodo")
            and "Certificación TOTAL" in text
        ):
            updated = _sentence_total(dataset, contexto)
        elif text.startswith("Aprendices con requisitos pendientes para certificación:"):
            # Bloque de limitaciones del original: se conserva completo.
            updated = _strip_annex_references(text)
        elif text.startswith("Realizar llamadas") or text.startswith(
            "Trabajar de la mano con el Líder"
        ):
            updated = _SUPRIMIR
        elif text.startswith("Coordinación realización") or text.startswith(
            "Matrículas I Convocatoria"
        ) or text.startswith("Inducción nuevos aprendices"):
            updated = _SUPRIMIR
        elif text.startswith("A continuación, se relacionan soportes"):
            updated = _SUPRIMIR
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

        if updated is _SUPRIMIR:
            # Ejemplo de la plantilla sustituido por la estrategia del periodo:
            # se retira para no dejar viñetas ni líneas vacías en el DOCX.
            _remove_paragraph(paragraph)
            continue
        if updated is None:
            updated = _strip_annex_references(text)
        elif updated and updated != text:
            updated = _strip_annex_references(updated)

        if updated != paragraph.text:
            _set_narrative_text(paragraph, updated)


def _annex_heading_indexes(doc) -> list[int]:
    """Posiciones de los párrafos cuyo texto es exactamente ``ANEXOS``."""
    body = doc._element.body
    indexes: list[int] = []
    for index, child in enumerate(list(body)):
        if child.tag != qn("w:p"):
            continue
        if Paragraph(child, doc._body).text.strip().upper() == "ANEXOS":
            indexes.append(index)
    return indexes


def _prepare_annex_detail(doc, *, incluir: bool):
    """Deja el bloque ``ANEXOS`` posterior a la firma listo para el detalle.

    La plantilla original trae dos bloques llamados ANEXOS: el primero es el
    índice de §5 (antes de la firma) y el segundo contiene pantallazos de
    ejemplo (después de la firma). Aquí se retira el contenido de ejemplo del
    segundo bloque y se conserva su encabezado cuando hay anexos reales.

    Devuelve el párrafo ``ANEXOS`` post-firma o ``None`` si no se usa.
    """
    positions = _annex_heading_indexes(doc)
    if len(positions) < 2:
        if not incluir:
            return None
        # Plantilla sin segundo bloque: se agrega el detalle al final, después
        # de la firma, en lugar de perder los anexos del periodo.
        try:
            return doc.add_paragraph("ANEXOS", style="Heading 1")
        except KeyError:
            return doc.add_paragraph("ANEXOS")

    body = doc._element.body
    children = list(body)
    heading_index = positions[1]
    heading_element = children[heading_index]

    # El bloque de ejemplo se extiende hasta el sectPr final del cuerpo.
    for child in children[heading_index + 1 :]:
        if child.tag != qn("w:sectPr"):
            body.remove(child)

    if not incluir:
        body.remove(heading_element)
        return None

    # Retira los párrafos vacíos que separan el salto de sección de la firma
    # del encabezado ANEXOS. Nunca se elimina el párrafo que lleva el sectPr,
    # porque es el que inicia el detalle en una página nueva.
    previous = heading_element.getprevious()
    while previous is not None and previous.tag == qn("w:p"):
        if previous.findall(".//" + qn("w:sectPr")):
            break
        paragraph = Paragraph(previous, doc._body)
        if paragraph.text.strip() or paragraph._p.findall(
            ".//" + qn("w:drawing")
        ):
            break
        before = previous.getprevious()
        body.remove(previous)
        previous = before

    return Paragraph(heading_element, doc._body)


def _remove_empty_list_paragraphs(doc) -> None:
    """Retira viñetas o numeraciones sin texto de todo el cuerpo.

    Word dibuja un ``•`` suelto cuando un párrafo conserva ``w:numPr`` pero no
    tiene contenido. Las estrategias y la sección 3.2 reemplazan ejemplos
    numerados de la plantilla, así que cualquier resto vacío se elimina antes
    de guardar: el DOCX nunca debe mostrar puntos que el usuario no escribió.
    """
    for paragraph in list(doc.paragraphs):
        p = paragraph._p
        if p.find(".//" + qn("w:numPr")) is None:
            continue
        if paragraph.text.strip():
            continue
        _remove_paragraph(paragraph)


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


# Ancho máximo de las imágenes insertadas en la sección 5. Se reduce además al
# ancho útil real de la página (ancho - márgenes) para no desbordar el DOCX.
ANCHO_MAXIMO_IMAGEN = Inches(6.0)
# Tope de alto: una captura muy vertical se escala manteniendo proporción para
# no empujar la firma fuera de la página.
ALTO_MAXIMO_IMAGEN = Inches(7.0)


def _ancho_util(doc):
    """Ancho disponible para una imagen dentro de los márgenes de la página."""
    try:
        section = doc.sections[0]
        disponible = (
            section.page_width - section.left_margin - section.right_margin
        )
    except (AttributeError, TypeError):
        return ANCHO_MAXIMO_IMAGEN
    if disponible and disponible > 0:
        return min(disponible, ANCHO_MAXIMO_IMAGEN)
    return ANCHO_MAXIMO_IMAGEN


def _listado_anexos(doc):
    """Devuelve ``(párrafos del listado, párrafo ancla)`` del primer ANEXOS.

    La plantilla trae un ``Heading 1`` "ANEXOS" seguido del listado oficial
    (ANEXO 1..15) y, más abajo, la firma. El ancla es el primer párrafo que ya
    no es un ítem del listado; ahí se insertan los anexos reales para que el
    bloque quede antes de la firma.
    """
    paragraphs = doc.paragraphs
    heading = None
    for index, paragraph in enumerate(paragraphs):
        if paragraph.text.strip().upper() == "ANEXOS":
            heading = index
            break
    if heading is None:
        return [], None

    listado = []
    for paragraph in paragraphs[heading + 1 :]:
        if paragraph.text.strip().upper().startswith("ANEXO"):
            listado.append(paragraph)
            continue
        if listado:
            return listado, paragraph
    return listado, None


def _insertar_parrafo_lista(anchor, texto: str, propiedades):
    """Inserta un párrafo antes del ancla conservando el formato del listado."""
    paragraph = anchor.insert_paragraph_before()
    if propiedades is not None:
        paragraph._p.insert(0, deepcopy(propiedades))
    paragraph.add_run(texto)
    return paragraph


# Prefijo que el rotulador de §5 agrega por su cuenta: no debe repetirse en el
# título (evita "ANEXO 1. ANEXO 1. Actas…").
_PREFIJO_ANEXO_RE = re.compile(
    r"^\s*anexo\s*(?:n[°º.]?\s*)?\d{1,3}\s*[.):\-–—]*\s*",
    re.IGNORECASE,
)
def _titulo_anexo(value: Any) -> str:
    """Título sin prefijo ``ANEXO N`` (defensa para filas antiguas)."""
    titulo = re.sub(r"\s+", " ", str(value or "")).strip()
    for _ in range(3):
        limpio = _PREFIJO_ANEXO_RE.sub("", titulo).strip()
        if limpio == titulo:
            break
        titulo = limpio
    return titulo


def _dimensiones_imagen(ancho: int, ancho_px: int, alto_px: int, alto=None):
    """Escala una imagen al ancho útil sin superar el alto máximo."""
    if not ancho_px or not alto_px:
        return int(ancho), int(alto or ALTO_MAXIMO_IMAGEN)
    ancho_final = int(ancho)
    alto_final = int(ancho_final * alto_px / ancho_px)
    limite_alto = int(alto or ALTO_MAXIMO_IMAGEN)
    if alto_final > limite_alto:
        alto_final = limite_alto
        ancho_final = int(alto_final * ancho_px / alto_px)
    return ancho_final, alto_final


def _insertar_imagen(anchor, ruta: Any, ancho, alto=None) -> None:
    """Inserta una imagen del anexo sin romper el DOCX si no es legible.

    python-docx no interpreta WEBP, así que, si falla la lectura directa, se
    convierte a PNG en memoria con Pillow (cuando está disponible). Un archivo
    corrupto se omite: el anexo conserva al menos su título y descripción.

    Cada imagen deja un espacio pequeño después para que dos capturas del mismo
    anexo no queden pegadas; la separación amplia entre anexos la agrega
    ``_write_annex_detail`` al cerrar el grupo.
    """
    if not ruta:
        return
    path = Path(str(ruta))
    if not path.is_file():
        return
    paragraph = anchor.insert_paragraph_before()
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(6)
    try:
        from docx.image.image import Image as DocxImage
        from docx.shared import Emu

        imagen = DocxImage.from_file(str(path))
        ancho_final, alto_final = _dimensiones_imagen(
            ancho, imagen.width, imagen.height, alto
        )
        paragraph.add_run().add_picture(
            str(path), width=Emu(ancho_final), height=Emu(alto_final)
        )
        return
    except Exception:
        pass

    try:
        from io import BytesIO

        from docx.shared import Emu
        from PIL import Image as PILImage

        with PILImage.open(path) as original:
            ancho_px, alto_px = original.size
            if original.mode not in ("RGB", "RGBA"):
                original = original.convert("RGBA")
            buffer = BytesIO()
            original.save(buffer, format="PNG")
        buffer.seek(0)
        ancho_final, alto_final = _dimensiones_imagen(
            ancho, ancho_px, alto_px, alto
        )
        paragraph.add_run().add_picture(
            buffer, width=Emu(ancho_final), height=Emu(alto_final)
        )
    except Exception:
        parent = paragraph._p.getparent()
        if parent is not None:
            parent.remove(paragraph._p)


def _next_bookmark_id(doc) -> int:
    """Siguiente ``w:id`` libre para los marcadores del detalle de anexos."""
    ids: list[int] = []
    for bookmark in doc.element.body.iter(qn("w:bookmarkStart")):
        try:
            ids.append(int(bookmark.get(qn("w:id")) or 0))
        except (TypeError, ValueError):
            continue
    return max(ids, default=0) + 1


def _add_bookmark(paragraph, name: str, bookmark_id: int) -> None:
    """Envuelve el párrafo con ``bookmarkStart`` / ``bookmarkEnd``."""
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(bookmark_id))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(bookmark_id))
    p = paragraph._p
    p.insert(1 if p.pPr is not None else 0, start)
    p.append(end)


def _write_annex_index(
    doc, anexos: list[dict[str, Any]] | None = None
) -> None:
    """Escribe el índice de §5 antes de la firma: solo ``ANEXO N. título``.

    No inserta descripciones ni imágenes: el detalle completo vive después de
    la firma. Sin anexos cargados se conserva el listado institucional de la
    plantilla para no romper la generación ni inventar un listado vacío.
    """
    if not anexos:
        return
    listado, anchor = _listado_anexos(doc)
    if anchor is None:
        return

    propiedades = (
        deepcopy(listado[0]._p.pPr)
        if listado and listado[0]._p.pPr is not None
        else None
    )
    for paragraph in listado:
        parent = paragraph._p.getparent()
        if parent is not None:
            parent.remove(paragraph._p)

    for index, anexo in enumerate(anexos, start=1):
        rotulo = f"ANEXO {index}"
        titulo = _titulo_anexo(anexo.get("titulo"))
        _insertar_parrafo_lista(
            anchor,
            f"{rotulo}. {titulo}" if titulo else rotulo,
            propiedades,
        )


def _write_annex_detail(
    doc,
    anexos: list[dict[str, Any]] | None = None,
    heading=None,
) -> None:
    """Escribe el detalle post-firma con título, descripción e imágenes.

    Cada encabezado ``ANEXO {n}. {título}`` lleva el marcador ``anexo-{n}`` que
    usan los hipervínculos internos de las estrategias. La numeración sigue la
    posición 1..N del periodo, igual que el índice de §5.
    """
    if not anexos or heading is None:
        return

    # Párrafo centinela después del encabezado: los bloques se insertan antes
    # de él para conservar el orden y luego se retira.
    sentinel = OxmlElement("w:p")
    heading._p.addnext(sentinel)
    anchor = Paragraph(sentinel, heading._parent)
    ancho = _ancho_util(doc)
    bookmark_id = _next_bookmark_id(doc)

    for index, anexo in enumerate(anexos, start=1):
        rotulo = f"ANEXO {index}"
        titulo = _titulo_anexo(anexo.get("titulo"))
        texto = f"{rotulo}. {titulo}" if titulo else rotulo
        try:
            detalle = anchor.insert_paragraph_before(texto, style="Heading 1")
        except KeyError:
            detalle = anchor.insert_paragraph_before(texto)
        _add_bookmark(detalle, f"anexo-{index}", bookmark_id)
        bookmark_id += 1

        descripcion = str(anexo.get("descripcion") or "").strip()
        if descripcion:
            # La descripción acepta el mismo HTML restringido que las
            # estrategias: negrita, cursiva, listas y saltos de línea.
            try:
                parrafo_descripcion = anchor.insert_paragraph_before(
                    style="Body Text"
                )
            except KeyError:
                parrafo_descripcion = anchor.insert_paragraph_before()
            html_to_docx_paragraphs(
                parrafo_descripcion,
                descripcion,
                placeholder="",
                layout="body",
            )

        archivos = anexo.get("archivos")
        if not archivos and anexo.get("ruta"):
            archivos = [
                {
                    "ruta": anexo.get("ruta"),
                    "content_type": anexo.get("content_type"),
                }
            ]
        for archivo in archivos or []:
            if str(archivo.get("content_type") or "").startswith("image/"):
                _insertar_imagen(anchor, archivo.get("ruta"), ancho)

        # Separación entre anexos: después del grupo completo (descripción e
        # imágenes) se deja una línea en blanco para que la última captura no
        # quede pegada al título del anexo siguiente. El último anexo no la
        # necesita.
        if index < len(anexos):
            separador = anchor.insert_paragraph_before()
            separador.paragraph_format.space_before = Pt(0)
            separador.paragraph_format.space_after = Pt(0)

    parent = sentinel.getparent()
    if parent is not None:
        parent.remove(sentinel)


def generate_report_docx(
    dataset: dict[str, Any],
    year: int | None = None,
    quarter: int | None = None,
    cutoff: date | None = None,
    estrategias: dict[str, str] | None = None,
    anexos: list[dict[str, Any]] | None = None,
) -> bytes:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Plantilla no encontrada: {TEMPLATE_PATH}")

    doc = Document(str(TEMPLATE_PATH))
    contexto = _periodo_contexto(dataset)
    year = year or int(contexto["anio"])
    if cutoff is not None:
        contexto["fin"] = cutoff
        contexto["fecha_corte"] = _format_date(cutoff)

    anclas = _anclas_anexos(anexos)
    _replace_periodo(doc, contexto, year)
    _write_indicator_table(doc, dataset)
    _update_narrative(doc, dataset, contexto, estrategias, anclas)
    # §5. ANEXOS (pre-firma): índice con solo rótulo y título.
    _write_annex_index(doc, anexos)
    # Post-firma: detalle con descripción, imágenes y marcadores anexo-N.
    detalle = _prepare_annex_detail(doc, incluir=bool(anexos))
    _write_annex_detail(doc, anexos, detalle)
    # Ninguna viñeta de plantilla debe quedar sin texto en el documento final.
    _remove_empty_list_paragraphs(doc)
    _trim_trailing_empty_paragraphs(doc)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()

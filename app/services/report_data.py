"""Datos del informe administrativo 2026.

Este modulo es la capa de composicion del informe. No vuelve a calcular los
indicadores institucionales: consume ``compute_indicadores_2026`` (fuente unica
de verdad) y agrega, en un solo lugar, los datos derivados que necesitan el
XLSX, el PDF, el CSV y la interfaz de exportacion.

Reglas que se conservan deliberadamente
---------------------------------------
* El universo institucional y el padron local NUNCA se suman.
* Un dato que no se puede calcular se representa con ``None``; no se convierte
  en cero.
* Las causas del analisis institucional salen de la hoja PENDIENTES del lote
  vigente. Los motivos del padron local solo se usan en los anexos locales y en
  la trazabilidad, claramente etiquetados.
* Las incidencias son asociaciones persona-causa. Una persona puede aportar a
  varias causas, por eso la suma de incidencias no equivale al total de personas
  pendientes unicas.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Act, ImportHistory, Learner, Requirement
from app.services import indicadores, parsers


INCIDENCE_NOTE = (
    "Un mismo aprendiz puede presentar más de una incidencia. Por esta razón, "
    "la suma de incidencias no necesariamente equivale al total de aprendices "
    "pendientes. En este informe cada causa cuenta personas únicas que la "
    "registran; la suma de las filas es el total de asociaciones persona-causa."
)
INCIDENCE_NOTE_SHORT = (
    "Un mismo aprendiz puede presentar más de una incidencia. Por esta razón, "
    "la suma de incidencias no necesariamente equivale al total de aprendices "
    "pendientes."
)

UNIVERSO_INSTITUCIONAL = "consolidado_institucional"
UNIVERSO_LOCAL = "padron_local"


def _pct(numerator: Any, denominator: Any) -> float | None:
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)):
        return None
    if denominator == 0:
        return None
    return round((numerator / denominator) * 100, 1)


def _clean_text(value: Any, fallback: str = "No disponible") -> str:
    text = str(value).strip() if value is not None else ""
    return text or fallback


def _status_info(learner: Learner) -> tuple[str, str | None]:
    """Etiqueta visible y alerta de calidad del estado local.

    Devuelve ``(etiqueta, alerta)``. Un estado vacio se muestra como
    ``Sin estado informado`` y un texto no reconocido se conserva tal cual para
    no inventar una clasificacion.
    """
    raw = learner.certification_status
    normalized = parsers.normalize_certification_status(raw)
    if normalized == "certificados":
        return "Certificado", None
    if normalized == "pendiente":
        return "Pendiente", None
    if not parsers.normalize_text(raw):
        return "Sin estado informado", "Sin estado informado"
    return str(raw).strip(), "Estado no reconocido"


def _reason_fragments(reason: Any) -> list[str]:
    return parsers.normalize_motivo_fragments(reason)


def _matches_search(learner: Learner, search: str) -> bool:
    term = parsers.normalize_text(search)
    if not term:
        return True
    haystack = " ".join(
        str(value or "")
        for value in (
            learner.identification,
            learner.name,
            learner.program,
            learner.group_code,
            learner.certification_status,
        )
    )
    return term in parsers.normalize_text(haystack)


def _matches_status(learner: Learner, status: str) -> bool:
    key = parsers.normalize_text(status)
    if not key:
        return True
    raw_text = parsers.normalize_text(learner.certification_status)
    if key in {"sin estado", "sin estado informado"}:
        return not raw_text
    learner_key = parsers.normalize_certification_status(learner.certification_status)
    filter_key = parsers.normalize_certification_status(status)
    return learner_key == filter_key or raw_text == key


def _learner_act_text(learner: Learner) -> str:
    value = learner.act_number
    if value is None:
        return "No disponible"
    text = str(value).strip()
    if not text or not any(character.isdigit() for character in text):
        return "No disponible"
    return text


def _local_cause_rows(pending_rows: list[dict[str, Any]], pending_total: int) -> list[dict[str, Any]]:
    reasons = [
        row.get("_motivo_raw")
        for row in pending_rows
        if row.get("_motivo_raw") is not None
    ]
    counts = parsers.aggregate_causas(reasons)
    total_incidencias = sum(counts.values())
    rows = []
    for cause, quantity in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold())):
        rows.append(
            {
                "motivo": cause,
                "personas": quantity,
                "porcentaje_personas": _pct(quantity, pending_total),
                "porcentaje_incidencias": _pct(quantity, total_incidencias),
            }
        )
    return rows


def build_local_universe(
    session: Session,
    *,
    search: str = "",
    status: str = "",
) -> dict[str, Any]:
    """Construye el universo local (padron SQLite) sin mezclarlo con ACTAS.

    ``search`` y ``status`` permiten exportar la vista filtrada actual del
    listado de aprendices. El filtro solo afecta este universo.
    """
    learners = list(
        session.scalars(select(Learner).order_by(Learner.name.asc(), Learner.identification.asc())).all()
    )
    filtered_learners = [
        learner
        for learner in learners
        if _matches_search(learner, search) and _matches_status(learner, status)
    ]

    status_counts: Counter[str] = Counter()
    learner_rows: list[dict[str, Any]] = []
    pending_rows: list[dict[str, Any]] = []
    sin_estado = 0
    unrecognized: Counter[str] = Counter()

    for learner in filtered_learners:
        label, alert = _status_info(learner)
        status_counts[label] += 1
        if alert == "Sin estado informado":
            sin_estado += 1
        elif alert == "Estado no reconocido":
            unrecognized[str(learner.certification_status).strip()] += 1

        act_text = _learner_act_text(learner)
        learner_rows.append(
            {
                "Documento": parsers.clean_identification(learner.identification) or "Sin documento",
                "Nombre": _clean_text(learner.name, "Sin nombre informado"),
                "Programa": _clean_text(learner.program),
                "Ficha": _clean_text(learner.group_code),
                "Estado": label,
                "Acta": act_text,
                "Alerta de calidad": alert or "",
            }
        )

        if label == "Pendiente":
            fragments = _reason_fragments(learner.non_certification_reason)
            has_reason = bool(fragments)
            pending_rows.append(
                {
                    "Documento": parsers.clean_identification(learner.identification) or "Sin documento",
                    "Nombre": _clean_text(learner.name, "Sin nombre informado"),
                    "Programa": _clean_text(learner.program),
                    "Ficha": _clean_text(learner.group_code),
                    "Motivo": (
                        str(learner.non_certification_reason).strip()
                        if has_reason
                        else "Sin motivo informado"
                    ),
                    "Estado": "Pendiente",
                    "Alerta de calidad": "" if has_reason else "Sin motivo informado",
                    "_motivo_raw": learner.non_certification_reason if has_reason else None,
                }
            )

    pending_total = len(pending_rows)
    pending_sin_motivo = sum(1 for row in pending_rows if not row.get("_motivo_raw"))
    local_causes = _local_cause_rows(pending_rows, pending_total)
    for row in pending_rows:
        row.pop("_motivo_raw", None)

    requirements_total = session.scalar(
        select(func.count()).select_from(Requirement)
    ) or 0
    requirements_pending = session.scalar(
        select(func.count())
        .select_from(Requirement)
        .where(func.lower(func.coalesce(Requirement.status, "")) == "pendiente")
    ) or 0
    acts = list(session.scalars(select(Act).order_by(Act.number.asc())).all())
    acts_sin_fecha = sum(1 for act in acts if not act.act_date)
    acts_sin_tipo = sum(1 for act in acts if not act.act_type)

    return {
        "universo": UNIVERSO_LOCAL,
        "etiqueta": "Padrón local (SQLite)",
        "total_aprendices": len(filtered_learners),
        "total_aprendices_sin_filtro": len(learners),
        "filtro": {
            "aplicado": bool(parsers.normalize_text(search) or parsers.normalize_text(status)),
            "search": search or "",
            "status": status or "",
        },
        "certificados": sum(1 for learner in filtered_learners if _status_info(learner)[0] == "Certificado"),
        "pendientes": pending_total,
        "sin_estado": sin_estado,
        "sin_estado_porcentaje": _pct(sin_estado, len(filtered_learners)),
        "estados_no_reconocidos": [
            {"estado": key, "cantidad": value}
            for key, value in sorted(unrecognized.items(), key=lambda item: (-item[1], item[0]))
        ],
        "por_estado": [
            {"estado": key, "cantidad": value}
            for key, value in sorted(status_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        "pendientes_sin_motivo": pending_sin_motivo,
        "pendientes_sin_motivo_porcentaje": _pct(pending_sin_motivo, pending_total),
        "causas": local_causes,
        "total_incidencias_causas": sum(row["personas"] for row in local_causes),
        "requisitos_registrados": requirements_total,
        "requisitos_pendientes": requirements_pending,
        "actas_registradas": len(acts),
        "actas_sin_fecha": acts_sin_fecha,
        "actas_sin_tipo": acts_sin_tipo,
        "learners_rows": learner_rows,
        "pending_rows": pending_rows,
    }


def _build_causes(ind: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for item in ind.get("motivos") or []:
        quantity = item.get("cantidad")
        rows.append(
            {
                "motivo": item.get("motivo"),
                "personas": item.get("personas", quantity),
                "porcentaje_personas": item.get("porcentaje_personas"),
                "porcentaje_incidencias": item.get("porcentaje"),
            }
        )
    return {
        "universo": UNIVERSO_INSTITUCIONAL,
        "total_incidencias": ind.get("total_incidencias_causas"),
        "aprendices_pendientes_unicos": ind.get("total_pendientes"),
        "personas_pendientes_registradas": ind.get("pendientes_unicos_total"),
        "aprendices_con_varios_motivos": ind.get("aprendices_con_causas_multiples"),
        "aprendices_sin_motivo": ind.get("aprendices_pendientes_sin_motivo"),
        "porcentaje_sin_motivo": ind.get("porcentaje_pendientes_sin_motivo"),
        "motivos": rows,
    }


def _build_monthly(ind: dict[str, Any]) -> dict[str, Any]:
    monthly = dict(ind.get("certificados_por_mes") or {})
    months = [dict(item) for item in monthly.get("meses") or []]
    total = monthly.get("total")
    if isinstance(total, (int, float)) and total > 0:
        running = 0
        for item in months:
            value = item.get("certificados")
            item["porcentaje"] = _pct(value, total)
            running += value if isinstance(value, int) else 0
            item["acumulado"] = running
    else:
        for item in months:
            item["porcentaje"] = None
            item["acumulado"] = None

    values = [
        item.get("certificados")
        for item in months
        if isinstance(item.get("certificados"), int)
    ]
    max_item = None
    min_item = None
    if values:
        max_value = max(values)
        min_value = min(values)
        max_items = [item for item in months if item.get("certificados") == max_value]
        min_items = [item for item in months if item.get("certificados") == min_value]
        max_item = {
            "mes": max_items[0].get("etiqueta") or max_items[0].get("mes"),
            "certificados": max_value,
            "empates": [item.get("etiqueta") or item.get("mes") for item in max_items],
        }
        min_item = {
            "mes": min_items[0].get("etiqueta") or min_items[0].get("mes"),
            "certificados": min_value,
            "empates": [item.get("etiqueta") or item.get("mes") for item in min_items],
        }

    monthly["meses"] = months
    monthly["resumen"] = {
        "total": total,
        "mes_mayor": max_item,
        "mes_menor": min_item,
        "meses_con_certificados": sum(1 for value in values if value > 0),
        "promedio_mensual": (
            round(total / len(months), 1)
            if isinstance(total, (int, float)) and months
            else None
        ),
    }
    return monthly


def _build_actas(ind: dict[str, Any]) -> dict[str, Any]:
    items = [dict(item) for item in (ind.get("actas_periodo") or ind.get("ultimas_actas") or [])]
    for item in items:
        if "metadata_completa" not in item:
            item["metadata_completa"] = bool(item.get("act_date") and item.get("act_type"))
    total = len(items)
    asociados = sum(
        item.get("aprendices_count")
        for item in items
        if isinstance(item.get("aprendices_count"), int)
    )
    return {
        "universo": UNIVERSO_INSTITUCIONAL,
        "items": items,
        "total": total,
        "con_detalle": sum(1 for item in items if item.get("act_id") is not None),
        "sin_registro_local": sum(1 for item in items if item.get("act_id") is None),
        "certificados_asociados": asociados,
        "con_fecha": sum(1 for item in items if item.get("act_date")),
        "con_tipo": sum(1 for item in items if item.get("act_type")),
        "sin_metadatos": sum(1 for item in items if not item.get("metadata_completa")),
    }


def _build_quality(
    *,
    ind: dict[str, Any],
    local: dict[str, Any],
    causes: dict[str, Any],
    monthly: dict[str, Any],
    actas: dict[str, Any],
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    def add(
        code: str,
        severity: str,
        title: str,
        detail: str,
        *,
        quantity: Any = None,
        percentage: Any = None,
        universe: str = UNIVERSO_INSTITUCIONAL,
    ) -> None:
        alerts.append(
            {
                "codigo": code,
                "severidad": severity,
                "titulo": title,
                "detalle": detail,
                "cantidad": quantity,
                "porcentaje": percentage,
                "universo": universe,
            }
        )

    if not ind.get("datos_suficientes"):
        add(
            "sin_datos",
            "alta",
            "No hay datos institucionales suficientes",
            "Importe ACTAS 2026 (certificados, pendientes, complementaria y meta) "
            "para calcular los indicadores del informe.",
            universe=UNIVERSO_INSTITUCIONAL,
        )

    if local.get("sin_estado", 0) > 0:
        add(
            "sin_estado_local",
            "alta",
            "Aprendices sin estado informado",
            f"{local['sin_estado']} registros del padrón local no tienen estado de "
            "certificación. Se conservan y se muestran como «Sin estado informado»; "
            "no se clasifican como certificados ni como pendientes.",
            quantity=local["sin_estado"],
            percentage=local.get("sin_estado_porcentaje"),
            universe=UNIVERSO_LOCAL,
        )

    if causes.get("aprendices_sin_motivo") not in (None, 0):
        add(
            "sin_motivo_institucional",
            "alta",
            "Pendientes sin motivo informado",
            f"{causes['aprendices_sin_motivo']} personas pendientes del consolidado "
            "no traen motivo de no certificación. Se mantienen como «Sin motivo "
            "informado»; no se les asigna una causa artificial.",
            quantity=causes["aprendices_sin_motivo"],
            percentage=causes.get("porcentaje_sin_motivo"),
            universe=UNIVERSO_INSTITUCIONAL,
        )

    if local.get("pendientes_sin_motivo", 0) > 0:
        add(
            "sin_motivo_local",
            "media",
            "Pendientes locales sin motivo",
            f"{local['pendientes_sin_motivo']} pendientes del padrón local no "
            "tienen motivo registrado. Se muestran como «Sin motivo informado» en "
            "el anexo local.",
            quantity=local["pendientes_sin_motivo"],
            percentage=local.get("pendientes_sin_motivo_porcentaje"),
            universe=UNIVERSO_LOCAL,
        )

    excluded = ind.get("certificados_fuera_de_periodo")
    if excluded:
        add(
            "fuera_periodo",
            "media",
            "Certificados fuera del periodo",
            f"{excluded} certificados del consolidado no se contaron porque su mes "
            "de certificación está fuera de enero-septiembre de 2026.",
            quantity=excluded,
            universe=UNIVERSO_INSTITUCIONAL,
        )

    conflicts = ind.get("conflictos") or {}
    if conflicts.get("detectados"):
        add(
            "conflictos",
            "alta" if conflicts.get("sin_resolver") else "media",
            "Conflictos certificado/pendiente",
            f"{conflicts.get('detectados', 0)} documentos figuran en CERTIFICADOS y "
            f"PENDIENTES. Resueltos: {conflicts.get('resueltos', 0)}; sin resolver: "
            f"{conflicts.get('sin_resolver', 0)}. Los conflictos sin resolver se "
            "excluyen de ambos universos.",
            quantity=conflicts.get("detectados"),
            universe=UNIVERSO_INSTITUCIONAL,
        )

    meta_faltante = [
        item.get("category_label")
        for item in ind.get("metricas") or []
        if item.get("meta") is None
    ]
    if meta_faltante:
        add(
            "meta_faltante",
            "media",
            "Metas no disponibles",
            "No se puede calcular el avance de: " + ", ".join(meta_faltante) + ".",
            quantity=len(meta_faltante),
            universe=UNIVERSO_INSTITUCIONAL,
        )

    sin_clasificar = ind.get("sin_clasificar") or {}
    unclassified = (sin_clasificar.get("certificados") or 0) + (
        sin_clasificar.get("pendientes") or 0
    )
    if unclassified:
        add(
            "sin_clasificar",
            "media",
            "Registros sin categoría misional",
            f"{unclassified} registros tienen un NIVEL sin regla de clasificación. "
            "No se asignaron por defecto a ninguna categoría.",
            quantity=unclassified,
            universe=UNIVERSO_INSTITUCIONAL,
        )

    if actas.get("sin_metadatos"):
        add(
            "actas_sin_metadatos",
            "baja",
            "Actas sin fecha o tipo",
            f"{actas['sin_metadatos']} de {actas.get('total', 0)} actas no tienen "
            "fecha y tipo completos en el módulo de Actas. Se muestran como «No "
            "disponible»; no se construyen fechas a partir del número de acta.",
            quantity=actas["sin_metadatos"],
            universe=UNIVERSO_INSTITUCIONAL,
        )

    if local.get("total_aprendices_sin_filtro", 0) == 0:
        add(
            "sin_padron_local",
            "baja",
            "Padrón local vacío",
            "No hay aprendices en la base local. Los anexos locales se generan sin "
            "filas, sin afectar los indicadores institucionales.",
            quantity=0,
            universe=UNIVERSO_LOCAL,
        )

    for item in local.get("estados_no_reconocidos") or []:
        add(
            "estado_no_reconocido",
            "media",
            "Estado local no reconocido",
            f"{item['cantidad']} aprendices tienen el estado «{item['estado']}», que "
            "no está dentro de las variantes documentadas. Se conserva el texto y se "
            "marca para revisión.",
            quantity=item["cantidad"],
            universe=UNIVERSO_LOCAL,
        )

    order = {"alta": 0, "media": 1, "baja": 2}
    alerts.sort(key=lambda item: (order.get(item["severidad"], 3), -(item.get("cantidad") or 0)))
    return alerts


def _reconcile_certificates(
    local: dict[str, Any], summary: dict[str, Any], monthly: dict[str, Any]
) -> dict[str, Any]:
    local_count = local.get("certificados")
    institutional = summary.get("certificados_personas")
    difference = (
        local_count - institutional
        if isinstance(local_count, int) and isinstance(institutional, int)
        else None
    )
    excluded = monthly.get("fuera_de_periodo")
    explained = (
        difference is not None and isinstance(excluded, int) and difference == excluded
    )
    if difference is None:
        explanation = (
            "No se puede establecer la diferencia porque falta uno de los dos "
            "universos. No se fuerza una igualdad."
        )
    elif difference == 0:
        explanation = (
            "Los certificados locales y los institucionales coinciden en cantidad, "
            "pero siguen siendo universos distintos: el local es el padrón y el "
            "institucional es el consolidado deduplicado del periodo."
        )
    elif explained:
        explanation = (
            f"La diferencia de {difference} coincide con los {excluded} certificados "
            "excluidos por estar fuera del periodo enero-septiembre de 2026. Es una "
            "diferencia de alcance, no un error de cálculo; no se suman los universos."
        )
    else:
        explanation = (
            f"La diferencia de {difference} no queda completamente explicada por los "
            f"{excluded if isinstance(excluded, int) else 'datos'} certificados fuera "
            "del periodo. Puede responder a deduplicación por documento, estados "
            "locales no equivalentes o registros de otros periodos. Los universos no "
            "son comparables y no se fuerza su igualdad."
        )
    return {
        "certificados_locales": local_count,
        "certificados_institucionales": institutional,
        "diferencia": difference,
        "certificados_excluidos_periodo": excluded,
        "coincide_con_exclusion": explained,
        "explicacion": explanation,
        "universos_comparables": False,
    }


def _cause_comparison(
    causes: dict[str, Any], local: dict[str, Any]
) -> list[dict[str, Any]]:
    institutional = {
        row.get("motivo"): row.get("personas")
        for row in causes.get("motivos") or []
        if row.get("motivo")
    }
    local_counts = {
        row.get("motivo"): row.get("personas")
        for row in local.get("causas") or []
        if row.get("motivo")
    }
    rows = []
    for cause in sorted(set(institutional) | set(local_counts), key=str.casefold):
        left = institutional.get(cause)
        right = local_counts.get(cause)
        rows.append(
            {
                "Causa": cause,
                "Personas institucional": left,
                "Personas local": right,
                "Diferencia (local - institucional)": (
                    right - left
                    if isinstance(left, int) and isinstance(right, int)
                    else None
                ),
            }
        )
    return rows


def _build_traceability(
    *,
    ind: dict[str, Any],
    local: dict[str, Any],
    summary: dict[str, Any],
    causes: dict[str, Any],
    monthly: dict[str, Any],
    actas: dict[str, Any],
    advertencias: list[str],
) -> dict[str, Any]:
    reconciliation = _reconcile_certificates(local, summary, monthly)
    cause_comparison = _cause_comparison(causes, local)
    sources = [
        {
            "nombre": "ACTAS 2026 · CERTIFICADOS",
            "detalle": "Certificados de personas del lote vigente. Se filtran al periodo enero-septiembre de 2026 y se deduplican por documento.",
            "universo": UNIVERSO_INSTITUCIONAL,
        },
        {
            "nombre": "ACTAS 2026 · PENDIENTES",
            "detalle": "Personas pendientes y motivo de no certificación. Es la fuente única del análisis de causas institucional.",
            "universo": UNIVERSO_INSTITUCIONAL,
        },
        {
            "nombre": "ACTAS 2026 · COMPLEMENTARIA",
            "detalle": "Certificados agregados de formación complementaria. No son personas y no entran en la efectividad.",
            "universo": UNIVERSO_INSTITUCIONAL,
        },
        {
            "nombre": "ACTAS 2026 · META / referencia institucional",
            "detalle": "Metas anuales institucionales. Si una meta no está disponible se muestra «No calculable», no cero.",
            "universo": UNIVERSO_INSTITUCIONAL,
        },
        {
            "nombre": "Padrón local SQLite",
            "detalle": "Aprendices, estados locales, requisitos, actas y seguimiento. Se usa solo en anexos locales y controles de calidad.",
            "universo": UNIVERSO_LOCAL,
        },
    ]
    return {
        "universos": [
            {
                "nombre": "Institucional",
                "descripcion": "Consolidado ACTAS 2026 del lote vigente. Certificados, pendientes, metas y formación complementaria.",
                "uso": "Indicadores, categorías, evolución mensual, análisis de causas y gestión documental.",
            },
            {
                "nombre": "Local",
                "descripcion": "Padrón de aprendices almacenado en SQLite y sus requisitos, actas y seguimiento.",
                "uso": "Anexos de aprendices y pendientes, controles de estado y motivo faltante.",
            },
        ],
        "fuentes": sources,
        "periodo": {
            "etiqueta": ind.get("periodo"),
            "inicio": ind.get("periodo_inicio"),
            "fin": ind.get("periodo_fin"),
            "criterio": (
                "CERTIFICADOS se filtra por MES DE CERTIFICACIÓN entre enero y "
                "septiembre de 2026. PENDIENTES es un censo de personas que siguen "
                "sin certificar y no se filtra por mes."
            ),
        },
        "deduplicacion": [
            "Los indicadores institucionales deduplican por documento normalizado dentro de cada hoja (CERTIFICADOS y PENDIENTES).",
            "Si un documento aparece en CERTIFICADOS y PENDIENTES, se aplica la resolución manual guardada. Sin resolución, se excluye de ambos universos y se informa en advertencias.",
            "Los certificados fuera del periodo no se cuentan y se informan como exclusión.",
            "El padrón local tiene una fila por identificación (restricción UNIQUE); sus motivos pueden diferir de la hoja PENDIENTES porque la actualización local conserva la última versión importada.",
            "Las causas institucionales se cuentan una vez por persona y causa; una persona con varias causas suma en varias filas. La suma de filas es el total de incidencias (asociaciones persona-causa).",
        ],
        "clasificacion": [
            "La categoría misional se deriva del NIVEL de formación con reglas documentadas. Un nivel no reconocido queda sin clasificar y no se asigna por defecto.",
            "Formación complementaria se informa separada: son certificados agregados, no personas, y no se usan como denominador de efectividad.",
            "El estado local vacío se muestra como «Sin estado informado»; no se clasifica como certificado ni como pendiente.",
            "Un pendiente sin motivo se muestra como «Sin motivo informado»; no se le asigna una causa.",
        ],
        "exclusiones": [
            "Certificados con mes de certificación fuera de enero-septiembre de 2026.",
            "Certificados sin número de documento: no se pueden deduplicar ni identificar.",
            "Documentos en conflicto sin resolución manual: excluidos de certificados y pendientes.",
            "Registros con NIVEL no clasificable: se informan, pero no se suman a una categoría.",
        ],
        "conciliacion_certificados": reconciliation,
        "comparacion_causas": cause_comparison,
        "nota_causas": (
            "La hoja «Causas» y la hoja «IncidenciasPendientes» del informe anterior "
            "no eran equivalentes: la primera se calculaba con la hoja PENDIENTES del "
            "consolidado y la segunda con los motivos del padrón local. Además, la "
            "deduplicación institucional conserva la primera aparición del documento, "
            "mientras que el padrón local conserva la última versión importada. Por eso "
            "podían aparecer diferencias como 58 frente a 57 o 13 frente a 12. En este "
            "informe el análisis institucional usa una sola fuente (PENDIENTES) y los "
            "motivos locales solo aparecen en el anexo local, claramente etiquetados."
        ),
        "nota_incidencias": INCIDENCE_NOTE,
        "limitaciones": [
            "El informe no crea fechas, tipos de acta ni causas que no estén en las fuentes.",
            "Las metas ausentes dejan el avance y la brecha como «No calculable».",
            "La base local no sustituye el consolidado institucional ni se suma a sus totales.",
            "La comparación entre certificados locales e institucionales es informativa; no se usa para calcular indicadores.",
            "La formación complementaria no se incluye en la efectividad de personas.",
        ],
        "advertencias": list(advertencias),
        "actas": {
            "total": actas.get("total"),
            "sin_metadatos": actas.get("sin_metadatos"),
            "nota": (
                "La hoja CERTIFICADOS solo informa el número de acta. La fecha y el "
                "tipo se completan únicamente si el acta existe en el módulo de Actas; "
                "si no, se muestran como «No disponible». No se construyen fechas a "
                "partir del número."
            ),
        },
    }


def consolidate_report_dataset(
    session: Session,
    *,
    year: int | None = None,
    local_search: str = "",
    local_status: str = "",
) -> dict[str, Any]:
    """Arma el payload completo del informe administrativo 2026."""
    if year is None:
        year = 2026

    ind = indicadores.compute_indicadores_2026(session)
    lote_id = ind.get("lote_vigente_id")
    file_name = None
    if lote_id is not None:
        file_name = session.scalar(
            select(ImportHistory.file_name).where(ImportHistory.id == lote_id)
        )

    advertencias: list[str] = list(ind.get("advertencias") or [])
    if lote_id is None:
        advertencias.insert(0, "Sin consolidado vigente. Importa ACTAS 2026.")
    if year != 2026:
        advertencias.insert(
            0,
            "El dataset de informe v1 cubre unicamente el periodo Ene-Sep 2026; "
            "el año solicitado no modifica el cálculo.",
        )

    local = build_local_universe(
        session, search=local_search, status=local_status
    )
    causes = _build_causes(ind)
    monthly = _build_monthly(ind)
    actas = _build_actas(ind)

    total_meta = ind.get("total_meta")
    total_certificados = ind.get("total_certificados")
    brecha_total = None
    if isinstance(total_meta, int) and isinstance(total_certificados, int):
        brecha_total = max(0, total_meta - total_certificados)

    summary = {
        "meta_total": total_meta,
        "total_meta": total_meta,
        "certificados_personas": ind.get("certificados_personas"),
        "certificados_complementaria": ind.get("certificados_complementaria"),
        "pendientes_personas": ind.get("pendientes_personas"),
        "total_certificados": total_certificados,
        "total_pendientes": ind.get("total_pendientes"),
        "avance_global": ind.get("avance_global"),
        "efectividad_global": ind.get("efectividad_global"),
        "brecha_total": brecha_total,
        "conflictos": ind.get("conflictos"),
        "conflictos_certificados_pendientes": ind.get("conflictos_certificados_pendientes"),
        "certificados_fuera_de_periodo": ind.get("certificados_fuera_de_periodo"),
        "certificados_excluidos_periodo": ind.get("certificados_fuera_de_periodo"),
        "registros_sin_clasificar": ind.get("sin_clasificar"),
        "total_incidencias_causas": ind.get("total_incidencias_causas"),
        "aprendices_pendientes_unicos": ind.get("total_pendientes"),
        "aprendices_pendientes_registrados": ind.get("pendientes_unicos_total"),
        "aprendices_sin_motivo": ind.get("aprendices_pendientes_sin_motivo"),
        "porcentaje_sin_motivo": ind.get("porcentaje_pendientes_sin_motivo"),
        "aprendices_con_varios_motivos": ind.get("aprendices_con_causas_multiples"),
        "sin_estado_local": local.get("sin_estado"),
        "porcentaje_sin_estado_local": local.get("sin_estado_porcentaje"),
        "pendientes_sin_motivo_local": local.get("pendientes_sin_motivo"),
        "porcentaje_sin_motivo_local": local.get("pendientes_sin_motivo_porcentaje"),
        "actas_total": actas.get("total"),
        "actas_sin_metadatos": actas.get("sin_metadatos"),
        "datos_suficientes": ind.get("datos_suficientes"),
        "universo": UNIVERSO_INSTITUCIONAL,
        "universo_efectividad": ind.get("universo_efectividad"),
    }

    quality = _build_quality(
        ind=ind, local=local, causes=causes, monthly=monthly, actas=actas
    )
    high_alerts = [item for item in quality if item["severidad"] == "alta"]
    summary["alertas_alta"] = len(high_alerts)
    summary["alertas_total"] = len(quality)

    traceability = _build_traceability(
        ind=ind,
        local=local,
        summary=summary,
        causes=causes,
        monthly=monthly,
        actas=actas,
        advertencias=advertencias,
    )

    payload = {
        "dataset_version": "2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "periodo": ind.get("periodo"),
        "periodo_inicio": ind.get("periodo_inicio"),
        "periodo_fin": ind.get("periodo_fin"),
        "period": {
            "label": ind.get("periodo"),
            "start": ind.get("periodo_inicio"),
            "end": ind.get("periodo_fin"),
        },
        "year": year,
        "source": "consolidado_lote_vigente",
        "universe": UNIVERSO_INSTITUCIONAL,
        "import_id": lote_id,
        "lote_vigente_id": lote_id,
        "file_name": file_name,
        "fuente_metas": ind.get("fuente_metas"),
        "fecha_corte_referencia": ind.get("fecha_corte_referencia"),
        "datos_suficientes": ind.get("datos_suficientes"),
        "advertencias": advertencias,
        "warning": " | ".join(advertencias) if advertencias else None,
        "resumen_ejecutivo": summary,
        "universo_institucional": {
            "universo": UNIVERSO_INSTITUCIONAL,
            "etiqueta": "Consolidado institucional ACTAS 2026",
            "resumen": summary,
            "metricas": ind.get("metricas") or [],
            "causas": causes,
            "certificados_por_mes": monthly,
            "actas": actas,
            "sin_clasificar": ind.get("sin_clasificar"),
            "complementaria_canales": ind.get("complementaria_canales"),
            "referencia_institucional": ind.get("referencia_institucional"),
            "conflictos": ind.get("conflictos"),
        },
        "universo_local": local,
        "desglose_por_categoria": ind.get("metricas") or [],
        "metricas": ind.get("metricas") or [],
        "certificados_por_mes": monthly,
        "causas_no_certificacion": causes,
        "motivos": causes.get("motivos") or [],
        "actas": actas,
        "ultimas_actas": ind.get("ultimas_actas") or [],
        "gestion_documental": actas,
        "calidad": {"alertas": quality},
        "trazabilidad": traceability,
        "sin_clasificar": ind.get("sin_clasificar"),
        "complementaria_canales": ind.get("complementaria_canales"),
        "referencia_institucional": ind.get("referencia_institucional"),
        "conflictos": ind.get("conflictos"),
    }
    # Aliases de compatibilidad con consumidores anteriores del dataset v1.
    payload["anexos"] = {
        "aprendices": local.get("learners_rows") or [],
        "pendientes": local.get("pending_rows") or [],
    }
    return payload


__all__ = [
    "INCIDENCE_NOTE",
    "INCIDENCE_NOTE_SHORT",
    "UNIVERSO_INSTITUCIONAL",
    "UNIVERSO_LOCAL",
    "build_local_universe",
    "consolidate_report_dataset",
]

"""Fachada de exportacion del modulo de informes 2026.

Este modulo no recalcula indicadores ni datasets: delega en
``report_data.consolidate_report_dataset`` (fuente unica) y en los generadores
``report_xlsx`` y ``report_pdf``. Su responsabilidad es:

* exponer el catalogo de tipos de informe y los formatos disponibles;
* validar parametros (tipo, formato, alcance, detalle, filtros locales);
* armar el dataset adecuado para cada tipo y alcance;
* generar CSV, XLSX y PDF con nombres de archivo consistentes;
* conservar compatibilidad con consumidores anteriores (``general``,
  ``consolidate_report_dataset``, ``export_consolidated_*``).

Reglas de alcance
-----------------
* Los informes institucionales (consolidado, ejecutivo, causas, actas) solo
  admiten alcance ``consolidado``.
* Los informes locales (aprendices, pendientes) admiten ``consolidado`` (todo
  el padron) o ``filtrado`` (busqueda y estado actuales del listado).
"""

from __future__ import annotations

from datetime import date
from io import BytesIO, StringIO
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Learner
from app.services import report_data
from app.services.report_data import consolidate_report_dataset
from app.services.report_pdf import build_consolidated_pdf, build_report_pdf
from app.services.report_xlsx import build_consolidated_xlsx, build_report_xlsx

REPORT_TYPES = {
    "consolidado": "Informe consolidado de certificación",
    "general": "Informe consolidado de certificación",
    "ejecutivo": "Informe ejecutivo",
    "aprendices": "Anexo de aprendices",
    "pendientes": "Anexo de pendientes",
    "causas": "Análisis de pendientes y causas",
    "actas": "Gestión documental y actas",
}

REPORT_DESCRIPTIONS = {
    "consolidado": "Reúne resumen, categorías, evolución mensual, pendientes, gestión documental y anexos locales cuando el detalle es completo.",
    "ejecutivo": "Resumen ejecutivo y trazabilidad metodológica. Ideal para lectura directiva.",
    "aprendices": "Detalle del padrón local de aprendices, estados y actas. Admite vista filtrada.",
    "pendientes": "Pendientes locales, causas institucionales y trazabilidad. Admite vista filtrada.",
    "causas": "Causas de no certificación del universo institucional.",
    "actas": "Actas del periodo, aprendices asociados y metadatos disponibles.",
}

REPORT_SCOPES = {
    "consolidado": ["consolidado"],
    "general": ["consolidado"],
    "ejecutivo": ["consolidado"],
    "causas": ["consolidado"],
    "actas": ["consolidado"],
    "aprendices": ["consolidado", "filtrado"],
    "pendientes": ["consolidado", "filtrado"],
}

REPORT_DETAILS = {
    "consolidado": ["completo", "ejecutivo"],
    "general": ["completo", "ejecutivo"],
    "ejecutivo": ["completo"],
    "causas": ["completo"],
    "actas": ["completo"],
    "aprendices": ["completo"],
    "pendientes": ["completo"],
}

REPORT_FORMATS = {
    "consolidado": ["pdf", "xlsx", "docx"],
    "general": ["pdf", "xlsx", "docx"],
    "ejecutivo": ["pdf", "xlsx", "csv"],
    "aprendices": ["pdf", "xlsx", "csv"],
    "pendientes": ["pdf", "xlsx", "csv"],
    "causas": ["pdf", "xlsx", "csv"],
    "actas": ["pdf", "xlsx", "csv"],
}


def available_report_formats(report_type: str) -> list[str]:
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Tipo de informe no soportado: {report_type}.")
    return list(REPORT_FORMATS[report_type])


def report_catalog() -> list[dict[str, Any]]:
    return [
        {
            "type": report_type,
            "name": REPORT_TYPES[report_type],
            "description": REPORT_DESCRIPTIONS[report_type],
            "formats": available_report_formats(report_type),
            "scopes": REPORT_SCOPES[report_type],
            "details": REPORT_DETAILS[report_type],
        }
        for report_type in REPORT_TYPES
        if report_type != "general"
    ]


# ---------------------------------------------------------------------------
# Compatibilidad con la API anterior
# ---------------------------------------------------------------------------


def consolidate_report_dataset_v1(
    session: Session,
    *,
    year: int | None = None,
    trimestre: Any = None,
    modo: Any = None,
) -> dict[str, Any]:
    return consolidate_report_dataset(
        session, year=year, trimestre=trimestre, modo=modo
    )


# ---------------------------------------------------------------------------
# Dataset por tipo y alcance
# ---------------------------------------------------------------------------


def _normalize_scope(report_type: str, scope: str | None) -> str:
    scope = (scope or "consolidado").strip().lower()
    if scope not in {"consolidado", "filtrado"}:
        raise ValueError(f"Alcance no soportado: {scope}.")
    if scope == "filtrado" and report_type not in {"aprendices", "pendientes"}:
        raise ValueError("El alcance filtrado solo aplica a informes locales.")
    return scope


def _normalize_detail(report_type: str, detail: str | None) -> str:
    detail = (detail or "completo").strip().lower()
    if detail not in {"completo", "ejecutivo"}:
        raise ValueError(f"Nivel de detalle no soportado: {detail}.")
    if detail == "ejecutivo" and report_type not in {"consolidado", "general"}:
        raise ValueError("El detalle ejecutivo solo aplica al informe consolidado.")
    return detail


def _dataset_for_report(
    session: Session,
    report_type: str,
    year: int | None = None,
    *,
    scope: str = "consolidado",
    detail: str = "completo",
    search: str = "",
    status: str = "",
    trimestre: Any = None,
    modo: Any = None,
) -> dict[str, Any]:
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Tipo de informe no soportado: {report_type}.")

    scope = _normalize_scope(report_type, scope)
    detail = _normalize_detail(report_type, detail)

    local_search = search if (scope == "filtrado" and report_type in {"aprendices", "pendientes"}) else ""
    local_status = status if (scope == "filtrado" and report_type in {"aprendices", "pendientes"}) else ""

    dataset = consolidate_report_dataset(
        session,
        year=year,
        local_search=local_search,
        local_status=local_status,
        trimestre=trimestre,
        modo=modo,
    )
    # Compatibilidad con consumidores que esperan el alias ``general``.
    dataset.setdefault("_report_type", report_type)
    dataset.setdefault("_detail", detail)
    dataset.setdefault("_scope", scope)
    return dataset


# ---------------------------------------------------------------------------
# Filas para CSV
# ---------------------------------------------------------------------------


def _csv_rows(dataset: dict[str, Any], report_type: str) -> tuple[str, list[dict[str, Any]], list[str]]:
    if report_type in {"consolidado", "general"}:
        summary = dataset.get("resumen_ejecutivo") or {}
        rows = [
            {"Indicador": "Periodo", "Valor": dataset.get("periodo")},
            {"Indicador": "Meta institucional", "Valor": summary.get("meta_total")},
            {"Indicador": "Certificados personas", "Valor": summary.get("certificados_personas")},
            {"Indicador": "Certificados complementaria", "Valor": summary.get("certificados_complementaria")},
            {"Indicador": "Pendientes personas", "Valor": summary.get("pendientes_personas")},
            {"Indicador": "Avance global %", "Valor": summary.get("avance_global")},
            {"Indicador": "Efectividad global %", "Valor": summary.get("efectividad_global")},
            {"Indicador": "Brecha", "Valor": summary.get("brecha_total")},
        ]
        return "Resumen", rows, ["Indicador", "Valor"]
    if report_type == "ejecutivo":
        summary = dataset.get("resumen_ejecutivo") or {}
        rows = [
            {"Indicador": "Periodo", "Valor": dataset.get("periodo")},
            {"Indicador": "Fuente", "Valor": dataset.get("source")},
            {"Indicador": "Archivo del lote vigente", "Valor": dataset.get("file_name")},
            {"Indicador": "Meta total", "Valor": summary.get("meta_total")},
            {"Indicador": "Certificados personas", "Valor": summary.get("certificados_personas")},
            {"Indicador": "Certificados complementaria", "Valor": summary.get("certificados_complementaria")},
            {"Indicador": "Pendientes personas", "Valor": summary.get("pendientes_personas")},
            {"Indicador": "Avance global %", "Valor": summary.get("avance_global")},
            {"Indicador": "Efectividad global %", "Valor": summary.get("efectividad_global")},
            {"Indicador": "Brecha total", "Valor": summary.get("brecha_total")},
        ]
        return "Ejecutivo", rows, ["Indicador", "Valor"]
    if report_type == "causas":
        causes = dataset.get("causas_no_certificacion") or {}
        rows = [
            {
                "Causa": item.get("motivo"),
                "Personas asociadas": item.get("personas"),
                "% sobre pendientes": item.get("porcentaje_personas"),
                "% sobre incidencias": item.get("porcentaje_incidencias"),
            }
            for item in causes.get("motivos") or []
        ]
        return "Causas", rows, ["Causa", "Personas asociadas", "% sobre pendientes", "% sobre incidencias"]
    if report_type == "actas":
        rows = [
            {
                "Acta": item.get("number"),
                "Aprendices": item.get("aprendices_count"),
                "Fecha": item.get("act_date"),
                "Tipo": item.get("act_type"),
                "Metadatos": (
                    "Completos"
                    if item.get("act_date") and item.get("act_type")
                    else ("Parciales" if item.get("act_date") or item.get("act_type") else "No disponibles")
                ),
                "Registro local": "Sí" if item.get("act_id") is not None else "No",
            }
            for item in (dataset.get("actas") or {}).get("items") or []
        ]
        return "Actas", rows, ["Acta", "Aprendices", "Fecha", "Tipo", "Metadatos", "Registro local"]
    if report_type == "aprendices":
        local = dataset.get("universo_local") or {}
        rows = list(local.get("learners_rows") or [])
        columns = ["Documento", "Nombre", "Programa", "Ficha", "Estado", "Acta", "Alerta de calidad"]
        return "Aprendices", rows, columns
    if report_type == "pendientes":
        local = dataset.get("universo_local") or {}
        rows = list(local.get("pending_rows") or [])
        columns = ["Documento", "Nombre", "Programa", "Ficha", "Motivo", "Estado", "Alerta de calidad"]
        return "Pendientes", rows, columns
    raise ValueError(f"Tipo de informe no soportado: {report_type}.")


# ---------------------------------------------------------------------------
# Exportaciones
# ---------------------------------------------------------------------------


def export_report_csv(
    session: Session,
    *,
    report_type: str = "general",
    year: int | None = None,
    scope: str = "consolidado",
    detail: str = "completo",
    search: str = "",
    status: str = "",
    trimestre: Any = None,
    modo: Any = None,
) -> bytes:
    if report_type == "consolidado" or report_type == "general":
        raise ValueError("El informe consolidado está disponible en PDF y XLSX.")
    dataset = _dataset_for_report(
        session,
        report_type,
        year,
        scope=scope,
        detail=detail,
        search=search,
        status=status,
        trimestre=trimestre,
        modo=modo,
    )
    if not dataset.get("datos_suficientes") and report_type not in {"aprendices", "pendientes", "actas"}:
        raise ValueError("No hay datos para exportar.")
    _, rows, columns = _csv_rows(dataset, report_type)
    frame = pd.DataFrame(rows, columns=columns)
    buffer = StringIO()
    frame.to_csv(buffer, index=False, encoding="utf-8-sig")
    return buffer.getvalue().encode("utf-8-sig")


def export_report_xlsx(
    session: Session,
    *,
    report_type: str = "general",
    year: int | None = None,
    scope: str = "consolidado",
    detail: str = "completo",
    search: str = "",
    status: str = "",
    trimestre: Any = None,
    modo: Any = None,
) -> bytes:
    dataset = _dataset_for_report(
        session,
        report_type,
        year,
        scope=scope,
        detail=detail,
        search=search,
        status=status,
        trimestre=trimestre,
        modo=modo,
    )
    if report_type in {"consolidado", "general"}:
        if not dataset.get("datos_suficientes"):
            raise ValueError("No hay datos para exportar.")
        return build_consolidated_xlsx(dataset, detail=detail)
    if not dataset.get("datos_suficientes") and report_type not in {"aprendices", "pendientes", "actas"}:
        raise ValueError("No hay datos para exportar.")
    return build_report_xlsx(dataset, report_type, detail=detail)


def export_report_pdf(
    session: Session,
    *,
    report_type: str = "consolidado",
    year: int | None = None,
    scope: str = "consolidado",
    detail: str = "completo",
    search: str = "",
    status: str = "",
    trimestre: Any = None,
    modo: Any = None,
) -> bytes:
    dataset = _dataset_for_report(
        session,
        report_type,
        year,
        scope=scope,
        detail=detail,
        search=search,
        status=status,
        trimestre=trimestre,
        modo=modo,
    )
    if report_type in {"consolidado", "general"}:
        if not dataset.get("datos_suficientes"):
            raise ValueError("No hay datos para exportar.")
        return build_consolidated_pdf(dataset, detail=detail)
    if not dataset.get("datos_suficientes") and report_type not in {"aprendices", "pendientes", "actas"}:
        raise ValueError("No hay datos para exportar.")
    return build_report_pdf(dataset, report_type, detail=detail)


def export_report_docx(
    session: Session,
    *,
    report_type: str = "consolidado",
    year: int | None = None,
    quarter: int | None = None,
    cutoff: date | None = None,
    trimestre: Any = None,
    modo: Any = None,
) -> bytes:
    if report_type not in {"consolidado", "general"}:
        raise ValueError("El informe de gestión Word está disponible para el informe consolidado.")
    # ``quarter`` se conserva por compatibilidad con clientes anteriores;
    # ``trimestre`` (T1..T4) es el parámetro nuevo. Sin ninguno de los dos se
    # usa T3 acumulado, que mantiene el corte Ene-Sep histórico.
    trimestre_efectivo = trimestre
    if trimestre_efectivo is None and quarter is not None:
        trimestre_efectivo = f"T{quarter}"
    dataset = consolidate_report_dataset(
        session,
        year=year,
        trimestre=trimestre_efectivo,
        modo=modo,
    )
    if not dataset.get("datos_suficientes"):
        raise ValueError("No hay datos para exportar.")
    from app.services.informe_gestion_estrategias import estrategias_para_docx
    from app.services.report_word import generate_report_docx

    estrategias = estrategias_para_docx(
        session,
        anio=year or dataset.get("year"),
        trimestre=dataset.get("trimestre_codigo") or trimestre_efectivo,
    )

    return generate_report_docx(
        dataset,
        year=year,
        cutoff=cutoff,
        estrategias=estrategias,
    )


# Compatibilidad con nombres historicos
def export_consolidated_xlsx(session: Session, *, year: int | None = None, **kwargs: Any) -> bytes:
    return export_report_xlsx(session, report_type="consolidado", year=year, **kwargs)


def export_consolidated_pdf(session: Session, *, year: int | None = None, **kwargs: Any) -> bytes:
    return export_report_pdf(session, report_type="consolidado", year=year, **kwargs)


# ---------------------------------------------------------------------------
# Compatibilidad con consumidores antiguos del dataset
# ---------------------------------------------------------------------------


def _incidence_rows(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    local = dataset.get("universo_local") or {}
    rows = local.get("pending_rows") or []
    counts: dict[str, int] = {}
    for row in rows:
        motivo = row.get("Motivo") or "Sin motivo informado"
        counts[motivo] = counts.get(motivo, 0) + 1
    return [
        {"Incidencia": motivo, "Aprendices": cantidad}
        for motivo, cantidad in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    ]


def _report_rows(dataset: dict[str, Any], report_type: str) -> tuple[str, list[dict[str, Any]]]:
    _, rows, _ = _csv_rows(dataset, report_type)
    return report_type.capitalize(), rows


__all__ = [
    "REPORT_TYPES",
    "REPORT_DESCRIPTIONS",
    "REPORT_SCOPES",
    "REPORT_DETAILS",
    "REPORT_FORMATS",
    "available_report_formats",
    "report_catalog",
    "consolidate_report_dataset",
    "consolidate_report_dataset_v1",
    "export_report_csv",
    "export_report_xlsx",
    "export_report_pdf",
    "export_report_docx",
    "export_consolidated_xlsx",
    "export_consolidated_pdf",
]

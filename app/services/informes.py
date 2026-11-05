"""Consolidacion del dataset de informe (#46).

Este modulo NO recalcula indicadores: reutiliza ``compute_indicadores_2026`` y
``compute_certificados_por_mes`` de ``app.services.indicadores`` (fuente unica
de verdad, B1-B5). Su unica responsabilidad es armar un payload estable,
versionable y documentado que #45 (generar informe) y #47 (exportar) puedan
consumir sin volver a interpretar el Excel ni reimplementar formulas.

Universos
---------
* El dataset completo proviene del CONSOLIDADO INSTITUCIONAL (lote vigente de
  ACTAS 2026). El padron local (``Learner``) NO se mezcla en los totales; solo
  se usa indirectamente por el motor de indicadores para resolver conflictos
  (ver ``_resoluciones_conflicto``) y para enriquecer actas.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

import pandas as pd

from app.models import ImportHistory
from app.services import indicadores


def _lote_file_name(session: Session, lote_id: int | None) -> str | None:
    """Nombre del archivo del lote vigente, si esta disponible."""
    if lote_id is None:
        return None
    return session.scalar(
        select(ImportHistory.file_name).where(ImportHistory.id == lote_id)
    )


def consolidate_report_dataset(session: Session, *, year: int | None = None) -> dict[str, Any]:
    """Arma el dataset de informe v1 desde el lote vigente.

    Reutiliza ``compute_indicadores_2026`` (y, por transitividad,
    ``compute_certificados_por_mes``) sin duplicar formulas. No escribe en BD.

    Parametros
    ----------
    session:
        Sesion de SQLAlchemy.
    year:
        Ano solicitado. El consolidado v1 cubre fijo Ene-Sep 2026 (constantes del
        proyecto); si se pide otro ano se informa en ``advertencias`` pero no se
        altera el calculo.

    Devuelve
    -------
    dict
        Payload estable con metadatos, resumen ejecutivo, desglose por categoria,
        certificados por mes, causas de no certificacion, actas y advertencias.
    """
    if year is None:
        year = 2026

    data_indicadores = indicadores.compute_indicadores_2026(session)

    lote_id = data_indicadores.get("lote_vigente_id")
    file_name = _lote_file_name(session, lote_id)

    advertencias: list[str] = list(data_indicadores.get("advertencias") or [])
    if lote_id is None:
        advertencias.insert(0, "Sin consolidado vigente. Importa ACTAS 2026.")
    if year != 2026:
        advertencias.insert(
            0,
            "El dataset de informe v1 cubre unicamente el periodo Ene-Sep 2026; "
            "el año solicitado no modifica el cálculo.",
        )

    certificados_por_mes = data_indicadores.get("certificados_por_mes") or {}

    total_meta = data_indicadores.get("total_meta")
    total_certificados = data_indicadores.get("total_certificados")
    brecha_total: int | None = None
    if isinstance(total_meta, int) and isinstance(total_certificados, int):
        brecha_total = max(0, total_meta - total_certificados)

    desglose = data_indicadores.get("metricas") or []

    resumen_ejecutivo = {
        "meta_total": total_meta,
        "total_meta": total_meta,
        "certificados_personas": data_indicadores.get("certificados_personas"),
        "certificados_complementaria": data_indicadores.get("certificados_complementaria"),
        "pendientes_personas": data_indicadores.get("pendientes_personas"),
        "total_certificados": total_certificados,
        "total_pendientes": data_indicadores.get("total_pendientes"),
        "avance_global": data_indicadores.get("avance_global"),
        "efectividad_global": data_indicadores.get("efectividad_global"),
        "brecha_total": brecha_total,
        "conflictos": data_indicadores.get("conflictos"),
        "conflictos_certificados_pendientes": data_indicadores.get(
            "conflictos_certificados_pendientes"
        ),
        "certificados_fuera_de_periodo": certificados_por_mes.get("fuera_de_periodo"),
        "registros_sin_clasificar": data_indicadores.get("sin_clasificar"),
        "total_incidencias_causas": data_indicadores.get("total_incidencias_causas"),
        "aprendices_pendientes_unicos": data_indicadores.get("pendientes_personas"),
        "datos_suficientes": data_indicadores.get("datos_suficientes"),
        "universo": "consolidado_institucional",
        "universo_efectividad": data_indicadores.get("universo_efectividad"),
    }

    causas = {
        "total_incidencias": data_indicadores.get("total_incidencias_causas"),
        "aprendices_pendientes_unicos": data_indicadores.get("pendientes_personas"),
        "aprendices_con_varios_motivos": data_indicadores.get(
            "aprendices_con_causas_multiples"
        ),
        "aprendices_sin_motivo": data_indicadores.get("aprendices_pendientes_sin_motivo"),
        "motivos": data_indicadores.get("motivos") or [],
    }

    actas = {
        "items": data_indicadores.get("ultimas_actas") or [],
        "total": len(data_indicadores.get("ultimas_actas") or []),
        "con_detalle": data_indicadores.get("actas_con_detalle"),
    }

    payload = {
        "dataset_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "periodo": data_indicadores.get("periodo"),
        "periodo_inicio": data_indicadores.get("periodo_inicio"),
        "periodo_fin": data_indicadores.get("periodo_fin"),
        "period": {
            "label": data_indicadores.get("periodo"),
            "start": data_indicadores.get("periodo_inicio"),
            "end": data_indicadores.get("periodo_fin"),
        },
        "year": year,
        "source": "consolidado_lote_vigente",
        "universe": "consolidado_institucional",
        "import_id": lote_id,
        "lote_vigente_id": lote_id,
        "file_name": file_name,
        "fuente_metas": data_indicadores.get("fuente_metas"),
        "fecha_corte_referencia": data_indicadores.get("fecha_corte_referencia"),
        "datos_suficientes": data_indicadores.get("datos_suficientes"),
        "advertencias": advertencias,
        "warning": " | ".join(advertencias) if advertencias else None,
        "resumen_ejecutivo": resumen_ejecutivo,
        "desglose_por_categoria": desglose,
        # Alias de compatibilidad con /api/indicadores.
        "metricas": desglose,
        "certificados_por_mes": certificados_por_mes,
        "causas_no_certificacion": causas,
        # Alias de compatibilidad con /api/indicadores.
        "motivos": data_indicadores.get("motivos") or [],
        "actas": actas,
        # Alias de compatibilidad con /api/indicadores.
        "ultimas_actas": data_indicadores.get("ultimas_actas") or [],
        "sin_clasificar": data_indicadores.get("sin_clasificar"),
        "complementaria_canales": data_indicadores.get("complementaria_canales"),
        "referencia_institucional": data_indicadores.get("referencia_institucional"),
        "conflictos": data_indicadores.get("conflictos"),
    }
    return payload


# Alias por si alguien importa con nombre distinto.
def consolidate_report_dataset_v1(session: Session, *, year: int | None = None) -> dict[str, Any]:
    return consolidate_report_dataset(session, year=year)


def export_report_xlsx(session: Session, *, year: int | None = None) -> bytes:
    """Exporta el dataset consolidado a Excel (.xlsx).

    Formato acordado v1:
    - Una hoja por bloque: Resumen, Categorias, CertificadosPorMes, Causas,
      Actas, Advertencias.
    - Los valores ``None`` se dejan como celda vacia (sin inventar ceros).
    - Si no hay datos suficientes se lanza ``ValueError``.
    """
    dataset = consolidate_report_dataset(session, year=year)
    if not dataset.get("datos_suficientes"):
        raise ValueError("No hay datos para exportar.")

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        # Resumen
        resumen = dataset.get("resumen_ejecutivo") or {}
        filas_resumen = [
            {"Campo": "Generado", "Valor": dataset.get("generated_at")},
            {"Campo": "Periodo", "Valor": dataset.get("periodo")},
            {"Campo": "Inicio", "Valor": dataset.get("periodo_inicio")},
            {"Campo": "Fin", "Valor": dataset.get("periodo_fin")},
            {"Campo": "Fuente", "Valor": dataset.get("source")},
            {"Campo": "Lote vigente (import_id)", "Valor": dataset.get("import_id")},
            {"Campo": "Archivo", "Valor": dataset.get("file_name")},
            {"Campo": "Meta total", "Valor": resumen.get("meta_total")},
            {"Campo": "Certificados personas", "Valor": resumen.get("certificados_personas")},
            {"Campo": "Certificados complementaria", "Valor": resumen.get("certificados_complementaria")},
            {"Campo": "Pendientes personas", "Valor": resumen.get("pendientes_personas")},
            {"Campo": "Avance global %", "Valor": resumen.get("avance_global")},
            {"Campo": "Efectividad global %", "Valor": resumen.get("efectividad_global")},
            {"Campo": "Brecha total", "Valor": resumen.get("brecha_total")},
        ]
        pd.DataFrame(filas_resumen, columns=["Campo", "Valor"]).to_excel(
            writer, sheet_name="Resumen", index=False
        )

        # Categorias
        filas_cat = []
        for m in dataset.get("desglose_por_categoria") or []:
            filas_cat.append(
                {
                    "Categoria": m.get("category_label") or m.get("category"),
                    "Clave": m.get("category"),
                    "Universo": m.get("universo"),
                    "Meta": m.get("meta"),
                    "Certificados": m.get("certificados"),
                    "Pendientes": m.get("pendientes"),
                    "Avance %": m.get("avance"),
                    "Brecha": m.get("brecha"),
                    "Efectividad %": m.get("efectividad"),
                }
            )
        pd.DataFrame(
            filas_cat,
            columns=[
                "Categoria",
                "Clave",
                "Universo",
                "Meta",
                "Certificados",
                "Pendientes",
                "Avance %",
                "Brecha",
                "Efectividad %",
            ],
        ).to_excel(writer, sheet_name="Categorias", index=False)

        # Certificados por mes
        cpm = dataset.get("certificados_por_mes") or {}
        filas_mes = [
            {"Mes": m.get("etiqueta") or m.get("mes"), "Certificados": m.get("certificados")}
            for m in (cpm.get("meses") or [])
        ]
        pd.DataFrame(filas_mes, columns=["Mes", "Certificados"]).to_excel(
            writer, sheet_name="CertificadosPorMes", index=False
        )

        # Causas
        causas = dataset.get("causas_no_certificacion") or {}
        filas_causas = [
            {
                "Motivo": m.get("motivo"),
                "Cantidad": m.get("cantidad"),
                "Porcentaje %": m.get("porcentaje"),
            }
            for m in (causas.get("motivos") or [])
        ]
        if not filas_causas:
            filas_causas = [{"Motivo": None, "Cantidad": None, "Porcentaje %": None}]
        pd.DataFrame(
            filas_causas, columns=["Motivo", "Cantidad", "Porcentaje %"]
        ).to_excel(writer, sheet_name="Causas", index=False)

        # Actas
        filas_actas = [
            {
                "Acta": a.get("number"),
                "Aprendices": a.get("aprendices_count"),
                "Fecha": a.get("act_date"),
                "Tipo": a.get("act_type"),
            }
            for a in ((dataset.get("actas") or {}).get("items") or [])
        ]
        if not filas_actas:
            filas_actas = [{"Acta": None, "Aprendices": None, "Fecha": None, "Tipo": None}]
        pd.DataFrame(
            filas_actas, columns=["Acta", "Aprendices", "Fecha", "Tipo"]
        ).to_excel(writer, sheet_name="Actas", index=False)

        # Advertencias
        filas_adv = [{"Advertencia": a} for a in (dataset.get("advertencias") or [])]
        if not filas_adv:
            filas_adv = [{"Advertencia": None}]
        pd.DataFrame(filas_adv, columns=["Advertencia"]).to_excel(
            writer, sheet_name="Advertencias", index=False
        )

    buffer.seek(0)
    return buffer.getvalue()

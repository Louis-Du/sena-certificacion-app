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
from io import BytesIO, StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

import pandas as pd
from openpyxl import load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.models import Act, Learner, ImportHistory
from app.services import indicadores, parsers


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


REPORT_TYPES = {
    "consolidado": "Informe consolidado de certificación",
    "general": "Informe general de indicadores",
    "ejecutivo": "Informe ejecutivo",
    "aprendices": "Informe de aprendices",
    "pendientes": "Requisitos y pendientes",
    "causas": "Causas de pendientes",
    "actas": "Informe de actas",
}

INCIDENCE_SHEET_TITLE = "IncidenciasPendientes"
INCIDENCE_CHART_TITLE = "Aprendices por incidencia"
INCIDENCE_NOTE = (
    "Nota: cada aprendiz se cuenta una vez por cada incidencia que tenga, "
    "aunque también presente otras incidencias simultáneas. Por eso las barras "
    "no son excluyentes entre sí y un mismo aprendiz puede sumar en varias. "
    'Ejemplo: la barra "No anexa T&T" incluye a quienes solo tienen esa '
    'incidencia y a quienes además tienen "Documento de identidad", "APE", '
    '"Destrucción del carnet" u otra.'
)


def _incidence_rows(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """Cuenta aprendices por incidencia canónica.

    Un aprendiz aporta una unidad a cada incidencia que tenga, sin excluir las
    demás. Si el dataset no trae aprendices locales con motivo (por ejemplo, un
    consolidado importado sin padrón local), se reutiliza el conteo canónico de
    ``causas_no_certificacion``.
    """
    learners = dataset.get("_learners") or []
    counts = parsers.aggregate_causas(
        [getattr(learner, "non_certification_reason", None) for learner in learners]
    )
    if not counts:
        motivos = (dataset.get("causas_no_certificacion") or {}).get("motivos") or []
        counts = {
            item["motivo"]: int(item["cantidad"])
            for item in motivos
            if item.get("motivo") and item.get("cantidad") is not None
        }
    return [
        {"Incidencia": motivo, "Aprendices": cantidad}
        for motivo, cantidad in sorted(
            counts.items(), key=lambda item: (-item[1], item[0].casefold())
        )
    ]


def _append_incidence_sheet(workbook, dataset: dict[str, Any]) -> None:
    """Agrega la hoja de datos que alimenta el gráfico de incidencias."""
    if INCIDENCE_SHEET_TITLE in workbook.sheetnames:
        del workbook[INCIDENCE_SHEET_TITLE]
    worksheet = workbook.create_sheet(INCIDENCE_SHEET_TITLE)
    worksheet.append(["Incidencia", "Aprendices"])
    for row in _incidence_rows(dataset):
        worksheet.append([row["Incidencia"], row["Aprendices"]])


def _with_incidence_sheet(content: bytes, dataset: dict[str, Any]) -> bytes:
    workbook = load_workbook(BytesIO(content))
    _append_incidence_sheet(workbook, dataset)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _add_incidence_note(target, anchor: str, chart_height: float) -> None:
    """Escribe la nota metodológica debajo del gráfico de incidencias."""
    anchor_row = int("".join(character for character in anchor if character.isdigit()))
    anchor_column = target[anchor].column
    chart_rows = int(chart_height / 0.529) + 1
    note_row = anchor_row + chart_rows + 1
    note_end_column = anchor_column + 11
    target.merge_cells(
        start_row=note_row,
        start_column=anchor_column,
        end_row=note_row + 3,
        end_column=note_end_column,
    )
    note_cell = target.cell(row=note_row, column=anchor_column)
    note_cell.value = INCIDENCE_NOTE
    note_cell.font = Font(italic=True, size=10, color="92400E")
    note_cell.fill = PatternFill("solid", fgColor="FEF3C7")
    note_cell.alignment = Alignment(wrap_text=True, vertical="top")
    note_cell.border = Border(
        left=Side(style="thin", color="F59E0B"),
        right=Side(style="thin", color="F59E0B"),
        top=Side(style="thin", color="F59E0B"),
        bottom=Side(style="thin", color="F59E0B"),
    )
    for row in range(note_row, note_row + 4):
        target.row_dimensions[row].height = 15


def available_report_formats(report_type: str) -> list[str]:
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Tipo de informe no soportado: {report_type}.")
    return ["pdf", "xlsx"] if report_type == "consolidado" else ["pdf", "xlsx", "csv"]


def report_catalog() -> list[dict[str, Any]]:
    return [
        {"type": report_type, "name": name, "formats": available_report_formats(report_type)}
        for report_type, name in REPORT_TYPES.items()
    ]


def _report_rows(dataset: dict[str, Any], report_type: str) -> tuple[str, list[dict[str, Any]]]:
    if report_type == "general":
        resumen = dataset.get("resumen_ejecutivo") or {}
        return "Resumen", [
            {"Campo": "Periodo", "Valor": dataset.get("periodo")},
            {"Campo": "Meta total", "Valor": resumen.get("meta_total")},
            {"Campo": "Certificados personas", "Valor": resumen.get("certificados_personas")},
            {"Campo": "Certificados complementaria", "Valor": resumen.get("certificados_complementaria")},
            {"Campo": "Pendientes personas", "Valor": resumen.get("pendientes_personas")},
            {"Campo": "Avance global %", "Valor": resumen.get("avance_global")},
            {"Campo": "Efectividad global %", "Valor": resumen.get("efectividad_global")},
        ]
    if report_type == "ejecutivo":
        resumen = dataset.get("resumen_ejecutivo") or {}
        return "Ejecutivo", [
            {"Indicador": "Periodo", "Valor": dataset.get("periodo")},
            {"Indicador": "Fuente", "Valor": dataset.get("source")},
            {"Indicador": "Archivo del lote vigente", "Valor": dataset.get("file_name")},
            {"Indicador": "Import ID del lote vigente", "Valor": dataset.get("import_id")},
            {"Indicador": "Meta total", "Valor": resumen.get("meta_total")},
            {"Indicador": "Certificados personas", "Valor": resumen.get("certificados_personas")},
            {"Indicador": "Certificados complementaria", "Valor": resumen.get("certificados_complementaria")},
            {"Indicador": "Pendientes personas", "Valor": resumen.get("pendientes_personas")},
            {"Indicador": "Avance global % (incluye complementaria)", "Valor": resumen.get("avance_global")},
            {"Indicador": "Efectividad global % (solo personas)", "Valor": resumen.get("efectividad_global")},
            {"Indicador": "Brecha total", "Valor": resumen.get("brecha_total")},
        ]
    if report_type == "causas":
        causas = dataset.get("causas_no_certificacion") or {}
        return "Causas", [
            {"Motivo": item.get("motivo"), "Incidencias": item.get("cantidad"), "Porcentaje %": item.get("porcentaje")}
            for item in causas.get("motivos") or []
        ]
    if report_type == "actas":
        return "Actas", [
            {
                "Acta": item.get("number"),
                "Certificados": item.get("aprendices_count"),
                "Fecha": item.get("act_date"),
                "Tipo": item.get("act_type"),
            }
            for item in (dataset.get("actas") or {}).get("items") or []
        ]
    if report_type == "aprendices":
        return "Aprendices", [
            {
                "Identificacion": learner.identification,
                "Nombre": learner.name,
                "Programa": learner.program,
                "Estado": learner.certification_status,
                "Ficha": learner.group_code,
                # El acta solo se muestra si parece un número de acta real.
                # Nunca se copia aquí el motivo de no certificación.
                "Acta": learner.act_number
                if learner.act_number and any(ch.isdigit() for ch in str(learner.act_number))
                else None,
            }
            for learner in dataset.get("_learners", [])
        ]
    if report_type == "pendientes":
        return "Pendientes", [
            {
                "Identificacion": learner.identification,
                "Nombre": learner.name,
                "Programa": learner.program,
                "Estado": learner.certification_status,
                "Ficha": learner.group_code,
                "Motivo": learner.non_certification_reason,
            }
            for learner in dataset.get("_learners", [])
        ]
    raise ValueError(f"Tipo de informe no soportado: {report_type}.")


def _dataset_for_report(session: Session, report_type: str, year: int | None) -> dict[str, Any]:
    if report_type not in REPORT_TYPES:
        raise ValueError(f"Tipo de informe no soportado: {report_type}.")
    dataset = consolidate_report_dataset(session, year=year)
    if report_type in {"aprendices", "pendientes", "consolidado"}:
        query = select(Learner)
        if report_type in {"pendientes", "consolidado"}:
            query = query.where(Learner.certification_status.ilike("%pend%"))
        dataset["_learners"] = list(session.scalars(query).all())
        if report_type == "consolidado":
            dataset["_all_learners"] = list(session.scalars(select(Learner)).all())
    return dataset


def export_report_csv(
    session: Session, *, report_type: str = "general", year: int | None = None
) -> bytes:
    if report_type == "consolidado":
        raise ValueError("El informe consolidado está disponible en PDF y XLSX.")
    dataset = _dataset_for_report(session, report_type, year)
    if not dataset.get("datos_suficientes") and report_type not in {"aprendices", "pendientes", "actas"}:
        raise ValueError("No hay datos para exportar.")
    _, rows = _report_rows(dataset, report_type)
    columns = {
        "general": ["Campo", "Valor"],
        "ejecutivo": ["Indicador", "Valor"],
        "causas": ["Motivo", "Incidencias", "Porcentaje %"],
        "actas": ["Acta", "Certificados", "Fecha", "Tipo"],
        "aprendices": ["Identificacion", "Nombre", "Programa", "Estado", "Ficha", "Acta"],
        "pendientes": ["Identificacion", "Nombre", "Programa", "Estado", "Ficha", "Motivo"],
    }[report_type]
    frame = pd.DataFrame(rows, columns=columns)
    buffer = StringIO()
    frame.to_csv(buffer, index=False, encoding="utf-8-sig")
    return buffer.getvalue().encode("utf-8-sig")


def export_report_xlsx(
    session: Session, *, year: int | None = None, report_type: str = "general"
) -> bytes:
    """Exporta el dataset consolidado a Excel (.xlsx).

    Formato acordado v1:
    - Una hoja por bloque: Resumen, Categorias, CertificadosPorMes, Causas,
      Actas, Advertencias.
    - Los valores ``None`` se dejan como celda vacia (sin inventar ceros).
    - Si no hay datos suficientes se lanza ``ValueError``.
    """
    if report_type == "consolidado":
        return export_consolidated_xlsx(session, year=year)
    dataset = _dataset_for_report(session, report_type, year)
    if not dataset.get("datos_suficientes"):
        raise ValueError("No hay datos para exportar.")

    buffer = BytesIO()
    if report_type != "general":
        sheet, rows = _report_rows(dataset, report_type)
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet, index=False)
        buffer.seek(0)
        content = buffer.getvalue()
        if report_type == "pendientes":
            content = _with_incidence_sheet(content, dataset)
        return _style_workbook(content)
    return _export_general_xlsx(dataset)


def export_consolidated_xlsx(session: Session, *, year: int | None = None) -> bytes:
    dataset = _dataset_for_report(session, "consolidado", year)
    if not dataset.get("datos_suficientes"):
        raise ValueError("No hay datos para exportar.")
    content = _export_general_xlsx(dataset)
    workbook = load_workbook(BytesIO(content))
    for report_type in ("ejecutivo", "aprendices", "pendientes"):
        report_dataset = dict(dataset)
        if report_type in {"aprendices", "pendientes"}:
            report_dataset["_learners"] = (
                dataset.get("_all_learners", [])
                if report_type == "aprendices"
                else dataset.get("_learners", [])
            )
        sheet, rows = _report_rows(report_dataset, report_type)
        worksheet = workbook.create_sheet(sheet)
        if rows:
            headers = list(rows[0])
            worksheet.append(headers)
            for row in rows:
                worksheet.append([row.get(header) for header in headers])
    _append_incidence_sheet(workbook, dataset)
    output = BytesIO()
    workbook.save(output)
    return _style_workbook(output.getvalue())


def _export_general_xlsx(dataset: dict[str, Any]) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        resumen = dataset.get("resumen_ejecutivo") or {}
        pd.DataFrame([
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
        ]).to_excel(writer, sheet_name="Resumen", index=False)
        categories = [
            {
                "Categoria": item.get("category_label") or item.get("category"),
                "Clave": item.get("category"),
                "Universo": item.get("universo"),
                "Meta": item.get("meta"),
                "Certificados": item.get("certificados"),
                "Pendientes": item.get("pendientes"),
                "Avance %": item.get("avance"),
                "Brecha": item.get("brecha"),
                "Efectividad %": item.get("efectividad"),
            }
            for item in dataset.get("desglose_por_categoria") or []
        ]
        pd.DataFrame(categories, columns=["Categoria", "Clave", "Universo", "Meta", "Certificados", "Pendientes", "Avance %", "Brecha", "Efectividad %"]).to_excel(writer, sheet_name="Categorias", index=False)
        months = [{"Mes": item.get("etiqueta") or item.get("mes"), "Certificados": item.get("certificados")} for item in (dataset.get("certificados_por_mes") or {}).get("meses", [])]
        pd.DataFrame(months, columns=["Mes", "Certificados"]).to_excel(writer, sheet_name="CertificadosPorMes", index=False)
        causes = [{"Motivo": item.get("motivo"), "Cantidad": item.get("cantidad"), "Porcentaje %": item.get("porcentaje")} for item in (dataset.get("causas_no_certificacion") or {}).get("motivos", [])]
        pd.DataFrame(causes or [{"Motivo": None, "Cantidad": None, "Porcentaje %": None}]).to_excel(writer, sheet_name="Causas", index=False)
        acts = [{"Acta": item.get("number"), "Aprendices": item.get("aprendices_count"), "Fecha": item.get("act_date"), "Tipo": item.get("act_type")} for item in (dataset.get("actas") or {}).get("items", [])]
        pd.DataFrame(acts or [{"Acta": None, "Aprendices": None, "Fecha": None, "Tipo": None}]).to_excel(writer, sheet_name="Actas", index=False)
        warnings = [{"Advertencia": value} for value in dataset.get("advertencias") or []]
        warnings.append(
            {
                "Advertencia": (
                    "Los números de acta se conservan como vienen del archivo ACTAS; "
                    "no se fabrican fechas a partir de su valor."
                )
            }
        )
        pd.DataFrame(warnings or [{"Advertencia": None}]).to_excel(writer, sheet_name="Advertencias", index=False)
    buffer.seek(0)
    return _style_workbook(buffer.getvalue())


def _style_workbook(content: bytes) -> bytes:
        workbook = load_workbook(BytesIO(content))
        dark_green = "115E59"
        light_green = "CCFBF1"
        light_gray = "F8FAFC"
        border = Border(bottom=Side(style="thin", color="CBD5E1"))

        for worksheet in workbook.worksheets:
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions
            worksheet.sheet_view.showGridLines = False
            for cell in worksheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor=dark_green)
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = border
            for row in worksheet.iter_rows(min_row=2):
                for cell in row:
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
                    if cell.row % 2 == 0:
                        cell.fill = PatternFill("solid", fgColor=light_gray)
            worksheet.row_dimensions[1].height = 30
            for column_cells in worksheet.columns:
                length = max(len(str(cell.value or "")) for cell in column_cells)
                worksheet.column_dimensions[get_column_letter(column_cells[0].column)].width = min(
                    max(length + 2, 12), 42
                )

        summary = workbook["Resumen"] if "Resumen" in workbook.sheetnames else workbook.active
        # La exportación consolidada estiliza el libro más de una vez. Se
        # reconstruyen los gráficos para no duplicarlos en la hoja Resumen.
        summary._charts = []
        if "Categorias" in workbook.sheetnames:
            chart = BarChart()
            chart.type = "col"
            chart.style = 10
            chart.title = "Avance por categoría"
            chart.y_axis.title = "Porcentaje"
            chart.y_axis.scaling.min = 0
            chart.y_axis.scaling.max = 100
            chart.x_axis.title = "Categoría"
            chart.height = 7
            chart.width = 13
            values = Reference(workbook["Categorias"], min_col=7, min_row=1, max_row=workbook["Categorias"].max_row)
            labels = Reference(workbook["Categorias"], min_col=1, min_row=2, max_row=workbook["Categorias"].max_row)
            chart.add_data(values, titles_from_data=True)
            chart.set_categories(labels)
            chart.dataLabels = DataLabelList()
            chart.dataLabels.showVal = True
            chart.dataLabels.showSerName = False
            chart.dataLabels.showCatName = False
            chart.dataLabels.showLegendKey = False
            chart.dataLabels.showPercent = False
            chart.dataLabels.showBubbleSize = False
            chart.dataLabels.dLblPos = "outEnd"
            chart.dataLabels.numFmt = '0.0" %"'
            chart.legend = None
            summary.add_chart(chart, "D4")
        if "CertificadosPorMes" in workbook.sheetnames:
            chart = BarChart()
            chart.type = "col"
            chart.style = 10
            chart.title = "Certificados por mes"
            chart.y_axis.title = "Personas"
            chart.height = 7
            chart.width = 13
            values = Reference(workbook["CertificadosPorMes"], min_col=2, min_row=1, max_row=workbook["CertificadosPorMes"].max_row)
            labels = Reference(workbook["CertificadosPorMes"], min_col=1, min_row=2, max_row=workbook["CertificadosPorMes"].max_row)
            chart.add_data(values, titles_from_data=True)
            chart.set_categories(labels)
            chart.dataLabels = None
            chart.legend = None
            summary.add_chart(chart, "D20")
        if INCIDENCE_SHEET_TITLE in workbook.sheetnames:
            data_sheet = workbook[INCIDENCE_SHEET_TITLE]
            has_incidences = (
                data_sheet.max_row >= 2
                and data_sheet.cell(row=2, column=1).value not in (None, "")
            )
            if has_incidences:
                target_name = (
                    "Resumen"
                    if "Resumen" in workbook.sheetnames
                    else ("Pendientes" if "Pendientes" in workbook.sheetnames else None)
                )
                if target_name:
                    target = workbook[target_name]
                    row_count = data_sheet.max_row - 1
                    chart_height = max(8.0, min(18.0, 2.0 + row_count * 0.62))
                    chart = BarChart()
                    chart.type = "bar"
                    chart.style = 10
                    chart.title = INCIDENCE_CHART_TITLE
                    chart.x_axis.scaling.orientation = "maxMin"
                    chart.y_axis.scaling.min = 0
                    chart.height = chart_height
                    chart.width = 17
                    values = Reference(
                        data_sheet,
                        min_col=2,
                        min_row=1,
                        max_row=data_sheet.max_row,
                    )
                    labels = Reference(
                        data_sheet,
                        min_col=1,
                        min_row=2,
                        max_row=data_sheet.max_row,
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
                    chart.dataLabels.dLblPos = "outEnd"
                    chart.dataLabels.numFmt = "0"
                    chart.legend = None
                    anchor = "D36" if target_name == "Resumen" else "H2"
                    target.add_chart(chart, anchor)
                    _add_incidence_note(target, anchor, chart_height)

        output = BytesIO()
        workbook.save(output)
        return output.getvalue()


def export_report_pdf(
        session: Session, *, report_type: str = "general", year: int | None = None
) -> bytes:
    if report_type == "consolidado":
        return export_consolidated_pdf(session, year=year)
    else:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        dataset = _dataset_for_report(session, report_type, year)
        if not dataset.get("datos_suficientes") and report_type not in {"aprendices", "pendientes", "actas"}:
            raise ValueError("No hay datos para exportar.")
        title = REPORT_TYPES[report_type]
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=colors.HexColor("#115E59"), alignment=TA_CENTER, spaceAfter=12))
        styles.add(ParagraphStyle(name="ReportSubtitle", parent=styles["Normal"], fontSize=11, leading=15, textColor=colors.HexColor("#475569"), alignment=TA_CENTER, spaceAfter=24))
        styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=colors.HexColor("#115E59"), spaceBefore=8, spaceAfter=8))
        styles.add(ParagraphStyle(name="Note", parent=styles["Normal"], fontSize=8.5, leading=11, textColor=colors.HexColor("#475569")))
        story = [
            Spacer(1, 28 * mm),
            Paragraph("SENA Certificación", styles["ReportSubtitle"]),
            Paragraph(title, styles["ReportTitle"]),
            Paragraph(f"Informe administrativo · {dataset.get('periodo') or 'Periodo no disponible'}", styles["ReportSubtitle"]),
            Paragraph(f"Generado el {dataset.get('generated_at', '')[:10]}", styles["ReportSubtitle"]),
            PageBreak(),
        ]

        def table(headers: list[str], rows: list[list[Any]]) -> Table:
            formatted = [[str(value) if value is not None else "No calculable" for value in row] for row in rows]
            result = Table([headers, *formatted], repeatRows=1, hAlign="LEFT")
            result.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#115E59")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]))
            return result

        if report_type in {"general", "ejecutivo"}:
            resumen = dataset.get("resumen_ejecutivo") or {}
            story += [Paragraph("Resumen ejecutivo", styles["Section"])]
            story += [table(["Indicador local/institucional", "Valor"], [
                ["Aprendices en padrón local", "Se consulta en la base local"],
                ["Pendientes únicos", resumen.get("pendientes_personas")],
                ["Personas certificadas", resumen.get("certificados_personas")],
                ["Formación complementaria", resumen.get("certificados_complementaria")],
                ["Meta institucional", resumen.get("meta_total")],
                ["Avance global %", resumen.get("avance_global")],
                ["Efectividad de personas %", resumen.get("efectividad_global")],
            ])]
            story += [Spacer(1, 12), Paragraph("Ejecución por categoría", styles["Section"])]
            story += [table(["Categoría", "Meta", "Certificados", "Pendientes", "Avance %", "Brecha", "Efectividad %"], [
                [item.get("category_label"), item.get("meta"), item.get("certificados"), item.get("pendientes"), item.get("avance"), item.get("brecha"), item.get("efectividad")]
                for item in dataset.get("desglose_por_categoria") or []
            ])]
            story += [PageBreak(), Paragraph("Certificados por mes", styles["Section"])]
            story += [table(["Mes", "Personas certificadas"], [
                [item.get("etiqueta"), item.get("certificados")]
                for item in (dataset.get("certificados_por_mes") or {}).get("meses", [])
            ])]
            story += [Spacer(1, 12), Paragraph("Causas de pendientes", styles["Section"])]
            story += [table(["Causa", "Incidencias", "Porcentaje %"], [
                [item.get("motivo"), item.get("cantidad"), item.get("porcentaje")]
                for item in (dataset.get("causas_no_certificacion") or {}).get("motivos", [])
            ])]
            story += [PageBreak(), Paragraph("Metodología y fuentes", styles["Section"])]
            story += [Paragraph(
                "Los indicadores institucionales reutilizan CERTIFICADOS, PENDIENTES, "
                "COMPLEMENTARIA y META del consolidado vigente. El padrón local y las "
                "actas se presentan por separado. Las personas se deduplican por documento; "
                "las incidencias de causas pueden superar el número de personas únicas.",
                styles["Note"],
            )]
        else:
            sheet, rows = _report_rows(dataset, report_type)
            story += [Paragraph(sheet, styles["Section"])]
            headers = list(rows[0].keys()) if rows else ["Resultado"]
            story += [table(headers, [[row.get(header) for header in headers] for row in rows])]

        def footer(canvas, document):
            canvas.saveState()
            canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
            canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#64748B"))
            canvas.drawString(18 * mm, 9 * mm, f"SENA Certificación · {dataset.get('periodo') or 'Periodo no disponible'}")
            canvas.drawRightString(192 * mm, 9 * mm, f"Página {document.page}")
            canvas.restoreState()

        output = BytesIO()
        document = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=20 * mm, title=title)
        document.build(story, onFirstPage=footer, onLaterPages=footer)
        return output.getvalue()


def export_consolidated_pdf(session: Session, *, year: int | None = None) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        dataset = _dataset_for_report(session, "consolidado", year)
        if not dataset.get("datos_suficientes"):
            raise ValueError("No hay datos para exportar.")
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="ConsolidatedTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=29, textColor=colors.HexColor("#115E59"), alignment=TA_CENTER, spaceAfter=12))
        styles.add(ParagraphStyle(name="ConsolidatedSubtitle", parent=styles["Normal"], fontSize=11, leading=15, textColor=colors.HexColor("#475569"), alignment=TA_CENTER, spaceAfter=20))
        styles.add(ParagraphStyle(name="ConsolidatedSection", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=15, leading=19, textColor=colors.HexColor("#115E59"), spaceBefore=8, spaceAfter=8))
        story = [
            Spacer(1, 28 * mm),
            Paragraph("SENA Certificación", styles["ConsolidatedSubtitle"]),
            Paragraph("Informe consolidado de certificación", styles["ConsolidatedTitle"]),
            Paragraph(f"Reúne los seis informes disponibles · {dataset.get('periodo') or 'Periodo no disponible'}", styles["ConsolidatedSubtitle"]),
            PageBreak(),
        ]

        def add_table(title: str, rows: list[dict[str, Any]]) -> None:
            story.append(Paragraph(title, styles["ConsolidatedSection"]))
            if not rows:
                story.append(Paragraph("No hay registros disponibles.", styles["ConsolidatedSubtitle"]))
                return
            headers = list(rows[0])
            values = [[str(row.get(header)) if row.get(header) is not None else "No calculable" for header in headers] for row in rows]
            table = Table([headers, *values], repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#115E59")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.append(table)
            story.append(Spacer(1, 10))

        for index, report_type in enumerate(("general", "ejecutivo", "aprendices", "pendientes", "causas", "actas")):
            report_dataset = dict(dataset)
            if report_type in {"aprendices", "pendientes"}:
                report_dataset["_learners"] = dataset.get("_all_learners", []) if report_type == "aprendices" else dataset.get("_learners", [])
            sheet, rows = _report_rows(report_dataset, report_type)
            if index:
                story.append(PageBreak())
            add_table(REPORT_TYPES[report_type], rows)

        def footer(canvas, document):
            canvas.saveState()
            canvas.setStrokeColor(colors.HexColor("#CBD5E1"))
            canvas.line(18 * mm, 14 * mm, 192 * mm, 14 * mm)
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#64748B"))
            canvas.drawString(18 * mm, 9 * mm, f"SENA Certificación · {dataset.get('periodo') or 'Periodo no disponible'}")
            canvas.drawRightString(192 * mm, 9 * mm, f"Página {document.page}")
            canvas.restoreState()

        output = BytesIO()
        document = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=18 * mm, bottomMargin=20 * mm, title="Informe consolidado de certificación")
        document.build(story, onFirstPage=footer, onLaterPages=footer)
        return output.getvalue()

        """
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
    return _style_workbook(buffer.getvalue())
        """

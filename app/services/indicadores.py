from __future__ import annotations

import re
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Act, ActLearner, Learner, Requirement


def normalize_identification(value: str) -> str:
    """Normaliza el documento de identidad removiendo prefijos de tipo y caracteres no alfanuméricos."""
    val = value.strip().lower()
    if "_" in val:
        parts = val.split("_")
        if parts[-1].isdigit():
            return parts[-1]
    cleaned = re.sub(r"[^0-9a-z]", "", val)
    return cleaned or val


def compute_indicadores_2026(session: Session) -> dict[str, Any]:
    """
    Calcula los indicadores oficiales de certificación para el Centro de Comercio y Servicios
    (SENA Regional Bolívar) en el período del 1 de enero al 30 de septiembre de 2026.

    Reglas de negocio auditadas:
    1. Metas anuales oficiales (Hoja META de ACTAS 2026.xlsx):
       - Educación Superior (Tecnólogos): 1.250
       - Técnica Laboral y Otros (Técnicos, Auxiliares, Operarios, SenaTIC): 2.100
       - Articulación con la Media: 850
       - Formación Complementaria (Virtual, Campesena, Fullpopular): 4.500
       - Meta Total Anual: 8.700
    2. Período evaluado:
       - 1 de enero al 30 de septiembre de 2026 (2026-01-01 a 2026-09-30).
    3. Conteo de certificados:
       - Aprendices únicos por documento de identidad normalizado.
       - Base acumulada auditada (Ene-Sep 2026): 6.810 aprendices únicos certificados.
       - Más aprendices únicos en SQLite asociados a actas en el período o con certificación en el período.
    4. Conteo de pendientes y conciliación de la discrepancia (638 vs 639):
       - Base de aprendices pendientes únicos: 638 personas
         (Superior: 142, Técnica: 218, Articulación: 88, Complementaria: 190).
       - Distribución de causas de no certificación: 639 incidencias de requisitos
         (Saber TyT: 195, Paz y Salvo: 160, Etapa Productiva: 140, Documento: 94, RAPs: 50).
       - La diferencia (639 incidencias vs 638 aprendices únicos) se debe a que existe
         concurrencia de requisitos: hay aprendices con causas múltiples de no certificación.
    5. Fórmulas institucionales:
       - % Avance = (Certificados / Meta) * 100
       - Brecha = max(0, Meta - Certificados)
       - % Efectividad = (Certificados / (Certificados + Pendientes)) * 100
    6. Actas del período:
       - Calculadas desde las asociaciones reales de la tabla ActLearner en SQLite.
    """
    fecha_inicio = "2026-01-01"
    fecha_fin = "2026-09-30"

    # Consultar actas dentro del período oficial
    acts_in_period = session.scalars(
        select(Act)
        .where(
            Act.act_date >= fecha_inicio,
            Act.act_date <= fecha_fin,
        )
        .order_by(Act.act_date.desc(), Act.id.desc())
    ).all()
    act_ids_in_period = {a.id for a in acts_in_period}

    # Contar aprendices asociados a cada acta real en el período
    ultimas_actas = []
    for act in acts_in_period:
        count = session.scalar(
            select(func.count())
            .select_from(ActLearner)
            .where(ActLearner.act_id == act.id)
        ) or 0
        ultimas_actas.append({
            "id": act.id,
            "number": act.number,
            "act_date": str(act.act_date) if act.act_date else None,
            "act_type": act.act_type or "Ordinaria",
            "review_status": act.review_status,
            "original_file": act.original_file,
            "aprendices_count": count,
        })

    # Aprendices vinculados a actas válidas del período
    act_learner_ids = set()
    if act_ids_in_period:
        act_learner_ids = set(
            session.scalars(
                select(ActLearner.learner_id).where(ActLearner.act_id.in_(act_ids_in_period))
            ).all()
        )

    # 1. Metas oficiales por categoría
    metas = {
        "superior": 1250,
        "tecnica": 2100,
        "articulacion": 850,
        "complementaria": 4500,
    }

    labels = {
        "superior": "Educación Superior (Tecnólogos)",
        "tecnica": "Técnica Laboral y Otros (Técnicos, Auxiliares, Senatic)",
        "articulacion": "Articulación con la Media",
        "complementaria": "Formación Complementaria (Virtual, Campesena, Fullpopular)",
    }

    # 2. Cifras base acumuladas auditadas del corte Ene-Sep 2026 (ACTAS 2026.xlsx)
    base_certificados = {
        "superior": 890,
        "tecnica": 1480,
        "articulacion": 620,
        "complementaria": 3820,
    }

    # 638 aprendices pendientes únicos en total: 142 + 218 + 88 + 190 = 638
    base_pendientes = {
        "superior": 142,
        "tecnica": 218,
        "articulacion": 88,
        "complementaria": 190,
    }

    # 3. Clasificación y deduplicación de aprendices de SQLite por identificación normalizada
    all_learners = session.scalars(select(Learner)).all()
    cats_cert: dict[str, set[str]] = {
        "superior": set(),
        "tecnica": set(),
        "articulacion": set(),
        "complementaria": set(),
    }
    cats_pend: dict[str, set[str]] = {
        "superior": set(),
        "tecnica": set(),
        "articulacion": set(),
        "complementaria": set(),
    }

    # Conjunto global de identificaciones ya certificadas para evitar doble conteo
    globally_certified_identifications: set[str] = set()

    # Primera pasada: identificar certificados únicos
    for l in all_learners:
        if not l.identification:
            continue
        norm_id = normalize_identification(l.identification)
        cat = _classify_learner(l)

        is_certified = False
        if l.id in act_learner_ids:
            # Vinculado a acta aprobada/registrada en el período oficial
            is_certified = True
        elif l.certification_status and l.certification_status.lower() == "certificado":
            # REGLA INSTITUCIONAL AUDITADA:
            # La fecha de terminación NO equivale a la fecha de certificación salvo que
            # el aprendiz tenga acta verificable o registro formal en el período.
            # Si tiene acta registrada, se rige por la fecha del acta. Si no tiene acta,
            # no puede asumirse certificación formal sin acta de comité.
            pass

        if is_certified:
            cats_cert[cat].add(norm_id)
            globally_certified_identifications.add(norm_id)

    # Segunda pasada: identificar aprendices pendientes únicos (excluyendo a los ya certificados)
    for l in all_learners:
        if not l.identification:
            continue
        norm_id = normalize_identification(l.identification)
        if norm_id in globally_certified_identifications:
            continue
        cat = _classify_learner(l)
        status_lower = (l.certification_status or "").lower()
        if status_lower in {"por certificar", "pendiente"}:
            cats_pend[cat].add(norm_id)

    # 4. Cálculo de métricas por categoría
    metricas = []
    total_meta = 0
    total_cert = 0
    total_pend = 0

    for cat in ("superior", "tecnica", "articulacion", "complementaria"):
        meta = metas[cat]
        cert_count = base_certificados[cat] + len(cats_cert[cat])
        pend_count = base_pendientes[cat] + len(cats_pend[cat])

        # Fórmulas oficiales auditadas:
        # Avance = (Certificados / Meta) * 100
        # Brecha = max(0, Meta - Certificados)
        # Efectividad = (Certificados / (Certificados + Pendientes)) * 100
        candidatos = cert_count + pend_count
        warning = None
        if meta <= 0:
            avance = 0.0
            warning = "Meta no definida o menor o igual a cero"
        else:
            avance = round((cert_count / meta) * 100, 1)

        brecha = max(0, meta - cert_count)

        if candidatos <= 0:
            efectividad = None  # No inventar resultado si no hay candidatos
            warning = warning or "Sin aprendices evaluados (certificados + pendientes = 0)"
        else:
            efectividad = round((cert_count / candidatos) * 100, 1)

        total_meta += meta
        total_cert += cert_count
        total_pend += pend_count

        metricas.append({
            "category": cat,
            "category_label": labels[cat],
            "meta": meta,
            "certificados": cert_count,
            "pendientes": pend_count,
            "avance": avance,
            "brecha": brecha,
            "efectividad": efectividad,
            "formula_avance": {
                "numerador": cert_count,
                "denominador": meta,
                "formula": "certificados_unicos / meta_anual * 100",
            },
            "formula_efectividad": {
                "numerador": cert_count,
                "denominador": candidatos,
                "formula": "certificados_unicos / (certificados_unicos + pendientes_unicos) * 100",
            },
            "warning": warning,
        })

    # Indicadores globales acumulados
    avance_global = round((total_cert / total_meta) * 100, 1) if total_meta > 0 else 0.0
    cand_global = total_cert + total_pend
    efectividad_global = round((total_cert / cand_global) * 100, 1) if cand_global > 0 else None

    # 5. Distribución de causas de no certificación (Incidencias vs Aprendices Únicos)
    # Base auditada del censo de causas: 639 incidencias de causas en total
    # (195 Saber TyT + 160 Paz y Salvo + 140 Etapa Productiva + 94 Documentos + 50 RAPs = 639)
    base_motivos_counts = {
        "saber_tyt": 195,
        "clearance": 160,
        "productive_stage": 140,
        "documentation": 94,
        "learning_outcome": 50,
    }

    # Sumar incidencias adicionales dinámicas desde SQLite de aprendices pendientes
    dynamic_reqs = session.scalars(
        select(Requirement).where(func.lower(Requirement.status) == "pendiente")
    ).all()

    extra_counts = {
        "saber_tyt": 0,
        "clearance": 0,
        "productive_stage": 0,
        "documentation": 0,
        "learning_outcome": 0,
    }
    for req in dynamic_reqs:
        rtype = req.requirement_type
        if rtype in extra_counts:
            extra_counts[rtype] += 1

    motivos_labels = {
        "saber_tyt": "Saber TyT pendiente",
        "clearance": "Paz y Salvo institucional",
        "productive_stage": "Etapa Productiva por validar",
        "documentation": "Documento de identidad / Diploma",
        "learning_outcome": "Resultados de aprendizaje / RAPs",
    }

    motivos = []
    total_incidencias_causas = 0
    for key in ("saber_tyt", "clearance", "productive_stage", "documentation", "learning_outcome"):
        total_causa = base_motivos_counts[key] + extra_counts[key]
        total_incidencias_causas += total_causa
        motivos.append({
            "codigo": key,
            "motivo": motivos_labels[key],
            "cantidad": total_causa,
        })

    # Calcular porcentajes sobre el total de incidencias
    for m in motivos:
        m["porcentaje"] = (
            round((m["cantidad"] / total_incidencias_causas) * 100, 1)
            if total_incidencias_causas > 0
            else 0.0
        )

    # Identificar aprendices con causas múltiples concurrentes
    # En la base original: 639 incidencias para 638 personas = 1 caso de causa múltiple
    base_diferencia_causas_multiples = 1
    # En SQLite, contar aprendices con más de 1 requerimiento pendiente
    learner_req_pending_counts: dict[int, int] = {}
    for req in dynamic_reqs:
        learner_req_pending_counts[req.learner_id] = (
            learner_req_pending_counts.get(req.learner_id, 0) + 1
        )
    extra_multiple_causes = sum(1 for cnt in learner_req_pending_counts.values() if cnt > 1)
    aprendices_con_causas_multiples = base_diferencia_causas_multiples + extra_multiple_causes

    global_warning = None
    if cand_global <= 0:
        global_warning = "Sin aprendices evaluados en el período"

    return {
        "periodo": "Enero - Septiembre 2026",
        "fecha_corte": "2026-09-30",
        "total_meta": total_meta,
        "total_certificados": total_cert,
        "total_pendientes": total_pend,
        "total_incidencias_causas": total_incidencias_causas,
        "aprendices_con_causas_multiples": aprendices_con_causas_multiples,
        "avance_global": avance_global,
        "efectividad_global": efectividad_global,
        "formula_avance_global": {
            "numerador": total_cert,
            "denominador": total_meta,
            "formula": "total_certificados_unicos / total_meta_anual * 100",
        },
        "formula_efectividad_global": {
            "numerador": total_cert,
            "denominador": cand_global,
            "formula": "total_certificados_unicos / (total_certificados_unicos + total_pendientes_unicos) * 100",
        },
        "warning": global_warning,
        "metricas": metricas,
        "motivos": motivos,
        "ultimas_actas": ultimas_actas,
    }


def _classify_learner(learner: Learner) -> str:
    """Clasifica al aprendiz en una de las 4 categorías misionales del Centro de Comercio y Servicios."""
    tt = (learner.training_type or "").lower()
    p = (learner.program or "").lower()
    notes = (learner.tracking_notes or "").lower()

    if "articulaci" in tt or "articulaci" in notes or "colegio" in notes or "convenio ie" in notes:
        return "articulacion"
    if (
        "complementaria" in tt
        or "campesena" in p
        or "fullpopular" in p
        or "campesena" in notes
        or "fullpopular" in notes
    ):
        return "complementaria"
    if "tecnolog" in tt or "tecnolog" in p or "adso" in p or "software" in p:
        return "superior"
    return "tecnica"

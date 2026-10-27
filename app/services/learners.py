from __future__ import annotations

import json
# Se importa hashlib para generar identificadores automáticos únicos para aprendices sin identificación proporcionada. Esto asegura que cada aprendiz pueda ser identificado de manera consistente incluso si no se proporciona un número de identificación explícito.
import hashlib
# Se importa unicodedata para normalizar cadenas de texto, eliminando acentos y caracteres especiales, lo que facilita la comparación y búsqueda de datos.
from unicodedata import normalize
# Se importa Any del módulo typing para indicar que una variable puede ser de cualquier tipo, lo que es útil para funciones que devuelven datos heterogéneos.
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Act, ActLearner, ImportedRecord, Learner, Requirement
from app.services.requirements import REQUIREMENT_TYPES, editor_requirements

POR_CERTIFICAR_STATUS = "Por Certificar"


def parse_sources(value: str | None) -> list[str]:
    """Devuelve la lista de fuentes guardada en ``data_sources`` (JSON).

    Un valor vacío, nulo o ilegible se trata como "sin origen registrado": no se
    inventa de qué archivo salió un aprendiz antiguo.
    """
    if not value:
        return []
    try:
        data = json.loads(value)
    except (TypeError, ValueError):
        return []
    if isinstance(data, list):
        return [str(item) for item in data if str(item).strip()]
    return []


def serialize_sources(sources: list[str]) -> str:
    return json.dumps(sources, ensure_ascii=False)


def set_learner_sources(
    session: Session, sources_by_identification: dict[str, list[str]]
) -> None:
    """Agrega fuentes de origen a los aprendices indicados sin borrar las previas.

    La procedencia se acumula: si un aprendiz ya venía de ACTAS 2026 · PENDIENTES
    y luego aparece en DF14A, conserva ambas etiquetas.
    """
    if not sources_by_identification:
        return
    # Los aprendices pueden haberse creado en esta misma transaccion (autoflush
    # desactivado en algunos entornos): se fuerza el flush para poder consultarlos.
    session.flush()
    learners = session.scalars(
        select(Learner).where(
            Learner.identification.in_(list(sources_by_identification))
        )
    ).all()
    for learner in learners:
        merged = parse_sources(learner.data_sources)
        for label in sources_by_identification[learner.identification]:
            if label and label not in merged:
                merged.append(label)
        if merged:
            learner.data_sources = serialize_sources(merged)


def list_learners(
    session: Session,
    search: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 25,
    missing_requirement: str = "",
) -> dict[str, Any]:
    learner_count = session.scalar(select(func.count()).select_from(Learner)) or 0
    if learner_count == 0:
        sync_learners_from_imports(session)
        session.commit()
    filters = []
    if search.strip():
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                Learner.name.ilike(term),
                Learner.identification.ilike(term),
                Learner.group_code.ilike(term),
                Learner.program.ilike(term),
                Learner.certification_status.ilike(term),
            )
        )
    if status.strip():
        filters.append(Learner.certification_status.ilike(status.strip()))
    if missing_requirement.strip():
        # Solo aprendices con ese tipo de requisito en estado Pendiente. Se usa
        # una subconsulta para no recorrer los requisitos fila por fila.
        filters.append(
            Learner.id.in_(
                select(Requirement.learner_id).where(
                    func.lower(Requirement.requirement_type)
                    == missing_requirement.strip().lower(),
                    func.lower(Requirement.status) == "pendiente",
                )
            )
        )
    query = select(Learner).order_by(Learner.name.asc(), Learner.id.asc())
    count_query = select(func.count()).select_from(Learner)
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)
    total = session.scalar(count_query) or 0
    por_certificar_total = session.scalar(
        select(func.count())
        .select_from(Learner)
        .where(func.lower(Learner.certification_status) == POR_CERTIFICAR_STATUS.lower())
    ) or 0
    learners = session.scalars(
        query.offset((page - 1) * page_size).limit(page_size)
    ).all()
    summaries = _requirements_summary(session, [learner.id for learner in learners])
    return {
        "items": [
            learner_result(learner, _summary(learner.id, summaries))
            for learner in learners
        ],
        "statuses": [
            value
            for value in session.scalars(
                select(Learner.certification_status)
                .where(Learner.certification_status.is_not(None))
                .distinct()
                .order_by(Learner.certification_status.asc())
            ).all()
            if value
        ],
        "requirement_types": REQUIREMENT_TYPES,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "por_certificar_total": por_certificar_total,
    }


def learners_with_pending(session: Session) -> list[dict[str, Any]]:
    """Aprendices con al menos un requisito en Pendiente.

    Reutiliza el mismo formato del listado (origen, motivo y resumen de
    requisitos) para que la tabla se pinte igual desde cualquier vista y sin una
    consulta por fila.
    """
    learner_ids = session.scalars(
        select(Requirement.learner_id)
        .where(func.lower(Requirement.status) == "pendiente")
        .distinct()
    ).all()
    if not learner_ids:
        return []
    learners = session.scalars(
        select(Learner).where(Learner.id.in_(learner_ids)).order_by(Learner.name.asc())
    ).all()
    summaries = _requirements_summary(session, [learner.id for learner in learners])
    return [learner_result(learner, _summary(learner.id, summaries)) for learner in learners]


def learner_result(
    learner: Learner, summary: dict[str, Any] | None = None
) -> dict[str, Any]:
    summary = summary or {"pending": [], "fulfilled_count": 0, "na_count": 0}
    return {
        "id": learner.id,
        "identification": learner.identification,
        "name": learner.name,
        "program": learner.program,
        "group_code": learner.group_code,
        "training_type": learner.training_type,
        "certification_status": learner.certification_status,
        # Motivo de no certificacion (PENDIENTES) y datos de seguimiento. El
        # motivo es el "porque" resumido, distinto de los requisitos y del estado.
        "non_certification_reason": learner.non_certification_reason,
        "certification_month": learner.certification_month,
        "instructor": learner.instructor,
        "act_number": learner.act_number,
        "email": learner.email,
        "phone": learner.phone,
        # Procedencia: archivo(s)/hoja(s) que alimentaron al aprendiz.
        "data_sources": parse_sources(learner.data_sources),
        # Conteo real de requisitos en Pendiente (0 si no tiene ninguno).
        "pending_count": len(summary.get("pending", [])),
        "requirements_summary": summary,
    }


def _empty_summary() -> dict[str, Any]:
    return {"pending": [], "fulfilled_count": 0, "na_count": 0}


def _summary(learner_id: int, summaries: dict[int, dict[str, Any]]) -> dict[str, Any]:
    return summaries.get(learner_id) or _empty_summary()


def _requirements_summary(
    session: Session, learner_ids: list[int]
) -> dict[int, dict[str, Any]]:
    """Resumen de requisitos por aprendiz en una sola consulta.

    ``pending`` lleva las etiquetas legibles de los requisitos en estado
    Pendiente; ``fulfilled_count`` y ``na_count`` cuentan Cumplido y No aplica.
    Evita una consulta por fila al renderizar el listado.
    """
    if not learner_ids:
        return {}
    rows = session.execute(
        select(
            Requirement.learner_id,
            Requirement.requirement_type,
            Requirement.status,
        ).where(Requirement.learner_id.in_(learner_ids))
    ).all()
    summaries: dict[int, dict[str, Any]] = {}
    for learner_id, requirement_type, status_value in rows:
        bucket = summaries.setdefault(learner_id, _empty_summary())
        normalized = str(status_value or "").strip().lower()
        if normalized == "pendiente":
            bucket["pending"].append(
                REQUIREMENT_TYPES.get(requirement_type or "", requirement_type)
            )
        elif normalized == "cumplido":
            bucket["fulfilled_count"] += 1
        elif normalized == "no aplica":
            bucket["na_count"] += 1
    return summaries


def get_learner_detail(session: Session, learner_id: int) -> dict[str, Any] | None:
    learner = session.get(Learner, learner_id)
    if learner is None:
        return None
    requirements = editor_requirements(session, learner_id)
    summary = _requirements_summary(session, [learner_id]).get(learner_id) or _empty_summary()
    return {
        "basic_info": learner_result(learner, summary),
        "requirements": requirements or [],
        "acts": learner_acts(session, learner_id),
        # Pendiente de definición funcional: ImportHistory/ImportedRecord no tienen
        # relación con Learner, así que no se atribuyen importaciones al aprendiz.
        "history": [],
        "dates": {
            "start_date": learner.start_date.isoformat() if learner.start_date else None,
            "termination_date": learner.termination_date.isoformat()
            if learner.termination_date
            else None,
        },
    }


def learner_acts(session: Session, learner_id: int) -> list[dict[str, Any]]:
    """Actas con las que el aprendiz está realmente asociado (tabla act_learners)."""
    rows = session.execute(
        select(Act, ActLearner.observations)
        .join(ActLearner, ActLearner.act_id == Act.id)
        .where(ActLearner.learner_id == learner_id)
        .order_by(Act.act_date.desc(), Act.id.desc())
    ).all()
    return [
        {
            "id": act.id,
            "number": act.number,
            "act_date": act.act_date.isoformat() if act.act_date else None,
            "act_type": act.act_type,
            "review_status": act.review_status,
            "observations": observations,
        }
        for act, observations in rows
    ]


def sync_learners_from_imports(session: Session) -> int:
    records = session.scalars(
        select(ImportedRecord)
        .where(ImportedRecord.information_type == "df14a")
        .order_by(ImportedRecord.id.asc())
    ).all()
    payloads = [json.loads(record.payload) for record in records]
    updated = upsert_learners_from_records(session, payloads)
    if updated:
        # Al rehidratar la tabla de aprendices desde el historial, se conserva la
        # procedencia real: esos registros vienen de DF14A.
        sources: dict[str, list[str]] = {}
        for record in payloads:
            prepared = _prepare_learner_row(record)
            if prepared is None:
                continue
            labels = sources.setdefault(prepared["identification"], [])
            if "DF14A" not in labels:
                labels.append("DF14A")
        set_learner_sources(session, sources)
    return updated


def upsert_learners_from_records(
    session: Session,
    records: list[dict[str, Any]],
    skip_status_for: set[str] | None = None,
) -> int:
    """Crea o actualiza aprendices a partir de registros importables.

    ``skip_status_for`` contiene identificaciones cuyo estado no debe elegirse
    automaticamente (por ejemplo, un conflicto CERTIFICADOS/PENDIENTES). Para
    esos aprendices se conserva el estado existente y, si son nuevos, queda sin
    definir. El resto de campos se actualiza con la primera fila disponible.
    """
    skip_status = {
        _clean_identification(value)
        for value in (skip_status_for or set())
        if value is not None and str(value).strip()
    }
    prepared_rows = []
    for record in records:
        prepared = _prepare_learner_row(record)
        if prepared is not None:
            prepared_rows.append(prepared)
    if not prepared_rows:
        return 0

    # Deduplicamos por identificacion para evitar fallos si el mismo aprendiz
    # aparece en varias hojas (ej: certificados y pendientes) o en el mismo archivo.
    seen = {}
    deduplicated_rows = []
    for row in prepared_rows:
        ident = row["identification"]
        if ident not in seen:
            seen[ident] = True
            deduplicated_rows.append(row)

    identifications = [row["identification"] for row in deduplicated_rows]
    existing = session.scalars(
        select(Learner).where(Learner.identification.in_(identifications))
    ).all()
    existing_by_identification = {learner.identification: learner for learner in existing}

    updated = 0
    for row in deduplicated_rows:
        if row["identification"] in skip_status:
            row["certification_status"] = None
        learner = existing_by_identification.get(row["identification"])
        if learner is None:
            session.add(Learner(**row))
            updated += 1
            continue
        changed = False
        for field, value in row.items():
            if value is None:
                continue
            if field == "name" and value == "Aprendiz sin nombre" and learner.name and learner.name != "Aprendiz sin nombre":
                continue
            if getattr(learner, field) != value:
                setattr(learner, field, value)
                changed = True
        if changed:
            updated += 1
    session.flush()
    return updated


def _prepare_learner_row(record: dict[str, Any]) -> dict[str, Any] | None:
    normalized = {_normalize_key(str(key)): value for key, value in record.items()}
    name = _first_value(normalized, "nombres", "nombre completo", "nombre", "aprendiz")
    apellidos = _first_value(normalized, "apellidos")
    if name and apellidos:
        full_name = f"{name} {apellidos}".strip()
    else:
        full_name = name or apellidos
    identification = _first_value(
        normalized,
        "numero de documento",
        "numero documento",
        "documento",
        "nis",
        "n de identificacion",
        "no de identificacion",
        "numero de identificacion",
        "identificacion",
        "cedula",
    )
    program = _first_value(normalized, "programa", "programa de formacion", "programa formacion")
    group_code = _first_value(normalized, "ficha", "codigo ficha", "grupo")
    training_type = _first_value(
        normalized,
        "nivel",
        "modalidad",
        "tipo formacion",
        "tipo de formacion",
    )
    certification_status = _first_value(
        normalized,
        "estado aspirante",
        "estado certificacion",
        "estado de certificacion",
        "estado",
    )
    email = _first_value(normalized, "correo", "correo electronico")
    act_number = _first_value(normalized, "acta", "numero de acta")
    # Motivo de no certificacion (hoja PENDIENTES) y datos de seguimiento. Se
    # guardan tal como vienen en el archivo: no se inventa ni se resume el motivo.
    non_certification_reason = _first_value(
        normalized, "motivo de no certificacion", "motivo"
    )
    certification_month = _first_value(normalized, "mes de certificacion")
    instructor = _first_value(normalized, "instructor de seguimiento", "instructor")
    phone = _first_value(normalized, "telefono", "celular")
    notes_parts = [p for p in (email, f"Acta: {act_number}" if act_number else None) if p]
    tracking_notes = "; ".join(notes_parts) if notes_parts else _first_value(
        normalized, "observaciones", "novedades", "seguimiento"
    )

    if not full_name and not identification:
        return None

    return {
        "identification": _clean_identification(identification) if identification else _auto_identification(record),
        "name": full_name or "Aprendiz sin nombre",
        "program": program,
        "group_code": group_code,
        "training_type": training_type,
        "certification_status": certification_status,
        "non_certification_reason": non_certification_reason,
        "certification_month": certification_month,
        "instructor": instructor,
        "act_number": act_number,
        "email": email,
        "phone": phone,
        "tracking_notes": tracking_notes,
    }


def _first_value(normalized: dict[str, Any], *candidates: str) -> str | None:
    for candidate in candidates:
        value = normalized.get(_normalize_key(candidate))
        if value is None:
            continue
        text_value = str(value).strip()
        if text_value and text_value.lower() not in {"nan", "nat", "none"}:
            return text_value
    return None


def _normalize_key(value: str) -> str:
    normalized = normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(normalized.lower().replace("_", " ").replace("-", " ").split())


def _auto_identification(record: dict[str, Any]) -> str:
    fingerprint = json.dumps(record, ensure_ascii=True, sort_keys=True, default=str)
    return f"AUTO-{hashlib.sha1(fingerprint.encode('utf-8')).hexdigest()[:12]}"


def _clean_identification(value: str) -> str:
    cleaned = str(value).strip()
    if "_" in cleaned:
        prefix, suffix = cleaned.split("_", 1)
        if suffix.isdigit():
            return suffix
    return cleaned

from __future__ import annotations

import json
import hashlib
from unicodedata import normalize
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import ImportedRecord, Learner
from app.services.requirements import editor_requirements

POR_CERTIFICAR_STATUS = "Por Certificar"


def list_learners(
    session: Session,
    search: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 25,
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
    return {
        "items": [learner_result(learner) for learner in learners],
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
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "por_certificar_total": por_certificar_total,
    }


def learner_result(learner: Learner) -> dict[str, Any]:
    return {
        "id": learner.id,
        "identification": learner.identification,
        "name": learner.name,
        "program": learner.program,
        "group_code": learner.group_code,
        "training_type": learner.training_type,
        "certification_status": learner.certification_status,
    }


def get_learner_detail(session: Session, learner_id: int) -> dict[str, Any] | None:
    learner = session.get(Learner, learner_id)
    if learner is None:
        return None
    requirements = editor_requirements(session, learner_id)
    return {
        "basic_info": learner_result(learner),
        "requirements": requirements or [],
        "acts": [],
        "history": [],
        "dates": {
            "start_date": learner.start_date.isoformat() if learner.start_date else None,
            "termination_date": learner.termination_date.isoformat()
            if learner.termination_date
            else None,
        },
    }


def sync_learners_from_imports(session: Session) -> int:
    records = session.scalars(
        select(ImportedRecord)
        .where(ImportedRecord.information_type == "df14a")
        .order_by(ImportedRecord.id.asc())
    ).all()
    return upsert_learners_from_records(session, [json.loads(record.payload) for record in records])


def upsert_learners_from_records(session: Session, records: list[dict[str, Any]]) -> int:
    prepared_rows = []
    for record in records:
        prepared = _prepare_learner_row(record)
        if prepared is not None:
            prepared_rows.append(prepared)
    if not prepared_rows:
        return 0

    identifications = [row["identification"] for row in prepared_rows]
    existing = session.scalars(
        select(Learner).where(Learner.identification.in_(identifications))
    ).all()
    existing_by_identification = {learner.identification: learner for learner in existing}

    updated = 0
    for row in prepared_rows:
        learner = existing_by_identification.get(row["identification"])
        if learner is None:
            session.add(Learner(**row))
            updated += 1
            continue
        changed = False
        for field, value in row.items():
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
    identification = _first_value(
        normalized,
        "documento",
        "nis",
        "numero documento",
        "n de identificacion",
        "no de identificacion",
        "numero de identificacion",
        "identificacion",
        "cedula",
    )
    program = _first_value(normalized, "programa", "programa de formacion", "programa formacion")
    group_code = _first_value(normalized, "ficha", "codigo ficha", "grupo")
    training_type = _first_value(normalized, "modalidad", "tipo formacion", "tipo de formacion")
    certification_status = _first_value(
        normalized,
        "estado aspirante",
        "estado certificacion",
        "estado de certificacion",
        "estado",
    )
    tracking_notes = _first_value(normalized, "correo electronico", "observaciones", "novedades", "seguimiento")

    if not name and not identification:
        return None

    return {
        "identification": _clean_identification(identification) if identification else _auto_identification(record),
        "name": name or "Aprendiz sin nombre",
        "program": program,
        "group_code": group_code,
        "training_type": training_type,
        "certification_status": certification_status,
        "tracking_notes": tracking_notes,
    }


def _first_value(normalized: dict[str, Any], *candidates: str) -> str | None:
    for candidate in candidates:
        value = normalized.get(_normalize_key(candidate))
        if value is None:
            continue
        text_value = str(value).strip()
        if text_value and text_value.lower() != "nan":
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

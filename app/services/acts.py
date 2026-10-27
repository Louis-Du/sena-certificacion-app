from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models import Act, ActLearner, Learner
from app.services.learners import POR_CERTIFICAR_STATUS, normalize_learner_name, normalize_program_name

REVIEW_STATUSES = {"pending", "reviewed", "rejected"}

# Valor canonico de "Sin estado": un aprendiz sin estado guardado aparece asi en
# la interfaz y debe tratarse igual que un estado vacio al fusionar.
SIN_ESTADO = "sin estado"


def acta_status_merge(current: str | None) -> tuple[str, str | None]:
    """Estado resultante al figurar un aprendiz en un acta oficial (issue #16).

    El acta oficial lista aprendices que cumplen requisitos para certificacion,
    por eso se marcan ``Por Certificar`` (no ``Certificado``). Devuelve
    ``(estado, advertencia)``; la advertencia es ``None`` cuando no hay
    conflicto. Reglas:
    1. ``CERTIFICADOS`` (consolidado) gana: no se degrada a Por Certificar.
    2. ``PENDIENTE`` (consolidado) se conserva: no se borra en silencio.
    3. Estado vacio o ``Sin estado`` pasa a ``Por Certificar``.
    4. Cualquier otro estado se conserva sin advertencia.
    """
    text = (current or "").strip()
    normalized = text.lower()
    if not normalized or normalized == SIN_ESTADO:
        return POR_CERTIFICAR_STATUS, None
    if "certificado" in normalized:
        return text, f"ya figuraba como {text} en el consolidado; se conserva ese estado"
    if "pendiente" in normalized:
        return text, f"figura como {text} en el consolidado; se conserva el estado de pendiente"
    return text, None


def acta_marks_por_certificar(current: str | None) -> bool:
    """Indica si el estado actual pasaria a ``Por Certificar`` al importar un acta."""
    return acta_status_merge(current)[0] == POR_CERTIFICAR_STATUS


def import_act_from_document(
    session: Session,
    extraction: dict[str, Any],
    original_file: str,
    import_id: int | None,
) -> dict[str, Any]:
    """Crea o actualiza el acta y vincula los aprendices identificados.

    Se apoya en la extraccion hecha por :mod:`app.services.parsers`. No inventa
    numero, fecha, documento ni nombre: si no hay numero no se registra el acta y
    los aprendices sin identificacion se informan sin asociarse. Reimportar el
    mismo documento no duplica el acta ni las relaciones, y los campos ya
    guardados no se sobrescriben con valores vacios.

    La funcion no confirma la transaccion: la atomicidad la garantiza el flujo de
    importacion, que revierte todo si algo falla.
    """
    number = (extraction.get("number") or "").strip()
    if not number:
        raise ValueError(
            "No se pudo identificar el numero del acta; no se registra un acta sin numero."
        )

    act = session.scalar(select(Act).where(Act.number == number))
    created = act is None
    if created:
        act = Act(
            number=number,
            act_date=date.fromisoformat(extraction["act_date"])
            if extraction.get("act_date")
            else None,
            act_type=str(extraction.get("act_type") or "").strip() or None,
            original_file=original_file,
            review_status="pending",
            import_id=import_id,
        )
        session.add(act)
        session.flush()
    else:
        if extraction.get("act_date") and not act.act_date:
            act.act_date = date.fromisoformat(extraction["act_date"])
        if extraction.get("act_type") and not act.act_type:
            act.act_type = extraction["act_type"]
        act.import_id = import_id

    linked = 0
    already_linked = 0
    not_linked = 0
    status_conflicts: list[str] = []
    for item in extraction.get("learners") or []:
        document = str(item.get("documento") or "").strip()
        if not document:
            not_linked += 1
            continue
        learner = session.scalar(select(Learner).where(Learner.identification == document))
        if learner is None:
            # El acta oficial lista aprendices que cumplen requisitos para
            # certificacion: se crean en estado "Por Certificar". No se marcan
            # como certificados: el certificado expedido solo consta en el
            # consolidado ACTAS 2026.
            learner = Learner(
                identification=document,
                name=normalize_learner_name(item.get("nombre")) or "Aprendiz sin nombre",
                group_code=str(item.get("ficha") or "").strip() or None,
                program=normalize_program_name(item.get("programa")),
                certification_status=POR_CERTIFICAR_STATUS,
            )
            session.add(learner)
            session.flush()
        else:
            merged_status, warning = acta_status_merge(learner.certification_status)
            if learner.certification_status != merged_status:
                learner.certification_status = merged_status
            if warning:
                status_conflicts.append(f"{learner.name or document}: {warning}")

        existing_link = session.scalar(
            select(ActLearner).where(
                ActLearner.act_id == act.id,
                ActLearner.learner_id == learner.id,
            )
        )
        if existing_link is not None:
            already_linked += 1
            continue
        session.add(
            ActLearner(
                act_id=act.id,
                learner_id=learner.id,
                observations=str(item.get("resultado") or "").strip() or None,
            )
        )
        linked += 1

    return {
        "act_id": act.id,
        "number": number,
        "created": created,
        "linked": linked,
        "already_linked": already_linked,
        "not_linked": not_linked,
        "status_conflicts": status_conflicts,
    }


def list_acts(
    session: Session,
    search: str = "",
    review_status: str | None = None,
) -> list[dict[str, Any]]:
    query = select(Act).options(joinedload(Act.learners)).order_by(Act.act_date.desc(), Act.id.desc())
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            Act.number.ilike(term)
            | Act.act_type.ilike(term)
            | Act.original_file.ilike(term)
            | Act.observations.ilike(term)
        )
    if review_status:
        validate_review_status(review_status)
        query = query.where(Act.review_status == review_status)
    return [act_result(act) for act in session.scalars(query).unique().all()]


def get_act_detail(session: Session, act_id: int) -> dict[str, Any] | None:
    act = session.scalar(
        select(Act)
        .options(joinedload(Act.learners).joinedload(ActLearner.learner))
        .where(Act.id == act_id)
    )
    return act_detail(act) if act else None


def create_act(
    session: Session,
    number: str,
    act_date: date,
    act_type: str | None,
    original_file: str,
    review_status: str,
    observations: str | None,
) -> dict[str, Any]:
    validate_review_status(review_status)
    act = Act(
        number=number.strip(),
        act_date=act_date,
        act_type=act_type.strip() if act_type else None,
        original_file=original_file.strip(),
        review_status=review_status,
        observations=observations.strip() if observations else None,
    )
    session.add(act)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ValueError("Ya existe un acta con ese número.") from error
    session.refresh(act)
    return act_result(act)


def update_act(session: Session, act_id: int, values: dict[str, Any]) -> dict[str, Any]:
    act = session.get(Act, act_id)
    if act is None:
        raise LookupError("Acta no encontrada.")
    if "review_status" in values:
        validate_review_status(values["review_status"])
    for field, value in values.items():
        if value is not None and isinstance(value, str):
            value = value.strip()
        setattr(act, field, value)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise ValueError("Ya existe un acta con ese número.") from error
    session.refresh(act)
    return act_result(act)


def delete_act(session: Session, act_id: int) -> None:
    act = session.get(Act, act_id)
    if act is None:
        raise LookupError("Acta no encontrada.")
    session.delete(act)
    session.commit()


def link_learner_to_act(
    session: Session,
    act_id: int,
    learner_id: int,
    observations: str | None,
) -> dict[str, Any]:
    if session.get(Act, act_id) is None:
        raise LookupError("Acta no encontrada.")
    if session.get(Learner, learner_id) is None:
        raise LookupError("Aprendiz no encontrado.")
    existing = session.scalar(
        select(ActLearner).where(
            ActLearner.act_id == act_id,
            ActLearner.learner_id == learner_id,
        )
    )
    if existing is not None:
        raise ValueError("El aprendiz ya está asociado a esta acta.")
    link = ActLearner(
        act_id=act_id,
        learner_id=learner_id,
        observations=observations.strip() if observations else None,
    )
    session.add(link)
    session.commit()
    session.refresh(link)
    return learner_result(link.learner, link.observations)


def unlink_learner_from_act(session: Session, act_id: int, learner_id: int) -> None:
    link = session.scalar(
        select(ActLearner).where(
            ActLearner.act_id == act_id,
            ActLearner.learner_id == learner_id,
        )
    )
    if link is None:
        raise LookupError("La asociación no existe.")
    session.delete(link)
    session.commit()


def act_options() -> dict[str, list[str]]:
    return {"review_statuses": sorted(REVIEW_STATUSES)}


def act_result(act: Act) -> dict[str, Any]:
    return {
        "id": act.id,
        "number": act.number,
        "act_date": act.act_date.isoformat() if act.act_date else None,
        "act_type": act.act_type,
        "original_file": act.original_file,
        "review_status": act.review_status,
        "observations": act.observations,
        "learners_count": len(act.learners),
    }


def act_detail(act: Act) -> dict[str, Any]:
    result = act_result(act)
    result["learners"] = [
        learner_result(link.learner, link.observations)
        for link in act.learners
        if link.learner is not None
    ]
    return result


def learner_result(learner: Learner, observations: str | None) -> dict[str, Any]:
    return {
        "id": learner.id,
        "identification": learner.identification,
        "name": learner.name,
        "program": learner.program,
        "group_code": learner.group_code,
        "observations": observations,
    }


def validate_review_status(status: str) -> None:
    if status not in REVIEW_STATUSES:
        raise ValueError("Estado de revisión no válido.")

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Learner, Requirement

REQUIREMENT_TYPES = {
    "learning_outcome": "Resultados de aprendizaje / RAP",
    "documentation": "Documentación",
    "productive_stage": "Etapa productiva",
    "clearance": "Paz y salvo",
    "saber_tyt": "Saber TyT",
}
REQUIREMENT_STATUSES = {"Pendiente", "Cumplido", "No aplica"}


def list_requirements(session: Session, learner_id: int) -> list[dict[str, Any]] | None:
    if session.get(Learner, learner_id) is None:
        return None
    requirements = session.scalars(
        select(Requirement)
        .where(Requirement.learner_id == learner_id)
        .order_by(Requirement.id.asc())
    ).all()
    return [requirement_result(item) for item in requirements]


def editor_requirements(session: Session, learner_id: int) -> list[dict[str, Any]] | None:
    registered = list_requirements(session, learner_id)
    if registered is None:
        return None
    by_type = {item["requirement_type"]: item for item in registered}
    return [
        by_type.get(
            requirement_type,
            {
                "id": None,
                "requirement_type": requirement_type,
                "label": label,
                "status": "Pendiente",
                "observations": None,
            },
        )
        for requirement_type, label in REQUIREMENT_TYPES.items()
    ]


def save_requirement(
    session: Session,
    learner_id: int,
    requirement_type: str,
    status: str,
    observations: str | None,
    requirement_id: int | None = None,
) -> dict[str, Any]:
    validate_requirement_type(requirement_type)
    validate_status(status)
    if session.get(Learner, learner_id) is None:
        raise LookupError("Aprendiz no encontrado.")

    requirement = session.get(Requirement, requirement_id) if requirement_id else None
    if requirement_id and (
        requirement is None or requirement.learner_id != learner_id
    ):
        raise LookupError("Requisito no encontrado para este aprendiz.")

    duplicate = session.scalar(
        select(Requirement).where(
            Requirement.learner_id == learner_id,
            func.lower(Requirement.requirement_type) == requirement_type.lower(),
            Requirement.id != (requirement.id if requirement else -1),
        )
    )
    if duplicate is not None:
        raise ValueError("Ya existe este requisito para el aprendiz.")

    if requirement is None:
        requirement = Requirement(learner_id=learner_id, requirement_type=requirement_type)
        session.add(requirement)
    requirement.requirement_type = requirement_type
    requirement.status = status
    requirement.observations = observations.strip() if observations else None
    session.commit()
    session.refresh(requirement)
    return requirement_result(requirement)


def pending_learners(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            Learner,
            func.count(Requirement.id).label("pending_count"),
        )
        .join(Requirement, Requirement.learner_id == Learner.id)
        .where(func.lower(Requirement.status) == "pendiente")
        .group_by(Learner.id)
        .order_by(Learner.name.asc())
    ).all()
    return [
        {
            "id": learner.id,
            "identification": learner.identification,
            "name": learner.name,
            "program": learner.program,
            "group_code": learner.group_code,
            "pending_count": pending_count,
        }
        for learner, pending_count in rows
    ]


def requirement_result(requirement: Requirement) -> dict[str, Any]:
    return {
        "id": requirement.id,
        "requirement_type": requirement.requirement_type,
        "label": REQUIREMENT_TYPES.get(
            requirement.requirement_type or "", requirement.requirement_type
        ),
        "status": requirement.status,
        "observations": requirement.observations,
    }


def validate_requirement_type(requirement_type: str) -> None:
    if requirement_type not in REQUIREMENT_TYPES:
        raise ValueError("Tipo de requisito no válido.")


def validate_status(status: str) -> None:
    if status not in REQUIREMENT_STATUSES:
        raise ValueError("Estado de requisito no válido.")

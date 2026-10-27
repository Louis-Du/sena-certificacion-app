from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Learner, Requirement

REQUIREMENT_TYPES = {
    # Tipos genéricos: se conservan para la edición manual y las cargas
    # históricas de requisitos (matriz "requisitos").
    "learning_outcome": "Resultados de aprendizaje / RAP",
    "documentation": "Documentación",
    "productive_stage": "Etapa productiva",
    "clearance": "Paz y salvo",
    # Tipos del checklist de ACTAS 2026 (hojas CERTIFICADOS / PENDIENTES). Cada
    # uno corresponde a una columna de evidencias del Excel; el importador crea
    # el requisito con el estado leído en la celda (X / N.A. / vacío).
    "biblioteca": "Paz y salvo biblioteca",
    "bienestar": "Bienestar del aprendiz",
    "almacen": "Paz y salvo almacén",
    "etapa_productiva": "Etapa productiva",
    "documento_identidad": "Documento de identidad",
    "saber_tyt": "Saber TyT",
    "ape": "Inscripción APE",
    "carnet": "Destrucción de carnet",
    "certificado_empresa": "Certificado de la empresa",
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
    """Requisitos realmente registrados del aprendiz, en el orden en que se crearon.

    Antes se rellenaba una plantilla con los tipos conocidos vacíos, lo que hacía
    aparecer cinco requisitos en "Pendiente" que no correspondían a ningún dato.
    Ahora solo se devuelven los requisitos que existen en la base de datos; si no
    hay ninguno, la lista viene vacía y la interfaz informa "Sin requisitos
    registrados".
    """
    return list_requirements(session, learner_id)


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


def evidence_status(value: Any) -> str:
    """Traduce el valor de una columna de evidencias de ACTAS 2026 a un estado.

    Regla acordada con el archivo real: ``X``/``x`` -> "Cumplido",
    ``N.A``/``N.A.``/``NA`` -> "No aplica", vacío u otro -> "Pendiente". Nunca se
    marca "Cumplido" si la celda no trae una "X": el estado se lee tal cual
    viene en el documento, no se deduce.
    """
    from app.services.parsers import normalize_text

    texto = normalize_text(value)
    if texto in {"x", "si", "cumplido"}:
        return "Cumplido"
    if texto.replace(" ", "").replace(".", "") in {"na", "noaplica"}:
        return "No aplica"
    return "Pendiente"

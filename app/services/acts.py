"""
Modulo de servicios para la gestion de Actas de certificacion y seguimiento.
Contiene la logica de negocio para:
- Listado paginado de actas con filtros por estado, tipo, fecha y busqueda textual
- Obtencion del detalle de un acta con los aprendices vinculados
- Creacion (con almacenamiento fisico del archivo), actualizacion y eliminacion de actas
- Vinculacion y desvinculacion manual de aprendices con un acta
- Catalogo de opciones (estados de revision y tipos de acta)

Nota: La extraccion automatica de aprendices desde el PDF/DOCX no se implementa aun,
porque no se conoce el formato real de las actas del SENA. La vinculacion es manual.
"""

from __future__ import annotations

import os
import uuid  # Para generar nombres de archivo seguros y unicos
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select  # Construccion de consultas
from sqlalchemy.orm import Session, joinedload  # Sesion y carga ansiosa de relaciones

from app.database import BASE_DIR  # Directorio base de la aplicacion
from app.models import Act, ActLearner, Learner  # Modelos ORM


# Directorio donde se almacenaran los archivos de actas subidos
UPLOAD_DIR = BASE_DIR / "uploads" / "acts"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Etiquetas legibles para los estados de revision de un acta
REVIEW_STATUS_LABELS = {
    "pending": "Pendiente de revision",
    "reviewed": "Revisada",
    "approved": "Aprobada",
    "rejected": "Rechazada",
}

# Tipos de acta soportados con su etiqueta para UI
ACT_TYPE_LABELS = {
    "certificacion": "Acta de certificacion",
    "seguimiento": "Acta de seguimiento",
    "comite": "Acta de comite",
    "otro": "Otro tipo de acta",
}


def list_acts(
    session: Session,
    search: str = "",
    page: int = 1,
    page_size: int = 25,
    review_status: str | None = None,
    act_type: str | None = None,
    act_date_from: date | None = None,
    act_date_to: date | None = None,
) -> dict[str, Any]:
    """
    Lista paginada de actas con soporte de busqueda y filtros.
    - search: busca por numero de acta, nombre de archivo u observaciones
    - review_status: filtra por estado de revision (pending/reviewed/approved/rejected)
    - act_type: filtra por tipo de acta (certificacion/seguimiento/comite/otro)
    - act_date_from / act_date_to: rango de fechas del acta
    Retorna items, total de registros y metadatos de paginacion.
    """
    filters = []
    if search.strip():
        term = f"%{search.strip()}%"
        filters.append(
            or_(
                Act.number.ilike(term),
                Act.original_file.ilike(term),
                Act.observations.ilike(term),
            )
        )
    if review_status:
        filters.append(Act.review_status == review_status)
    if act_type:
        filters.append(Act.act_type.ilike(f"%{act_type}%"))
    if act_date_from:
        filters.append(Act.act_date >= act_date_from)
    if act_date_to:
        filters.append(Act.act_date <= act_date_to)
    query = select(Act).order_by(Act.act_date.desc().nullslast(), Act.id.desc())
    count_query = select(func.count()).select_from(Act)
    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)
    total = session.scalar(count_query) or 0
    acts = session.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [act_result(act) for act in acts],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


def act_result(act: Act) -> dict[str, Any]:
    """
    Convierte un objeto Act ORM a un diccionario plano para el listado.
    Incluye tanto el valor crudo como la etiqueta legible para tipo de acta
    y estado de revision. Las fechas se serializan a ISO 8601.
    """
    return {
        "id": act.id,
        "number": act.number,
        "act_date": act.act_date.isoformat() if act.act_date else None,
        "act_type": act.act_type,
        "act_type_label": ACT_TYPE_LABELS.get(act.act_type, act.act_type) if act.act_type else None,
        "original_file": act.original_file,
        "review_status": act.review_status,
        "review_status_label": REVIEW_STATUS_LABELS.get(act.review_status, act.review_status),
        "observations": act.observations,
    }


def get_act_detail(session: Session, act_id: int) -> dict[str, Any] | None:
    """
    Obtiene el detalle completo de un acta por ID, incluyendo la lista de
    aprendices vinculados a traves de ActLearner. Usa joinedload para evitar
    consultas N+1. Retorna None si el acta no existe.
    """
    act = session.scalar(
        select(Act)
        .options(joinedload(Act.learners).joinedload(ActLearner.learner))
        .where(Act.id == act_id)
    )
    if act is None:
        return None
    learners = []
    for link in act.learners:
        if link.learner:
            learners.append(
                {
                    "id": link.learner.id,
                    "identification": link.learner.identification,
                    "name": link.learner.name,
                    "program": link.learner.program,
                    "group_code": link.learner.group_code,
                    "observations": link.observations,
                }
            )
    return {
        **act_result(act),
        "learners": learners,
        "learners_count": len(learners),
    }


def create_act(
    session: Session,
    *,
    number: str | None = None,
    act_date: date | None = None,
    act_type: str | None = None,
    original_file_name: str,
    file_content: bytes | None = None,
    review_status: str = "pending",
    observations: str | None = None,
) -> dict[str, Any]:
    """
    Crea un nuevo registro de acta y opcionalmente almacena el archivo fisico.
    - Si file_content se proporciona, guarda el archivo en UPLOAD_DIR con un
      nombre UUID unico (para evitar colisiones y path traversal).
    - Si no hay contenido, usa original_file_name directamente (modo offline).
    Retorna el diccionario del acta creada.
    """
    stored_file_name = _save_act_file(original_file_name, file_content) if file_content else original_file_name
    act = Act(
        number=number,
        act_date=act_date,
        act_type=act_type,
        original_file=stored_file_name,
        review_status=review_status,
        observations=observations,
    )
    session.add(act)
    session.flush()
    session.refresh(act)
    return act_result(act)


def update_act(
    session: Session,
    act_id: int,
    *,
    number: str | None = None,
    act_date: date | None = None,
    act_type: str | None = None,
    review_status: str | None = None,
    observations: str | None = None,
) -> dict[str, Any] | None:
    """
    Actualiza los metadatos de un acta existente (numero, fecha, tipo, estado,
    observaciones). Los campos con valor None se mantienen sin cambios.
    Retorna None si el acta no existe.
    """
    act = session.get(Act, act_id)
    if act is None:
        return None
    if number is not None:
        act.number = number
    if act_date is not None:
        act.act_date = act_date
    if act_type is not None:
        act.act_type = act_type
    if review_status is not None:
        act.review_status = review_status
    if observations is not None:
        act.observations = observations
    session.flush()
    session.refresh(act)
    return act_result(act)


def delete_act(session: Session, act_id: int) -> bool:
    """
    Elimina un acta por su ID. Elimina tambien el archivo fisico asociado si existe.
    Retorna True si se elimino, False si el acta no existia.
    """
    act = session.get(Act, act_id)
    if act is None:
        return False
    _remove_act_file(act.original_file)
    session.delete(act)
    session.flush()
    return True


def link_learner_to_act(
    session: Session,
    act_id: int,
    learner_id: int,
    observations: str | None = None,
) -> dict[str, Any] | None:
    """
    Vincula manualmente un aprendiz a un acta a traves de la tabla puente ActLearner.
    Si el vinculo ya existe, actualiza solo las observaciones si se proporcionan.
    Retorna None si el acta o el aprendiz no existen.
    """
    act = session.get(Act, act_id)
    learner = session.get(Learner, learner_id)
    if act is None or learner is None:
        return None
    existing = session.scalar(
        select(ActLearner).where(ActLearner.act_id == act_id, ActLearner.learner_id == learner_id)
    )
    if existing:
        # Vinculo existente: actualizar observaciones si vienen nuevas
        if observations is not None:
            existing.observations = observations
            session.flush()
        link = existing
    else:
        # Vinculo nuevo
        link = ActLearner(act_id=act_id, learner_id=learner_id, observations=observations)
        session.add(link)
        session.flush()
    return {
        "act_id": link.act_id,
        "learner_id": link.learner_id,
        "observations": link.observations,
    }


def unlink_learner_from_act(session: Session, act_id: int, learner_id: int) -> bool:
    """
    Elimina la vinculacion entre un aprendiz y un acta (tabla ActLearner).
    Retorna True si existia el vinculo y se elimino, False en caso contrario.
    """
    link = session.scalar(
        select(ActLearner).where(ActLearner.act_id == act_id, ActLearner.learner_id == learner_id)
    )
    if link is None:
        return False
    session.delete(link)
    session.flush()
    return True


def list_act_options() -> dict[str, list[dict[str, str]]]:
    """
    Retorna el catalogo de opciones para poblar los selectores de la UI:
    - review_statuses: estados de revision con sus etiquetas
    - act_types: tipos de acta con sus etiquetas
    """
    return {
        "review_statuses": [
            {"value": value, "label": label} for value, label in REVIEW_STATUS_LABELS.items()
        ],
        "act_types": [
            {"value": value, "label": label} for value, label in ACT_TYPE_LABELS.items()
        ],
    }


def _save_act_file(original_name: str, content: bytes) -> str:
    """
    Almacena un archivo de acta en el directorio de uploads.
    - Genera un nombre aleatorio UUID4 + extension original para evitar colisiones
      y ataques de path traversal.
    - Retorna solo el nombre de archivo (sin ruta) para almacenar en BD.
    """
    suffix = Path(original_name).suffix or ".bin"
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    target = UPLOAD_DIR / safe_name
    target.write_bytes(content)
    return safe_name


def _remove_act_file(stored_name: str) -> None:
    """
    Elimina el archivo fisico de un acta si existe.
    Protegido contra rutas fuera de UPLOAD_DIR (solo usa stored_name como componente final).
    Silencia errores de borrado para no fallar la transaccion si el archivo ya no existe.
    """
    if not stored_name:
        return
    target = UPLOAD_DIR / stored_name
    if target.exists() and target.is_file():
        try:
            target.unlink()
        except OSError:
            pass

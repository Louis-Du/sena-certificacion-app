from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Learner


def list_learners(session: Session, limit: int = 50) -> list[dict[str, Any]]:
    learners = session.scalars(
        select(Learner).order_by(Learner.name.asc(), Learner.id.asc()).limit(limit)
    ).all()
    return [learner_result(learner) for learner in learners]


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

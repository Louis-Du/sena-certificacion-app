"""Actividad temporal para el heatmap de certificación.

Agrega cambios de estado (RequirementStatusHistory) e importaciones
por día, y permite consultar aprendices relacionados a una fecha.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import ImportHistory, Learner, RequirementStatusHistory


def _as_utc_date(value: datetime | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date()
    return value


def build_activity_heatmap(session: Session, year: int = 2026) -> dict[str, Any]:
    """Devuelve celdas diarias con conteo de eventos de actividad real."""
    start = date(year, 1, 1)
    end = date(year, 12, 31)

    start_dt = datetime(year, 1, 1, tzinfo=timezone.utc)
    end_dt = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    counts: dict[str, int] = defaultdict(int)
    by_source: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    # Cambios de requisitos / estado
    history_rows = session.scalars(
        select(RequirementStatusHistory).where(
            RequirementStatusHistory.recorded_at >= start_dt,
            RequirementStatusHistory.recorded_at <= end_dt,
        )
    ).all()
    for row in history_rows:
        day = _as_utc_date(row.recorded_at)
        if not day:
            continue
        key = day.isoformat()
        counts[key] += 1
        by_source[key]["status_changes"] += 1

    # Importaciones confirmadas
    imports = session.scalars(
        select(ImportHistory).where(
            ImportHistory.imported_at >= start_dt,
            ImportHistory.imported_at <= end_dt,
        )
    ).all()
    for item in imports:
        day = _as_utc_date(item.imported_at)
        if not day:
            continue
        key = day.isoformat()
        # Peso por volumen de registros tocados
        weight = max(1, int((item.new_records or 0) + (item.updated_records or 0)))
        # Limitar peso para no saturar la escala visual
        weight = min(weight, 40)
        counts[key] += weight
        by_source[key]["imports"] += 1
        by_source[key]["import_records"] += int(
            (item.new_records or 0) + (item.updated_records or 0)
        )

    if counts:
        max_count = max(counts.values())
    else:
        max_count = 0

    def level(n: int) -> int:
        if n <= 0 or max_count <= 0:
            return 0
        ratio = n / max_count
        if ratio <= 0.15:
            return 1
        if ratio <= 0.35:
            return 2
        if ratio <= 0.6:
            return 3
        return 4

    days: list[dict[str, Any]] = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        n = int(counts.get(key, 0))
        days.append(
            {
                "date": key,
                "count": n,
                "level": level(n),
                "sources": dict(by_source.get(key, {})),
            }
        )
        cursor += timedelta(days=1)

    return {
        "year": year,
        "max_count": max_count,
        "total_events": int(sum(counts.values())),
        "days": days,
        "source": "requirement_status_history+import_history",
    }


def learners_for_activity_date(
    session: Session, day: date, limit: int = 25
) -> dict[str, Any]:
    """Aprendices relacionados con actividad en una fecha concreta."""
    start_dt = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=1)

    rows = session.scalars(
        select(RequirementStatusHistory)
        .options(joinedload(RequirementStatusHistory.learner))
        .where(
            RequirementStatusHistory.recorded_at >= start_dt,
            RequirementStatusHistory.recorded_at < end_dt,
        )
        .order_by(RequirementStatusHistory.recorded_at.desc())
        .limit(limit * 3)
    ).unique().all()

    seen: set[int] = set()
    learners: list[dict[str, Any]] = []
    for row in rows:
        learner = row.learner
        if not learner or learner.id in seen:
            continue
        seen.add(learner.id)
        learners.append(
            {
                "id": learner.id,
                "name": learner.full_name or learner.name or "Sin nombre",
                "identification": learner.identification,
                "certification_status": learner.certification_status,
                "requirement_type": row.requirement_type,
                "status": row.status,
                "recorded_at": row.recorded_at.isoformat() if row.recorded_at else None,
            }
        )
        if len(learners) >= limit:
            break

    imports = session.scalars(
        select(ImportHistory).where(
            ImportHistory.imported_at >= start_dt,
            ImportHistory.imported_at < end_dt,
        )
    ).all()

    return {
        "date": day.isoformat(),
        "learners": learners,
        "learner_count": len(learners),
        "imports": [
            {
                "id": item.id,
                "file_name": item.file_name,
                "new_records": item.new_records,
                "updated_records": item.updated_records,
                "status": item.status,
            }
            for item in imports
        ],
    }

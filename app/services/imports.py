from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from unicodedata import normalize

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Act,
    ActLearner,
    ImportHistory,
    ImportedRecord,
    Learner,
    RequirementStatusHistory,
)
from app.services import parsers
from app.services.acts import acta_marks_por_certificar, import_act_from_document
from app.services.learners import (
    _prepare_learner_row,
    set_learner_sources,
    upsert_learners_from_records,
)
from app.services.records import (
    parse_records,
    prepare_records,
    record_key,
)
from app.services.requirement_conflicts import (
    EVIDENCE_FIELDS,
    REQUIREMENT_CONFLICT_STATUSES,
    requirement_conflict_key,
    requirement_conflicts,
)
from app.services.validation import (
    TYPE_LABELS,
    ValidationResult,
    coherence_conflicts,
    validate_file,
)


@dataclass
class StagedImport:
    validation_id: str
    file_name: str
    content: bytes
    information_type: str
    result: ValidationResult


_staged_imports: dict[str, StagedImport] = {}

# Estados canonicos admitidos al resolver un cruce CERTIFICADOS/PENDIENTES.
CONFLICT_STATUSES = {"CERTIFICADOS", "PENDIENTE"}
_CONFLICT_STATUS_LABELS = {"CERTIFICADOS": "Certificado", "PENDIENTE": "Pendiente"}


def _normalize_conflict_status(value: Any) -> str | None:
    status = str(value or "").strip().upper()
    return status if status in CONFLICT_STATUSES else None


def _explicit_conflict_resolutions(
    conflicts: list[dict[str, Any]],
    raw_resolutions: list[dict[str, Any]] | None,
) -> dict[str, str]:
    """Lee y valida las decisiones enviadas por la UI."""
    required = {item["identification"]: item for item in conflicts}
    if not required:
        return {}

    resolutions: dict[str, str] = {}
    invalid: list[str] = []
    for item in raw_resolutions or []:
        identification = str(item.get("identification") or "").strip()
        if identification not in required:
            # Una resolucion de otro lote no debe romper la importacion actual.
            continue
        status = _normalize_conflict_status(item.get("status"))
        if status is None:
            invalid.append(
                f"{identification}: {str(item.get('status') or '').strip() or 'sin estado'}"
            )
            continue
        resolutions[identification] = status

    if invalid:
        raise ValueError(
            "Resolucion de conflicto no valida para "
            f"{', '.join(invalid)}. Use CERTIFICADOS o PENDIENTE."
        )
    return resolutions


def stored_conflict_resolutions(
    session: Session, conflicts: list[dict[str, Any]]
) -> dict[str, str]:
    """Desempates vigentes o historicos para los documentos en conflicto.

    ``conflict_resolution`` solo existe mientras el documento esta en la
    interseccion. ``last_conflict_resolution`` conserva la ultima decision para
    reaplicarla en silencio si el documento vuelve a aparecer en ambas hojas.
    Las bases anteriores a la columna nueva se reconocen por la nota historica.
    """
    documents = {
        str(item.get("identification") or "").strip() for item in conflicts
    }
    documents.discard("")
    if not documents:
        return {}

    learners = session.scalars(
        select(Learner).where(Learner.identification.in_(documents))
    ).all()
    resolutions: dict[str, str] = {}
    for learner in learners:
        status = _normalize_conflict_status(learner.conflict_resolution)
        if status is None:
            status = _normalize_conflict_status(
                getattr(learner, "last_conflict_resolution", None)
            )
        if status is None:
            notes = learner.tracking_notes or ""
            if "Conflicto resuelto: Certificado" in notes:
                status = "CERTIFICADOS"
            elif "Conflicto resuelto: Pendiente" in notes:
                status = "PENDIENTE"
        if status is not None:
            resolutions[learner.identification] = status
    return resolutions


def split_conflicts_by_resolution(
    session: Session, conflicts: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Separa los cruces que aun requieren decision de los ya desempatados."""
    saved = stored_conflict_resolutions(session, conflicts)
    unresolved = [
        item
        for item in conflicts
        if str(item.get("identification") or "").strip() not in saved
    ]
    return unresolved, saved


def _resolve_conflict_decisions(
    session: Session,
    conflicts: list[dict[str, Any]],
    raw_resolutions: list[dict[str, Any]] | None,
) -> dict[str, str]:
    """Combina decisiones nuevas con los desempates ya guardados.

    La decision enviada por el usuario tiene prioridad. Si el documento ya
    tenia un desempate vigente, se reutiliza sin volver a interrumpir el flujo.
    """
    required = {item["identification"]: item for item in conflicts}
    if not required:
        return {}

    explicit = _explicit_conflict_resolutions(conflicts, raw_resolutions)
    effective = {**stored_conflict_resolutions(session, conflicts), **explicit}
    missing = [
        identification
        for identification in required
        if identification not in effective
    ]
    if missing:
        raise ValueError(
            f"Faltan {len(missing)} resolucion(es) de conflicto: {', '.join(missing)}. "
            "Elija Certificado o Pendiente para cada aprendiz antes de confirmar."
        )
    return effective


def _apply_conflict_resolutions(session: Session, resolutions: dict[str, str]) -> None:
    """Fija el estado elegido y deja rastro en las notas de seguimiento."""
    learners = session.scalars(
        select(Learner).where(Learner.identification.in_(resolutions))
    ).all()
    for learner in learners:
        status = resolutions[learner.identification]
        learner.certification_status = status
        learner.conflict_resolution = status
        learner.last_conflict_resolution = status
        note = f"Conflicto resuelto: {_CONFLICT_STATUS_LABELS[status]}"
        current = (learner.tracking_notes or "").strip()
        if note not in current:
            learner.tracking_notes = f"{current}; {note}" if current else note
    session.flush()


def _clear_inactive_conflict_resolutions(
    session: Session, active_documents: set[str]
) -> int:
    """Limpia el desempate de documentos que ya no estan en la interseccion.

    La decision historica (``last_conflict_resolution``) y la nota de auditoria
    se conservan. Solo se retira el estado condicional que ya no aplica.
    """
    learners = session.scalars(
        select(Learner).where(Learner.conflict_resolution.is_not(None))
    ).all()
    cleared = 0
    for learner in learners:
        if learner.identification not in active_documents:
            learner.conflict_resolution = None
            cleared += 1
    if cleared:
        session.flush()
    return cleared


# Origen con el que se guarda una decision manual de incongruencia entre una
# columna de evidencias y el MOTIVO DE NO CERTIFICACION. No se agrega una
# columna nueva al aprendiz: el historial de requisitos ya conserva el hecho.
REQUIREMENT_CONFLICT_SOURCE = "conflict:requirement"


def _normalize_requirement_conflict_status(value: Any) -> str | None:
    """Devuelve el estado canonico elegido por el usuario, o ``None``."""
    text = str(value or "").strip().lower()
    for status in REQUIREMENT_CONFLICT_STATUSES:
        if status.lower() == text:
            return status
    return None


def _explicit_requirement_conflict_resolutions(
    conflicts: list[dict[str, Any]],
    raw_resolutions: list[dict[str, Any]] | None,
) -> dict[str, str]:
    """Lee y valida las decisiones de requisitos enviadas por la UI.

    La llave es ``documento|tipo_requisito`` para que un mismo aprendiz pueda
    tener varias decisiones en el mismo lote sin que se pisen entre si.
    """
    required = {
        requirement_conflict_key(item["identification"], item["requirement_type"]): item
        for item in conflicts
    }
    if not required:
        return {}

    resolutions: dict[str, str] = {}
    invalid: list[str] = []
    for item in raw_resolutions or []:
        identification = str(item.get("identification") or "").strip()
        requirement_type = str(item.get("requirement_type") or "").strip()
        key = requirement_conflict_key(identification, requirement_type)
        if key not in required:
            # Una decision de otro lote no debe romper la importacion actual.
            continue
        status = _normalize_requirement_conflict_status(item.get("status"))
        if status is None:
            invalid.append(
                f"{identification} · {requirement_type}: "
                f"{str(item.get('status') or '').strip() or 'sin estado'}"
            )
            continue
        resolutions[key] = status

    if invalid:
        raise ValueError(
            "Resolucion de requisito no valida para "
            f"{', '.join(invalid)}. Use Cumplido, Pendiente o No aplica."
        )
    return resolutions


def stored_requirement_conflict_resolutions(
    session: Session, conflicts: list[dict[str, Any]]
) -> dict[str, str]:
    """Ultima decision manual guardada para cada requisito en conflicto.

    Se apoya en ``RequirementStatusHistory`` con origen
    ``conflict:requirement``. Asi una reimportacion del mismo consolidado no
    vuelve a interrumpir al usuario y, si el requisito cambia de estado mas
    adelante, la decision historica se conserva como referencia.
    """
    if not conflicts:
        return {}

    documents = {
        str(item.get("identification") or "").strip() for item in conflicts
    }
    documents.discard("")
    requirement_types = {
        str(item.get("requirement_type") or "").strip() for item in conflicts
    }
    requirement_types.discard("")
    if not documents or not requirement_types:
        return {}

    learners = session.scalars(
        select(Learner).where(Learner.identification.in_(documents))
    ).all()
    learner_by_id = {learner.id: learner for learner in learners}
    learner_by_document = {learner.identification: learner for learner in learners}
    if not learner_by_id:
        return {}

    types_by_learner: dict[int, set[str]] = {}
    for item in conflicts:
        learner = learner_by_document.get(
            str(item.get("identification") or "").strip()
        )
        if learner is None:
            continue
        types_by_learner.setdefault(learner.id, set()).add(
            str(item.get("requirement_type") or "").strip()
        )
    if not types_by_learner:
        return {}

    events = session.scalars(
        select(RequirementStatusHistory)
        .where(
            RequirementStatusHistory.learner_id.in_(types_by_learner),
            RequirementStatusHistory.requirement_type.in_(requirement_types),
            RequirementStatusHistory.source == REQUIREMENT_CONFLICT_SOURCE,
        )
        .order_by(
            RequirementStatusHistory.recorded_at.desc(),
            RequirementStatusHistory.id.desc(),
        )
    ).all()

    resolutions: dict[str, str] = {}
    for event in events:
        learner = learner_by_id.get(event.learner_id)
        if learner is None:
            continue
        if event.requirement_type not in types_by_learner.get(event.learner_id, set()):
            continue
        key = requirement_conflict_key(learner.identification, event.requirement_type)
        if key in resolutions:
            continue
        status = _normalize_requirement_conflict_status(event.status)
        if status is not None:
            resolutions[key] = status
    return resolutions


def split_requirement_conflicts_by_resolution(
    session: Session, conflicts: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Separa los requisitos que aun requieren decision de los ya resueltos."""
    saved = stored_requirement_conflict_resolutions(session, conflicts)
    unresolved = [
        item
        for item in conflicts
        if requirement_conflict_key(
            item.get("identification"), item.get("requirement_type")
        )
        not in saved
    ]
    return unresolved, saved


def _resolve_requirement_conflict_decisions(
    session: Session,
    conflicts: list[dict[str, Any]],
    raw_resolutions: list[dict[str, Any]] | None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Combina decisiones nuevas con las guardadas y exige cubrir el lote.

    Devuelve ``(decisiones_efectivas, decisiones_explicitas)``. La segunda
    tupla permite distinguir en el historial entre una resolucion manual y una
    decision previa reaplicada en silencio.
    """
    required = {
        requirement_conflict_key(item["identification"], item["requirement_type"]): item
        for item in conflicts
    }
    if not required:
        return {}, {}

    explicit = _explicit_requirement_conflict_resolutions(conflicts, raw_resolutions)
    effective = {
        **stored_requirement_conflict_resolutions(session, conflicts),
        **explicit,
    }
    missing = [key for key in required if key not in effective]
    if missing:
        labels = [
            f"{required[key]['identification']} · {required[key]['requirement_label']}"
            for key in missing
        ]
        raise ValueError(
            f"Faltan {len(missing)} resolucion(es) de requisito: "
            f"{', '.join(labels)}. Elija Cumplido, Pendiente o No aplica para "
            "cada requisito antes de confirmar."
        )
    return effective, explicit


def _apply_requirement_conflict_resolutions(
    session: Session,
    conflicts: list[dict[str, Any]],
    resolutions: dict[str, str],
    recorded_at: datetime | None = None,
) -> int:
    """Fija el estado elegido y deja un evento de historial trazable."""
    from app.services.requirements import upsert_requirement_status

    if not resolutions:
        return 0

    documents = {
        item["identification"]
        for item in conflicts
        if requirement_conflict_key(item["identification"], item["requirement_type"])
        in resolutions
    }
    if not documents:
        return 0
    learners = session.scalars(
        select(Learner).where(Learner.identification.in_(documents))
    ).all()
    by_document = {learner.identification: learner for learner in learners}

    count = 0
    for item in conflicts:
        key = requirement_conflict_key(
            item["identification"], item["requirement_type"]
        )
        status = resolutions.get(key)
        if status is None:
            continue
        learner = by_document.get(item["identification"])
        if learner is None:
            continue
        upsert_requirement_status(
            session,
            learner_id=learner.id,
            requirement_type=item["requirement_type"],
            status=status,
            source=REQUIREMENT_CONFLICT_SOURCE,
            recorded_at=recorded_at,
            note=f"Conflicto resuelto: {status}",
            force_history=True,
            dedupe_history=True,
        )
        count += 1
    return count


def _actas_snapshot_has_both_sheets(content: bytes) -> bool:
    """Indica si el lote trae ambas hojas del cruce.

    Sin las dos hojas no se puede afirmar que un documento haya dejado la
    interseccion, asi que no se limpian desempates en ese caso.
    """
    try:
        sheets = parsers.list_excel_sheets(content)
    except Exception:
        return False
    names = {str(sheet).strip().upper() for sheet in sheets or []}
    return {"CERTIFICADOS", "PENDIENTES"}.issubset(names)


def stage_file(
    file_name: str,
    content: bytes,
    information_type: str,
    validation_id: str | None = None,
) -> StagedImport:
    result = validate_file(file_name, content, information_type)
    validation_id = validation_id or uuid.uuid4().hex
    staged = StagedImport(validation_id, file_name, content, information_type, result)
    _staged_imports[validation_id] = staged
    return staged


def get_staged(validation_id: str) -> StagedImport | None:
    return _staged_imports.get(validation_id)


def import_preview(staged: StagedImport, session: Session) -> dict[str, Any]:
    prepared = prepare_records(staged.file_name, staged.content, staged.information_type)
    if not prepared.importable:
        raise ValueError(
            "El archivo no contiene registros importables. Corrija los errores de "
            "validacion antes de confirmar."
        )

    keys = [entry.key for entry in prepared.importable]
    existing = _existing_keys_multi(session, keys)
    warnings = [
        check["label"]
        for check in staged.result.checks
        if check["status"] in {"warning", "error"}
    ]
    conflicts = (
        coherence_conflicts(prepared)
        if staged.information_type == "actas_completo"
        else []
    )
    saved_resolutions = (
        stored_conflict_resolutions(session, conflicts) if conflicts else {}
    )
    requirement_items = (
        requirement_conflicts(prepared)
        if staged.information_type == "actas_completo"
        else []
    )
    saved_requirement_resolutions = (
        stored_requirement_conflict_resolutions(session, requirement_items)
        if requirement_items
        else {}
    )
    preview = {
        "validation_id": staged.validation_id,
        "file_name": staged.file_name,
        "information_type": TYPE_LABELS.get(staged.information_type, staged.information_type),
        "records_count": len(prepared.importable),
        "parsed_records": prepared.records_found,
        "rejected_records": prepared.rejected_records,
        "duplicate_records": prepared.duplicate_records,
        "new_records": sum(key not in existing for key in keys),
        "updated_records": sum(key in existing for key in keys),
        "warnings": warnings,
        "status": staged.result.status,
        "detected_columns": staged.result.detected_columns,
        "missing_columns": staged.result.missing_columns,
        "breakdown": prepared.breakdown(),
        "coherence_conflicts": conflicts,
        # Mapa documento -> desempate guardado. La UI lo usa para preseleccionar
        # la decision previa sin alterar el contrato de ``coherence_conflicts``.
        "conflict_resolutions": saved_resolutions,
        # Incongruencias entre cada columna de evidencias y el motivo de no
        # certificacion. La llave de una decision es ``documento|requisito``.
        "requirement_conflicts": requirement_items,
        "requirement_conflict_resolutions": saved_requirement_resolutions,
        "missing_complementaria": getattr(staged.result, "missing_complementaria", False),
    }
    if staged.information_type == "acta":
        # Una acta no se revisa como una tabla: la vista previa explica si el
        # acta es nueva, que aprendices se asociaran y cuales ya lo estaban.
        preview["acta"] = _acta_preview(staged, session)
    return preview


def _acta_preview(staged: StagedImport, session: Session) -> dict[str, Any]:
    """Resume la relacion propuesta entre el acta y los aprendices leidos."""
    extraction = parsers.extract_acta_data(staged.file_name, staged.content)
    number = extraction.get("number")
    act = session.scalar(select(Act).where(Act.number == number)) if number else None

    documents = [item.get("documento") for item in extraction.get("learners") or [] if item.get("documento")]
    statuses: dict[str, str | None] = {}
    if documents:
        statuses = dict(
            session.execute(
                select(Learner.identification, Learner.certification_status).where(
                    Learner.identification.in_(documents)
                )
            ).all()
        )
    registered = set(statuses)
    already_linked: set[str] = set()
    if act is not None:
        already_linked = set(
            session.scalars(
                select(Learner.identification)
                .join(ActLearner, ActLearner.learner_id == Learner.id)
                .where(ActLearner.act_id == act.id)
            ).all()
        )

    to_link = 0
    already = 0
    not_registered: list[str] = []
    for document in documents:
        if document in already_linked:
            already += 1
        else:
            to_link += 1
        if document not in registered:
            not_registered.append(document)

    # Cuantos aprendices quedaran en estado "Por Certificar" tras confirmar: los
    # nuevos y los que aun no tienen estado. Los ya CERTIFICADOS o PENDIENTES del
    # consolidado no se degradan.
    por_certificar = sum(
        1 for document in documents if acta_marks_por_certificar(statuses.get(document))
    )

    return {
        "number": number,
        "act_date": extraction.get("act_date"),
        "act_type": extraction.get("act_type"),
        "exists": act is not None,
        "act_id": act.id if act is not None else None,
        "learners_found": len(documents),
        "learners_to_link": to_link,
        "learners_already_linked": already,
        "learners_not_registered": not_registered,
        "learners_por_certificar": por_certificar,
        "warnings": extraction.get("warnings", []),
    }


def _format_acta_message(result: dict[str, Any]) -> str:
    estado = "creada" if result["created"] else "actualizada"
    parts = [
        f"Acta No. {result['number']} {estado}",
        f"{result['linked']} aprendiz(es) vinculado(s)",
    ]
    if result["already_linked"]:
        parts.append(f"{result['already_linked']} ya estaba(n) asociado(s)")
    if result["not_linked"]:
        parts.append(f"{result['not_linked']} registro(s) sin identificacion, no vinculados")
    # Conflicto de estado: aprendices que ya figuran en el consolidado con otro
    # estado (CERTIFICADOS/PENDIENTE) y se conservan sin degradar a Por Certificar.
    conflicts = result.get("status_conflicts") or []
    if conflicts:
        parts.append(
            f"{len(conflicts)} aprendiz(es) conservan su estado del consolidado "
            "(no se degradan a Por Certificar)"
        )
    return ". ".join(parts) + "."


def _format_breakdown_message(breakdown: dict[str, dict[str, int]]) -> str:
    labels = {
        "certificados": "aprendices para certificar",
        "pendientes": "aprendices con pendientes",
        "complementaria": "registros de formación complementaria",
        "meta": "metas institucionales",
        "requisitos": "requisitos de aprendices",
        "df14a": "aprendices (Base DF14A)",
        "acta": "documentos de acta",
        "informe": "tablas de informe de gestión",
        "otro": "documentos de apoyo",
    }
    parts = []
    for itype, counts in breakdown.items():
        if counts.get("valid_records", 0) > 0:
            label = labels.get(itype, itype)
            parts.append(f"{counts['valid_records']} {label}")
    
    if not parts:
        return "Importación confirmada sin registros nuevos."
    
    return "Se importaron: " + ", ".join(parts) + "."


def confirm_import(
    validation_id: str,
    session: Session,
    conflict_resolutions: list[dict[str, Any]] | None = None,
    accept_missing_complementaria: bool = False,
    sheets_manual_cleanup_acknowledged: bool = False,
    requirement_conflict_resolutions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    staged = get_staged(validation_id)
    if staged is None:
        raise KeyError("La validacion ya no esta disponible. Cargue el archivo nuevamente.")
    if staged.result.status == "error":
        raise ValueError("El archivo tiene errores que impiden la importacion.")
    if getattr(staged.result, "missing_complementaria", False) and not accept_missing_complementaria:
        raise ValueError(
            "Falta la hoja COMPLEMENTARIA. Acepte continuar sin ella o cargue otro archivo."
        )
    try:
        prepared = prepare_records(staged.file_name, staged.content, staged.information_type)
        if not prepared.importable:
            raise ValueError(
                "El archivo no contiene registros importables. Corrija los errores de "
                "validacion antes de confirmar."
            )

        conflicts = (
            coherence_conflicts(prepared)
            if staged.information_type == "actas_completo"
            else []
        )
        resolutions = _resolve_conflict_decisions(
            session, conflicts, conflict_resolutions
        )
        requirement_items = (
            requirement_conflicts(prepared)
            if staged.information_type == "actas_completo"
            else []
        )
        requirement_resolutions, explicit_requirement_resolutions = (
            _resolve_requirement_conflict_decisions(
                session, requirement_items, requirement_conflict_resolutions
            )
        )
        has_full_conflict_snapshot = (
            staged.information_type == "actas_completo"
            and _actas_snapshot_has_both_sheets(staged.content)
        )

        final_records = [
            (entry.record, entry.information_type) for entry in prepared.importable
        ]
        keys = [entry.key for entry in prepared.importable]
        existing = _existing_records_multi(session, keys)

        new_records = sum(key not in existing for key in keys)
        updated_records = sum(key in existing for key in keys)
        history = ImportHistory(
            file_name=staged.file_name,
            information_type=TYPE_LABELS.get(staged.information_type, staged.information_type),
            source_type=staged.information_type,
            records_count=len(final_records),
            new_records=new_records,
            updated_records=updated_records,
            warning_count=sum(
                check["status"] == "warning" for check in staged.result.checks
            ),
            error_count=0,
            status="completed",
            message=_format_breakdown_message(prepared.breakdown()),
        )
        session.add(history)
        session.flush()

        for row_number, ((record, rtype), key) in enumerate(
            zip(final_records, keys), start=2
        ):
            current = existing.get(key)
            payload = json.dumps(record, ensure_ascii=True, default=str)
            if current is None:
                session.add(
                    ImportedRecord(
                        import_id=history.id,
                        information_type=rtype,
                        record_key=key,
                        row_number=row_number,
                        payload=payload,
                    )
                )
            else:
                current.import_id = history.id
                current.row_number = row_number
                current.payload = payload

        # Politica #34: si un aprendiz figura en CERTIFICADOS y PENDIENTES,
        # el estado final es CERTIFICADOS. Para que gane, los registros de
        # PENDIENTES se procesan primero y los de CERTIFICADOS despues (el
        # upsert conserva el ultimo por identificacion).
        learners_records = [
            record
            for record, rtype in sorted(
                [(r, t) for r, t in final_records if t in {"df14a", "certificados", "pendientes"}],
                key=lambda item: 0 if item[1] == "pendientes" else 1,
            )
        ]
        if learners_records:
            upsert_learners_from_records(session, learners_records)

        if resolutions:
            _apply_conflict_resolutions(session, resolutions)
            if conflict_resolutions:
                history.message = (
                    f"{history.message} Conflictos resueltos manualmente: "
                    f"{len(resolutions)}."
                )
            else:
                history.message = (
                    f"{history.message} Desempates guardados reaplicados: "
                    f"{len(resolutions)}."
                )
            if sheets_manual_cleanup_acknowledged:
                # Solo trazabilidad local: el acuse no dispara ninguna escritura
                # ni sincronizacion inversa hacia Google Sheets.
                history.message = (
                    f"{history.message} El usuario confirmó la corrección manual "
                    "del registro duplicado en Google Sheets (solo documental)."
                )

        if has_full_conflict_snapshot:
            # Regla condicional: si el documento dejo la interseccion, el
            # desempate ya no aplica y manda el estado de la unica hoja vigente.
            _clear_inactive_conflict_resolutions(
                session,
                {
                    str(item.get("identification") or "").strip()
                    for item in conflicts
                },
            )

        # Las columnas de evidencias de CERTIFICADOS/PENDIENTES se convierten en
        # requisitos del aprendiz (X -> Cumplido, N.A -> No aplica, vacio ->
        # Pendiente). El motivo de no certificacion ya quedo en el aprendiz.
        evidence_records = [
            record
            for record, rtype in final_records
            if rtype in {"certificados", "pendientes"}
        ]
        sync_recorded_at = datetime.now(timezone.utc)
        if evidence_records:
            _sync_actas_requirements(
                session,
                evidence_records,
                source="import:actas_completo",
                recorded_at=sync_recorded_at,
            )

        # La decision del usuario sobre una incongruencia columna/motivo manda
        # sobre el estado leido en la celda de evidencias. Se aplica despues de
        # la sincronizacion para que el requisito quede con el estado elegido.
        if requirement_resolutions:
            applied_requirement_conflicts = _apply_requirement_conflict_resolutions(
                session,
                requirement_items,
                requirement_resolutions,
                recorded_at=sync_recorded_at,
            )
            if applied_requirement_conflicts:
                if explicit_requirement_resolutions:
                    history.message = (
                        f"{history.message} Conflictos de requisitos resueltos "
                        f"manualmente: {applied_requirement_conflicts}."
                    )
                else:
                    history.message = (
                        f"{history.message} Decisiones de requisitos guardadas "
                        f"reaplicadas: {applied_requirement_conflicts}."
                    )

        requisitos_records = [
            record for record, rtype in final_records if rtype == "requisitos"
        ]
        if requisitos_records:
            _sync_requirements_from_records(
                session,
                requisitos_records,
                source="import:requisitos",
                recorded_at=sync_recorded_at,
            )

        if staged.information_type == "acta":
            # El acta y sus relaciones se guardan en la misma transaccion que el
            # historial: si algo falla no queda un acta a medias ni relaciones
            # incompletas.
            extraction = parsers.extract_acta_data(staged.file_name, staged.content)
            acta_result = import_act_from_document(
                session, extraction, staged.file_name, history.id
            )
            history.message = _format_acta_message(acta_result)

        # Procedencia: se registra de que archivo/hoja salio cada aprendiz. Se
        # acumula (union) y no reemplaza los origenes previos.
        _register_sources(session, final_records, staged.file_name)

        session.commit()
        _staged_imports.pop(validation_id, None)
        return import_result(history)
    except Exception:
        session.rollback()
        raise


def import_result(history: ImportHistory) -> dict[str, Any]:
    return {
        "id": history.id,
        "file_name": history.file_name,
        "information_type": history.information_type,
        "imported_at": (
            history.imported_at.replace(tzinfo=timezone.utc).isoformat()
            if history.imported_at is not None and history.imported_at.tzinfo is None
            else (history.imported_at.isoformat() if history.imported_at else None)
        ),
        "records_count": history.records_count,
        "new_records": history.new_records,
        "updated_records": history.updated_records,
        "warning_count": history.warning_count,
        "error_count": history.error_count,
        "user_name": history.user_name,
        "status": history.status,
        "message": history.message,
    }


def list_imports(session: Session) -> list[dict[str, Any]]:
    histories = session.scalars(
        select(ImportHistory).order_by(ImportHistory.imported_at.desc())
    ).all()
    return [import_result(history) for history in histories]


def _existing_keys(session: Session, information_type: str, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    return set(
        session.scalars(
            select(ImportedRecord.record_key).where(
                ImportedRecord.information_type == information_type,
                ImportedRecord.record_key.in_(keys),
            )
        ).all()
    )


def _existing_records(session: Session, information_type: str, keys: list[str]) -> dict[str, ImportedRecord]:
    if not keys:
        return {}
    records = session.scalars(
        select(ImportedRecord).where(
            ImportedRecord.information_type == information_type,
            ImportedRecord.record_key.in_(keys),
        )
    ).all()
    return {record.record_key: record for record in records}


def _existing_keys_multi(session: Session, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    return set(
        session.scalars(
            select(ImportedRecord.record_key).where(
                ImportedRecord.record_key.in_(keys),
            )
        ).all()
    )


def _existing_records_multi(session: Session, keys: list[str]) -> dict[str, ImportedRecord]:
    if not keys:
        return {}
    records = session.scalars(
        select(ImportedRecord).where(
            ImportedRecord.record_key.in_(keys),
        )
    ).all()
    return {record.record_key: record for record in records}


def _first_value(record: dict[str, Any], *candidates: str) -> str | None:
    normalized = {_normalize_key(str(key)): value for key, value in record.items()}
    for candidate in candidates:
        value = normalized.get(_normalize_key(candidate))
        if value is None:
            continue
        text_value = str(value).strip()
        if text_value:
            return text_value
    return None


def _normalize_key(value: str) -> str:
    ascii_value = normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().replace("_", " ").split())


def _sync_requirements_from_records(
    session: Session,
    records: list[dict[str, Any]],
    source: str = "import:requisitos",
    recorded_at: datetime | None = None,
) -> int:
    from app.services.parsers import clean_identification, normalize_text
    from app.services.requirements import REQUIREMENT_TYPES, upsert_requirement_status

    req_map = {
        "rap": "learning_outcome",
        "resultados de aprendizaje": "learning_outcome",
        "aprendizaje": "learning_outcome",
        "resultado de aprendizaje": "learning_outcome",
        "documento": "documentation",
        "documentacion": "documentation",
        "cedula": "documentation",
        "tarjeta de identidad": "documentation",
        "ti": "documentation",
        "cc": "documentation",
        "etapa productiva": "productive_stage",
        "etapa": "productive_stage",
        "practica": "productive_stage",
        "paz y salvo": "clearance",
        "paz": "clearance",
        "salvo": "clearance",
        "saber tyt": "saber_tyt",
        "tyt": "saber_tyt",
        "saber pro": "saber_tyt",
    }
    for k in REQUIREMENT_TYPES:
        req_map[k] = k
        req_map[normalize_text(REQUIREMENT_TYPES[k])] = k

    count = 0
    for record in records:
        norm = {normalize_text(k): v for k, v in record.items()}
        doc_raw = norm.get("documento") or norm.get("numero documento") or norm.get("identificacion")
        doc = clean_identification(doc_raw)
        if not doc:
            continue

        name_raw = norm.get("nombres") or norm.get("nombre") or norm.get("aprendiz") or "Aprendiz"
        name = str(name_raw).strip()

        learner = session.scalar(select(Learner).where(Learner.identification == doc))
        if learner is None:
            learner = Learner(identification=doc, name=name, certification_status="Por Certificar")
            session.add(learner)
            session.flush()

        req_raw = norm.get("requisito") or norm.get("tipo requisito")
        if not req_raw:
            continue
        req_text = normalize_text(req_raw)

        req_type = None
        for key, candidate in req_map.items():
            if key in req_text:
                req_type = candidate
                break
        if not req_type or req_type not in REQUIREMENT_TYPES:
            continue

        status_raw = normalize_text(norm.get("estado"))
        if any(w in status_raw for w in ("cumplid", "aprob", "si", "ok", "listo")):
            status = "Cumplido"
        elif any(w in status_raw for w in ("no aplica", "exento", "n/a")):
            status = "No aplica"
        elif not status_raw:
            status = "Sin información"
        else:
            status = "Pendiente"

        obs = norm.get("observaciones") or norm.get("novedades") or norm.get("motivo")
        obs_text = str(obs).strip() if obs and not pd.isna(obs) else None

        upsert_requirement_status(
            session,
            learner_id=learner.id,
            requirement_type=req_type,
            status=status,
            observations=obs_text,
            source=source,
            recorded_at=recorded_at,
        )
        count += 1
    return count


# Columnas de evidencias de ACTAS 2026 que se convierten en requisitos. La lista
# compartida vive en ``requirement_conflicts`` para que la deteccion y la
# importacion no se desincronicen. Cada clave coincide con el
# ``requirement_type`` registrado en ``app.services.requirements``.
# Fecha real de recibido asociada a cada paz y salvo del consolidado. Solo se
# usa cuando la celda de evidencia marca el requisito como cumplido; una fecha
# aislada no convierte un pendiente en cumplido.
_EVIDENCE_DATE_FIELDS: dict[str, tuple[str, ...]] = {
    "biblioteca": (
        "fecha_recibido_biblioteca",
        "fecha de recibido (paz y salvo biblioteca)",
        "fecha de recibido paz y salvo biblioteca",
        "fecha recibido (paz y salvo biblioteca)",
    ),
    "bienestar": (
        "fecha_recibido_bienestar",
        "fecha de recibido (bienestar del aprendiz)",
        "fecha de recibido (paz y salvo bienestar)",
        "fecha de recibido bienestar del aprendiz",
    ),
    "almacen": (
        "fecha_recibido_almacen",
        "fecha de recibido (paz y salvo almacen)",
        "fecha de recibido paz y salvo almacen",
        "fecha recibido (paz y salvo almacen)",
    ),
}

# Nota estable para distinguir en el historial un evento fechado por el
# documento de uno fechado por la importacion.
_RECEIVED_DATE_NOTE = "Fecha de recibido según consolidado"


def _received_date_for(record: dict[str, Any], field: str) -> date | None:
    """Fecha de recibido valida de un requisito, o ``None`` si no la trae."""
    raw = _first_value(record, *_EVIDENCE_DATE_FIELDS.get(field, ()))
    if raw is None:
        return None
    iso_date = parsers.parse_date_value(raw)
    if not iso_date:
        return None
    try:
        return date.fromisoformat(iso_date)
    except ValueError:
        return None


def _received_date_recorded_at(received_date: date) -> datetime:
    """Momento UTC del evento de historial para una fecha de recibido.

    Se usa el mediodia UTC para que al mostrarlo en es-CO (UTC-5) siga siendo
    el mismo dia del documento y no se corra al dia anterior.
    """
    return datetime.combine(received_date, time(hour=12), tzinfo=timezone.utc)


# Etiquetas de procedencia por tipo interno. Describen de que archivo/hoja salio
# cada registro; se acumulan en el aprendiz y nunca reemplazan un origen previo.
_SOURCE_LABELS = {
    "certificados": "ACTAS 2026 · CERTIFICADOS",
    "pendientes": "ACTAS 2026 · PENDIENTES",
    "complementaria": "ACTAS 2026 · COMPLEMENTARIA",
    "meta": "ACTAS 2026 · META",
    "df14a": "DF14A",
    "requisitos": "Matriz de requisitos",
}


def _source_label(rtype: str, record: dict[str, Any], file_name: str) -> str | None:
    """Etiqueta legible del origen de un registro, o ``None`` si no se conoce."""
    if rtype == "acta":
        number = _first_value(record, "numero de acta", "acta")
        return f"Acta {number}" if number else f"Acta oficial · {file_name}"
    return _SOURCE_LABELS.get(rtype)


def _register_sources(
    session: Session, final_records: list[tuple[dict[str, Any], str]], file_name: str
) -> None:
    """Acumula en cada aprendiz las fuentes que lo alimentaron en esta importacion.

    Solo se registra un origen conocido; si el tipo no tiene etiqueta (por
    ejemplo documentos de apoyo) no se inventa procedencia.
    """
    sources: dict[str, list[str]] = {}
    for record, rtype in final_records:
        label = _source_label(rtype, record, file_name)
        if not label:
            continue
        prepared = _prepare_learner_row(record)
        if prepared is None:
            continue
        labels = sources.setdefault(prepared["identification"], [])
        if label not in labels:
            labels.append(label)
    set_learner_sources(session, sources)


def _sync_actas_requirements(
    session: Session,
    records: list[dict[str, Any]],
    source: str = "import:actas_completo",
    recorded_at: datetime | None = None,
) -> int:
    """Crea o actualiza los requisitos desde las columnas de evidencias del acta.

    Cada columna de checklist de CERTIFICADOS/PENDIENTES es un requisito del
    aprendiz con el estado leido en la celda: ``X`` -> Cumplido, ``N.A`` -> No
    aplica, vacio u otro -> Pendiente. Solo se procesan las columnas que existen
    en la hoja; una columna ausente no genera un requisito inventado.

    Para biblioteca, bienestar y almacen, si el requisito esta cumplido y la
    hoja trae la fecha real de recibido, el evento de historial usa esa fecha
    (al mediodia UTC para que no se corra de dia en es-CO). Una fecha sin marca
    de cumplimiento no cambia el estado ni se usa para fabricar un evento.
    """
    from app.services.parsers import clean_identification
    from app.services.requirements import evidence_status, upsert_requirement_status

    count = 0
    for record in records:
        document = clean_identification(
            _first_value(record, "numero de documento", "documento")
        )
        if not document:
            continue
        learner = session.scalar(
            select(Learner).where(Learner.identification == document)
        )
        if learner is None:
            continue
        for field in EVIDENCE_FIELDS:
            if field not in record:
                continue
            status = evidence_status(record.get(field))
            # Solo un requisito cumplido puede fecharse con la fecha de
            # recibido del documento. Si la celda no tiene marca de
            # cumplimiento, la fecha no se usa para inventar un "Cumplido".
            received_date = (
                _received_date_for(record, field) if status == "Cumplido" else None
            )
            event_at = (
                _received_date_recorded_at(received_date)
                if received_date is not None
                else recorded_at
            )
            upsert_requirement_status(
                session,
                learner_id=learner.id,
                requirement_type=field,
                status=status,
                source=source,
                recorded_at=event_at,
                note=_RECEIVED_DATE_NOTE if received_date is not None else None,
                force_history=received_date is not None,
                dedupe_history=True,
            )
            count += 1
    return count

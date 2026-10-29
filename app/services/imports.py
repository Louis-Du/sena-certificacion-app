from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from unicodedata import normalize

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Act, ActLearner, ImportHistory, ImportedRecord, Learner
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


def _conflict_resolution_map(
    conflicts: list[dict[str, Any]],
    raw_resolutions: list[dict[str, Any]] | None,
) -> dict[str, str]:
    """Valida que cada conflicto tenga una decision explicita del usuario."""
    required = {item["identification"]: item for item in conflicts}
    if not required:
        return {}

    resolutions: dict[str, str] = {}
    invalid: list[str] = []
    for item in raw_resolutions or []:
        identification = str(item.get("identification") or "").strip()
        status = str(item.get("status") or "").strip().upper()
        if identification not in required:
            continue
        if status not in CONFLICT_STATUSES:
            invalid.append(f"{identification}: {status or 'sin estado'}")
            continue
        resolutions[identification] = status

    if invalid:
        raise ValueError(
            "Resolucion de conflicto no valida para "
            f"{', '.join(invalid)}. Use CERTIFICADOS o PENDIENTE."
        )
    missing = [identification for identification in required if identification not in resolutions]
    if missing:
        raise ValueError(
            f"Faltan {len(missing)} resolucion(es) de conflicto: {', '.join(missing)}. "
            "Elija Certificado o Pendiente para cada aprendiz antes de confirmar."
        )
    return resolutions


def _apply_conflict_resolutions(session: Session, resolutions: dict[str, str]) -> None:
    """Fija el estado elegido y deja rastro en las notas de seguimiento."""
    learners = session.scalars(
        select(Learner).where(Learner.identification.in_(resolutions))
    ).all()
    for learner in learners:
        status = resolutions[learner.identification]
        learner.certification_status = status
        note = f"Conflicto resuelto: {_CONFLICT_STATUS_LABELS[status]}"
        current = (learner.tracking_notes or "").strip()
        if note not in current:
            learner.tracking_notes = f"{current}; {note}" if current else note
    session.flush()


def stage_file(file_name: str, content: bytes, information_type: str) -> StagedImport:
    result = validate_file(file_name, content, information_type)
    validation_id = uuid.uuid4().hex
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
        "coherence_conflicts": (
            coherence_conflicts(prepared)
            if staged.information_type == "actas_completo"
            else []
        ),
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
        resolutions = _conflict_resolution_map(conflicts, conflict_resolutions)

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
            history.message = (
                f"{history.message} Conflictos resueltos manualmente: {len(resolutions)}."
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
        if not req_type:
            req_type = "documentation"

        status_raw = normalize_text(norm.get("estado"))
        if any(w in status_raw for w in ("cumplid", "aprob", "si", "ok", "listo")):
            status = "Cumplido"
        elif any(w in status_raw for w in ("no aplica", "exento", "n/a")):
            status = "No aplica"
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


# Columnas de evidencias de ACTAS 2026 que se convierten en requisitos. La clave
# es el nombre de campo interno que produce ``parsers._actas_records`` y coincide
# con el ``requirement_type`` registrado en ``app.services.requirements``.
_EVIDENCE_FIELDS = (
    "biblioteca",
    "bienestar",
    "almacen",
    "etapa_productiva",
    "documento_identidad",
    "saber_tyt",
    "ape",
    "carnet",
    "certificado_empresa",
)


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
        for field in _EVIDENCE_FIELDS:
            if field not in record:
                continue
            status = evidence_status(record.get(field))
            upsert_requirement_status(
                session,
                learner_id=learner.id,
                requirement_type=field,
                status=status,
                source=source,
                recorded_at=recorded_at,
            )
            count += 1
    return count

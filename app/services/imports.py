from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
from unicodedata import normalize

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Act, ActLearner, ImportHistory, ImportedRecord, Learner
from app.services import parsers
from app.services.acts import import_act_from_document
from app.services.learners import upsert_learners_from_records
from app.services.records import (
    parse_records,
    prepare_records,
    record_key,
)
from app.services.validation import (
    TYPE_LABELS,
    ValidationResult,
    conflicting_pairs,
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
    registered: set[str] = set()
    if documents:
        registered = set(
            session.scalars(
                select(Learner.identification).where(Learner.identification.in_(documents))
            ).all()
        )
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


def confirm_import(validation_id: str, session: Session) -> dict[str, Any]:
    staged = get_staged(validation_id)
    if staged is None:
        raise KeyError("La validacion ya no esta disponible. Cargue el archivo nuevamente.")
    if staged.result.status == "error":
        raise ValueError("El archivo tiene errores que impiden la importacion.")

    try:
        prepared = prepare_records(staged.file_name, staged.content, staged.information_type)
        if not prepared.importable:
            raise ValueError(
                "El archivo no contiene registros importables. Corrija los errores de "
                "validacion antes de confirmar."
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

        learners_records = [
            record
            for record, rtype in final_records
            if rtype in {"df14a", "certificados", "pendientes"}
        ]
        conflicted_identifications = set()
        if staged.information_type == "actas_completo":
            # Un aprendiz que aparece en CERTIFICADOS y PENDIENTES no debe
            # recibir un estado elegido automaticamente. Sus registros se
            # guardan, pero el estado del aprendiz se deja como estaba (o sin
            # definir si es nuevo) hasta que una persona lo resuelva.
            conflicted_identifications = {
                documento for documento, _ in conflicting_pairs(prepared)
            }
        if learners_records:
            upsert_learners_from_records(
                session,
                learners_records,
                skip_status_for=conflicted_identifications,
            )

        # Las columnas de evidencias de CERTIFICADOS/PENDIENTES se convierten en
        # requisitos del aprendiz (X -> Cumplido, N.A -> No aplica, vacio ->
        # Pendiente). El motivo de no certificacion ya quedo en el aprendiz.
        evidence_records = [
            record
            for record, rtype in final_records
            if rtype in {"certificados", "pendientes"}
        ]
        if evidence_records:
            _sync_actas_requirements(session, evidence_records)

        requisitos_records = [
            record for record, rtype in final_records if rtype == "requisitos"
        ]
        if requisitos_records:
            _sync_requirements_from_records(session, requisitos_records)

        if staged.information_type == "acta":
            # El acta y sus relaciones se guardan en la misma transaccion que el
            # historial: si algo falla no queda un acta a medias ni relaciones
            # incompletas.
            extraction = parsers.extract_acta_data(staged.file_name, staged.content)
            acta_result = import_act_from_document(
                session, extraction, staged.file_name, history.id
            )
            history.message = _format_acta_message(acta_result)

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
        "imported_at": history.imported_at.isoformat(),
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


def _upsert_learners(records: list[dict[str, Any]], session: Session) -> None:
    prepared_rows = [_prepare_learner_row(record) for record in records]
    rows = [row for row in prepared_rows if row is not None]
    if not rows:
        return

    identifications = [row["identification"] for row in rows]
    existing = session.scalars(
        select(Learner).where(Learner.identification.in_(identifications))
    ).all()
    existing_by_identification = {learner.identification: learner for learner in existing}

    for row in rows:
        learner = existing_by_identification.get(row["identification"])
        if learner is None:
            session.add(Learner(**row))
            continue
        if row.get("name") and row["name"] != "Aprendiz sin nombre":
            learner.name = row["name"]
        if row.get("program"):
            learner.program = row["program"]
        if row.get("group_code"):
            learner.group_code = row["group_code"]
        if row.get("training_type"):
            learner.training_type = row["training_type"]
        if row.get("certification_status"):
            learner.certification_status = row["certification_status"]
        if row.get("tracking_notes"):
            learner.tracking_notes = row["tracking_notes"]


def _prepare_learner_row(record: dict[str, Any]) -> dict[str, Any] | None:
    name = _first_value(
        record,
        "nombre",
        "nombres",
        "aprendiz",
        "nombre aprendiz",
        "nombre completo",
        "nombre_aprendiz",
    )
    identification = _first_value(
        record,
        "identificacion",
        "identificación",
        "documento",
        "numero documento",
        "numero_documento",
        "cedula",
        "cédula",
        "id",
    )
    if not name and not identification:
        return None

    generated_identification = identification or f"AUTO-{record_key('learner', record)[:12]}"
    return {
        "identification": generated_identification,
        "name": name or "Aprendiz sin nombre",
        "program": _first_value(record, "programa", "programa formacion", "programa de formacion"),
        "group_code": _first_value(record, "ficha", "grupo", "codigo grupo", "codigo ficha"),
        "training_type": _first_value(record, "tipo formacion", "modalidad"),
        "certification_status": _first_value(record, "estado", "estado certificacion", "estado de certificacion"),
        "tracking_notes": _first_value(record, "observaciones", "novedades", "seguimiento", "notas"),
    }


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


def _sync_requirements_from_records(session: Session, records: list[dict[str, Any]]) -> int:
    from app.models import Requirement
    from app.services.parsers import clean_identification, normalize_text
    from app.services.requirements import REQUIREMENT_TYPES

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

        existing_req = session.scalar(
            select(Requirement).where(
                Requirement.learner_id == learner.id,
                Requirement.requirement_type == req_type,
            )
        )
        if existing_req is None:
            session.add(
                Requirement(
                    learner_id=learner.id,
                    requirement_type=req_type,
                    status=status,
                    observations=obs_text,
                )
            )
        else:
            existing_req.status = status
            if obs_text:
                existing_req.observations = obs_text
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


def _sync_actas_requirements(session: Session, records: list[dict[str, Any]]) -> int:
    """Crea o actualiza los requisitos desde las columnas de evidencias del acta.

    Cada columna de checklist de CERTIFICADOS/PENDIENTES es un requisito del
    aprendiz con el estado leido en la celda: ``X`` -> Cumplido, ``N.A`` -> No
    aplica, vacio u otro -> Pendiente. Solo se procesan las columnas que existen
    en la hoja; una columna ausente no genera un requisito inventado.
    """
    from app.models import Requirement
    from app.services.parsers import clean_identification
    from app.services.requirements import evidence_status

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
            existing = session.scalar(
                select(Requirement).where(
                    Requirement.learner_id == learner.id,
                    Requirement.requirement_type == field,
                )
            )
            if existing is None:
                session.add(
                    Requirement(
                        learner_id=learner.id,
                        requirement_type=field,
                        status=status,
                    )
                )
            else:
                existing.status = status
            count += 1
    return count

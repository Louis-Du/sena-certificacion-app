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

from app.models import ImportHistory, ImportedRecord, Learner
from app.services.learners import upsert_learners_from_records
from app.services.validation import TYPE_LABELS, ValidationResult, validate_file


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
    records = parse_records(staged.file_name, staged.content, staged.information_type)
    
    keys = []
    for r in records:
        # Copiamos para no modificar el original durante el preview
        record_copy = r.copy()
        rtype = record_copy.pop("__type__", staged.information_type)
        keys.append(record_key(rtype, record_copy))
        
    existing = _existing_keys_multi(session, keys)
    warnings = [check["label"] for check in staged.result.checks if check["status"] == "warning"]
    return {
        "validation_id": staged.validation_id,
        "file_name": staged.file_name,
        "information_type": TYPE_LABELS.get(staged.information_type, staged.information_type),
        "records_count": len(records),
        "new_records": sum(key not in existing for key in keys),
        "updated_records": sum(key in existing for key in keys),
        "warnings": warnings,
        "status": staged.result.status,
        "detected_columns": staged.result.detected_columns,
        "missing_columns": staged.result.missing_columns,
    }


def confirm_import(validation_id: str, session: Session) -> dict[str, Any]:
    staged = get_staged(validation_id)
    if staged is None:
        raise KeyError("La validacion ya no esta disponible. Cargue el archivo nuevamente.")
    if staged.result.status == "error":
        raise ValueError("El archivo tiene errores que impiden la importacion.")

    records = parse_records(staged.file_name, staged.content, staged.information_type)
    
    # Procesamos los registros para extraer el tipo si viene incrustado (Smart Import)
    final_records = []
    keys = []
    for r in records:
        rtype = r.pop("__type__", staged.information_type)
        final_records.append((r, rtype))
        keys.append(record_key(rtype, r))

    existing = _existing_records_multi(session, keys)
    history = ImportHistory(
        file_name=staged.file_name,
        information_type=TYPE_LABELS.get(staged.information_type, staged.information_type),
        records_count=len(records),
        new_records=sum(key not in existing for key in keys),
        updated_records=sum(key in existing for key in keys),
        warning_count=sum(check["status"] == "warning" for check in staged.result.checks),
        status="completed",
        message="Importacion confirmada por el usuario.",
    )
    session.add(history)
    session.flush()

    for row_number, ((record, rtype), key) in enumerate(zip(final_records, keys), start=2):
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

    # Si hay registros de aprendices, actualizamos la tabla maestra
    learners_records = [r for r, t in final_records if t in {"df14a", "certificados", "pendientes"}]
    if learners_records:
        upsert_learners_from_records(session, learners_records)

    # Si hay registros de requisitos, actualizamos los requisitos de los aprendices
    requisitos_records = [r for r, t in final_records if t == "requisitos"]
    if requisitos_records:
        _sync_requirements_from_records(session, requisitos_records)

    session.commit()
    _staged_imports.pop(validation_id, None)
    return import_result(history)


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


def parse_records(file_name: str, content: bytes, information_type: str = "otro") -> list[dict[str, Any]]:
    """
    Convierte un archivo validado en una lista de registros (diccionarios).

    Aqui se decide, segun el TIPO DE INFORMACION y la EXTENSION, que lector de
    ``app.services.parsers`` corresponde. Cada lector devuelve ya los registros en
    formato diccionario, con nombres de campo internos (en minusculas y sin
    tildes) para que el resto de la aplicacion no dependa de los encabezados
    exactos que traiga el archivo original.

    Reglas:
    * ``certificados`` / ``pendientes`` / ``complementaria`` -> leen su hoja
      especifica dentro de ACTAS 2026.xlsx (no la primera hoja cualquiera).
      ``certificados`` y ``pendientes`` tambien aceptan un CSV con la misma
      estructura de columnas.
    * ``meta`` -> lee la hoja META y devuelve UN solo registro con las metas.
    * ``informe`` -> lee la tabla de referencia del Word de gestion.
    * ``df14a`` -> lee el XML SpreadsheetML.
    * Cualquier otro caso cae en la lectura tabular generica.
    """
    from app.services import parsers

    extension = Path(file_name).suffix.lower()
    if information_type == "df14a" and extension == ".xml":
        frame = parsers.parse_df14a_xml(content)
        return parsers.frame_to_records(frame)
    if information_type == "certificados" and extension in {".xlsx", ".xls"}:
        return parsers.read_certificados_records(content)
    if information_type == "pendientes" and extension in {".xlsx", ".xls"}:
        return parsers.read_pendientes_records(content)
    # Los mismos listados de personas pueden venir en CSV (por ejemplo
    # "ACTAS 2026(PENDIENTES).csv"). Se normalizan con el mismo lector para que
    # las columnas queden con nombres internos; si no, se contarian 0 aprendices.
    if information_type in {"certificados", "pendientes"} and extension == ".csv":
        return parsers.read_actas_csv_records(content)
    if information_type == "csv_certificacion" and extension == ".csv":
        from app.services.validation import _read_csv, detect_csv_certificacion_type
        frame = _read_csv(content)
        sub_type, _ = detect_csv_certificacion_type(frame)
        records = parsers.read_actas_csv_records(content)
        for r in records:
            r["__type__"] = sub_type
        return records
    if information_type == "complementaria" and extension in {".xlsx", ".xls"}:
        return parsers.read_complementaria_records(content)
    if information_type == "meta" and extension in {".xlsx", ".xls"}:
        # La hoja META produce un unico registro "de cabecera" con todas las metas.
        metas = parsers.read_meta_sheet(content)
        return [metas] if metas else []
    if information_type == "actas_completo" and extension in {".xlsx", ".xls"}:
        return parsers.read_actas_full(content)
    if information_type == "informe" and extension == ".docx":
        return parsers.parse_informe_referencia(content)
    if information_type == "requisitos":
        if extension in {".xlsx", ".xls", ".csv"}:
            return _parse_generic_tabular(extension, content)
        return []
    if information_type == "acta" and extension == ".docx":
        result = parsers.parse_acta_docx(content)
        return result.get("records", [])
    if extension in {".pdf", ".docx"}:
        return [{"file_name": file_name, "format": extension[1:]}]
    return _parse_generic_tabular(extension, content)


def _parse_generic_tabular(extension: str, content: bytes) -> list[dict[str, Any]]:
    if extension == ".csv":
        from app.services.validation import _read_csv

        frame = _read_csv(content)
        return _frame_records(frame)
    if extension in {".xlsx", ".xls"}:
        frame = pd.read_excel(BytesIO(content))
        return _frame_records(frame)
    return []


def record_key(information_type: str, record: dict[str, Any]) -> str:
    from app.services.parsers import clean_identification

    clean = {k: v for k, v in record.items() if k != "__type__"}
    if information_type in {"certificados", "pendientes"}:
        doc = clean_identification(clean.get("numero de documento") or clean.get("documento"))
        if doc:
            ficha = clean_identification(clean.get("ficha")) or ""
            return hashlib.sha256(f"{information_type}:{doc}:{ficha}".encode("utf-8")).hexdigest()

    normalized = json.dumps(
        {"information_type": information_type, "record": clean},
        ensure_ascii=True,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean_frame = frame.where(pd.notna(frame), None)
    return [
        {str(key): value for key, value in row.items() if value is not None}
        for row in clean_frame.to_dict(orient="records")
        if any(value is not None for value in row.values())
    ]


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
        learner.name = row["name"]
        learner.program = row["program"]
        learner.group_code = row["group_code"]
        learner.training_type = row["training_type"]
        learner.certification_status = row["certification_status"]
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

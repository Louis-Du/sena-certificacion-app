from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ImportHistory, ImportedRecord
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
    records = parse_records(staged.file_name, staged.content)
    keys = [record_key(staged.information_type, record) for record in records]
    existing = _existing_keys(session, staged.information_type, keys)
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
    }


def confirm_import(validation_id: str, session: Session) -> dict[str, Any]:
    staged = get_staged(validation_id)
    if staged is None:
        raise KeyError("La validacion ya no esta disponible. Cargue el archivo nuevamente.")
    if staged.result.status == "error":
        raise ValueError("El archivo tiene errores que impiden la importacion.")

    records = parse_records(staged.file_name, staged.content)
    keys = [record_key(staged.information_type, record) for record in records]
    existing = _existing_records(session, staged.information_type, keys)
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

    for row_number, (record, key) in enumerate(zip(records, keys), start=2):
        current = existing.get(key)
        payload = json.dumps(record, ensure_ascii=True, default=str)
        if current is None:
            session.add(
                ImportedRecord(
                    import_id=history.id,
                    information_type=staged.information_type,
                    record_key=key,
                    row_number=row_number,
                    payload=payload,
                )
            )
        else:
            current.import_id = history.id
            current.row_number = row_number
            current.payload = payload

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
        "status": history.status,
        "message": history.message,
    }


def list_imports(session: Session) -> list[dict[str, Any]]:
    histories = session.scalars(
        select(ImportHistory).order_by(ImportHistory.imported_at.desc())
    ).all()
    return [import_result(history) for history in histories]


def parse_records(file_name: str, content: bytes) -> list[dict[str, Any]]:
    extension = Path(file_name).suffix.lower()
    if extension == ".csv":
        frame = pd.read_csv(BytesIO(content))
        return _frame_records(frame)
    if extension in {".xlsx", ".xls"}:
        frame = pd.read_excel(BytesIO(content))
        return _frame_records(frame)
    if extension in {".pdf", ".docx"}:
        return [{"file_name": file_name, "format": extension[1:]}]
    return []


def record_key(information_type: str, record: dict[str, Any]) -> str:
    normalized = json.dumps(
        {"information_type": information_type, "record": record},
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

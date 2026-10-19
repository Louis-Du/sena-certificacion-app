from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any
from unicodedata import normalize

import pandas as pd


MAX_FILE_SIZE = 20 * 1024 * 1024

SUPPORTED_TYPES: dict[str, set[str]] = {
    "df14a": {".xlsx", ".xls", ".csv", ".xml"},
    "certificados": {".xlsx", ".xls", ".csv"},
    "pendientes": {".xlsx", ".xls", ".csv"},
    # La hoja COMPLEMENTARIA no es una tabla con encabezados (son bloques de
    # fecha/cantidad por canal), por eso solo se lee desde el Excel: un CSV con
    # la estructura equivocada produciria un total en cero sin avisar.
    "complementaria": {".xlsx", ".xls"},
    # "meta" se lee de la hoja META de ACTAS 2026.xlsx: alli viven las metas anuales
    # oficiales (Tecnico laboral y otros, Articulacion, Educacion superior, etc.).
    "meta": {".xlsx", ".xls"},
    # "informe" es el documento Word de gestion. Se usa UNICAMENTE para la tabla de
    # referencia institucional (metas y avance reportado a la fecha de corte).
    "informe": {".docx"},
    "acta": {".pdf", ".docx"},
    "requisitos": {".xlsx", ".xls", ".csv"},
    "actas_completo": {".xlsx", ".xls"},
    "csv_certificacion": {".csv"},
    "otro": {".xlsx", ".xls", ".csv", ".pdf", ".docx"},
}

TYPE_LABELS = {
    "df14a": "DF14A",
    "certificados": "Listado de certificados",
    "pendientes": "Listado de pendientes",
    "complementaria": "Formación complementaria",
    "meta": "Metas oficiales (hoja META)",
    "informe": "Informe de gestion (tabla de referencia)",
    "acta": "Acta de certificacion",
    "requisitos": "Requisitos / pendientes",
    "actas_completo": "Excel institucional (ACTAS 2026)",
    "csv_certificacion": "CSV alternativo (Certificados / Pendientes)",
    "otro": "Otro archivo",
}

REQUIRED_COLUMNS: dict[str, list[str]] = {
    "df14a": ["FICHA"],
    "certificados": ["NÚMERO DE DOCUMENTO", "NOMBRE", "FICHA"],
    "pendientes": ["NÚMERO DE DOCUMENTO", "NOMBRE", "FICHA"],
    "requisitos": ["DOCUMENTO", "NOMBRES", "REQUISITO", "ESTADO"],
}


@dataclass
class ValidationResult:
    file_name: str
    information_type: str
    status: str
    checks: list[dict[str, str]]
    records_found: int | None = None
    valid_records: int | None = None
    inconsistencies: int = 0
    message: str | None = None
    detected_columns: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "information_type": self.information_type,
            "status": self.status,
            "checks": self.checks,
            "records_found": self.records_found,
            "valid_records": self.valid_records,
            "inconsistencies": self.inconsistencies,
            "message": self.message,
            "detected_columns": self.detected_columns,
            "missing_columns": self.missing_columns,
            "extra_columns": self.extra_columns,
        }


def validate_file(file_name: str, content: bytes, information_type: str) -> ValidationResult:
    checks: list[dict[str, str]] = []
    extension = Path(file_name).suffix.lower()
    label = TYPE_LABELS.get(information_type, information_type)

    if information_type not in SUPPORTED_TYPES:
        return _error(file_name, label, "Tipo de informacion no reconocido.")
    if not content:
        return _error(file_name, label, "El archivo esta vacio.")
    if len(content) > MAX_FILE_SIZE:
        return _error(file_name, label, "El archivo supera el limite recomendado de 20 MB.")

    checks.append({"label": "Archivo abierto correctamente", "status": "ok"})
    if extension not in SUPPORTED_TYPES[information_type]:
        return ValidationResult(
            file_name=file_name,
            information_type=label,
            status="error",
            checks=checks + [{"label": "Formato compatible", "status": "error"}],
            message=f"{extension or 'Sin extension'} no es compatible con {label}.",
        )

    checks.append({"label": "Formato compatible", "status": "ok"})
    records_found: int | None = None
    valid_records: int | None = None
    inconsistencies = 0
    detected_columns: list[str] = []
    missing_columns: list[str] = []
    extra_columns: list[str] = []
    try:
        frame = None
        target_type = information_type
        if extension == ".csv":
            frame = _read_csv(content)
            checks.append({"label": "Columnas leidas correctamente", "status": "ok"})
            if information_type == "csv_certificacion":
                sub_type, sub_label = detect_csv_certificacion_type(frame)
                target_type = sub_type
                checks.append({"label": f"Contenido detectado: {sub_label}", "status": "ok"})
        elif extension in {".xlsx", ".xls"}:
            if information_type == "meta":
                # La hoja META no es una tabla con encabezados: son rotulos y valores
                # en celdas sueltas. Por eso no se lee como DataFrame normal, sino con
                # el lector especializado y se informa cuantas metas se reconocieron.
                from app.services.parsers import read_meta_sheet

                metas = read_meta_sheet(content)
                if metas:
                    checks.append(
                        {"label": f"{len([k for k in metas if not k.endswith('_celda') and k != 'fila_rotulos'])} metas reconocidas", "status": "ok"}
                    )
                else:
                    checks.append({"label": "No se reconocieron metas en la hoja META", "status": "warning"})
            elif information_type == "actas_completo":
                from app.services.parsers import list_excel_sheets
                sheets = list_excel_sheets(content)
                sheet_map = {s.strip().upper(): s for s in sheets}
                expected = ["CERTIFICADOS", "PENDIENTES", "COMPLEMENTARIA", "META"]
                found = [s for s in expected if s in sheet_map]
                missing = [s for s in expected if s not in sheet_map]
                
                for s in found:
                    checks.append({"label": f"Hoja {sheet_map[s]} detectada", "status": "ok"})
                for s in missing:
                    checks.append({"label": f"Hoja {s} no encontrada", "status": "warning"})
                
                if not found:
                    raise ValueError("El archivo no contiene ninguna de las hojas esperadas del paquete ACTAS 2026.")
                
                # Resumen rapido: sumamos registros de hojas de personas
                records_found = 0
                if "CERTIFICADOS" in sheet_map:
                    records_found += len(pd.read_excel(BytesIO(content), sheet_name=sheet_map["CERTIFICADOS"]))
                if "PENDIENTES" in sheet_map:
                    records_found += len(pd.read_excel(BytesIO(content), sheet_name=sheet_map["PENDIENTES"]))
                if "COMPLEMENTARIA" in sheet_map:
                    checks.append({"label": "La hoja COMPLEMENTARIA se procesara por canales", "status": "info"})
                
                valid_records = records_found
                checks.append({"label": "Contenido multi-hoja validado", "status": "ok"})
            else:
                frame = pd.read_excel(BytesIO(content))
                checks.append({"label": "Columnas leidas correctamente", "status": "ok"})
        elif extension == ".xml":
            from app.services.parsers import parse_df14a_xml

            frame = parse_df14a_xml(content)
            checks.append({"label": "Columnas leidas correctamente", "status": "ok"})
        elif extension == ".pdf":
            import fitz

            document = fitz.open(stream=content, filetype="pdf")
            if document.page_count == 0:
                raise ValueError("El PDF no contiene paginas.")
            checks.append({"label": "Documento PDF abierto correctamente", "status": "ok"})
        elif extension == ".docx":
            from docx import Document

            document = Document(BytesIO(content))
            if not document.paragraphs and not document.tables:
                raise ValueError("El documento no contiene contenido.")
            checks.append({"label": "Documento Word abierto correctamente", "status": "ok"})

        if frame is not None:
            detected_columns = [str(c) for c in frame.columns]
            missing_columns, extra_columns = check_required_columns(
                target_type, detected_columns
            )
            if missing_columns:
                checks.append(
                    {
                        "label": f"Faltan {len(missing_columns)} columna(s) obligatoria(s): {', '.join(missing_columns)}",
                        "status": "warning",
                    }
                )
            else:
                checks.append({"label": "Columnas obligatorias presentes", "status": "ok"})
            if extra_columns:
                checks.append(
                    {
                        "label": f"{len(extra_columns)} columna(s) adicional(es) detectada(s)",
                        "status": "info",
                    }
                )
            records_found, valid_records, inconsistencies, duplicate_rows = _tabular_summary(frame)
            if duplicate_rows:
                checks.append({"label": f"{duplicate_rows} registros duplicados detectados", "status": "warning"})
    except Exception as error:
        return ValidationResult(
            file_name=file_name,
            information_type=label,
            status="warning",
            checks=checks + [{"label": "Contenido legible", "status": "warning"}],
            message=f"El formato parece correcto, pero no se pudo leer su contenido: {error}",
        )

    if records_found is not None:
        checks.append({"label": f"{records_found:,} registros encontrados".replace(",", "."), "status": "ok"})
        checks.append({"label": f"{valid_records:,} registros validos".replace(",", "."), "status": "ok"})
        if inconsistencies:
            checks.append({"label": f"{inconsistencies} registros presentan inconsistencias", "status": "warning"})

    return ValidationResult(
        file_name=file_name,
        information_type=label,
        status="warning" if (inconsistencies or missing_columns) else "ready",
        checks=checks,
        records_found=records_found,
        valid_records=valid_records,
        inconsistencies=inconsistencies,
        detected_columns=detected_columns,
        missing_columns=missing_columns,
        extra_columns=extra_columns,
        message="La validacion es preliminar y no se han guardado datos.",
    )


def _read_csv(content: bytes) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(BytesIO(content), encoding=encoding)
        except UnicodeDecodeError as error:
            last_error = error
        except pd.errors.ParserError as error:
            try:
                return pd.read_csv(BytesIO(content), encoding=encoding, on_bad_lines="skip")
            except Exception as inner:
                last_error = inner
    if last_error is not None:
        raise last_error
    raise ValueError("No se pudo decodificar el archivo CSV.")


def detect_csv_certificacion_type(frame: pd.DataFrame) -> tuple[str, str]:
    from app.services.parsers import normalize_text

    col_names = [normalize_column_name(str(c)) for c in frame.columns]
    has_motivo = any("motivo" in c for c in col_names)
    has_mes = any("mes" in c for c in col_names)

    estado_col = next((c for c in frame.columns if normalize_column_name(str(c)) == "estado"), None)
    estados: set[str] = set()
    if estado_col is not None:
        estados = {normalize_text(v) for v in frame[estado_col].dropna().unique()}

    if has_motivo or any("pendiente" in e for e in estados):
        return "pendientes", "Listado de pendientes"
    if has_mes or any("certificado" in e for e in estados):
        return "certificados", "Listado de certificados"

    missing_cert, _ = check_required_columns("certificados", [str(c) for c in frame.columns])
    missing_pend, _ = check_required_columns("pendientes", [str(c) for c in frame.columns])
    if len(missing_pend) < len(missing_cert):
        return "pendientes", "Listado de pendientes"
    return "certificados", "Listado de certificados"


def normalize_column_name(value: str) -> str:
    ascii_value = normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_value.lower().replace("_", " ").replace("-", " ").split())


def check_required_columns(
    information_type: str, columns: list[str]
) -> tuple[list[str], list[str]]:
    required = REQUIRED_COLUMNS.get(information_type)
    if not required:
        return [], []
    normalized_columns = {normalize_column_name(str(c)): str(c) for c in columns}
    missing: list[str] = []
    for col in required:
        if normalize_column_name(col) not in normalized_columns:
            missing.append(col)
    extra = [
        original
        for original in columns
        if normalize_column_name(str(original)) not in {normalize_column_name(c) for c in required}
    ]
    return missing, extra


def _tabular_summary(frame: pd.DataFrame) -> tuple[int, int, int, int]:
    records_found = len(frame.index)
    invalid_rows = int(frame.isna().all(axis=1).sum())
    duplicate_rows = int(frame.duplicated(keep="first").sum())
    return records_found, records_found - invalid_rows, invalid_rows + duplicate_rows, duplicate_rows


def _error(file_name: str, label: str, message: str) -> ValidationResult:
    return ValidationResult(
        file_name=file_name,
        information_type=label,
        status="error",
        checks=[{"label": message, "status": "error"}],
        message=message,
    )
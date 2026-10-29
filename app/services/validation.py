from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from app.services import parsers
from app.services.records import META_VALUE_KEYS, prepare_records


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

# Se conservan estos alias porque otros modulos y pruebas los importan desde
# este servicio. La implementacion vive en parsers/records para evitar ciclos.
normalize_column_name = parsers.normalize_column_name
detect_csv_certificacion_type = parsers.detect_csv_certificacion_type
_read_csv = parsers.read_csv_frame


@dataclass
class ValidationResult:
    file_name: str
    information_type: str
    status: str
    checks: list[dict[str, str]]
    records_found: int | None = None
    valid_records: int | None = None
    rejected_records: int = 0
    duplicate_records: int = 0
    inconsistencies: int = 0
    message: str | None = None
    detected_columns: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    extra_columns: list[str] = field(default_factory=list)
    breakdown: dict[str, dict[str, int]] = field(default_factory=dict)
    coherence_conflicts: list[dict[str, Any]] = field(default_factory=list)
    missing_complementaria: bool = False

    def as_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "information_type": self.information_type,
            "status": self.status,
            "checks": self.checks,
            "records_found": self.records_found,
            "valid_records": self.valid_records,
            "rejected_records": self.rejected_records,
            "duplicate_records": self.duplicate_records,
            "inconsistencies": self.inconsistencies,
            "message": self.message,
            "detected_columns": self.detected_columns,
            "missing_columns": self.missing_columns,
            "extra_columns": self.extra_columns,
            "breakdown": self.breakdown,
            "coherence_conflicts": self.coherence_conflicts,
            "missing_complementaria": self.missing_complementaria,
        }


def validate_file(file_name: str, content: bytes, information_type: str) -> ValidationResult:
    """Valida estructura, legibilidad y registros importables de un archivo.

    La validacion es preliminar: no escribe en la base de datos. El estado final
    se decide con los contadores de :mod:`app.services.records`:

    * ``error``: el archivo no se puede leer o no queda ningun registro
      importable. La vista previa y la confirmacion se bloquean.
    * ``warning``: hay registros importables, pero tambien advertencias o filas
      rechazadas. Se permite importacion parcial de los registros validos.
    * ``ready``: todos los registros detectados son importables y no hay
      advertencias.
    """
    checks: list[dict[str, str]] = []
    extension = Path(file_name).suffix.lower()
    label = TYPE_LABELS.get(information_type, information_type)

    if information_type not in SUPPORTED_TYPES:
        return _error(file_name, label, "Tipo de informacion no reconocido.")
    if not content:
        return _error(file_name, label, "El archivo esta vacio.")
    if len(content) > MAX_FILE_SIZE:
        return _error(file_name, label, "El archivo supera el limite recomendado de 20 MB.")

    # "Archivo recibido" describe la recepcion, que si esta comprobada. No se
    # afirma que el contenido se haya podido abrir: eso solo se sabe despues de
    # leerlo, y en un archivo ilegible no debe aparecer como estado positivo.
    checks.append({"label": "Archivo recibido", "status": "ok"})
    if extension not in SUPPORTED_TYPES[information_type]:
        return ValidationResult(
            file_name=file_name,
            information_type=label,
            status="error",
            checks=checks + [{"label": "Formato compatible", "status": "error"}],
            records_found=0,
            valid_records=0,
            message=f"{extension or 'Sin extension'} no es compatible con {label}.",
        )

    checks.append({"label": "Formato compatible", "status": "ok"})

    detected_columns: list[str] = []
    missing_columns: list[str] = []
    extra_columns: list[str] = []
    inconsistencies = 0
    missing_complementaria = False
    target_type = information_type
    frame: pd.DataFrame | None = None

    try:
        if information_type == "actas_completo":
            missing_count, missing_complementaria = _check_actas_sheets(content, checks)
            inconsistencies += missing_count
        elif extension == ".csv":
            frame = parsers.read_csv_frame(content)
            checks.append({"label": "Columnas leidas correctamente", "status": "ok"})
            if information_type == "csv_certificacion":
                target_type, sub_label = parsers.detect_csv_certificacion_type(frame)
                checks.append({"label": f"Contenido detectado: {sub_label}", "status": "ok"})
        elif extension in {".xlsx", ".xls"}:
            if information_type == "meta":
                metas = parsers.read_meta_sheet(content)
                recognized = [key for key in META_VALUE_KEYS if key in metas]
                if recognized:
                    checks.append(
                        {"label": f"{len(recognized)} metas reconocidas", "status": "ok"}
                    )
                else:
                    checks.append(
                        {"label": "No se reconocieron metas en la hoja META", "status": "warning"}
                    )
            else:
                frame = pd.read_excel(BytesIO(content))
                checks.append({"label": "Columnas leidas correctamente", "status": "ok"})
        elif extension == ".xml":
            frame = parsers.parse_df14a_xml(content)
            checks.append({"label": "Columnas leidas correctamente", "status": "ok"})
        elif extension == ".pdf":
            _validate_pdf(content)
            checks.append({"label": "Documento PDF abierto correctamente", "status": "ok"})
        elif extension == ".docx":
            _validate_docx(content)
            checks.append({"label": "Documento Word abierto correctamente", "status": "ok"})

        if information_type == "acta":
            # Un acta oficial no es una tabla: se informa que se pudo leer de su
            # contenido y que se podra asociar a los aprendices identificados.
            acta_checks = _acta_checks(parsers.extract_acta_data(file_name, content))
            checks.extend(acta_checks)
            inconsistencies += sum(check["status"] == "warning" for check in acta_checks)

        if frame is not None:
            detected_columns = [str(column) for column in frame.columns]
            missing_columns, extra_columns = check_required_columns(
                target_type, detected_columns
            )
            if missing_columns:
                checks.append(
                    {
                        "label": (
                            f"Faltan {len(missing_columns)} columna(s) obligatoria(s): "
                            f"{', '.join(missing_columns)}"
                        ),
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

        prepared = prepare_records(file_name, content, information_type)
        records_found = prepared.records_found
        valid_records = prepared.valid_records
        rejected_records = prepared.rejected_records
        duplicate_records = prepared.duplicate_records
        breakdown = prepared.breakdown()
        coherence = (
            coherence_conflicts(prepared)
            if information_type == "actas_completo"
            else []
        )

        if duplicate_records:
            inconsistencies += 1
            checks.append(
                {
                    "label": (
                        f"{duplicate_records} registros duplicados dentro del archivo; "
                        "se conservara el ultimo y no se insertaran filas repetidas"
                    ),
                    "status": "warning",
                }
            )

        if rejected_records:
            reasons = sorted(
                {entry.reason for entry in prepared.rejected if entry.reason}
            )
            checks.append(
                {
                    "label": (
                        f"{rejected_records} registro(s) rechazado(s) por datos "
                        f"incompletos: {', '.join(reasons)}"
                    ),
                    "status": "warning" if valid_records else "error",
                }
            )

        if records_found == 0:
            checks.append(
                {
                    "label": "No se encontraron registros para importar en el archivo",
                    "status": "error",
                }
            )
        elif valid_records == 0:
            checks.append(
                {
                    "label": (
                        "No hay registros importables; corrija los errores antes de "
                        "confirmar la importacion"
                    ),
                    "status": "error",
                }
            )
        else:
            checks.append(
                {"label": f"{valid_records:,} registro(s) importable(s)".replace(",", "."), "status": "ok"}
            )

        checks.append(
            {"label": f"{records_found:,} registro(s) encontrado(s)".replace(",", "."), "status": "info"}
        )

        # Advertencias transversales: se calculan por separado sobre los
        # registros importables y sobre los rechazados. Asi una advertencia
        # nunca afirma que se importara una fila que en realidad fue descartada.
        importable_people = _people_frame(prepared.importable)
        rejected_people = _people_frame(prepared.rejected)

        if importable_people is not None and not importable_people.empty:
            u_count, u_names = check_formation_levels(importable_people)
            if u_count > 0:
                inconsistencies += 1
                checks.append(
                    {
                        "label": (
                            f"{u_count} registro(s) con nivel de formacion sin clasificar "
                            f"({', '.join(sorted(set(u_names))[:3])}); se importan, pero no "
                            "se asignan automaticamente a ninguna categoria"
                        ),
                        "status": "warning",
                    }
                )

            date_warns = check_dates_and_periods(importable_people, target_type)
            for warning in date_warns:
                if warning["status"] == "warning":
                    inconsistencies += 1
                checks.append(warning)

        if rejected_people is not None and not rejected_people.empty:
            r_count, r_names = check_formation_levels(rejected_people)
            if r_count > 0:
                checks.append(
                    {
                        "label": (
                            f"Se detectaron {r_count} registro(s) con nivel de formacion "
                            f"sin clasificar ({', '.join(sorted(set(r_names))[:3])}) en filas "
                            "rechazadas; no seran importadas"
                        ),
                        "status": "warning",
                    }
                )

        if information_type == "actas_completo":
            inconsistencies += _append_actas_warnings(prepared, checks)

        if information_type == "informe" and records_found == 0:
            checks.append(
                {
                    "label": "No se encontro la tabla de referencia institucional en el documento",
                    "status": "error",
                }
            )

        if inconsistencies:
            checks.append(
                {
                    "label": (
                        f"Advertencias detectadas: {inconsistencies} "
                        "(el detalle de filas esta arriba; no bloquean los registros validos)"
                    ),
                    "status": "warning",
                }
            )

        if valid_records == 0 or records_found == 0:
            return ValidationResult(
                file_name=file_name,
                information_type=label,
                status="error",
                checks=checks,
                records_found=records_found,
                valid_records=valid_records,
                rejected_records=rejected_records,
                duplicate_records=duplicate_records,
                inconsistencies=inconsistencies,
                message=(
                    "El archivo no contiene registros importables. Corrija los errores "
                    "senalados; no se ha guardado ningun dato."
                ),
                detected_columns=detected_columns,
                missing_columns=missing_columns,
                extra_columns=extra_columns,
                breakdown=breakdown,
                coherence_conflicts=coherence,
                missing_complementaria=missing_complementaria,
            )

        status = (
            "warning"
            if inconsistencies or missing_columns or rejected_records or duplicate_records
            else "ready"
        )
        return ValidationResult(
            file_name=file_name,
            information_type=label,
            status=status,
            checks=checks,
            records_found=records_found,
            valid_records=valid_records,
            rejected_records=rejected_records,
            duplicate_records=duplicate_records,
            inconsistencies=inconsistencies,
            message=(
                "La validacion es preliminar y no se han guardado datos. "
                f"Se importaran {valid_records} registro(s) valido(s)"
                + (f" y se rechazaran {rejected_records}." if rejected_records else ".")
            ),
            detected_columns=detected_columns,
            missing_columns=missing_columns,
            extra_columns=extra_columns,
            breakdown=breakdown,
            coherence_conflicts=coherence,
            missing_complementaria=missing_complementaria,
        )
    except Exception as error:
        return ValidationResult(
            file_name=file_name,
            information_type=label,
            status="error",
            checks=checks + [{"label": "Contenido legible", "status": "error"}],
            records_found=0,
            valid_records=0,
            message=f"No se pudo leer el contenido del archivo: {error}",
        )


def _check_actas_sheets(content: bytes, checks: list[dict[str, str]]) -> int:
    """Verifica las hojas del paquete ACTAS 2026 sin aplicar reglas de otros tipos.

    Devuelve cuantas hojas faltan para que la validacion pueda reflejar esa
    advertencia en el estado y en el contador de inconsistencias. La ausencia de
    COMPLEMENTARIA no se convierte en error: queda pendiente una decision
    administrativa documentada.
    """
    sheets = parsers.list_excel_sheets(content)
    if not sheets:
        raise ValueError("El archivo no es un Excel legible.")
    sheet_map = {sheet.strip().upper(): sheet for sheet in sheets}
    expected = ["CERTIFICADOS", "PENDIENTES", "COMPLEMENTARIA", "META"]
    found = [name for name in expected if name in sheet_map]
    missing = [name for name in expected if name not in sheet_map]

    for name in found:
        checks.append({"label": f"Hoja {sheet_map[name]} detectada", "status": "ok"})

    if not found:
        # Si el usuario selecciono por error el flujo ACTAS para una matriz de
        # requisitos, se lo decimos sin volver a evaluar el archivo con reglas
        # ajenas. Cada tipo conserva su propio lector y sus propios mensajes.
        try:
            frame = pd.read_excel(BytesIO(content))
        except Exception:
            frame = None
        if frame is not None:
            columns = {normalize_column_name(str(column)) for column in frame.columns}
            if columns & {"documento", "nombres", "requisito", "estado"}:
                raise ValueError(
                    "El archivo parece ser una matriz de requisitos, no un paquete "
                    "ACTAS 2026. Seleccione la categoria 'Requisitos de aprendices'."
                )
        raise ValueError(
            "El archivo no contiene ninguna de las hojas esperadas del paquete ACTAS 2026."
        )

    missing_complementaria = "COMPLEMENTARIA" in missing
    for name in missing:
        if name == "COMPLEMENTARIA":
            checks.append(
                {
                    "label": (
                        "No se detectó la hoja COMPLEMENTARIA. Esta importación no "
                        "actualizará formación complementaria."
                    ),
                    "status": "warning",
                }
            )
        else:
            checks.append({"label": f"Hoja {name} no encontrada", "status": "warning"})
    return len(missing), missing_complementaria


def _people_frame(entries) -> pd.DataFrame | None:
    """Construye una tabla con los registros de personas (certificados, pendientes, df14a).

    Las advertencias de nivel y de mes se calculan sobre un grupo concreto de
    registros (importables o rechazados), nunca mezclando ambos: mezclarlos hacia
    que se anunciara como importada una fila que ya habia sido rechazada.
    """
    records = [
        entry.record
        for entry in entries
        if entry.information_type in {"certificados", "pendientes", "df14a"}
    ]
    return pd.DataFrame(records) if records else None


def _conflict_pair(record: dict[str, Any]) -> tuple[str, str] | None:
    """Devuelve ``(documento, ficha)`` normalizados para detectar cruces."""
    doc = parsers.clean_identification(
        record.get("numero de documento") or record.get("documento")
    )
    ficha = parsers.clean_identification(record.get("ficha"))
    if doc and ficha:
        return (doc, ficha)
    return None


def conflicting_pairs(prepared) -> list[tuple[str, str]]:
    """Devuelve ``(documento, ficha)`` que aparecen en CERTIFICADOS y PENDIENTES.

    Solo considera registros importables: un conflicto con una fila rechazada no
    debe mostrarse como si fuera a guardarse. No elige ni modifica ningun estado.
    """
    cert_records = [
        entry.record
        for entry in prepared.importable
        if entry.information_type == "certificados"
    ]
    pend_records = [
        entry.record
        for entry in prepared.importable
        if entry.information_type == "pendientes"
    ]

    def pairs(records):
        return {
            pair
            for record in records
            if (pair := _conflict_pair(record)) is not None
        }

    return sorted(pairs(cert_records) & pairs(pend_records))


def coherence_conflicts(prepared) -> list[dict[str, Any]]:
    """Estructura los conflictos CERTIFICADOS/PENDIENTES para la vista previa.

    Cada elemento identifica al aprendiz y la ficha en la que aparece en ambas
    hojas. El nombre se toma de la primera fila que lo traiga. No aplica ninguna
    decision: la eleccion es obligatoria y la envia el usuario al confirmar.
    """
    cert_records = {}
    pend_records = {}
    for entry in prepared.importable:
        pair = _conflict_pair(entry.record)
        if pair is None:
            continue
        if entry.information_type == "certificados":
            cert_records.setdefault(pair, entry.record)
        elif entry.information_type == "pendientes":
            pend_records.setdefault(pair, entry.record)

    conflicts: list[dict[str, Any]] = []
    seen_documents: set[str] = set()
    for pair in sorted(set(cert_records) & set(pend_records)):
        if pair[0] in seen_documents:
            # El frontend y el contrato de resolucion trabajan por documento:
            # si apareciera en dos fichas se muestra una sola fila.
            continue
        seen_documents.add(pair[0])
        record = cert_records[pair]
        name = (
            record.get("nombre")
            or record.get("nombres")
            or pend_records[pair].get("nombre")
            or pend_records[pair].get("nombres")
        )
        conflicts.append(
            {
                "identification": pair[0],
                "group_code": pair[1],
                "name": str(name).strip() if name else None,
                "in_certificados": True,
                "in_pendientes": True,
            }
        )
    return conflicts


def _append_actas_warnings(prepared, checks: list[dict[str, str]]) -> int:
    """Agrega conflictos CERTIFICADOS/PENDIENTES que requieren decision manual."""
    conflicts = coherence_conflicts(prepared)
    if not conflicts:
        return 0

    detail = ", ".join(
        f"{item['identification']} (ficha {item['group_code']})"
        for item in conflicts[:3]
    )
    if len(conflicts) > 3:
        detail += f" y {len(conflicts) - 3} mas"
    checks.append(
        {
            "label": (
                f"Coherencia: {len(conflicts)} aprendices figuran simultáneamente en "
                f"CERTIFICADOS y PENDIENTES con la misma ficha ({detail}). Elija el "
                "estado final de cada uno antes de confirmar."
            ),
            "status": "warning",
        }
    )
    return 1


def _acta_checks(extraction: dict) -> list[dict[str, str]]:
    """Resume lo que se pudo leer de un acta oficial y lo que quedo pendiente.

    Un acta sin numero no se puede registrar de forma fiable, por eso se marca
    como error. La fecha y los aprendices son advertencias: el acta sigue siendo
    valida y se conserva, pero queda visible lo que no se pudo extraer.
    """
    checks: list[dict[str, str]] = []

    number = extraction.get("number")
    if number:
        checks.append({"label": f"Acta identificada: No. {number}", "status": "ok"})
    else:
        checks.append(
            {
                "label": (
                    "No se pudo identificar el numero del acta en el documento; "
                    "no se registra un acta sin numero"
                ),
                "status": "error",
            }
        )

    act_date = extraction.get("act_date")
    if act_date:
        checks.append({"label": f"Fecha del acta: {act_date}", "status": "ok"})
    else:
        checks.append({"label": "No se pudo identificar la fecha del acta", "status": "warning"})

    learners = extraction.get("learners") or []
    if learners:
        checks.append(
            {"label": f"{len(learners)} aprendiz(es) identificado(s) en el acta", "status": "ok"}
        )
    else:
        checks.append(
            {
                "label": (
                    "El acta no aporta aprendices con numero de documento; no se "
                    "asociara a ningun aprendiz"
                ),
                "status": "warning",
            }
        )
    return checks


def _validate_pdf(content: bytes) -> None:
    """Abre el PDF y comprueba que tenga al menos una pagina legible."""
    import fitz

    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception as error:
        raise ValueError(f"PDF ilegible: {error}") from error
    try:
        if document.page_count == 0:
            raise ValueError("El PDF no contiene paginas.")
        document.load_page(0)
    finally:
        document.close()


def _validate_docx(content: bytes) -> None:
    """Abre el DOCX y exige contenido real (parrafos o tablas)."""
    from docx import Document

    try:
        document = Document(BytesIO(content))
    except Exception as error:
        raise ValueError(f"DOCX ilegible: {error}") from error
    if not document.paragraphs and not document.tables:
        raise ValueError("El documento no contiene texto ni tablas interpretables.")


def check_required_columns(
    information_type: str, columns: list[str]
) -> tuple[list[str], list[str]]:
    required = REQUIRED_COLUMNS.get(information_type)
    if not required:
        return [], []
    normalized_columns = {normalize_column_name(str(column)): str(column) for column in columns}
    missing: list[str] = []
    for column in required:
        if normalize_column_name(column) not in normalized_columns:
            missing.append(column)
    required_normalized = {normalize_column_name(column) for column in required}
    extra = [
        original
        for original in columns
        if normalize_column_name(str(original)) not in required_normalized
    ]
    return missing, extra


def _tabular_summary(frame: pd.DataFrame) -> tuple[int, int, int, int]:
    """Resumen heredado para compatibilidad; el flujo usa ``prepare_records``."""
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
        records_found=0,
        valid_records=0,
        message=message,
    )


def check_formation_levels(frame: pd.DataFrame) -> tuple[int, list[str]]:
    nivel_col = next(
        (column for column in frame.columns if "nivel" in parsers.normalize_text(str(column))),
        None,
    )
    if nivel_col is None:
        return 0, []
    unclassified_names: set[str] = set()
    count = 0
    for value in frame[nivel_col].dropna():
        text = str(value).strip()
        if not text or text.lower() in {"nan", "nat", "none"}:
            continue
        if parsers.classify_nivel(value) is None:
            count += 1
            unclassified_names.add(text)
    return count, sorted(unclassified_names)


def check_dates_and_periods(frame: pd.DataFrame, target_type: str) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    meses_validos = {
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    }
    meses_periodo = {
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre",
    }

    mes_col = next(
        (column for column in frame.columns if "mes" in parsers.normalize_text(str(column))),
        None,
    )
    if mes_col is not None:
        fuera_periodo = 0
        invalido = 0
        for value in frame[mes_col].dropna():
            texto = parsers.normalize_text(str(value))
            if not texto or texto in {"nan", "nat", "none"}:
                continue
            if texto not in meses_validos:
                invalido += 1
            elif texto not in meses_periodo:
                fuera_periodo += 1
        if invalido:
            warnings.append(
                {
                    "label": f"{invalido} registros con mes de certificacion no valido",
                    "status": "warning",
                }
            )
        if fuera_periodo:
            warnings.append(
                {
                    "label": (
                        f"{fuera_periodo} registros corresponden a meses fuera del período "
                        "de análisis (Ene-Sep 2026); se importan como referencia, pero no "
                        "se suman a los indicadores del período"
                    ),
                    "status": "info",
                }
            )
    return warnings

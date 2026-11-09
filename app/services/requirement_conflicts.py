"""Deteccion de incongruencias entre evidencias y motivo de no certificacion.

El consolidado ACTAS 2026 trae dos fuentes para el mismo hecho:

* las columnas de evidencias (``X``, ``N.A`` o vacio), que el importador
  convierte en requisitos ``Cumplido`` / ``No aplica`` / ``Pendiente``;
* la columna ``MOTIVO DE NO CERTIFICACION``, que explica en texto libre por que
  el aprendiz no se certifica.

Ambas fuentes pueden contradecirse. Este modulo no decide cual es la correcta:
solo detecta los casos y los estructura para que el usuario elija el estado
final antes de importar. La deteccion es pura (no escribe en la base de datos).
"""

from __future__ import annotations

from typing import Any

from app.services import parsers
from app.services.requirements import REQUIREMENT_TYPES, evidence_status


# Mismos campos internos que produce ``parsers._actas_records``. Se mantienen en
# un solo lugar para que la deteccion y la importacion no se desincronicen.
EVIDENCE_FIELDS: tuple[str, ...] = (
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

# Estados finales que el usuario puede elegir para un requisito en conflicto.
REQUIREMENT_CONFLICT_STATUSES = ("Cumplido", "Pendiente", "No aplica")

# Palabras clave del motivo que permiten asociar una causa con una columna de
# evidencia. El motivo es texto libre; si una causa no se reconoce no se
# inventa un requisito: simplemente no participa en la comparacion.
_MOTIVO_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("t&t", "tyt", "saber t", "pruebas saber"), "saber_tyt"),
    (("agencia publica de empleo",), "ape"),
    (("carnet",), "carnet"),
    (("documento de identidad", "documento vencido", "identidad vencida"), "documento_identidad"),
    (("etapa productiva",), "etapa_productiva"),
    (("certificado de la empresa", "certificado empresa"), "certificado_empresa"),
    (("biblioteca",), "biblioteca"),
    (("bienestar",), "bienestar"),
    (("almacen",), "almacen"),
)

_BLANK_VALUES = {"", "nan", "nat", "none", "null"}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    return bool(text) and text.lower() not in _BLANK_VALUES


def requirement_for_cause(cause: Any) -> str | None:
    """Traduce una causa canonica del motivo a un tipo de requisito, o ``None``.

    No se fuerza una equivalencia cuando el texto es generico ("no ha remitido
    documentos"): en ese caso no se puede afirmar que columna falta.
    """
    text = parsers.normalize_text(cause)
    if not text:
        return None
    # ``APE`` se compara como palabra completa para no confundirlo con otros
    # textos que contengan esas letras (por ejemplo, "mapa").
    if text == "ape":
        return "ape"
    for keywords, requirement_type in _MOTIVO_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            return requirement_type
    return None


def requirement_level_applies(record: dict[str, Any], requirement_type: str) -> bool:
    """Indica si el requisito aplica al nivel de formacion del aprendiz.

    Saber TyT esta marcado en el consolidado como "(SOLO TGO)": para los demas
    niveles una celda vacia no es una incongruencia, porque el requisito no
    aplica. El resto de requisitos se evaluan para todos los niveles.
    """
    if requirement_type != "saber_tyt":
        return True
    return parsers.normalize_nivel(record.get("nivel")) == "tecnologo"


def requirement_conflict_key(identification: str, requirement_type: str) -> str:
    """Llave estable que usa la UI para enviar y preseleccionar una decision."""
    return f"{str(identification).strip()}|{str(requirement_type).strip()}"


def _document(record: dict[str, Any]) -> str | None:
    return parsers.clean_identification(
        record.get("numero de documento") or record.get("documento")
    )


def _first_motivo(rows: list[tuple[str, dict[str, Any]]]) -> Any:
    for _, record in reversed(rows):
        value = record.get("motivo de no certificacion")
        if _has_value(value):
            return value
    return None


def _first_value(rows: list[tuple[str, dict[str, Any]]], *keys: str) -> Any:
    for _, record in rows:
        for key in keys:
            value = record.get(key)
            if _has_value(value):
                return value
    return None


def requirement_conflicts(prepared: Any) -> list[dict[str, Any]]:
    """Devuelve los requisitos donde la columna y el motivo no coinciden.

    Se comparan solo registros importables de CERTIFICADOS/PENDIENTES. Cuando un
    documento aparece en ambas hojas se usa el ultimo registro leido para cada
    campo (PENDIENTES se procesa despues de CERTIFICADOS), que es el mismo valor
    que termina guardando la importacion.
    """
    grouped: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for entry in prepared.importable:
        if entry.information_type not in {"certificados", "pendientes"}:
            continue
        document = _document(entry.record)
        if not document:
            continue
        grouped.setdefault(document, []).append((entry.information_type, entry.record))

    conflicts: dict[tuple[str, str], dict[str, Any]] = {}
    for document, rows in grouped.items():
        motivo_raw = _first_motivo(rows)
        if not _has_value(motivo_raw):
            continue
        causes = parsers.normalize_motivo_fragments(motivo_raw)
        motivo_types = {
            requirement_type
            for cause in causes
            if (requirement_type := requirement_for_cause(cause)) is not None
        }
        if not motivo_types:
            # Sin una causa reconocible no hay una columna concreta que comparar.
            continue

        effective: dict[str, tuple[str, dict[str, Any]]] = {}
        for information_type, record in rows:
            for field in EVIDENCE_FIELDS:
                if field in record:
                    effective[field] = (information_type, record)

        name = _first_value(rows, "nombre", "nombres")
        group_code = _first_value(rows, "ficha", "codigo ficha")
        for field, (information_type, record) in effective.items():
            if not requirement_level_applies(record, field):
                continue
            status = evidence_status(record.get(field))
            in_motivo = field in motivo_types
            if in_motivo and status != "Pendiente":
                reason = "motivo_missing_evidence_present"
                reason_label = (
                    f"La columna marca el requisito como {status}, pero el motivo "
                    f"indica que falta: «{', '.join(causes)}»."
                )
            elif not in_motivo and status == "Pendiente":
                reason = "evidence_missing_motivo_other"
                reason_label = (
                    "La columna no registra este requisito (Pendiente), pero el "
                    f"motivo menciona otra causa: «{str(motivo_raw).strip()}»."
                )
            else:
                continue

            conflicts[(document, field)] = {
                "identification": document,
                "group_code": str(group_code).strip() if _has_value(group_code) else None,
                "name": str(name).strip() if _has_value(name) else None,
                "requirement_type": field,
                "requirement_label": REQUIREMENT_TYPES.get(field, field),
                "source": information_type,
                "evidence_status": status,
                "motivo": str(motivo_raw).strip(),
                "motivo_causes": causes,
                "reason": reason,
                "reason_label": reason_label,
            }

    return sorted(
        conflicts.values(),
        key=lambda item: (item["identification"], item["requirement_type"]),
    )

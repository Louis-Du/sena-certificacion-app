"""Deteccion y clasificacion de incongruencias entre evidencias y motivo.

El consolidado ACTAS 2026 trae dos fuentes para el mismo hecho:

* las columnas de evidencias (``X``, ``N.A``, ``Pendiente`` o vacio);
* la columna ``MOTIVO DE NO CERTIFICACION``, que explica en texto libre por que
  el aprendiz no se certifica.

Este modulo no decide por el usuario: detecta las contradicciones reales y
propone una decision preliminar. La decision final se confirma antes de
importar y queda auditada.

Reglas de producto implementadas
--------------------------------
1. Una celda vacia **no** equivale a ``Pendiente``. Se interpreta como
   ``Sin información``; solo el motivo puede justificar un ``Pendiente``.
2. Si la celda esta vacia y el motivo no nombra ese requisito, no se crea un
   conflicto fantasma. Es el caso tipico de ``No anexa T&T`` con APE, carnet o
   documento vacios: el motivo no habla de ellos.
3. Saber TyT esta marcado ``(SOLO TGO)``. Si el nivel no es Tecnologo y la
   celda esta vacia, se aplica la regla automatica ``No aplica``.
4. ``X`` (Cumplido) + motivo que dice que falta, y ``N.A.`` + motivo que dice
   que falta, son contradicciones reales. La segunda exige revision manual.
5. Una celda vacia + motivo que si nombra el requisito es una contradiccion
   leve: el motivo aporta la evidencia de que falta. Se agrupa como "Media" y
   se sugiere ``Pendiente``.
"""

from __future__ import annotations

import hashlib
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
REQUIREMENT_CONFLICT_STATUSES = ("Pendiente", "Cumplido", "No aplica")

# Origen de una decision. La UI envia ``user`` o ``bulk``; ``rule`` lo usa el
# backend para las reglas automaticas; ``saved`` solo se usa para pintar una
# decision recuperada de una importacion anterior.
RESOLUTION_SOURCES = ("user", "bulk", "rule", "saved")

# Grupos visibles del modal. El orden es el de la UI.
CONFLICT_GROUPS: tuple[str, ...] = ("high", "medium", "review")

GROUP_LABELS = {
    "high": "Alta confianza / auto-sugerible",
    "medium": "Media",
    "review": "Requiere revisión",
}

# Patrones de contradiccion. ``group`` determina la seccion del modal,
# ``suggested_status`` la preseleccion visible (nunca una decision implicita) y
# ``auto_resolved`` indica que el backend puede aplicarla sin bloquear.
PATTERNS: dict[str, dict[str, Any]] = {
    "evidence_fulfilled_motivo_missing": {
        "group": "high",
        "label": "Columna X · el motivo indica que falta",
        "short": "X vs motivo",
        "suggested_status": "Pendiente",
        "auto_resolved": False,
        "suggestion_reason": (
            "La columna marca Cumplido, pero el motivo humano dice que falta. "
            "En duda, el motivo suele mandar."
        ),
    },
    "evidence_blank_motivo_missing": {
        "group": "medium",
        "label": "Columna vacía · el motivo nombra el requisito",
        "short": "Vacía vs motivo",
        "suggested_status": "Pendiente",
        "auto_resolved": False,
        "suggestion_reason": (
            "La celda no trae evidencia y el motivo menciona este requisito. "
            "Se sugiere Pendiente, pero requiere confirmación."
        ),
    },
    "evidence_na_motivo_missing": {
        "group": "review",
        "label": "Columna N.A. · el motivo indica que falta",
        "short": "N.A. vs motivo",
        "suggested_status": None,
        "auto_resolved": False,
        "suggestion_reason": (
            "La columna marca No aplica y el motivo dice que falta. No hay una "
            "sugerencia fuerte: revise el caso."
        ),
    },
    "tyt_not_applicable_level": {
        "group": "high",
        "label": "Saber TyT no aplica al nivel (regla)",
        "short": "TyT no TGO",
        "suggested_status": "No aplica",
        "auto_resolved": True,
        "suggestion_reason": (
            "Saber TyT es solo para Tecnólogos. El nivel del aprendiz no es TGO "
            "y la celda no trae evidencia."
        ),
    },
    "tyt_level_mismatch": {
        "group": "review",
        "label": "Saber TyT marcado fuera de TGO",
        "short": "TyT fuera de nivel",
        "suggested_status": "No aplica",
        "auto_resolved": False,
        "suggestion_reason": (
            "Saber TyT es solo para Tecnólogos y el aprendiz tiene otro nivel, "
            "pero la columna trae una marca. Confirme si corresponde."
        ),
    },
}

# Orden estable para secciones internas del modal.
PATTERN_ORDER = {
    "evidence_fulfilled_motivo_missing": 10,
    "evidence_blank_motivo_missing": 20,
    "evidence_na_motivo_missing": 30,
    "tyt_not_applicable_level": 40,
    "tyt_level_mismatch": 50,
}

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


def _raw_evidence(value: Any) -> str:
    """Texto legible de la celda, sin inventar un valor que no existe."""
    if not _has_value(value):
        return ""
    return str(value).strip()


def _raw_label(raw: str) -> str:
    return f"«{raw}»" if raw else "vacía"


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


def conflict_fingerprint(
    requirement_type: str,
    evidence_raw: str,
    evidence: str,
    motivo: str,
    nivel: str | None,
) -> str:
    """Huella del contraste que origino el conflicto.

    Permite reaplicar una decision guardada solo si la columna, el motivo y el
    nivel siguen siendo los mismos. Si el consolidado cambia el hecho, el
    conflicto se reabre en lugar de reutilizar una decision vieja.
    """
    material = "|".join(
        [
            parsers.normalize_text(requirement_type),
            parsers.normalize_text(evidence_raw),
            parsers.normalize_text(evidence),
            parsers.normalize_text(motivo),
            parsers.normalize_text(nivel or ""),
        ]
    )
    return hashlib.sha1(material.encode("utf-8")).hexdigest()[:20]


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


def _effective_records(
    rows: list[tuple[str, dict[str, Any]]],
) -> dict[str, tuple[str, dict[str, Any]]]:
    """Ultimo registro leido por campo.

    PENDIENTES se procesa despues de CERTIFICADOS, que es el mismo criterio que
    usa la importacion para quedarse con un valor por aprendiz.
    """
    effective: dict[str, tuple[str, dict[str, Any]]] = {}
    for information_type, record in rows:
        for field in EVIDENCE_FIELDS:
            if field in record:
                effective[field] = (information_type, record)
    return effective


def _pattern_for(
    *,
    requirement_type: str,
    status: str,
    in_motivo: bool,
    applies: bool,
) -> str | None:
    """Devuelve el patron de conflicto o ``None`` si no hay contradiccion real."""
    if requirement_type == "saber_tyt" and not applies:
        if status == "Sin información":
            # Regla automatica: TyT vacio en un nivel que no es TGO.
            return "tyt_not_applicable_level"
        if status == "No aplica":
            # La columna ya dice lo que corresponde al nivel.
            return None
        if status in {"Cumplido", "Pendiente"} and in_motivo:
            return "tyt_level_mismatch"
        return None

    if not in_motivo:
        # La celda vacia no se convierte en Pendiente por si sola. Si el motivo
        # habla de otra causa, este requisito no participa en el modal.
        return None

    if status == "Cumplido":
        return "evidence_fulfilled_motivo_missing"
    if status == "No aplica":
        return "evidence_na_motivo_missing"
    if status == "Sin información":
        return "evidence_blank_motivo_missing"
    # ``Pendiente`` explicito + motivo que lo nombra es coherente: no hay
    # contradiccion que mostrar. Tampoco se crea conflicto cuando el motivo
    # habla de otra causa.
    return None


def requirement_conflicts(prepared: Any) -> list[dict[str, Any]]:
    """Devuelve solo las contradicciones reales entre columna y motivo.

    Se comparan registros importables de CERTIFICADOS/PENDIENTES. Cuando un
    documento aparece en ambas hojas se usa el ultimo registro leido para cada
    campo, igual que en la importacion.
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
        motivo_text = str(motivo_raw).strip() if _has_value(motivo_raw) else ""
        causes = parsers.normalize_motivo_fragments(motivo_raw)
        motivo_types = {
            requirement_type
            for cause in causes
            if (requirement_type := requirement_for_cause(cause)) is not None
        }
        # Sin una causa reconocible no se compara columna contra motivo, pero la
        # regla de Saber TyT fuera de TGO sigue aplicando aunque no haya motivo:
        # la celda vacia se resuelve como No aplica sin intervencion del usuario.

        name = _first_value(rows, "nombre", "nombres")
        group_code = _first_value(rows, "ficha", "codigo ficha")
        effective = _effective_records(rows)
        for field, (information_type, record) in effective.items():
            raw = _raw_evidence(record.get(field))
            status = evidence_status(record.get(field))
            in_motivo = field in motivo_types
            applies = requirement_level_applies(record, field)
            pattern = _pattern_for(
                requirement_type=field,
                status=status,
                in_motivo=in_motivo,
                applies=applies,
            )
            if pattern is None:
                continue

            meta = PATTERNS[pattern]
            nivel_raw = record.get("nivel")
            nivel = parsers.normalize_nivel(nivel_raw)
            suggested = meta["suggested_status"]
            auto_resolved = bool(meta["auto_resolved"] and suggested)
            requirement_label = REQUIREMENT_TYPES.get(field, field)

            if pattern == "evidence_fulfilled_motivo_missing":
                reason_label = (
                    f"La columna marca {status}, pero el motivo dice que falta."
                )
            elif pattern == "evidence_na_motivo_missing":
                reason_label = (
                    "La columna marca No aplica, pero el motivo dice que falta."
                )
            elif pattern == "evidence_blank_motivo_missing":
                reason_label = (
                    "La columna está vacía y el motivo nombra este requisito."
                )
            elif pattern == "tyt_not_applicable_level":
                reason_label = (
                    "Saber TyT es solo para TGO; el nivel no es Tecnólogo y la "
                    "celda está vacía."
                )
            else:
                reason_label = (
                    "Saber TyT es solo para TGO y la columna trae una marca."
                )

            conflicts[(document, field)] = {
                "identification": document,
                "group_code": str(group_code).strip() if _has_value(group_code) else None,
                "name": str(name).strip() if _has_value(name) else None,
                "requirement_type": field,
                "requirement_label": requirement_label,
                "source": information_type,
                "evidence_raw": raw,
                "evidence_label": _raw_label(raw),
                "evidence_status": status,
                "motivo": motivo_text,
                "motivo_causes": causes,
                "motivo_mentions": in_motivo,
                "level": nivel_raw if _has_value(nivel_raw) else None,
                "level_applies": applies,
                "pattern": pattern,
                "pattern_label": meta["label"],
                "pattern_short": meta["short"],
                "group": meta["group"],
                "group_label": GROUP_LABELS[meta["group"]],
                "suggested_status": suggested,
                "suggested_source": "rule" if suggested else None,
                "suggestion_reason": meta["suggestion_reason"],
                "auto_resolved": auto_resolved,
                "reason": pattern,
                "reason_label": reason_label,
                "fingerprint": conflict_fingerprint(
                    field,
                    raw,
                    status,
                    motivo_text,
                    str(nivel_raw) if _has_value(nivel_raw) else None,
                ),
            }

    return sorted(
        conflicts.values(),
        key=lambda item: (
            CONFLICT_GROUPS.index(item["group"])
            if item["group"] in CONFLICT_GROUPS
            else len(CONFLICT_GROUPS),
            PATTERN_ORDER.get(item["pattern"], 999),
            str(item["identification"]),
            item["requirement_type"],
        ),
    )


def requirement_conflict_summary(conflicts: list[dict[str, Any]]) -> dict[str, Any]:
    """Resumen estable para la barra de progreso y las pestanas."""
    groups = {group: 0 for group in CONFLICT_GROUPS}
    patterns: dict[str, int] = {}
    auto_resolved = 0
    for item in conflicts:
        group = item.get("group")
        if group in groups:
            groups[group] += 1
        pattern = str(item.get("pattern") or "")
        if pattern:
            patterns[pattern] = patterns.get(pattern, 0) + 1
        if item.get("auto_resolved"):
            auto_resolved += 1
    total = len(conflicts)
    return {
        "total": total,
        "auto_resolved": auto_resolved,
        "requires_decision": total - auto_resolved,
        "groups": groups,
        "patterns": patterns,
    }

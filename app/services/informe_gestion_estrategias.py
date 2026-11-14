"""Persistencia de los textos de estrategias del Informe de Gestión.

La dependencia redacta las actividades del bloque 3 del informe oficial. Estos
textos no se deducen de los datos del consolidado: se guardan por
``(año, trimestre)`` y el generador DOCX los inserta al exportar.

El campo de cada sección acepta HTML restringido (párrafos, saltos, negrita,
cursiva y listas) o el texto plano histórico. Todo valor se sanea con
:func:`app.services.rich_text.sanitize_estrategia_html` antes de guardarse y al
devolverse por API.

El modo de exportación (``solo_trimestre`` / ``acumulado``) solo afecta a las
cifras; no crea un juego distinto de estrategias.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import InformeGestionEstrategia
from app.services.rich_text import sanitize_estrategia_html

# Orden y rótulos visibles para la UI y el DOCX.
SECCIONES: tuple[tuple[str, str], ...] = (
    ("3.1.1", "Educación Superior"),
    ("3.1.2", "Técnico Laboral y Otros (sin incluir Media Técnica)"),
    ("3.1.3", "Articulación con la Media"),
    ("3.1.4", "Formación Complementaria"),
    ("3.1.5", "Certificación Total / Centros de Formación"),
    ("3.2", "Otras actividades del trimestre"),
)

SECCION_KEYS: tuple[str, ...] = tuple(key for key, _ in SECCIONES)

# Mapeo entre la clave pública de sección y la columna del modelo.
_CAMPO_POR_SECCION = {
    "3.1.1": "educacion_superior",
    "3.1.2": "tecnico_laboral",
    "3.1.3": "articulacion_media",
    "3.1.4": "formacion_complementaria",
    "3.1.5": "certificacion_total",
    "3.2": "otras_actividades",
}


def normalizar_trimestre(value: Any) -> str:
    """Normaliza ``3``, ``"3"``, ``"T3"`` o ``"III"`` a ``T1``..``T4``."""
    if value is None or str(value).strip() == "":
        return "T3"
    texto = str(value).strip().upper()
    romanos = {"I": "T1", "II": "T2", "III": "T3", "IV": "T4"}
    if texto in romanos:
        return romanos[texto]
    if texto.startswith("T"):
        texto = texto[1:]
    if texto in {"1", "2", "3", "4"}:
        return f"T{texto}"
    raise ValueError("Trimestre no válido. Use T1, T2, T3 o T4.")


def normalizar_anio(value: Any) -> int:
    try:
        anio = int(value) if value is not None else 2026
    except (TypeError, ValueError) as error:
        raise ValueError("Año no válido.") from error
    if not 2000 <= anio <= 2100:
        raise ValueError("Año no válido.")
    return anio


def _texto(value: Any) -> str:
    """Normaliza el valor de una sección y elimina HTML no permitido.

    Los textos históricos en plano se devuelven tal cual (solo se recortan los
    extremos); el HTML del editor se sanea con la allowlist de ``rich_text``.
    """
    return sanitize_estrategia_html(value)


def _registro(
    session: Session, anio: int, trimestre: str
) -> InformeGestionEstrategia | None:
    return session.scalar(
        select(InformeGestionEstrategia).where(
            InformeGestionEstrategia.anio == anio,
            InformeGestionEstrategia.trimestre == trimestre,
        )
    )


def _payload(
    anio: int, trimestre: str, registro: InformeGestionEstrategia | None
) -> dict[str, Any]:
    secciones = {
        key: _texto(getattr(registro, _CAMPO_POR_SECCION[key], None))
        if registro is not None
        else ""
        for key in SECCION_KEYS
    }
    return {
        "anio": anio,
        "trimestre": trimestre,
        "existe": registro is not None,
        "secciones": secciones,
        "actualizado_en": (
            registro.updated_at.isoformat()
            if registro is not None and registro.updated_at is not None
            else None
        ),
    }


def get_estrategias(
    session: Session,
    *,
    anio: Any = None,
    trimestre: Any = None,
) -> dict[str, Any]:
    """Devuelve los textos del periodo; si no existen, secciones vacías."""
    anio_normalizado = normalizar_anio(anio)
    trimestre_normalizado = normalizar_trimestre(trimestre)
    registro = _registro(session, anio_normalizado, trimestre_normalizado)
    return _payload(anio_normalizado, trimestre_normalizado, registro)


def save_estrategias(
    session: Session,
    *,
    anio: Any = None,
    trimestre: Any = None,
    secciones: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Crea o actualiza el registro único ``(año, trimestre)``.

    ``secciones`` usa las claves públicas ``3.1.1`` .. ``3.2``. Las claves
    desconocidas se rechazan para evitar perder texto por un error de tipeo.
    """
    anio_normalizado = normalizar_anio(anio)
    trimestre_normalizado = normalizar_trimestre(trimestre)
    secciones = secciones or {}
    desconocidas = sorted(set(secciones) - set(SECCION_KEYS))
    if desconocidas:
        raise ValueError(
            "Sección de estrategias no válida: " + ", ".join(desconocidas) + "."
        )

    registro = _registro(session, anio_normalizado, trimestre_normalizado)
    if registro is None:
        registro = InformeGestionEstrategia(
            anio=anio_normalizado, trimestre=trimestre_normalizado
        )
        session.add(registro)

    for key, campo in _CAMPO_POR_SECCION.items():
        if key in secciones:
            texto = _texto(secciones[key])
            setattr(registro, campo, texto or None)

    registro.updated_at = datetime.now(timezone.utc)
    try:
        session.commit()
    except IntegrityError:
        # Dos peticiones simultáneas pueden intentar crear el mismo periodo.
        # Se reintenta como actualización del registro ya existente.
        session.rollback()
        registro = _registro(session, anio_normalizado, trimestre_normalizado)
        if registro is None:
            raise
        for key, campo in _CAMPO_POR_SECCION.items():
            if key in secciones:
                texto = _texto(secciones[key])
                setattr(registro, campo, texto or None)
        registro.updated_at = datetime.now(timezone.utc)
        session.commit()

    session.refresh(registro)
    return _payload(anio_normalizado, trimestre_normalizado, registro)


def list_periodos(session: Session, *, anio: Any = None) -> list[dict[str, Any]]:
    """Lista los periodos con registro, opcionalmente filtrados por año."""
    query = select(InformeGestionEstrategia).order_by(
        InformeGestionEstrategia.anio.desc(),
        InformeGestionEstrategia.trimestre,
    )
    if anio is not None:
        query = query.where(InformeGestionEstrategia.anio == normalizar_anio(anio))
    registros = session.scalars(query).all()
    return [
        {
            "anio": registro.anio,
            "trimestre": registro.trimestre,
            "actualizado_en": (
                registro.updated_at.isoformat()
                if registro.updated_at is not None
                else None
            ),
        }
        for registro in registros
    ]


def estrategias_para_docx(
    session: Session, *, anio: Any = None, trimestre: Any = None
) -> dict[str, str]:
    """Mapa simple ``sección -> texto`` que consume ``report_word``."""
    return get_estrategias(session, anio=anio, trimestre=trimestre)["secciones"]


__all__ = [
    "SECCIONES",
    "SECCION_KEYS",
    "normalizar_anio",
    "normalizar_trimestre",
    "get_estrategias",
    "save_estrategias",
    "list_periodos",
    "estrategias_para_docx",
]

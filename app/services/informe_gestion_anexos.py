"""Anexos del Informe de Gestión Administrativa (sección 5 del DOCX).

Los soportes se guardan por ``(año, trimestre)``, igual que las estrategias: el
modo de exportación (``solo_trimestre`` / ``acumulado``) solo afecta a las
cifras y nunca crea un juego distinto de anexos.

El binario se escribe en disco y la fila de la base de datos solo conserva la
referencia:

* Raíz por defecto: ``<proyecto>/data/informe_gestion_anexos`` (el mismo
  volumen ``app_data`` que usa SQLite en Docker).
* Se puede cambiar con la variable de entorno ``INFORME_ANEXOS_DIR`` (las
  pruebas la apuntan a ``tmp_path``).
* Cada archivo se renombra a ``{anio}-{trimestre}-{uuid}{ext}`` para evitar
  colisiones y nombres arbitrarios del cliente; ``nombre_archivo`` conserva el
  nombre original solo para mostrarlo/descargarlo.

Tipos permitidos en v1 (validados por firma binaria, no solo por la extensión):
PNG, JPEG, WEBP, PDF y DOCX. Tamaño máximo: 10 MB.

Regla de numeración (única para catálogo y DOCX):

* El listado se ordena por ``orden`` ascendente y, a igual orden, por ``id``
  (el alta asigna automáticamente ``max(orden) + 1``, así que el orden por
  defecto es el de creación).
* El rótulo siempre es ``ANEXO {n}. {titulo}``. ``n`` es la posición 1..N o el
  número de un código manual único y válido (``ANEXO 3``, ``3``, ``N° 3`` …).
* Los códigos manuales numéricos reservan su número. Los anexos sin código
  reciben el menor número libre, de modo que no haya dos ``ANEXO 3`` ni huecos
  cuando todos los códigos están vacíos.
* El título se guarda sin el prefijo ``ANEXO N``: el sistema lo agrega al
  exportar, de modo que nunca se produce ``ANEXO 1. ANEXO 1. …``.
* Un código repetido en el mismo ``(año, trimestre)`` se rechaza con 400.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import InformeGestionAnexo
from app.services.informe_gestion_estrategias import (
    normalizar_anio,
    normalizar_trimestre,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_STORAGE_DIR = BASE_DIR / "data" / "informe_gestion_anexos"

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_TITULO = 255
MAX_CODIGO = 40
MAX_DESCRIPCION = 4000

# Código manual que representa un número de anexo: "ANEXO 3", "Anexo N° 3",
# "N° 3", "3", "3." … Cualquier otro texto ("A-2") se conserva como rótulo.
_CODIGO_NUMERICO_RE = re.compile(
    r"^\s*(?:anexo\s*(?:n[°º.]?\s*)?|n[°º.]?\s*)?(\d{1,3})\s*[.):\-–—]?\s*$",
    re.IGNORECASE,
)
# Prefijo "ANEXO 3. " / "Anexo N° 3: " que el usuario no debe repetir en el
# título porque el rotulador del DOCX ya lo agrega.
_PREFIJO_TITULO_RE = re.compile(
    r"^\s*anexo\s*(?:n[°º.]?\s*)?\d{1,3}\s*[.):\-–—]*\s*",
    re.IGNORECASE,
)

DOCX_MIME = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
TIPOS_PERMITIDOS: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    DOCX_MIME: ".docx",
}


class AnexoError(ValueError):
    """Error de validación de un anexo (400 por defecto)."""

    status_code = 400


class AnexoNoEncontrado(AnexoError):
    status_code = 404


class AnexoTipoInvalido(AnexoError):
    status_code = 415


class AnexoDemasiadoGrande(AnexoError):
    status_code = 413


def storage_dir() -> Path:
    """Directorio raíz de los binarios, resuelto en cada llamada.

    Se resuelve en tiempo de ejecución para que las pruebas puedan usar
    ``tmp_path`` mediante ``INFORME_ANEXOS_DIR`` sin tocar ``data/``.
    """
    override = os.getenv("INFORME_ANEXOS_DIR")
    return Path(override) if override else DEFAULT_STORAGE_DIR


def _detectar_tipo(nombre: str, contenido: bytes) -> tuple[str, str]:
    """Devuelve ``(content_type, extensión)`` validando la firma del archivo."""
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if contenido.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp", ".webp"
    if contenido.startswith(b"%PDF-"):
        return "application/pdf", ".pdf"
    if contenido.startswith(b"PK\x03\x04"):
        # Un ZIP puede ser DOCX, XLSX o PPTX: solo se acepta con extensión
        # .docx declarada por el cliente.
        if Path(nombre).suffix.lower() == ".docx":
            return DOCX_MIME, ".docx"
    raise AnexoTipoInvalido(
        "Tipo de archivo no permitido. Usa PNG, JPEG, WEBP, PDF o DOCX."
    )


def _validar_archivo(nombre: str, contenido: bytes) -> tuple[str, str, str]:
    """Valida tamaño/firma y devuelve ``(nombre_original, content_type, ext)``."""
    if not contenido:
        raise AnexoError("El archivo está vacío.")
    if len(contenido) > MAX_BYTES:
        raise AnexoDemasiadoGrande(
            f"El archivo supera el máximo de {MAX_BYTES // (1024 * 1024)} MB."
        )
    nombre_original = Path(nombre or "anexo").name.strip() or "anexo"
    content_type, extension = _detectar_tipo(nombre_original, contenido)
    return nombre_original, content_type, extension


def _limpiar_texto(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _titulo(value: Any) -> str:
    """Título sin el prefijo ``ANEXO N`` que agrega el DOCX."""
    titulo = _limpiar_texto(value)
    for _ in range(3):
        limpio = _PREFIJO_TITULO_RE.sub("", titulo).strip()
        if limpio == titulo:
            break
        titulo = limpio
    if not titulo:
        raise AnexoError(
            "El título debe describir el soporte; el sistema agrega «ANEXO N»."
        )
    return titulo[:MAX_TITULO]


def _codigo(value: Any) -> str | None:
    """Normaliza el código manual a ``ANEXO N`` cuando representa un número."""
    codigo = _limpiar_texto(value)
    if not codigo:
        return None
    coincidencia = _CODIGO_NUMERICO_RE.match(codigo)
    if coincidencia:
        numero = int(coincidencia.group(1))
        if numero < 1:
            raise AnexoError("El código debe ser un número mayor o igual a 1.")
        return f"ANEXO {numero}"
    return codigo[:MAX_CODIGO]


def _numero_de_codigo(codigo: str | None) -> int | None:
    """Número reservado por un código manual numérico, si lo hay."""
    if not codigo:
        return None
    coincidencia = _CODIGO_NUMERICO_RE.match(codigo)
    return int(coincidencia.group(1)) if coincidencia else None


def _rotulo(numero: int, codigo: str | None) -> str:
    """Rótulo del DOCX: ``ANEXO {n}`` salvo códigos no numéricos propios."""
    if codigo and _numero_de_codigo(codigo) is None:
        return codigo
    return f"ANEXO {numero}"


def _asignar_numeros(registros: list[InformeGestionAnexo]) -> dict[int, int]:
    """Reserva los números manuales y reparte los libres en orden de listado.

    ``registros`` debe venir ordenado por ``(orden, id)``. Si todos los códigos
    están vacíos la asignación es 1..N; si hay un código ``ANEXO 3``, ese
    número queda reservado y los automáticos toman 1, 2, 4… evitando repetir.

    Los datos creados antes de validar la unicidad pueden traer dos filas con
    ``ANEXO 3``. La primera conserva el 3 y la segunda recibe el menor número
    libre, de modo que el DOCX nunca repite un rótulo.
    """
    reservados: set[int] = set()
    numeros: dict[int, int] = {}
    pendientes: list[InformeGestionAnexo] = []
    for registro in registros:
        manual = _numero_de_codigo(registro.codigo)
        if manual is not None and manual not in reservados:
            numeros[registro.id] = manual
            reservados.add(manual)
        else:
            pendientes.append(registro)
    siguiente = 1
    for registro in pendientes:
        while siguiente in reservados:
            siguiente += 1
        numeros[registro.id] = siguiente
        reservados.add(siguiente)
        siguiente += 1
    return numeros


def _validar_codigo_unico(
    session: Session,
    *,
    anio: int,
    trimestre: str,
    codigo: str | None,
    excluir_id: int | None = None,
) -> None:
    """Rechaza un código manual repetido dentro del mismo periodo."""
    if not codigo:
        return
    normalizado = codigo.strip().upper()
    registros = session.scalars(
        select(InformeGestionAnexo).where(
            InformeGestionAnexo.anio == anio,
            InformeGestionAnexo.trimestre == trimestre,
        )
    ).all()
    for registro in registros:
        if excluir_id is not None and registro.id == excluir_id:
            continue
        if (registro.codigo or "").strip().upper() == normalizado:
            raise AnexoError(
                f"El código «{codigo}» ya está usado en este periodo. "
                "Usa otro código o déjalo vacío para numeración automática."
            )


def _descripcion(value: Any) -> str | None:
    texto = str(value or "").replace("\r\n", "\n").strip()
    return texto[:MAX_DESCRIPCION] or None


def _siguiente_orden(session: Session, anio: int, trimestre: str) -> int:
    actual = session.scalar(
        select(func.max(InformeGestionAnexo.orden)).where(
            InformeGestionAnexo.anio == anio,
            InformeGestionAnexo.trimestre == trimestre,
        )
    )
    return int(actual or 0) + 1


def _registro(session: Session, anexo_id: int) -> InformeGestionAnexo:
    registro = session.get(InformeGestionAnexo, anexo_id)
    if registro is None:
        raise AnexoNoEncontrado("Anexo no encontrado.")
    return registro


def ruta_absoluta(registro: InformeGestionAnexo) -> Path:
    return storage_dir() / registro.ruta_archivo


def _serializar(
    registro: InformeGestionAnexo, numero: int | None = None
) -> dict[str, Any]:
    data = {
        "id": registro.id,
        "anio": registro.anio,
        "trimestre": registro.trimestre,
        "codigo": registro.codigo,
        "titulo": registro.titulo,
        "descripcion": registro.descripcion,
        "nombre_archivo": registro.nombre_archivo,
        "content_type": registro.content_type,
        "tamano": registro.tamano,
        "orden": registro.orden,
        "created_at": (
            registro.created_at.isoformat() if registro.created_at else None
        ),
        "updated_at": (
            registro.updated_at.isoformat() if registro.updated_at else None
        ),
        "download_url": f"/api/informes/anexos/{registro.id}/download",
    }
    if numero is not None:
        data["numero"] = numero
        data["rotulo"] = _rotulo(numero, registro.codigo)
    return data


def _registros_periodo(
    session: Session, anio: int, trimestre: str
) -> list[InformeGestionAnexo]:
    """Registros del periodo en el orden único de catálogo y DOCX."""
    return session.scalars(
        select(InformeGestionAnexo)
        .where(
            InformeGestionAnexo.anio == anio,
            InformeGestionAnexo.trimestre == trimestre,
        )
        .order_by(InformeGestionAnexo.orden, InformeGestionAnexo.id)
    ).all()


def _items_numerados(
    session: Session, anio: int, trimestre: str
) -> list[tuple[InformeGestionAnexo, int]]:
    registros = _registros_periodo(session, anio, trimestre)
    numeros = _asignar_numeros(registros)
    return [(registro, numeros[registro.id]) for registro in registros]


def _serializar_uno(
    session: Session, registro: InformeGestionAnexo
) -> dict[str, Any]:
    """Serializa un registro con el número que le corresponde en su periodo."""
    for candidato, numero in _items_numerados(
        session, registro.anio, registro.trimestre
    ):
        if candidato.id == registro.id:
            return _serializar(registro, numero)
    return _serializar(registro)


def crear_anexo(
    session: Session,
    *,
    anio: Any,
    trimestre: Any,
    titulo: Any,
    descripcion: Any = None,
    codigo: Any = None,
    orden: Any = None,
    nombre_archivo: str,
    contenido: bytes,
) -> dict[str, Any]:
    """Guarda el binario en disco y registra los metadatos del anexo."""
    anio_normalizado = normalizar_anio(anio)
    trimestre_normalizado = normalizar_trimestre(trimestre)
    titulo_normalizado = _titulo(titulo)
    codigo_normalizado = _codigo(codigo)
    _validar_codigo_unico(
        session,
        anio=anio_normalizado,
        trimestre=trimestre_normalizado,
        codigo=codigo_normalizado,
    )
    nombre_original, content_type, extension = _validar_archivo(
        nombre_archivo, contenido
    )

    orden_final = (
        int(orden)
        if orden not in (None, "")
        else _siguiente_orden(session, anio_normalizado, trimestre_normalizado)
    )

    directorio = storage_dir()
    directorio.mkdir(parents=True, exist_ok=True)
    nombre_disco = (
        f"{anio_normalizado}-{trimestre_normalizado}-{uuid4().hex}{extension}"
    )
    destino = directorio / nombre_disco
    destino.write_bytes(contenido)

    registro = InformeGestionAnexo(
        anio=anio_normalizado,
        trimestre=trimestre_normalizado,
        codigo=codigo_normalizado,
        titulo=titulo_normalizado,
        descripcion=_descripcion(descripcion),
        nombre_archivo=nombre_original,
        content_type=content_type,
        ruta_archivo=nombre_disco,
        tamano=len(contenido),
        orden=orden_final,
    )
    session.add(registro)
    try:
        session.commit()
    except Exception:
        session.rollback()
        destino.unlink(missing_ok=True)
        raise
    session.refresh(registro)
    return _serializar_uno(session, registro)


def listar_anexos(
    session: Session, *, anio: Any = None, trimestre: Any = None
) -> dict[str, Any]:
    """Catálogo del periodo en el orden único ``(orden, id)`` con su número."""
    anio_normalizado = normalizar_anio(anio)
    trimestre_normalizado = normalizar_trimestre(trimestre)
    items = _items_numerados(session, anio_normalizado, trimestre_normalizado)
    return {
        "anio": anio_normalizado,
        "trimestre": trimestre_normalizado,
        "total": len(items),
        "items": [
            _serializar(registro, numero) for registro, numero in items
        ],
    }


def obtener_anexo(session: Session, anexo_id: int) -> dict[str, Any]:
    return _serializar_uno(session, _registro(session, anexo_id))


def actualizar_anexo(
    session: Session,
    anexo_id: int,
    *,
    titulo: Any = None,
    descripcion: Any = None,
    codigo: Any = None,
    orden: Any = None,
    nombre_archivo: str | None = None,
    contenido: bytes | None = None,
) -> dict[str, Any]:
    """Actualiza metadatos y, si llega un archivo, reemplaza el binario.

    Los campos en ``None`` no se tocan. Para vaciar ``descripcion`` o
    ``codigo`` se envía una cadena vacía.
    """
    registro = _registro(session, anexo_id)

    codigo_normalizado = None
    if codigo is not None:
        codigo_normalizado = _codigo(codigo)
        _validar_codigo_unico(
            session,
            anio=registro.anio,
            trimestre=registro.trimestre,
            codigo=codigo_normalizado,
            excluir_id=registro.id,
        )

    if titulo is not None:
        registro.titulo = _titulo(titulo)
    if descripcion is not None:
        registro.descripcion = _descripcion(descripcion)
    if codigo is not None:
        registro.codigo = codigo_normalizado
    if orden not in (None, ""):
        registro.orden = int(orden)

    destino_nuevo: Path | None = None
    destino_anterior: Path | None = None
    if contenido is not None:
        nombre_original, content_type, extension = _validar_archivo(
            nombre_archivo or registro.nombre_archivo, contenido
        )
        directorio = storage_dir()
        directorio.mkdir(parents=True, exist_ok=True)
        nombre_disco = (
            f"{registro.anio}-{registro.trimestre}-{uuid4().hex}{extension}"
        )
        destino_nuevo = directorio / nombre_disco
        destino_nuevo.write_bytes(contenido)
        destino_anterior = ruta_absoluta(registro)
        registro.nombre_archivo = nombre_original
        registro.content_type = content_type
        registro.ruta_archivo = nombre_disco
        registro.tamano = len(contenido)

    registro.updated_at = datetime.now(timezone.utc)
    try:
        session.commit()
    except Exception:
        session.rollback()
        if destino_nuevo is not None:
            destino_nuevo.unlink(missing_ok=True)
        raise
    if destino_anterior is not None and destino_anterior != destino_nuevo:
        destino_anterior.unlink(missing_ok=True)
    session.refresh(registro)
    return _serializar_uno(session, registro)


def eliminar_anexo(session: Session, anexo_id: int) -> None:
    """Elimina el registro y su archivo en disco."""
    registro = _registro(session, anexo_id)
    ruta = ruta_absoluta(registro)
    session.delete(registro)
    session.commit()
    ruta.unlink(missing_ok=True)


def anexos_para_docx(
    session: Session, *, anio: Any = None, trimestre: Any = None
) -> list[dict[str, Any]]:
    """Lista que consume ``report_word`` (número, rótulo y ruta absoluta)."""
    anio_normalizado = normalizar_anio(anio)
    trimestre_normalizado = normalizar_trimestre(trimestre)
    return [
        {
            "numero": numero,
            "rotulo": _rotulo(numero, registro.codigo),
            "codigo": registro.codigo,
            "titulo": registro.titulo,
            "descripcion": registro.descripcion,
            "nombre_archivo": registro.nombre_archivo,
            "content_type": registro.content_type,
            "ruta": str(ruta_absoluta(registro)),
        }
        for registro, numero in _items_numerados(
            session, anio_normalizado, trimestre_normalizado
        )
    ]


__all__ = [
    "MAX_BYTES",
    "TIPOS_PERMITIDOS",
    "AnexoError",
    "AnexoNoEncontrado",
    "AnexoTipoInvalido",
    "AnexoDemasiadoGrande",
    "storage_dir",
    "crear_anexo",
    "listar_anexos",
    "obtener_anexo",
    "actualizar_anexo",
    "eliminar_anexo",
    "anexos_para_docx",
    "ruta_absoluta",
]

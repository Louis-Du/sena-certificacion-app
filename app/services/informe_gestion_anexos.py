"""Anexos del Informe de Gestión Administrativa (sección 5 del DOCX).

Los soportes se guardan por ``(año, trimestre)``, igual que las estrategias: el
modo de exportación (``solo_trimestre`` / ``acumulado``) solo afecta a las
cifras y nunca crea un juego distinto de anexos.

Un anexo agrupa **una o varias imágenes**. El binario se escribe en disco y las
filas de la base de datos solo conservan las referencias:

* Raíz por defecto: ``<proyecto>/data/informe_gestion_anexos`` (el mismo
  volumen ``app_data`` que usa SQLite en Docker).
* Se puede cambiar con la variable de entorno ``INFORME_ANEXOS_DIR`` (las
  pruebas la apuntan a ``tmp_path``).
* Cada archivo se renombra a ``{anio}-{trimestre}-{uuid}{ext}`` para evitar
  colisiones y nombres arbitrarios del cliente; ``nombre_archivo`` conserva el
  nombre original solo para mostrarlo/descargarlo.

Tipos permitidos: PNG, JPEG y WEBP, validados por firma binaria. Tamaño máximo:
10 MB por imagen.

Reglas de numeración y orden:

* El listado se ordena por ``orden`` ascendente y, a igual orden, por ``id``.
  El alta asigna automáticamente ``max(orden) + 1``.
* El frontend puede reordenar las tarjetas con drag-and-drop; el endpoint de
  reordenamiento reescribe ``orden`` como 1..N.
* El rótulo siempre es ``ANEXO {n}. {titulo}`` y ``n`` es la posición estable
  1..N del listado. No existe código manual.
* El título se guarda sin el prefijo ``ANEXO N``: el sistema lo agrega al
  exportar, de modo que nunca se produce ``ANEXO 1. ANEXO 1. …``.

Compatibilidad: las filas heredadas de la versión anterior (un solo archivo en
la tabla del anexo) se migran a la tabla hija. Si una fila antigua apunta a un
PDF/DOCX, se conserva en la base de datos pero queda fuera del catálogo y del
DOCX porque ya no es un soporte válido.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import InformeGestionAnexo, InformeGestionAnexoArchivo
from app.services.informe_gestion_estrategias import (
    normalizar_anio,
    normalizar_trimestre,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_STORAGE_DIR = BASE_DIR / "data" / "informe_gestion_anexos"

MAX_BYTES = 10 * 1024 * 1024  # 10 MB por imagen
MAX_TITULO = 255
MAX_DESCRIPCION = 4000

# Prefijo "ANEXO 3. " / "Anexo N° 3: " que el usuario no debe repetir en el
# título porque el rotulador del DOCX ya lo agrega.
_PREFIJO_TITULO_RE = re.compile(
    r"^\s*anexo\s*(?:n[°º.]?\s*)?\d{1,3}\s*[.):\-–—]*\s*",
    re.IGNORECASE,
)

TIPOS_PERMITIDOS: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}
_EXTENSIONES_IMAGEN = {".png", ".jpg", ".jpeg", ".webp"}


class AnexoError(ValueError):
    """Error de validación de un anexo (400 por defecto)."""

    status_code = 400


class AnexoNoEncontrado(AnexoError):
    status_code = 404


class AnexoTipoInvalido(AnexoError):
    status_code = 400


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
    """Devuelve ``(content_type, extensión)`` validando la firma de la imagen."""
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if contenido.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp", ".webp"
    raise AnexoTipoInvalido(
        "Solo se permiten imágenes PNG, JPEG o WEBP."
    )


def _validar_archivo(nombre: str, contenido: bytes) -> tuple[str, str, str]:
    """Valida tamaño/firma y devuelve ``(nombre_original, content_type, ext)``."""
    if not contenido:
        raise AnexoError("La imagen está vacía.")
    if len(contenido) > MAX_BYTES:
        raise AnexoDemasiadoGrande(
            f"La imagen supera el máximo de {MAX_BYTES // (1024 * 1024)} MB."
        )
    nombre_original = Path(nombre or "imagen").name.strip() or "imagen"
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
    registro = session.scalar(
        select(InformeGestionAnexo)
        .where(InformeGestionAnexo.id == anexo_id)
        .options(selectinload(InformeGestionAnexo.archivos))
    )
    if registro is None:
        raise AnexoNoEncontrado("Anexo no encontrado.")
    return registro


def ruta_absoluta(archivo: InformeGestionAnexoArchivo) -> Path:
    return storage_dir() / archivo.ruta_archivo


def _archivo_disponible(archivo: InformeGestionAnexoArchivo) -> bool:
    """Indica si el binario referenciado sigue presente en disco."""
    try:
        return ruta_absoluta(archivo).is_file()
    except OSError:
        return False


def _es_imagen_permitida(archivo: InformeGestionAnexoArchivo) -> bool:
    """Filtra filas heredadas PDF/DOCX y binarios que ya no son válidos."""
    if str(archivo.content_type or "").lower() in TIPOS_PERMITIDOS:
        return True
    return Path(archivo.nombre_archivo or "").suffix.lower() in _EXTENSIONES_IMAGEN


def _archivos_imagen(registro: InformeGestionAnexo) -> list[InformeGestionAnexoArchivo]:
    archivos = sorted(
        registro.archivos or [], key=lambda item: (item.orden, item.id or 0)
    )
    return [archivo for archivo in archivos if _es_imagen_permitida(archivo)]


def _borrar_archivo(ruta: Path | None) -> None:
    """Borra el binario sin tumbar la operación si está bloqueado.

    En Windows es habitual que el visor de imágenes/antivirus mantenga el
    archivo abierto justo después de una descarga. El registro de la BD ya se
    eliminó (o actualizó), así que un ``PermissionError`` al limpiar el archivo
    no debe convertir un DELETE correcto en un 500 para la UI.
    """
    if ruta is None:
        return
    try:
        ruta.unlink(missing_ok=True)
    except OSError as error:
        logger.warning("No se pudo borrar la imagen del anexo %s: %s", ruta, error)


def _guardar_binario(
    anio: int, trimestre: str, contenido: bytes, extension: str
) -> Path:
    directorio = storage_dir()
    directorio.mkdir(parents=True, exist_ok=True)
    nombre_disco = f"{anio}-{trimestre}-{uuid4().hex}{extension}"
    destino = directorio / nombre_disco
    destino.write_bytes(contenido)
    return destino


def _serializar_archivo(
    anexo_id: int, archivo: InformeGestionAnexoArchivo
) -> dict[str, Any]:
    download_url = (
        f"/api/informes/anexos/{anexo_id}/archivos/{archivo.id}/download"
    )
    return {
        "id": archivo.id,
        "nombre_archivo": archivo.nombre_archivo,
        "content_type": archivo.content_type,
        "tamano": archivo.tamano,
        "orden": archivo.orden,
        "archivo_disponible": _archivo_disponible(archivo),
        "download_url": download_url,
        "preview_url": download_url,
    }


def _serializar(
    registro: InformeGestionAnexo, numero: int | None = None
) -> dict[str, Any]:
    archivos = [
        _serializar_archivo(registro.id, archivo)
        for archivo in _archivos_imagen(registro)
    ]
    data = {
        "id": registro.id,
        "anio": registro.anio,
        "trimestre": registro.trimestre,
        "titulo": registro.titulo,
        "descripcion": registro.descripcion,
        "orden": registro.orden,
        "total_archivos": len(archivos),
        "archivo_disponible": bool(archivos)
        and all(archivo["archivo_disponible"] for archivo in archivos),
        "archivos": archivos,
        "download_url": archivos[0]["download_url"] if archivos else None,
        "preview_url": archivos[0]["preview_url"] if archivos else None,
        "created_at": (
            registro.created_at.isoformat() if registro.created_at else None
        ),
        "updated_at": (
            registro.updated_at.isoformat() if registro.updated_at else None
        ),
    }
    if numero is not None:
        data["numero"] = numero
        data["rotulo"] = f"ANEXO {numero}"
    return data


def _registros_periodo(
    session: Session, anio: int, trimestre: str
) -> list[InformeGestionAnexo]:
    """Anexos válidos del periodo en el orden único de catálogo y DOCX."""
    registros = session.scalars(
        select(InformeGestionAnexo)
        .where(
            InformeGestionAnexo.anio == anio,
            InformeGestionAnexo.trimestre == trimestre,
        )
        .options(selectinload(InformeGestionAnexo.archivos))
        .order_by(InformeGestionAnexo.orden, InformeGestionAnexo.id)
    ).all()
    # Sin imágenes válidas no hay anexo que mostrar/exportar. Esto deja fuera
    # automáticamente filas heredadas de PDF/DOCX.
    return [registro for registro in registros if _archivos_imagen(registro)]


def _items_numerados(
    session: Session, anio: int, trimestre: str
) -> list[tuple[InformeGestionAnexo, int]]:
    registros = _registros_periodo(session, anio, trimestre)
    return [
        (registro, posicion)
        for posicion, registro in enumerate(registros, start=1)
    ]


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
    archivos: list[tuple[str, bytes]] | None = None,
) -> dict[str, Any]:
    """Crea un anexo con una o varias imágenes."""
    anio_normalizado = normalizar_anio(anio)
    trimestre_normalizado = normalizar_trimestre(trimestre)
    titulo_normalizado = _titulo(titulo)
    descripcion_normalizada = _descripcion(descripcion)
    if not archivos:
        raise AnexoError("Selecciona al menos una imagen para el anexo.")

    # Validar todas antes de escribir: si una es inválida no queda basura.
    validados = [
        (*_validar_archivo(nombre, contenido), contenido)
        for nombre, contenido in archivos
    ]
    orden_final = _siguiente_orden(
        session, anio_normalizado, trimestre_normalizado
    )
    registro = InformeGestionAnexo(
        anio=anio_normalizado,
        trimestre=trimestre_normalizado,
        titulo=titulo_normalizado,
        descripcion=descripcion_normalizada,
        orden=orden_final,
    )
    session.add(registro)
    destinos: list[Path] = []
    try:
        session.flush()
        for posicion, (nombre, content_type, extension, contenido) in enumerate(
            validados
        ):
            destino = _guardar_binario(
                anio_normalizado,
                trimestre_normalizado,
                contenido,
                extension,
            )
            destinos.append(destino)
            registro.archivos.append(
                InformeGestionAnexoArchivo(
                    nombre_archivo=nombre,
                    content_type=content_type,
                    ruta_archivo=destino.name,
                    tamano=len(contenido),
                    orden=posicion,
                )
            )
        session.commit()
    except Exception:
        session.rollback()
        for destino in destinos:
            _borrar_archivo(destino)
        raise
    return _serializar_uno(session, _registro(session, registro.id))


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
) -> dict[str, Any]:
    """Actualiza solo los metadatos; las imágenes se gestionan aparte."""
    registro = _registro(session, anexo_id)
    if titulo is not None:
        registro.titulo = _titulo(titulo)
    if descripcion is not None:
        registro.descripcion = _descripcion(descripcion)
    registro.updated_at = datetime.now(timezone.utc)
    session.commit()
    return _serializar_uno(session, _registro(session, anexo_id))


def agregar_archivos(
    session: Session,
    anexo_id: int,
    archivos: list[tuple[str, bytes]] | None,
) -> dict[str, Any]:
    """Añade una o varias imágenes a un anexo existente."""
    registro = _registro(session, anexo_id)
    if not archivos:
        raise AnexoError("Selecciona al menos una imagen para añadir.")
    validados = [
        (*_validar_archivo(nombre, contenido), contenido)
        for nombre, contenido in archivos
    ]
    existentes = _archivos_imagen(registro)
    siguiente = max((archivo.orden for archivo in existentes), default=-1) + 1
    destinos: list[Path] = []
    try:
        for posicion, (nombre, content_type, extension, contenido) in enumerate(
            validados, start=siguiente
        ):
            destino = _guardar_binario(
                registro.anio,
                registro.trimestre,
                contenido,
                extension,
            )
            destinos.append(destino)
            registro.archivos.append(
                InformeGestionAnexoArchivo(
                    nombre_archivo=nombre,
                    content_type=content_type,
                    ruta_archivo=destino.name,
                    tamano=len(contenido),
                    orden=posicion,
                )
            )
        registro.updated_at = datetime.now(timezone.utc)
        session.commit()
    except Exception:
        session.rollback()
        for destino in destinos:
            _borrar_archivo(destino)
        raise
    return _serializar_uno(session, _registro(session, anexo_id))


def eliminar_archivo(
    session: Session, anexo_id: int, archivo_id: int
) -> dict[str, Any]:
    """Elimina una imagen dejando al menos una en el anexo."""
    registro = _registro(session, anexo_id)
    archivos = _archivos_imagen(registro)
    archivo = next((item for item in archivos if item.id == archivo_id), None)
    if archivo is None:
        raise AnexoNoEncontrado("Imagen del anexo no encontrada.")
    if len(archivos) <= 1:
        raise AnexoError(
            "No se puede eliminar la última imagen. Elimina el anexo completo "
            "o añade otra imagen antes."
        )
    ruta = ruta_absoluta(archivo)
    registro.archivos.remove(archivo)
    for posicion, restante in enumerate(_archivos_imagen(registro)):
        restante.orden = posicion
    registro.updated_at = datetime.now(timezone.utc)
    session.commit()
    _borrar_archivo(ruta)
    return _serializar_uno(session, _registro(session, anexo_id))


def eliminar_anexo(session: Session, anexo_id: int) -> None:
    """Elimina el anexo y todas sus imágenes; la limpieza es best-effort."""
    registro = _registro(session, anexo_id)
    rutas = [ruta_absoluta(archivo) for archivo in registro.archivos]
    session.delete(registro)
    session.commit()
    for ruta in rutas:
        _borrar_archivo(ruta)


def reordenar_anexos(
    session: Session,
    *,
    anio: Any,
    trimestre: Any,
    anexo_ids: list[int] | None,
) -> dict[str, Any]:
    """Reescribe ``orden`` 1..N según la lista ordenada del drag-and-drop."""
    anio_normalizado = normalizar_anio(anio)
    trimestre_normalizado = normalizar_trimestre(trimestre)
    if not anexo_ids:
        raise AnexoError("La lista de anexos para reordenar está vacía.")
    ids = [int(valor) for valor in anexo_ids]
    if len(ids) != len(set(ids)):
        raise AnexoError("La lista de anexos contiene identificadores repetidos.")
    registros = _registros_periodo(
        session, anio_normalizado, trimestre_normalizado
    )
    por_id = {registro.id: registro for registro in registros}
    if set(ids) != set(por_id):
        raise AnexoError(
            "La lista de anexos debe incluir exactamente los anexos del periodo."
        )
    for posicion, anexo_id in enumerate(ids, start=1):
        por_id[anexo_id].orden = posicion
    session.commit()
    return listar_anexos(
        session, anio=anio_normalizado, trimestre=trimestre_normalizado
    )


def anexos_para_docx(
    session: Session, *, anio: Any = None, trimestre: Any = None
) -> list[dict[str, Any]]:
    """Lista que consume ``report_word`` (número, rótulo y rutas de imágenes)."""
    anio_normalizado = normalizar_anio(anio)
    trimestre_normalizado = normalizar_trimestre(trimestre)
    resultado: list[dict[str, Any]] = []
    for registro, numero in _items_numerados(
        session, anio_normalizado, trimestre_normalizado
    ):
        resultado.append(
            {
                "numero": numero,
                "rotulo": f"ANEXO {numero}",
                "titulo": registro.titulo,
                "descripcion": registro.descripcion,
                "archivos": [
                    {
                        "nombre_archivo": archivo.nombre_archivo,
                        "content_type": archivo.content_type,
                        "ruta": str(ruta_absoluta(archivo)),
                    }
                    for archivo in _archivos_imagen(registro)
                ],
            }
        )
    return resultado


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
    "agregar_archivos",
    "eliminar_archivo",
    "eliminar_anexo",
    "reordenar_anexos",
    "anexos_para_docx",
    "ruta_absoluta",
]

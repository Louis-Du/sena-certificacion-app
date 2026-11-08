from __future__ import annotations

import asyncio
import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import SheetSyncConfig
from app.services.imports import confirm_import, get_staged, import_preview, stage_file


_sync_lock = threading.Lock()


def extract_sheet_id(url: str | None) -> str | None:
    if not url:
        return None
    text = str(url).strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", text)
    if match:
        return match.group(1)
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", text)
    if match:
        return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", text):
        return text
    return None


def build_export_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"


def download_sheet(sheet_id: str) -> bytes:
    url = build_export_url(sheet_id)
    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
    except httpx.HTTPError as error:
        raise RuntimeError(f"No fue posible descargar la hoja: {error}") from error

    if response.status_code in (401, 403):
        raise PermissionError(
            "La hoja no es pública o no tiene permisos de lectura. "
            "Compártela como 'Cualquier persona con el enlace' → Lector."
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"Error al descargar la hoja (HTTP {response.status_code})."
        )

    content = response.content or b""
    lowered = content[:500].lower()
    if b"<html" in lowered or b"<!doctype html" in lowered:
        text = content.decode("utf-8", errors="ignore").lower()
        if (
            "sign in" in text
            or "accounts.google" in text
            or "login" in text
            or "permiso" in text
        ):
            raise PermissionError(
                "La hoja no es pública o no tiene permisos de lectura. "
                "Compártela como 'Cualquier persona con el enlace' → Lector."
            )
        raise RuntimeError(
            "Google devolvió una página HTML en lugar del archivo Excel. "
            "Verifique la URL y los permisos de compartición."
        )
    if not content:
        raise RuntimeError("El archivo descargado está vacío.")
    return content


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime,)):
        return _iso(value)
    return str(value)


def _fingerprint_conflicts(conflicts: list[dict[str, Any]]) -> str | None:
    """Huella estable del conjunto de documentos en conflicto.

    Se ordena y deduplica por documento para que el mismo conjunto produzca
    siempre el mismo valor aunque cambie el orden de las filas de la hoja.
    """
    documents = sorted(
        {
            str(item.get("identification") or "").strip()
            for item in conflicts
            if str(item.get("identification") or "").strip()
        }
    )
    if not documents:
        return None
    payload = "\n".join(documents).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _pending_conflicts(config: SheetSyncConfig) -> list[dict[str, Any]]:
    try:
        value = json.loads(config.pending_conflicts_json or "[]")
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _pending_preview(config: SheetSyncConfig) -> dict[str, Any] | None:
    try:
        value = json.loads(config.pending_preview_json or "null")
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _clear_pending_state(config: SheetSyncConfig) -> None:
    """Limpia el lote pendiente sin tocar el historial de importaciones."""
    config.pending_validation_id = None
    config.pending_conflict_count = 0
    config.pending_conflict_fingerprint = None
    config.pending_hash = None
    config.pending_file_name = None
    config.pending_content = None
    config.pending_conflicts_json = None
    config.pending_preview_json = None
    config.notified_at = None


def _store_pending_state(
    config: SheetSyncConfig,
    *,
    staged: Any,
    sheet_hash: str,
    file_name: str,
    conflicts: list[dict[str, Any]],
    preview: dict[str, Any] | None,
) -> None:
    fingerprint = _fingerprint_conflicts(conflicts)
    previous_fingerprint = config.pending_conflict_fingerprint
    previous_notified_at = config.notified_at

    config.last_status = "conflict_pending"
    config.pending_validation_id = staged.validation_id
    config.pending_conflict_count = len(conflicts)
    config.pending_conflict_fingerprint = fingerprint
    config.pending_hash = sheet_hash
    config.pending_file_name = file_name
    config.pending_content = staged.content
    config.pending_conflicts_json = json.dumps(
        conflicts, ensure_ascii=False, default=_json_default
    )
    config.pending_preview_json = (
        json.dumps(preview, ensure_ascii=False, default=_json_default)
        if preview is not None
        else None
    )
    # Solo se vuelve a notificar cuando cambia el conjunto de documentos. Si el
    # contenido cambia pero los conflictos son los mismos, se conserva la marca
    # para no repetir el toast.
    config.notified_at = (
        previous_notified_at if previous_fingerprint == fingerprint else None
    )


def _restore_staged(config: SheetSyncConfig) -> Any | None:
    """Recupera el lote de conflicto desde memoria o desde SQLite."""
    validation_id = config.pending_validation_id
    if not validation_id:
        return None
    staged = get_staged(validation_id)
    if staged is not None:
        return staged
    if not config.pending_content:
        return None
    try:
        return stage_file(
            config.pending_file_name or f"GoogleSheets_{validation_id}.xlsx",
            bytes(config.pending_content),
            config.information_type,
            validation_id=validation_id,
        )
    except Exception:
        return None


def get_config(session: Session) -> SheetSyncConfig | None:
    return session.get(SheetSyncConfig, 1)


def config_to_status(config: SheetSyncConfig | None, running: bool = True) -> dict[str, Any]:
    if config is None:
        return {
            "configured": False,
            "enabled": False,
            "running": running,
            "url": None,
            "information_type": None,
            "interval_seconds": None,
            "last_hash": None,
            "last_check_at": None,
            "last_import_at": None,
            "last_status": None,
            "last_message": None,
            "conflict_pending": False,
            "pending_conflict_count": 0,
            "pending_validation_id": None,
            "pending_conflict_fingerprint": None,
            "pending_conflict_summary": None,
            "notified_at": None,
            "notification_pending": False,
        }
    conflict_pending = config.last_status == "conflict_pending"
    pending_count = int(config.pending_conflict_count or 0) if conflict_pending else 0
    return {
        "configured": True,
        "enabled": bool(config.enabled),
        "running": running,
        "url": config.url,
        "information_type": config.information_type,
        "interval_seconds": config.interval_seconds,
        "last_hash": config.last_hash,
        "last_check_at": _iso(config.last_check_at),
        "last_import_at": _iso(config.last_import_at),
        "last_status": config.last_status,
        "last_message": config.last_message,
        "conflict_pending": conflict_pending,
        "pending_conflict_count": pending_count,
        "pending_validation_id": (
            config.pending_validation_id if conflict_pending else None
        ),
        "pending_conflict_fingerprint": (
            config.pending_conflict_fingerprint if conflict_pending else None
        ),
        "pending_conflict_summary": (
            {
                "count": pending_count,
                "file_name": config.pending_file_name,
                "fingerprint": config.pending_conflict_fingerprint,
                "detected_at": _iso(config.last_check_at),
                "notified_at": _iso(config.notified_at),
            }
            if conflict_pending
            else None
        ),
        "notified_at": _iso(config.notified_at) if conflict_pending else None,
        "notification_pending": bool(
            conflict_pending
            and config.pending_conflict_fingerprint
            and config.notified_at is None
        ),
    }


def save_config(
    session: Session,
    url: str,
    information_type: str | None = None,
    interval_seconds: int = 60,
    enabled: bool = True,
) -> SheetSyncConfig:
    sheet_id = extract_sheet_id(url)
    if not sheet_id:
        raise ValueError("URL de Google Sheets no válida.")

    try:
        interval = int(interval_seconds)
    except (TypeError, ValueError) as error:
        raise ValueError("El intervalo debe ser un número entero.") from error
    if interval < 15:
        raise ValueError("El intervalo mínimo es de 15 segundos.")

    if not information_type:
        information_type = "actas_completo"

    config = session.get(SheetSyncConfig, 1)
    url_changed = config is None or config.url != url

    if config is None:
        config = SheetSyncConfig(
            id=1,
            url=url,
            information_type=information_type,
            enabled=1 if enabled else 0,
            interval_seconds=interval,
        )
        session.add(config)
    else:
        config.url = url
        config.information_type = information_type
        config.interval_seconds = interval
        config.enabled = 1 if enabled else 0

    if url_changed:
        config.last_hash = None
        config.last_check_at = None
        config.last_import_at = None
        config.last_status = "idle"
        config.last_message = "Configuración guardada. Pendiente de sincronización."
        _clear_pending_state(config)

    session.commit()
    session.refresh(config)
    return config


def update_enabled(session: Session, enabled: bool) -> SheetSyncConfig | None:
    config = session.get(SheetSyncConfig, 1)
    if config is None:
        return None
    config.enabled = 1 if enabled else 0
    session.commit()
    session.refresh(config)
    return config


def delete_config(session: Session) -> None:
    config = session.get(SheetSyncConfig, 1)
    if config is not None:
        session.delete(config)
        session.commit()


def _run_sync_impl(session: Session) -> SheetSyncConfig:
    config = session.get(SheetSyncConfig, 1)
    if config is None:
        raise ValueError("No hay configuración de sincronización.")

    sheet_id = extract_sheet_id(config.url)
    config.last_check_at = _now()

    if not sheet_id:
        config.last_status = "error"
        config.last_message = "URL de Google Sheets no válida."
        session.commit()
        return config

    try:
        content = download_sheet(sheet_id)
    except Exception as error:  # noqa: BLE001
        config.last_status = "error"
        config.last_message = str(error)
        session.commit()
        return config

    new_hash = hashlib.sha256(content).hexdigest()

    # Un lote en conflicto se conserva hasta que el usuario decida. Si la hoja
    # no cambió desde ese lote, no se vuelve a validar ni a notificar.
    if config.last_status == "conflict_pending" and config.pending_hash == new_hash:
        config.last_message = (
            f"Hay {config.pending_conflict_count} conflicto(s) entre CERTIFICADOS "
            "y PENDIENTES pendientes de resolución. El lote no se reimportará solo."
        )
        session.commit()
        return config

    if config.last_hash is not None and config.last_hash == new_hash:
        # La hoja volvió al contenido ya importado: el lote en conflicto dejó
        # de existir y no debe seguir mostrándose como pendiente.
        _clear_pending_state(config)
        config.last_status = "unchanged"
        config.last_message = "Sin cambios en la hoja desde la última revisión."
        session.commit()
        return config

    file_name = f"GoogleSheets_{sheet_id}.xlsx"
    try:
        staged = stage_file(file_name, content, config.information_type)
    except Exception as error:  # noqa: BLE001
        config.last_status = "error"
        config.last_message = f"Error de validación: {error}"
        session.commit()
        return config

    result = staged.result
    if getattr(result, "status", None) == "error":
        config.last_status = "error"
        config.last_message = getattr(result, "message", None) or "El archivo no pasó la validación."
        session.commit()
        return config

    conflicts = getattr(result, "coherence_conflicts", None) or []
    if conflicts:
        # La sincronización automática no decide por el usuario: si hay
        # aprendices en CERTIFICADOS y PENDIENTES a la vez, se deja el lote
        # pendiente, se conserva el hash anterior y se solicita la
        # notificación nativa (una sola vez por conjunto de documentos).
        preview: dict[str, Any] | None = None
        try:
            preview = import_preview(staged, session)
        except Exception:
            preview = None
        _store_pending_state(
            config,
            staged=staged,
            sheet_hash=new_hash,
            file_name=file_name,
            conflicts=conflicts,
            preview=preview,
        )
        config.last_message = (
            f"Se detectaron {len(conflicts)} conflicto(s) entre CERTIFICADOS y "
            "PENDIENTES. Abra 'Resolver ahora' para elegir el estado final de cada "
            "aprendiz; el lote no se importará automáticamente."
        )
        session.commit()
        return config

    # Sin conflictos: se importa automáticamente y se limpia cualquier lote
    # pendiente anterior. La configuración se actualiza en la misma transacción
    # que la importación (confirm_import hace commit).
    config.last_hash = new_hash
    config.last_import_at = _now()
    config.last_status = "imported"
    config.last_message = "Importación completada."
    _clear_pending_state(config)
    try:
        import_result = confirm_import(
            staged.validation_id,
            session,
            conflict_resolutions=None,
            accept_missing_complementaria=True,
        )
    except Exception as error:  # noqa: BLE001
        session.rollback()
        config = session.get(SheetSyncConfig, 1)
        if config is not None:
            config.last_status = "error"
            config.last_message = f"Error al importar: {error}"
            session.commit()
            return config
        raise
    config.last_message = import_result.get("message") or "Importación completada."
    session.commit()
    return config


async def run_background_worker() -> None:
    while True:
        wait = 15
        try:
            def _cycle() -> int | None:
                with SessionLocal() as session:
                    config = get_config(session)
                    if config is None or not config.enabled:
                        return None
                    run_sync(session)
                    # Re-read interval after sync in case it changed.
                    refreshed = get_config(session)
                    return refreshed.interval_seconds if refreshed is not None else None

            interval = await asyncio.to_thread(_cycle)
            if interval is not None:
                try:
                    wait = max(15, int(interval))
                except (TypeError, ValueError):
                    wait = 15
            else:
                wait = 15
        except asyncio.CancelledError:
            raise
        except Exception:
            wait = 15
        try:
            await asyncio.sleep(wait)
        except asyncio.CancelledError:
            raise

def run_sync(session: Session) -> SheetSyncConfig:
    with _sync_lock:
        return _run_sync_impl(session)


def prepare_sync(
    session: Session,
    url: str | None = None,
    information_type: str | None = None,
    interval_seconds: int | None = None,
) -> dict[str, Any]:
    """Descarga y valida la hoja sin importar; deja el lote listo para revisar."""
    if url:
        config = save_config(
            session,
            url,
            information_type or "actas_completo",
            interval_seconds or 60,
            True,
        )
    else:
        config = get_config(session)
        if config is None:
            raise ValueError("No hay configuración de sincronización.")

    sheet_id = extract_sheet_id(config.url)
    config.last_check_at = _now()
    if not sheet_id:
        config.last_status = "error"
        config.last_message = "URL de Google Sheets no válida."
        session.commit()
        return {
            "status": "error",
            "message": config.last_message,
            "config": config_to_status(config),
        }

    with _sync_lock:
        try:
            content = download_sheet(sheet_id)
        except Exception as error:  # noqa: BLE001
            config.last_status = "error"
            config.last_message = str(error)
            session.commit()
            return {
                "status": "error",
                "message": config.last_message,
                "config": config_to_status(config),
            }

        new_hash = hashlib.sha256(content).hexdigest()
        if config.last_hash is not None and config.last_hash == new_hash:
            _clear_pending_state(config)
            config.last_status = "unchanged"
            config.last_message = "Sin cambios en la hoja desde la última revisión."
            session.commit()
            return {
                "status": "unchanged",
                "message": config.last_message,
                "config": config_to_status(config),
            }

        # Si se pulsa "Sincronizar" con el mismo lote que quedó en conflicto,
        # se reutiliza el staged guardado y se mantiene el estado pendiente
        # hasta que el usuario confirme la resolución.
        if config.last_status == "conflict_pending" and config.pending_hash == new_hash:
            pending_staged = _restore_staged(config)
            if pending_staged is not None:
                preview = _pending_preview(config)
                if preview is None:
                    try:
                        preview = import_preview(pending_staged, session)
                    except Exception:
                        preview = None
                config.last_message = (
                    f"Hay {config.pending_conflict_count} conflicto(s) entre "
                    "CERTIFICADOS y PENDIENTES pendientes de resolución."
                )
                session.commit()
                return {
                    "status": "ready",
                    "validation_id": pending_staged.validation_id,
                    "preview": preview,
                    "message": config.last_message,
                    "config": config_to_status(config),
                }

        file_name = f"GoogleSheets_{sheet_id}.xlsx"
        staged = stage_file(file_name, content, config.information_type)
        result = staged.result
        if getattr(result, "status", None) == "error":
            config.last_status = "error"
            config.last_message = (
                getattr(result, "message", None) or "El archivo no pasó la validación."
            )
            session.commit()
            return {
                "status": "error",
                "message": config.last_message,
                "config": config_to_status(config),
            }

        try:
            preview = import_preview(staged, session)
        except Exception as error:  # noqa: BLE001
            config.last_status = "error"
            config.last_message = f"No fue posible preparar la importación: {error}"
            session.commit()
            return {
                "status": "error",
                "message": config.last_message,
                "config": config_to_status(config),
            }

        if config.last_status != "conflict_pending":
            config.last_status = "idle"
        config.last_message = "Cambios detectados. Revise la información y confirme la importación."
        session.commit()
        return {
            "status": "ready",
            "validation_id": staged.validation_id,
            "preview": preview,
            "message": config.last_message,
            "config": config_to_status(config),
        }


def confirm_sync(
    session: Session,
    validation_id: str,
    conflict_resolutions: list[dict[str, Any]] | None = None,
    accept_missing_complementaria: bool = False,
) -> dict[str, Any]:
    """Confirma el lote preparado y actualiza el hash/estado de la sincronización."""
    config = get_config(session)
    if config is None:
        raise ValueError("No hay configuración de sincronización.")

    staged = get_staged(validation_id)
    if staged is None and config.pending_validation_id == validation_id:
        staged = _restore_staged(config)
    if staged is None:
        raise KeyError("La validación ya no está disponible. Sincronice nuevamente.")

    new_hash = hashlib.sha256(staged.content).hexdigest()
    if config.last_hash is not None and config.last_hash == new_hash:
        raise ValueError(
            "La hoja ya fue importada en la última revisión. Sincronice nuevamente "
            "si el documento cambió."
        )
    with _sync_lock:
        try:
            # Cualquier importación confirmada supera el lote en conflicto: el
            # estado pendiente se limpia en la misma transacción.
            _clear_pending_state(config)
            result = confirm_import(
                validation_id,
                session,
                conflict_resolutions,
                accept_missing_complementaria=accept_missing_complementaria,
            )
        except Exception:
            session.rollback()
            raise

        config.last_hash = new_hash
        config.last_import_at = _now()
        config.last_status = "imported"
        config.last_message = result.get("message") or "Importación completada."
        session.commit()
    return {
        "status": "imported",
        "result": result,
        "config": config_to_status(config),
    }


def pending_conflicts_payload(session: Session) -> dict[str, Any]:
    """Devuelve el lote en conflicto listo para la UI de resolución.

    Es seguro llamarlo mientras no haya un conflicto pendiente: responde
    ``status="none"`` para que el polling del banner no genere errores.
    """
    config = get_config(session)
    if config is None or config.last_status != "conflict_pending":
        return {
            "status": "none",
            "conflict_pending": False,
            "conflicts": [],
            "coherence_conflicts": [],
            "preview": None,
            "pending_conflict_count": 0,
            "notified_at": None,
            "notification_pending": False,
            "config": config_to_status(config),
        }

    conflicts = _pending_conflicts(config)
    preview = _pending_preview(config)
    staged = _restore_staged(config)
    if staged is not None:
        try:
            live_preview = import_preview(staged, session)
            live_conflicts = live_preview.get("coherence_conflicts") or conflicts
            preview = live_preview
            conflicts = live_conflicts
        except Exception:
            # Se conserva el resumen persistido para que la UI siga mostrando
            # el lote aunque una validación puntual falle.
            pass

    payload = {
        "status": "conflict_pending",
        "conflict_pending": True,
        "validation_id": config.pending_validation_id,
        "pending_validation_id": config.pending_validation_id,
        "pending_conflict_count": len(conflicts)
        or int(config.pending_conflict_count or 0),
        "fingerprint": config.pending_conflict_fingerprint,
        "pending_conflict_fingerprint": config.pending_conflict_fingerprint,
        "conflicts": conflicts,
        "coherence_conflicts": conflicts,
        "preview": preview,
        "staged_available": staged is not None,
        "notified_at": _iso(config.notified_at),
        "notification_pending": bool(
            config.pending_conflict_fingerprint and config.notified_at is None
        ),
        "config": config_to_status(config),
    }
    return payload


def mark_notified(session: Session, fingerprint: str | None = None) -> dict[str, Any]:
    """Marca que el toast del SO ya se mostró para esta huella de conflictos."""
    config = get_config(session)
    if config is None or config.last_status != "conflict_pending":
        return {"status": "noop", "config": config_to_status(config)}

    if (
        fingerprint
        and config.pending_conflict_fingerprint
        and fingerprint != config.pending_conflict_fingerprint
    ):
        return {
            "status": "stale",
            "message": "El conjunto de conflictos cambió; se notificará de nuevo.",
            "config": config_to_status(config),
        }

    if config.notified_at is None:
        config.notified_at = _now()
        session.commit()
    return {"status": "notified", "config": config_to_status(config)}


def resolve_pending(
    session: Session,
    conflict_resolutions: list[dict[str, Any]] | None = None,
    accept_missing_complementaria: bool = False,
) -> dict[str, Any]:
    """Resuelve el lote pendiente y completa su importación."""
    config = get_config(session)
    if config is None or config.last_status != "conflict_pending":
        raise ValueError("No hay un lote pendiente de conflictos.")
    if not config.pending_validation_id:
        raise ValueError("El lote pendiente no tiene una validación asociada.")

    staged = _restore_staged(config)
    if staged is None:
        raise KeyError(
            "El lote pendiente ya no está disponible. Sincronice la hoja nuevamente."
        )

    validation_id = staged.validation_id
    new_hash = config.pending_hash or hashlib.sha256(staged.content).hexdigest()
    with _sync_lock:
        try:
            config.last_hash = new_hash
            config.last_import_at = _now()
            config.last_status = "imported"
            config.last_message = "Importación completada."
            _clear_pending_state(config)
            result = confirm_import(
                validation_id,
                session,
                conflict_resolutions,
                accept_missing_complementaria=accept_missing_complementaria,
            )
        except Exception:
            session.rollback()
            raise

        config.last_message = result.get("message") or "Importación completada."
        session.commit()
    return {
        "status": "imported",
        "result": result,
        "config": config_to_status(config),
    }

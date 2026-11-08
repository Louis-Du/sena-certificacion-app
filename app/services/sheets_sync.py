from __future__ import annotations

import asyncio
import hashlib
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
        }
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

    if config.last_hash is not None and config.last_hash == new_hash:
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
        # pendiente para que se resuelva desde el flujo manual.
        config.last_status = "idle"
        config.last_message = (
            f"Se detectaron {len(conflicts)} conflicto(s) entre CERTIFICADOS y "
            "PENDIENTES. Use 'Sincronizar' para revisarlos y elegir el estado final."
        )
        session.commit()
        return config

    try:
        import_result = confirm_import(
            staged.validation_id,
            session,
            conflict_resolutions=None,
            accept_missing_complementaria=True,
        )
    except Exception as error:  # noqa: BLE001
        config.last_status = "error"
        config.last_message = f"Error al importar: {error}"
        session.commit()
        return config

    config.last_hash = new_hash
    config.last_import_at = _now()
    config.last_status = "imported"
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
            config.last_status = "unchanged"
            config.last_message = "Sin cambios en la hoja desde la última revisión."
            session.commit()
            return {
                "status": "unchanged",
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
    staged = get_staged(validation_id)
    if staged is None:
        raise KeyError("La validación ya no está disponible. Sincronice nuevamente.")
    config = get_config(session)
    if config is None:
        raise ValueError("No hay configuración de sincronización.")

    new_hash = hashlib.sha256(staged.content).hexdigest()
    if config.last_hash is not None and config.last_hash == new_hash:
        raise ValueError(
            "La hoja ya fue importada en la última revisión. Sincronice nuevamente "
            "si el documento cambió."
        )
    with _sync_lock:
        try:
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

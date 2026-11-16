"""Comprobación y aplicación de actualizaciones desde GitHub Releases.

El workflow de release publica ``version.json`` junto al instalador. La app
consulta ese manifiesto con la URL estable
``releases/latest/download/version.json``, que no requiere autenticación ni
consume la cuota de la API de GitHub. Si el manifiesto no está disponible se
usa ``GET /repos/{owner}/{repo}/releases/latest`` como respaldo.

El resultado se cachea en memoria durante ``CACHE_TTL_SECONDS`` para que la
interfaz pueda consultar al arrancar y al recuperar el foco sin golpear la red
en cada ciclo. La descarga del instalador se verifica con el SHA-256 publicado.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.runtime import data_dir, is_frozen
from app.version import APP_VERSION

DEFAULT_REPOSITORY = "Louis-Du/sena-certificacion-app"
CACHE_TTL_SECONDS = 30 * 60
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = f"SENACertificacion/{APP_VERSION}"

_lock = threading.Lock()
_cache: dict[str, Any] | None = None
_cache_at = 0.0


class UpdateError(RuntimeError):
    """Error controlado del flujo de actualización."""


def repository() -> str:
    value = os.getenv("SENA_UPDATE_REPOSITORY", DEFAULT_REPOSITORY)
    return (value or DEFAULT_REPOSITORY).strip() or DEFAULT_REPOSITORY


def manifest_url() -> str:
    override = os.getenv("SENA_UPDATE_MANIFEST_URL", "").strip()
    if override:
        return override
    return (
        f"https://github.com/{repository()}/releases/latest/download/version.json"
    )


def api_url() -> str:
    return f"https://api.github.com/repos/{repository()}/releases/latest"


def parse_version(value: str) -> tuple[int, ...]:
    """Convierte ``v1.2.3`` (o ``1.2``) en una tupla comparable."""
    match = re.search(r"(\d+(?:\.\d+)*)", str(value or ""))
    if not match:
        return ()
    parts = [int(part) for part in match.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def is_newer(candidate: str, current: str = APP_VERSION) -> bool:
    """Indica si ``candidate`` es una versión posterior a ``current``."""
    candidate_parts = parse_version(candidate)
    current_parts = parse_version(current)
    if not candidate_parts:
        return False
    if not current_parts:
        return True
    size = max(len(candidate_parts), len(current_parts))
    padded_candidate = candidate_parts + (0,) * (size - len(candidate_parts))
    padded_current = current_parts + (0,) * (size - len(current_parts))
    return padded_candidate > padded_current


def _get_json(url: str, timeout: int = REQUEST_TIMEOUT_SECONDS) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise UpdateError("El servidor de actualizaciones devolvió una respuesta inesperada.")
    return data


def _clean_note_line(line: str) -> str:
    line = re.sub(r"^[-*]\s+", "", line.strip())
    line = re.sub(r"^#+\s*", "", line)
    line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
    line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
    return line.strip()


def notes_items(notes: str, limit: int = 60) -> list[str]:
    """Convierte las notas del release en una lista legible y segura."""
    items: list[str] = []
    for line in str(notes or "").splitlines():
        cleaned = _clean_note_line(line)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered.startswith(("instalador:", "sha-256:")):
            continue
        items.append(cleaned)
        if len(items) >= limit:
            break
    return items


def _normalize_release(
    *,
    version: str,
    notes: str,
    setup_url: str,
    sha256: str,
    published_at: str,
    release_url: str,
    source: str,
) -> dict[str, Any]:
    version = str(version or "").strip().lstrip("vV")
    if not version:
        raise UpdateError("El release no informa una versión.")
    setup_url = str(setup_url or "").strip()
    return {
        "version": version,
        "notes": str(notes or "").strip(),
        "notes_items": notes_items(notes),
        "setup_url": setup_url,
        "sha256": str(sha256 or "").strip().lower(),
        "published_at": str(published_at or "").strip(),
        "release_url": str(release_url or "").strip(),
        "source": source,
    }


def _release_url(version: str) -> str:
    return f"https://github.com/{repository()}/releases/tag/v{version}"


def _sha_from_api_manifest(
    assets: list[dict[str, Any]],
    timeout: int = REQUEST_TIMEOUT_SECONDS,
) -> tuple[str, str]:
    """Obtiene notas/SHA del version.json adjunto cuando se usa la API."""
    for asset in assets:
        name = str(asset.get("name") or "").lower()
        if name != "version.json":
            continue
        url = str(asset.get("browser_download_url") or "")
        if not url:
            continue
        try:
            manifest = _get_json(url, timeout=timeout)
        except Exception:
            return "", ""
        return str(manifest.get("sha256") or ""), str(manifest.get("notes") or "")
    return "", ""


def _fetch_latest() -> dict[str, Any]:
    """Consulta el manifiesto y, si falla, la API de GitHub Releases."""
    errors: list[str] = []

    try:
        manifest = _get_json(manifest_url())
        version = str(manifest.get("version") or "")
        setup_url = str(manifest.get("setup_url") or "")
        if version and setup_url:
            return _normalize_release(
                version=version,
                notes=str(manifest.get("notes") or ""),
                setup_url=setup_url,
                sha256=str(manifest.get("sha256") or ""),
                published_at=str(manifest.get("published_at") or ""),
                release_url=_release_url(version),
                source="version.json",
            )
        errors.append("version.json no contiene version/setup_url")
    except Exception as error:  # noqa: BLE001
        errors.append(f"version.json: {error}")

    try:
        release = _get_json(api_url())
        version = str(release.get("tag_name") or "")
        assets = release.get("assets") or []
        setup_url = ""
        for asset in assets:
            name = str(asset.get("name") or "").lower()
            if name.endswith(".exe") and "setup" in name:
                setup_url = str(asset.get("browser_download_url") or "")
                break
        sha256, manifest_notes = _sha_from_api_manifest(assets)
        notes = manifest_notes or str(release.get("body") or "")
        return _normalize_release(
            version=version,
            notes=notes,
            setup_url=setup_url,
            sha256=sha256,
            published_at=str(release.get("published_at") or ""),
            release_url=str(release.get("html_url") or _release_url(version)),
            source="github-api",
        )
    except Exception as error:  # noqa: BLE001
        errors.append(f"GitHub API: {error}")

    raise UpdateError("No se pudo consultar el release: " + "; ".join(errors))


def reset_cache() -> None:
    """Limpia la caché (pruebas y comprobaciones forzadas)."""
    global _cache, _cache_at
    with _lock:
        _cache = None
        _cache_at = 0.0


def _state_path() -> Path:
    updates_dir = data_dir() / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    return updates_dir / "state.json"


def _read_state() -> dict[str, Any]:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(state: dict[str, Any]) -> None:
    try:
        _state_path().write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        # La preferencia es opcional: si no se puede guardar, el banner vuelve
        # a aparecer en la próxima sesión, pero la app sigue funcionando.
        pass


def dismissed_version() -> str:
    return str(_read_state().get("dismissed_version") or "")


def dismiss_version(version: str) -> None:
    version = str(version or "").strip().lstrip("vV")
    if not version:
        return
    state = _read_state()
    state["dismissed_version"] = version
    state["dismissed_at"] = (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )
    _write_state(state)


def _checked_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def check_for_update(force: bool = False) -> dict[str, Any]:
    """Devuelve el estado de actualización listo para la interfaz."""
    global _cache, _cache_at

    now = time.monotonic()
    with _lock:
        cached = _cache
        cached_at = _cache_at
    if cached is not None and not force and (now - cached_at) < CACHE_TTL_SECONDS:
        result = dict(cached)
        result["cached"] = True
        result["dismissed_version"] = dismissed_version()
        return result

    try:
        latest = _fetch_latest()
        result = {
            "current_version": APP_VERSION,
            "latest_version": latest["version"],
            "update_available": is_newer(latest["version"]),
            "notes": latest["notes"],
            "notes_items": latest["notes_items"],
            "setup_url": latest["setup_url"],
            "sha256": latest["sha256"],
            "published_at": latest["published_at"],
            "release_url": latest["release_url"],
            "source": latest["source"],
            "checked_at": _checked_at(),
            "error": None,
        }
    except Exception as error:  # noqa: BLE001
        result = {
            "current_version": APP_VERSION,
            "latest_version": None,
            "update_available": False,
            "notes": "",
            "notes_items": [],
            "setup_url": "",
            "sha256": "",
            "published_at": "",
            "release_url": "",
            "source": None,
            "checked_at": _checked_at(),
            "error": str(error),
        }

    result["cached"] = False
    result["dismissed_version"] = dismissed_version()
    result["can_self_update"] = bool(is_frozen() and sys.platform == "win32")
    with _lock:
        _cache = result
        _cache_at = now
    return result


def _validate_setup_url(url: str) -> str:
    url = str(url or "").strip()
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (
        host == "github.com" or host.endswith(".github.com")
    ):
        raise UpdateError("La URL del instalador no apunta a GitHub Releases.")
    return url


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_installer(update: dict[str, Any] | None = None) -> Path:
    """Descarga y verifica el instalador del release indicado."""
    info = update or check_for_update(force=True)
    if not info.get("update_available"):
        raise UpdateError("La aplicación ya está en la última versión.")
    setup_url = _validate_setup_url(str(info.get("setup_url") or ""))
    filename = Path(urllib.parse.urlparse(setup_url).path).name
    if not filename.lower().endswith(".exe"):
        raise UpdateError("El release no publica un instalador .exe.")

    target = _state_path().parent / filename
    expected_sha = str(info.get("sha256") or "").lower()
    if target.is_file():
        if not expected_sha or _sha256_of(target) == expected_sha:
            return target
        try:
            target.unlink()
        except OSError:
            pass

    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(
        setup_url,
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response, partial.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        if expected_sha and _sha256_of(partial) != expected_sha:
            raise UpdateError(
                "El SHA-256 del instalador no coincide con el publicado."
            )
        partial.replace(target)
    except UpdateError:
        partial.unlink(missing_ok=True)
        raise
    except Exception as error:  # noqa: BLE001
        partial.unlink(missing_ok=True)
        raise UpdateError(f"No se pudo descargar el instalador: {error}") from error
    return target


def apply_update() -> dict[str, Any]:
    """Descarga y lanza el instalador; el frontend cierra la app después."""
    info = check_for_update(force=True)
    if info.get("error"):
        raise UpdateError(str(info["error"]))
    if not info.get("update_available"):
        return {
            "launched": False,
            "reason": "up-to-date",
            "update": info,
        }
    if not info.get("can_self_update"):
        return {
            "launched": False,
            "reason": "manual",
            "setup_url": info.get("setup_url"),
            "release_url": info.get("release_url"),
            "update": info,
        }

    installer = download_installer(info)
    try:
        subprocess.Popen(
            [str(installer), "/CLOSEAPPLICATIONS", "/NORESTART"],
            close_fds=True,
        )
    except Exception as error:  # noqa: BLE001
        raise UpdateError(f"No se pudo iniciar el instalador: {error}") from error
    return {
        "launched": True,
        "reason": "started",
        "path": str(installer),
        "version": info.get("latest_version"),
        "update": info,
    }


def launch_url(url: str) -> bool:
    """Abre una URL externa (para el modo navegador o desarrollo)."""
    url = str(url or "").strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    try:
        import webbrowser

        return bool(webbrowser.open(url))
    except Exception:
        return False

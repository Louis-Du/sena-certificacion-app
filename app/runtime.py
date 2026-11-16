"""Utilidades de rutas compatibles con el modo empaquetado (PyInstaller)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Directorio de trabajo de la aplicación (carpeta del .exe o raíz del repo)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """Directorio donde viven los recursos empaquetados (estáticos, plantillas)."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle)
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Directorio de datos persistentes (SQLite)."""
    override = os.getenv("SENA_DATA_DIR")
    if override:
        path = Path(override).expanduser().resolve()
    else:
        path = project_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_database_url() -> str:
    db_path = (data_dir() / "sena_certificacion.db").as_posix()
    return f"sqlite:///{db_path}"

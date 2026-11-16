"""Icono en la bandeja del sistema para el modo en segundo plano."""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

import requests

from app.runtime import resource_root


def _load_icon():
    from PIL import Image

    icon_path = resource_root() / "assets" / "SENACertificacion.ico"
    if icon_path.is_file():
        try:
            return Image.open(icon_path)
        except Exception:
            pass
    # Icono de respaldo simple.
    img = Image.new("RGB", (64, 64), color=(30, 41, 59))
    return img


def run_tray(port: int, on_exit) -> None:
    """Ejecuta el icono en la bandeja (bloqueante)."""
    import pystray

    url = f"http://127.0.0.1:{port}"

    def open_app(icon, item):
        webbrowser.open(url)

    def sync_now(icon, item):
        try:
            requests.post(f"{url}/api/sheets/sync/run", timeout=30)
        except Exception:
            pass

    def exit_app(icon, item):
        icon.stop()
        if on_exit:
            on_exit()

    icon = pystray.Icon(
        "SENACertificacion",
        _load_icon(),
        "SENA Certificacion",
        menu=pystray.Menu(
            pystray.MenuItem("Abrir", open_app, default=True),
            pystray.MenuItem("Sincronizar ahora", sync_now),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", exit_app),
        ),
    )
    icon.run()


def start_tray_thread(port: int, on_exit) -> threading.Thread:
    thread = threading.Thread(target=run_tray, args=(port, on_exit), daemon=True)
    thread.start()
    return thread
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path


if getattr(sys, "frozen", False):
    os.chdir(Path(sys.executable).resolve().parent)
    (Path.cwd() / "data").mkdir(parents=True, exist_ok=True)

from app.main import app
import uvicorn


def available_port(preferred_port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", preferred_port))
        except OSError:
            probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def server_is_ready(port: int, timeout: float = 10.0) -> bool:
    """Espera a que el servidor local acepte conexiones."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def run_desktop_window(url: str) -> None:
    """Abre la aplicación en una ventana nativa de escritorio."""
    try:
        import webview
    except ImportError:
        if os.getenv("SENA_USE_BROWSER") == "1":
            import webbrowser

            webbrowser.open(url)
            return
        raise RuntimeError(
            "Falta pywebview. Reinstale la aplicación o defina "
            "SENA_USE_BROWSER=1 para usar el navegador externo."
        )

    window = webview.create_window(
        "SENA Certificación",
        url,
        width=1440,
        height=900,
        min_size=(1024, 700),
        confirm_close=True,
    )
    webview.start()


if __name__ == "__main__":
    port = available_port(int(os.getenv("PORT", "8000")))
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
    )
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    try:
        if not server_is_ready(port):
            raise RuntimeError(f"El servidor local no respondió en {url}")
        run_desktop_window(url)
    except (OSError, SystemExit) as error:
        print(f"No fue posible iniciar la aplicacion en {url}:\n{error}")
        input("Presiona Enter para cerrar...")
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)

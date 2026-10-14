from __future__ import annotations

import os
import socket
import sys
import threading
import webbrowser
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


if __name__ == "__main__":
    port = available_port(int(os.getenv("PORT", "8000")))
    url = f"http://127.0.0.1:{port}"
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=port)
    except (OSError, SystemExit) as error:
        print(f"No fue posible iniciar la aplicacion en {url}:\n{error}")
        input("Presiona Enter para cerrar...")

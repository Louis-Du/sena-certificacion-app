import os
import socket
import subprocess
import sys
import time
from collections.abc import Generator
from pathlib import Path

import pytest

from tests.conftest import csv_bytes, pdf_bytes, xlsx_bytes


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def e2e_server(tmp_path) -> Generator[dict, None, None]:
    db_path = tmp_path / "e2e.db"
    port = _free_port()
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30
    ready = False
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                ready = True
                break
        except OSError:
            time.sleep(0.5)

    if not ready:
        process.terminate()
        process.wait(timeout=5)
        raise RuntimeError("No se pudo iniciar el servidor de pruebas E2E.")

    yield {"base_url": base_url, "db_path": db_path}

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@pytest.fixture
def app_url(e2e_server) -> str:
    return e2e_server["base_url"]

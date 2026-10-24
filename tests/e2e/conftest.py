"""Infraestructura E2E: servidor FastAPI real + base SQLite temporal por prueba.

Cada prueba arranca su propio `uvicorn` en un puerto libre con DATABASE_URL apuntando a
un archivo dentro de `tmp_path`, de modo que nunca se toca data/sena_certificacion.db.
Los datos son ficticios.
"""
from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DF14A_HEADER = "DOCUMENTO,NOMBRES,FICHA,PROGRAMA,ESTADO_ASPIRANTE\n"


@dataclass
class LiveServer:
    url: str
    db_path: Path

    def count(self, table: str) -> int:
        connection = sqlite3.connect(self.db_path)
        try:
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            connection.close()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def live_server(tmp_path) -> LiveServer:
    port = _free_port()
    db_path = tmp_path / "e2e.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=REPO_ROOT,
        env=env,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    while True:
        if process.poll() is not None:
            raise RuntimeError("El servidor E2E terminó antes de estar listo.")
        try:
            with urllib.request.urlopen(f"{url}/api/information-types", timeout=1):
                break
        except (urllib.error.URLError, ConnectionError, OSError):
            if time.monotonic() > deadline:
                process.terminate()
                raise RuntimeError("El servidor E2E no respondió a tiempo.")
            time.sleep(0.1)
    yield LiveServer(url=url, db_path=db_path)
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:  # pragma: no cover
        process.kill()


@pytest.fixture
def app_url(live_server: LiveServer) -> str:
    return live_server.url


@pytest.fixture
def make_file(tmp_path):
    def factory(name: str, content: bytes | str) -> Path:
        path = tmp_path / name
        path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        return path

    return factory


def df14a_csv(count: int, status_cycle=("Por Certificar", "En Formacion", "Certificado")) -> str:
    rows = [
        f"{1000 + i},Aprendiz {i:02d},300{i % 3},Programa {'A' if i % 2 == 0 else 'B'},"
        f"{status_cycle[i % len(status_cycle)]}\n"
        for i in range(count)
    ]
    return DF14A_HEADER + "".join(rows)


@pytest.fixture
def seed_df14a(live_server, page):
    """Importa un DF14A ficticio por la API (validar + confirmar) y devuelve el JSON final."""

    def seed(count: int = 5, **kwargs) -> dict:
        content = df14a_csv(count, **kwargs).encode("utf-8")
        validated = page.request.post(
            f"{live_server.url}/api/files/validate",
            multipart={
                "information_type": "df14a",
                "file": {"name": "seed_df14a.csv", "mimeType": "text/csv", "buffer": content},
            },
        )
        assert validated.ok
        confirmed = page.request.post(f"{live_server.url}/api/imports/{validated.json()['validation_id']}/confirm")
        assert confirmed.ok
        return confirmed.json()

    return seed


@pytest.fixture
def seed_act(live_server, page):
    def seed(number: str, act_date: str = "2026-10-01", **extra) -> dict:
        response = page.request.post(
            f"{live_server.url}/api/acts",
            data={"number": number, "act_date": act_date, **extra},
        )
        assert response.status == 201
        return response.json()

    return seed

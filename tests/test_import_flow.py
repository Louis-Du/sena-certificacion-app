from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.main import app


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def upload(client: TestClient, content: bytes = b"nombre,estado\nAna,Por Certificar\n") -> str:
    response = client.post(
        "/api/files/validate",
        data={"information_type": "df14a"},
        files={"file": ("df14a.csv", content, "text/csv")},
    )
    assert response.status_code == 200
    return response.json()["validation_id"]


def test_validation_does_not_persist(client: TestClient):
    upload(client)

    history = client.get("/api/imports/history")

    assert history.status_code == 200
    assert history.json()["items"] == []


def test_validation_reports_duplicate_rows(client: TestClient):
    response = client.post(
        "/api/files/validate",
        data={"information_type": "df14a"},
        files={
            "file": (
                "df14a.csv",
                b"nombre,estado\nAna,Por Certificar\nAna,Por Certificar\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "warning"
    assert any("duplicados" in check["label"] for check in response.json()["checks"])


def test_confirm_creates_history_and_updates_existing_records(client: TestClient):
    validation_id = upload(
        client,
        b"nombre,estado\nAna,Por Certificar\nLuis,Por Certificar\n",
    )
    preview = client.get(f"/api/imports/{validation_id}/preview")
    first_import = client.post(f"/api/imports/{validation_id}/confirm")

    assert preview.json()["new_records"] == 2
    assert preview.json()["updated_records"] == 0
    assert first_import.json()["new_records"] == 2

    second_validation = upload(
        client,
        b"nombre,estado\nAna,Por Certificar\nLuis,Por Certificar\n",
    )
    second_preview = client.get(f"/api/imports/{second_validation}/preview")
    second_import = client.post(f"/api/imports/{second_validation}/confirm")

    assert second_preview.json()["new_records"] == 0
    assert second_preview.json()["updated_records"] == 2
    assert second_import.json()["updated_records"] == 2
    assert len(client.get("/api/imports/history").json()["items"]) == 2


def test_confirm_updates_learners_list_in_sqlite(client: TestClient):
    validation_id = upload(
        client,
        b"identificacion,nombre,programa,estado\n1001,Ana,Analisis y Desarrollo,Por certificar\n",
    )

    confirmed = client.post(f"/api/imports/{validation_id}/confirm")
    learners = client.get("/api/learners")

    assert confirmed.status_code == 200
    assert learners.status_code == 200
    assert len(learners.json()["items"]) == 1
    assert learners.json()["items"][0]["identification"] == "1001"
    assert learners.json()["items"][0]["name"] == "Ana"

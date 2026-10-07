from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import Learner


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path / 'acts.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        test_client.session_factory = factory
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def seed_learner(client: TestClient) -> int:
    with client.session_factory() as session:
        learner = Learner(identification="100", name="Aprendiz Uno", program="Programa", group_code="1")
        session.add(learner)
        session.commit()
        return learner.id


def test_create_list_detail_and_update_act(client: TestClient):
    response = client.post("/api/acts", json={"number": "ACT-01", "act_date": "2026-10-05"})
    assert response.status_code == 201
    act_id = response.json()["id"]
    assert client.get("/api/acts").json()["items"][0]["number"] == "ACT-01"
    assert client.get(f"/api/acts/{act_id}").json()["learners"] == []
    updated = client.patch(f"/api/acts/{act_id}", json={"observations": "Revisada"})
    assert updated.status_code == 200
    assert updated.json()["observations"] == "Revisada"


def test_link_duplicate_and_unlink_learner(client: TestClient):
    learner_id = seed_learner(client)
    act_id = client.post("/api/acts", json={"number": "ACT-02", "act_date": "2026-10-05"}).json()["id"]
    assert client.post(f"/api/acts/{act_id}/learners", json={"learner_id": learner_id}).status_code == 201
    assert client.post(f"/api/acts/{act_id}/learners", json={"learner_id": learner_id}).status_code == 400
    detail = client.get(f"/api/acts/{act_id}").json()
    assert len(detail["learners"]) == 1
    assert client.delete(f"/api/acts/{act_id}/learners/{learner_id}").status_code == 204
    assert client.get(f"/api/acts/{act_id}").json()["learners"] == []


@pytest.mark.parametrize(
    ("method", "url", "payload"),
    [
        ("post", "/api/acts", {"act_date": "2026-10-05"}),
        ("post", "/api/acts/999/learners", {"learner_id": 1}),
        ("post", "/api/acts/999/learners", {"learner_id": 999}),
    ],
)
def test_act_validation_errors(client: TestClient, method: str, url: str, payload: dict):
    assert getattr(client, method)(url, json=payload).status_code in {400, 404, 422}


def test_duplicate_act_number_is_rejected(client: TestClient):
    payload = {"number": "ACT-03", "act_date": "2026-10-05"}
    assert client.post("/api/acts", json=payload).status_code == 201
    assert client.post("/api/acts", json=payload).status_code == 400

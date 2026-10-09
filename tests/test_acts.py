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


def test_acts_options_and_information_types_are_available(client: TestClient):
    options = client.get("/api/acts/options")
    types = client.get("/api/information-types")

    assert options.status_code == 200
    assert set(options.json()["review_statuses"]) == {"pending", "reviewed", "rejected"}
    assert types.status_code == 200
    assert {item["value"] for item in types.json()["items"]} == {
        "df14a",
        "acta",
        "requisitos",
        "otro",
    }


def test_create_act_rejects_blank_number_and_invalid_review_status(client: TestClient):
    blank = client.post("/api/acts", json={"number": "   ", "act_date": "2026-10-05"})
    invalid = client.post(
        "/api/acts",
        json={"number": "ACT-04", "act_date": "2026-10-05", "review_status": "otro"},
    )

    assert blank.status_code == 422
    assert invalid.status_code == 400


def test_list_acts_supports_search_and_review_status_filter(client: TestClient):
    client.post(
        "/api/acts",
        json={"number": "ACT-BUS-01", "act_date": "2026-10-01", "act_type": "Certificacion"},
    )
    client.post(
        "/api/acts",
        json={
            "number": "ACT-BUS-02",
            "act_date": "2026-10-02",
            "review_status": "reviewed",
            "observations": "Lista para firma",
        },
    )

    search = client.get("/api/acts", params={"search": "firma"})
    filtered = client.get("/api/acts", params={"review_status": "reviewed"})
    invalid = client.get("/api/acts", params={"review_status": "desconocido"})

    assert search.json()["items"][0]["number"] == "ACT-BUS-02"
    assert [item["number"] for item in filtered.json()["items"]] == ["ACT-BUS-02"]
    assert invalid.status_code == 400


def test_update_act_rejects_duplicate_number_and_missing_act(client: TestClient):
    first = client.post("/api/acts", json={"number": "ACT-A", "act_date": "2026-10-05"}).json()["id"]
    client.post("/api/acts", json={"number": "ACT-B", "act_date": "2026-10-05"})

    duplicate = client.patch(f"/api/acts/{first}", json={"number": "ACT-B"})
    missing = client.patch("/api/acts/9999", json={"observations": "x"})

    assert duplicate.status_code == 400
    assert missing.status_code == 404


def test_unlink_missing_association_and_missing_act_return_404(client: TestClient):
    learner_id = seed_learner(client)
    act_id = client.post("/api/acts", json={"number": "ACT-05", "act_date": "2026-10-05"}).json()["id"]

    assert client.delete(f"/api/acts/{act_id}/learners/{learner_id}").status_code == 404
    assert client.delete("/api/acts/9999/learners/1").status_code == 404
    assert client.delete("/api/acts/9999").status_code == 404


def test_link_unknown_learner_returns_404(client: TestClient):
    act_id = client.post("/api/acts", json={"number": "ACT-06", "act_date": "2026-10-05"}).json()["id"]

    response = client.post(f"/api/acts/{act_id}/learners", json={"learner_id": 9999})

    assert response.status_code == 404

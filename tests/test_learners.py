from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models import ImportHistory, ImportedRecord, Learner
from app.services.learners import _prepare_learner_row


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'learners.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        test_client.session_factory = session_factory
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def seed_learners(client: TestClient, count: int = 26) -> None:
    with client.session_factory() as session:
        session.add_all(
            [
                Learner(
                    identification=str(1000 + index),
                    name=f"Aprendiz {index:02d}",
                    program="Programa Logistico" if index % 2 else "Programa Software",
                    group_code=str(3000 + index),
                    certification_status="Por certificar",
                )
                for index in range(count)
            ]
        )
        session.commit()


def test_prepare_learner_row_supports_real_df14a_columns():
    row = _prepare_learner_row(
        {
            "DOCUMENTO": "TI_1028865527",
            "NOMBRES": "SANTIAGO JIMENEZ ANGEL",
            "FICHA": 3466192,
            "PROGRAMA": "DESARROLLO PUBLICITARIO",
            "ESTADO_ASPIRANTE": 8,
        }
    )

    assert row == {
        "identification": "1028865527",
        "name": "SANTIAGO JIMENEZ ANGEL",
        "program": "DESARROLLO PUBLICITARIO",
        "group_code": "3466192",
        "training_type": None,
        "certification_status": "8",
        "tracking_notes": None,
    }


def test_learners_api_paginates_results(client: TestClient):
    seed_learners(client)

    response = client.get("/api/learners?page=2&page_size=5")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 26
    assert body["page"] == 2
    assert body["pages"] == 6
    assert len(body["items"]) == 5


def test_learners_api_searches_name_program_and_group(client: TestClient):
    seed_learners(client)

    expected_totals = {"Aprendiz 03": 1, "Software": 13, "3003": 1}
    for search, expected_total in expected_totals.items():
        response = client.get("/api/learners", params={"search": search})
        assert response.status_code == 200
        assert response.json()["total"] == expected_total


def test_learners_api_rejects_invalid_pagination(client: TestClient):
    assert client.get("/api/learners?page=0").status_code == 422
    assert client.get("/api/learners?page_size=101").status_code == 422


def test_learners_api_returns_empty_search_result(client: TestClient):
    seed_learners(client)

    response = client.get("/api/learners", params={"search": "No existe"})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
    assert response.json()["pages"] == 0


def test_learners_api_migrates_existing_imported_records_when_table_is_empty(client: TestClient):
    with client.session_factory() as session:
        history = ImportHistory(
            file_name="legacy.csv",
            information_type="DF14A",
            records_count=1,
            status="completed",
        )
        session.add(history)
        session.flush()
        session.add(
            ImportedRecord(
                import_id=history.id,
                information_type="df14a",
                record_key="legacy-row",
                row_number=2,
                payload='{"DOCUMENTO": "CC_12345", "NOMBRES": "Aprendiz legado", "FICHA": 4567}',
            )
        )
        session.commit()

    response = client.get("/api/learners")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["identification"] == "12345"


def test_learner_search_matches_name_document_program_group_and_status(client: TestClient):
    with client.session_factory() as session:
        session.add_all(
            [
                Learner(
                    identification="2001",
                    name="Ana Nombre",
                    program="Programa Redes",
                    group_code="FICHA-01",
                    certification_status="Por certificar",
                ),
                Learner(
                    identification="2002",
                    name="Bruno",
                    program="Programa Software",
                    group_code="FICHA-02",
                    certification_status="Certificado",
                ),
            ]
        )
        session.commit()

    for term in ("Ana Nombre", "2001", "Programa Redes", "FICHA-01", "Por certificar"):
        response = client.get("/api/learners", params={"search": term})
        assert response.status_code == 200
        assert [item["identification"] for item in response.json()["items"]] == ["2001"]

    response = client.get("/api/learners", params={"status": "Certificado"})
    assert response.status_code == 200
    assert [item["identification"] for item in response.json()["items"]] == ["2002"]


def test_requirements_can_be_created_updated_and_retrieved(client: TestClient):
    seed_learners(client, count=1)
    learner_id = client.get("/api/learners").json()["items"][0]["id"]

    created = client.post(
        f"/api/learners/{learner_id}/requirements",
        json={
            "requirement_type": "documentation",
            "status": "Pendiente",
            "observations": "Falta documento de identidad.",
        },
    )
    assert created.status_code == 201
    requirement_id = created.json()["id"]

    updated = client.patch(
        f"/api/learners/{learner_id}/requirements/{requirement_id}",
        json={
            "requirement_type": "documentation",
            "status": "Cumplido",
            "observations": "Validado el 07/10/2026.",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "Cumplido"

    listed = client.get(f"/api/learners/{learner_id}/requirements")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["observations"] == "Validado el 07/10/2026."

    detail = client.get(f"/api/learners/{learner_id}")
    assert detail.status_code == 200
    assert detail.json()["requirements"][1]["status"] == "Cumplido"


def test_learner_detail_exposes_editable_requirement_slots_without_registering_them(client: TestClient):
    seed_learners(client, count=1)
    learner_id = client.get("/api/learners").json()["items"][0]["id"]

    detail = client.get(f"/api/learners/{learner_id}")

    assert detail.status_code == 200
    assert {item["requirement_type"] for item in detail.json()["requirements"]} == {
        "learning_outcome",
        "documentation",
        "productive_stage",
        "clearance",
        "saber_tyt",
    }
    assert client.get("/api/learners/with-pending-requirements").json()["items"] == []


def test_pending_requirements_only_include_registered_pending_status(client: TestClient):
    seed_learners(client, count=3)
    learners = client.get("/api/learners").json()["items"]
    client.post(
        f"/api/learners/{learners[0]['id']}/requirements",
        json={"requirement_type": "documentation", "status": "Pendiente"},
    )
    client.post(
        f"/api/learners/{learners[1]['id']}/requirements",
        json={"requirement_type": "documentation", "status": "Cumplido"},
    )
    client.post(
        f"/api/learners/{learners[2]['id']}/requirements",
        json={"requirement_type": "documentation", "status": "No aplica"},
    )

    response = client.get("/api/learners/with-pending-requirements")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [learners[0]["id"]]
    assert response.json()["items"][0]["pending_count"] == 1


def test_requirements_validate_learner_type_status_and_duplicates(client: TestClient):
    seed_learners(client, count=1)
    learner_id = client.get("/api/learners").json()["items"][0]["id"]

    assert client.post(
        f"/api/learners/{learner_id}/requirements",
        json={"requirement_type": "unknown", "status": "Pendiente"},
    ).status_code == 400
    assert client.post(
        f"/api/learners/{learner_id}/requirements",
        json={"requirement_type": "documentation", "status": "Otro"},
    ).status_code == 400
    assert client.post(
        f"/api/learners/{learner_id}/requirements",
        json={"requirement_type": "documentation", "status": "Pendiente"},
    ).status_code == 201
    assert client.post(
        f"/api/learners/{learner_id}/requirements",
        json={"requirement_type": "documentation", "status": "Cumplido"},
    ).status_code == 400
    assert client.get("/api/learners/9999/requirements").status_code == 404
    assert client.patch(
        f"/api/learners/9999/requirements/1",
        json={"requirement_type": "documentation", "status": "Cumplido"},
    ).status_code == 404

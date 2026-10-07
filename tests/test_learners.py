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


def test_prepare_learner_row_supports_df14a_with_unnamed_excel_columns():
    row = _prepare_learner_row(
        {
            "RESULTADOS DE PRUEBAS POR ASPIRANTE": 34547126,
            "Unnamed: 3": 1041979481,
            "Unnamed: 4": "MARIA DE LOS ANGELES",
            "Unnamed: 5": "HINESTROZA TORRES",
            "Unnamed: 15": "Seleccionado",
        }
    )

    assert row == {
        "identification": "1041979481",
        "name": "MARIA DE LOS ANGELES HINESTROZA TORRES",
        "program": None,
        "group_code": None,
        "training_type": None,
        "certification_status": "Seleccionado",
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


def test_learner_detail_returns_basic_info_provisional_requirements_and_history(client: TestClient):
    with client.session_factory() as session:
        learner = Learner(
            identification="1028865527",
            name="Juan Perez",
            program="Programa de Software",
            group_code="123456",
            training_type="Tecnólogo",
            certification_status="Por certificar",
        )
        session.add(learner)
        session.flush()
        history = ImportHistory(
            file_name="DF14A.xlsx",
            information_type="DF14A",
            records_count=1,
            status="completed",
        )
        session.add(history)
        session.flush()
        session.add(
            ImportedRecord(
                import_id=history.id,
                information_type="DF14A",
                record_key="learner-row",
                row_number=2,
                payload='{"DOCUMENTO": "1028865527", "NOMBRES": "Juan Perez"}',
            )
        )
        session.commit()
        learner_id = learner.id

    response = client.get(f"/api/learners/{learner_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["basic_info"]["identification"] == "1028865527"
    assert body["requirements"]["documentation"] == "Pendiente"
    assert body["requirements"]["saber_tyt"] == "Pendiente"
    assert body["acts"] == []
    assert body["history"][0]["event"] == "Actualizacion DF14A"


def test_learner_detail_returns_404_for_unknown_learner(client: TestClient):
    response = client.get("/api/learners/9999")

    assert response.status_code == 404


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

from fastapi.testclient import TestClient

from app.models import Act, ActLearner, ImportHistory, ImportedRecord, Learner

from tests.conftest import csv_bytes, pdf_bytes, xlsx_bytes


def _validate(client: TestClient, filename: str, content: bytes, information_type: str = "df14a"):
    response = client.post(
        "/api/files/validate",
        data={"information_type": information_type},
        files={"file": (filename, content, "application/octet-stream")},
    )
    assert response.status_code == 200
    return response.json()


def test_validate_preview_confirm_persists_only_after_confirm(client: TestClient):
    content = csv_bytes(
        "DOCUMENTO,NOMBRES,FICHA,PROGRAMA,ESTADO_ASPIRANTE\n"
        "TI_1001,Ana Lopez,3001,Analisis,Por Certificar\n"
        "CC_1002,Luis Perez,3001,Analisis,Certificado\n"
    )
    validated = _validate(client, "df14a.csv", content)
    validation_id = validated["validation_id"]

    assert client.get("/api/imports/history").json()["items"] == []
    assert client.get("/api/learners").json()["total"] == 0

    preview = client.get(f"/api/imports/{validation_id}/preview")
    assert preview.status_code == 200
    assert preview.json()["new_records"] == 2
    assert preview.json()["updated_records"] == 0
    assert client.get("/api/learners").json()["total"] == 0

    confirmed = client.post(f"/api/imports/{validation_id}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["new_records"] == 2
    assert confirmed.json()["status"] == "completed"

    history = client.get("/api/imports/history").json()["items"]
    learners = client.get("/api/learners").json()
    assert len(history) == 1
    assert learners["total"] == 2
    identifications = {item["identification"] for item in learners["items"]}
    assert identifications == {"1001", "1002"}

    with client.session_factory() as session:
        assert session.query(ImportHistory).count() == 1
        assert session.query(ImportedRecord).count() == 2
        assert session.query(Learner).count() == 2


def test_second_confirm_of_same_validation_is_rejected(client: TestClient):
    validated = _validate(client, "df14a.csv", csv_bytes("nombre\nAna\n"))
    validation_id = validated["validation_id"]

    assert client.post(f"/api/imports/{validation_id}/confirm").status_code == 200
    second = client.post(f"/api/imports/{validation_id}/confirm")

    assert second.status_code == 404
    assert client.get("/api/imports/history").json()["items"].__len__() == 1


def test_reimport_updates_learners_without_duplicating_sqlite_rows(client: TestClient):
    first = csv_bytes("DOCUMENTO,NOMBRES,PROGRAMA\n1001,Ana,Software\n")
    same = csv_bytes("DOCUMENTO,NOMBRES,PROGRAMA\n1001,Ana,Software\n")
    changed = csv_bytes("DOCUMENTO,NOMBRES,PROGRAMA\n1001,Ana Maria,Redes\n")

    first_id = _validate(client, "df14a.csv", first)["validation_id"]
    client.post(f"/api/imports/{first_id}/confirm")

    same_id = _validate(client, "df14a.csv", same)["validation_id"]
    same_preview = client.get(f"/api/imports/{same_id}/preview").json()
    client.post(f"/api/imports/{same_id}/confirm")
    assert same_preview["updated_records"] == 1
    assert same_preview["new_records"] == 0

    changed_id = _validate(client, "df14a.csv", changed)["validation_id"]
    client.post(f"/api/imports/{changed_id}/confirm")

    learners = client.get("/api/learners").json()
    assert learners["total"] == 1
    assert learners["items"][0]["name"] == "Ana Maria"
    assert learners["items"][0]["program"] == "Redes"


def test_xlsx_import_then_learner_search_and_act_association(client: TestClient):
    content = xlsx_bytes(
        [
            {
                "DOCUMENTO": "2001",
                "NOMBRES": "Carla Diaz",
                "FICHA": "4100",
                "PROGRAMA": "Logistica",
                "ESTADO_ASPIRANTE": "Por Certificar",
            }
        ]
    )
    validation_id = _validate(client, "df14a.xlsx", content)["validation_id"]
    client.post(f"/api/imports/{validation_id}/confirm")

    search = client.get("/api/learners", params={"search": "Carla"})
    assert search.status_code == 200
    learner_id = search.json()["items"][0]["id"]
    assert search.json()["items"][0]["group_code"] == "4100"

    created = client.post(
        "/api/acts",
        json={
            "number": "ACT-REG-01",
            "act_date": "2026-10-09",
            "act_type": "Certificacion",
            "review_status": "pending",
            "observations": "Acta de prueba",
        },
    )
    assert created.status_code == 201
    act_id = created.json()["id"]

    linked = client.post(
        f"/api/acts/{act_id}/learners",
        json={"learner_id": learner_id, "observations": "Incluida en el acta"},
    )
    assert linked.status_code == 201
    detail = client.get(f"/api/acts/{act_id}")
    assert detail.status_code == 200
    assert detail.json()["learners_count"] == 1
    assert detail.json()["learners"][0]["identification"] == "2001"
    assert detail.json()["learners"][0]["observations"] == "Incluida en el acta"

    with client.session_factory() as session:
        assert session.query(Act).count() == 1
        assert session.query(ActLearner).count() == 1


def test_acta_pdf_confirm_does_not_create_learners(client: TestClient):
    validation_id = _validate(client, "acta.pdf", pdf_bytes(), "acta")["validation_id"]
    confirmed = client.post(f"/api/imports/{validation_id}/confirm")

    assert confirmed.status_code == 200
    assert confirmed.json()["records_count"] == 1
    assert client.get("/api/learners").json()["total"] == 0
    assert client.get("/api/imports/history").json()["items"][0]["information_type"] == "Acta de certificacion"


def test_preview_and_confirm_missing_or_invalid_validation(client: TestClient):
    assert client.get("/api/imports/missing/preview").status_code == 404
    assert client.post("/api/imports/missing/confirm").status_code == 404

    error_id = _validate(client, "acta.pdf", pdf_bytes(), "df14a")["validation_id"]
    assert client.get(f"/api/imports/{error_id}/preview").status_code == 400
    assert client.post(f"/api/imports/{error_id}/confirm").status_code == 400


def test_deleting_act_removes_associations_but_keeps_learner(client: TestClient):
    with client.session_factory() as session:
        learner = Learner(identification="9001", name="Eva", program="Redes", group_code="1")
        session.add(learner)
        session.commit()
        learner_id = learner.id

    act_id = client.post(
        "/api/acts",
        json={"number": "ACT-DEL-01", "act_date": "2026-10-01"},
    ).json()["id"]
    client.post(f"/api/acts/{act_id}/learners", json={"learner_id": learner_id})

    deleted = client.delete(f"/api/acts/{act_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/acts/{act_id}").status_code == 404
    assert client.get("/api/learners").json()["total"] == 1

    with client.session_factory() as session:
        assert session.query(ActLearner).count() == 0
        assert session.get(Learner, learner_id) is not None

"""Detalle del aprendiz: el campo `acts` refleja las asociaciones reales con actas.

El campo `history` queda sin definición funcional (ver docs en learners.py):
ImportHistory/ImportedRecord no tienen relación con Learner.
"""
from app.models import ImportHistory, ImportedRecord, Learner


def seed_learner(client, identification="1001", name="Aprendiz Ficticio"):
    with client.session_factory() as session:
        learner = Learner(
            identification=identification,
            name=name,
            program="Programa Demo",
            group_code="9999",
            certification_status="Por Certificar",
        )
        session.add(learner)
        session.commit()
        return learner.id


def create_act(client, number, act_date="2026-10-05", **extra):
    response = client.post("/api/acts", json={"number": number, "act_date": act_date, **extra})
    assert response.status_code == 201
    return response.json()["id"]


def test_detail_without_acts_returns_empty_list_and_keeps_contract(client):
    learner_id = seed_learner(client)

    detail = client.get(f"/api/learners/{learner_id}").json()

    assert set(detail) == {"basic_info", "requirements", "acts", "history", "dates"}
    assert detail["acts"] == []
    assert detail["history"] == []


def test_detail_lists_acts_the_learner_is_really_associated_with(client):
    learner_id = seed_learner(client)
    act_a = create_act(client, "ACT-A", "2026-09-01", act_type="Titulada")
    act_b = create_act(client, "ACT-B", "2026-10-01")
    create_act(client, "ACT-C")  # sin asociar: no debe aparecer
    client.post(f"/api/acts/{act_a}/learners", json={"learner_id": learner_id, "observations": "Falta paz y salvo"})
    client.post(f"/api/acts/{act_b}/learners", json={"learner_id": learner_id})

    acts = client.get(f"/api/learners/{learner_id}").json()["acts"]

    assert [item["number"] for item in acts] == ["ACT-B", "ACT-A"]  # más reciente primero
    by_number = {item["number"]: item for item in acts}
    assert by_number["ACT-A"]["observations"] == "Falta paz y salvo"
    assert by_number["ACT-A"]["act_type"] == "Titulada"
    assert by_number["ACT-A"]["review_status"] == "pending"
    assert by_number["ACT-A"]["act_date"] == "2026-09-01"


def test_detail_does_not_mix_acts_between_learners(client):
    first = seed_learner(client, "1001", "Uno")
    second = seed_learner(client, "1002", "Dos")
    act_id = create_act(client, "ACT-X")
    client.post(f"/api/acts/{act_id}/learners", json={"learner_id": first})

    assert len(client.get(f"/api/learners/{first}").json()["acts"]) == 1
    assert client.get(f"/api/learners/{second}").json()["acts"] == []


def test_detail_reflects_unlink_and_act_deletion(client):
    learner_id = seed_learner(client)
    act_a = create_act(client, "ACT-A")
    act_b = create_act(client, "ACT-B")
    client.post(f"/api/acts/{act_a}/learners", json={"learner_id": learner_id})
    client.post(f"/api/acts/{act_b}/learners", json={"learner_id": learner_id})

    client.delete(f"/api/acts/{act_a}/learners/{learner_id}")
    assert [a["number"] for a in client.get(f"/api/learners/{learner_id}").json()["acts"]] == ["ACT-B"]

    client.delete(f"/api/acts/{act_b}")
    assert client.get(f"/api/learners/{learner_id}").json()["acts"] == []


def test_detail_reflects_act_edits(client):
    learner_id = seed_learner(client)
    act_id = create_act(client, "ACT-A")
    client.post(f"/api/acts/{act_id}/learners", json={"learner_id": learner_id})

    client.patch(f"/api/acts/{act_id}", json={"review_status": "reviewed", "number": "ACT-A2"})

    act = client.get(f"/api/learners/{learner_id}").json()["acts"][0]
    assert (act["number"], act["review_status"]) == ("ACT-A2", "reviewed")


def test_detail_history_is_not_attributed_from_unrelated_imports(client):
    """Hay importaciones DF14A con la misma identificación, pero no existe relación
    real con el aprendiz: `history` no debe inventar eventos."""
    learner_id = seed_learner(client, "1001")
    with client.session_factory() as session:
        history = ImportHistory(file_name="df14a.csv", information_type="df14a", records_count=1)
        session.add(history)
        session.flush()
        session.add(
            ImportedRecord(
                import_id=history.id,
                information_type="df14a",
                record_key="k" * 64,
                payload='{"DOCUMENTO": "1001"}',
            )
        )
        session.commit()

    assert client.get(f"/api/learners/{learner_id}").json()["history"] == []


def test_detail_unknown_learner_returns_404_even_with_acts_present(client):
    create_act(client, "ACT-A")

    response = client.get("/api/learners/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Aprendiz no encontrado."

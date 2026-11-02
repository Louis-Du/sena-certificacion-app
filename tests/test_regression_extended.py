"""Regresión ampliada: protege flujos existentes sin modificar las pruebas previas.

Los datos son ficticios y cada prueba usa una base SQLite temporal (fixture `client`).
"""
from fastapi.testclient import TestClient

from app.models import Act, ActLearner, ImportHistory, ImportedRecord, Learner, Requirement
from tests.conftest import csv_bytes, xlsx_bytes

DF14A_HEADER = "DOCUMENTO,NOMBRES,FICHA,PROGRAMA,ESTADO_ASPIRANTE\n"


def validate(client: TestClient, filename: str, content: bytes, information_type: str = "df14a") -> dict:
    response = client.post(
        "/api/files/validate",
        data={"information_type": information_type},
        files={"file": (filename, content, "application/octet-stream")},
    )
    assert response.status_code == 200
    return response.json()


def import_df14a(client: TestClient, body: str) -> dict:
    validated = validate(client, "df14a.csv", csv_bytes(DF14A_HEADER + body))
    response = client.post(f"/api/imports/{validated['validation_id']}/confirm")
    assert response.status_code == 200
    return response.json()


def table_counts(client: TestClient) -> dict[str, int]:
    with client.session_factory() as session:
        return {
            model.__tablename__: session.query(model).count()
            for model in (ImportHistory, ImportedRecord, Learner, Requirement, Act, ActLearner)
        }


# --- Cancelar / abandonar una importación -------------------------------------------------


def test_abandoned_import_after_validate_and_preview_persists_nothing(client):
    """El botón Cancelar de la interfaz solo descarta la validación en el cliente:
    sin confirmar, no debe quedar nada en SQLite."""
    validated = validate(client, "df14a.csv", csv_bytes(DF14A_HEADER + "1001,Ana,3001,Analisis,Por Certificar\n"))
    assert client.get(f"/api/imports/{validated['validation_id']}/preview").status_code == 200

    assert all(count == 0 for count in table_counts(client).values())
    assert client.get("/api/imports/history").json()["items"] == []
    assert client.get("/api/learners").json()["total"] == 0


def test_abandoned_import_does_not_block_a_later_import_of_the_same_file(client):
    content = csv_bytes(DF14A_HEADER + "1001,Ana,3001,Analisis,Por Certificar\n")
    validate(client, "df14a.csv", content)  # abandonada

    second = validate(client, "df14a.csv", content)
    confirmed = client.post(f"/api/imports/{second['validation_id']}/confirm").json()

    assert confirmed["new_records"] == 1
    assert client.get("/api/learners").json()["total"] == 1


# --- Errores de validación no dejan registros parciales ------------------------------------


def test_invalid_files_never_leave_partial_records(client):
    bad_uploads = [
        ("vacio.csv", b""),
        ("df14a.pdf", b"%PDF-1.4 no es un df14a"),  # extensión incompatible con DF14A
        ("df14a.csv", b"\xff\xfe\x00"),  # contenido ilegible
    ]
    for filename, content in bad_uploads:
        response = client.post(
            "/api/files/validate",
            data={"information_type": "df14a"},
            files={"file": (filename, content, "application/octet-stream")},
        )
        if response.status_code == 200:
            validation_id = response.json()["validation_id"]
            if response.json()["status"] == "error":
                assert client.get(f"/api/imports/{validation_id}/preview").status_code == 400
                assert client.post(f"/api/imports/{validation_id}/confirm", json={"accept_missing_complementaria": True}).status_code == 400

    assert all(count == 0 for count in table_counts(client).values())


def test_confirm_of_unknown_validation_id_changes_nothing(client):
    import_df14a(client, "1001,Ana,3001,Analisis,Por Certificar\n")
    before = table_counts(client)

    assert client.post("/api/imports/no-existe/confirm").status_code == 404

    assert table_counts(client) == before


# --- Reimportación conserva integridad -----------------------------------------------------


def test_reimport_keeps_learner_id_requirements_and_act_links(client):
    import_df14a(client, "1001,Ana Lopez,3001,Analisis,Por Certificar\n")
    learner = client.get("/api/learners").json()["items"][0]
    client.post(
        f"/api/learners/{learner['id']}/requirements",
        json={"requirement_type": "documentation", "status": "Pendiente"},
    )
    act_id = client.post("/api/acts", json={"number": "ACT-1", "act_date": "2026-10-01"}).json()["id"]
    client.post(f"/api/acts/{act_id}/learners", json={"learner_id": learner["id"]})

    result = import_df14a(client, "1001,Ana Lopez,3001,Analisis,Certificado\n")

    # Nota: una fila con contenido distinto cuenta como registro "nuevo" del historial
    # (la llave es un hash del contenido); el aprendiz sí se actualiza sin duplicarse.
    assert result["new_records"] + result["updated_records"] == 1
    after = client.get("/api/learners").json()["items"]
    assert len(after) == 1 and after[0]["id"] == learner["id"]
    assert after[0]["certification_status"] == "Certificado"
    detail = client.get(f"/api/learners/{learner['id']}").json()
    assert [a["number"] for a in detail["acts"]] == ["ACT-1"]
    assert len(client.get(f"/api/learners/{learner['id']}/requirements").json()["items"]) == 1


def test_reimport_of_xlsx_and_csv_with_same_document_does_not_duplicate(client):
    import_df14a(client, "TI_1001,Ana,3001,Analisis,Por Certificar\n")
    xlsx = xlsx_bytes(
        [{"DOCUMENTO": "CC_1001", "NOMBRES": "Ana", "FICHA": "3001", "PROGRAMA": "Analisis",
          "ESTADO_ASPIRANTE": "Por Certificar"}]
    )
    validated = validate(client, "df14a.xlsx", xlsx)
    client.post(f"/api/imports/{validated['validation_id']}/confirm")

    assert client.get("/api/learners").json()["total"] == 1


# --- Búsqueda y paginación -----------------------------------------------------------------


def test_search_status_and_pagination_work_together(client):
    rows = "".join(
        f"{2000 + i},Aprendiz {i:02d},4001,Programa {'A' if i % 2 else 'B'},"
        f"{'Por Certificar' if i % 3 == 0 else 'En Formacion'}\n"
        for i in range(12)
    )
    import_df14a(client, rows)

    page1 = client.get("/api/learners", params={"status": "Por Certificar", "page_size": 3, "page": 1}).json()
    page2 = client.get("/api/learners", params={"status": "Por Certificar", "page_size": 3, "page": 2}).json()
    beyond = client.get("/api/learners", params={"status": "Por Certificar", "page_size": 3, "page": 9}).json()

    assert page1["total"] == page2["total"] == 4  # i = 0, 3, 6, 9
    assert (len(page1["items"]), len(page2["items"])) == (3, 1)
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})
    assert beyond["items"] == [] and beyond["total"] == 4
    assert client.get("/api/learners", params={"search": "Programa A", "page_size": 100}).json()["total"] == 6


# --- Actas: edición, eliminación y consistencia --------------------------------------------


def test_editing_act_keeps_its_learner_associations(client):
    import_df14a(client, "1001,Ana,3001,Analisis,Por Certificar\n1002,Luis,3001,Analisis,Por Certificar\n")
    learners = client.get("/api/learners").json()["items"]
    act_id = client.post("/api/acts", json={"number": "ACT-1", "act_date": "2026-10-01"}).json()["id"]
    for learner in learners:
        client.post(f"/api/acts/{act_id}/learners", json={"learner_id": learner["id"]})

    client.patch(f"/api/acts/{act_id}", json={"number": "ACT-1B", "review_status": "reviewed"})

    detail = client.get(f"/api/acts/{act_id}").json()
    assert detail["number"] == "ACT-1B" and detail["review_status"] == "reviewed"
    assert detail["learners_count"] == 2
    assert {item["id"] for item in detail["learners"]} == {item["id"] for item in learners}


def test_deleting_act_keeps_learners_requirements_and_import_history(client):
    import_df14a(client, "1001,Ana,3001,Analisis,Por Certificar\n")
    learner_id = client.get("/api/learners").json()["items"][0]["id"]
    client.post(
        f"/api/learners/{learner_id}/requirements",
        json={"requirement_type": "documentation", "status": "Pendiente"},
    )
    act_id = client.post("/api/acts", json={"number": "ACT-1", "act_date": "2026-10-01"}).json()["id"]
    client.post(f"/api/acts/{act_id}/learners", json={"learner_id": learner_id})

    assert client.delete(f"/api/acts/{act_id}").status_code == 204

    counts = table_counts(client)
    assert (counts["acts"], counts["act_learners"]) == (0, 0)
    assert (counts["learners"], counts["requirements"], counts["import_history"]) == (1, 1, 1)
    assert client.get(f"/api/acts/{act_id}").status_code == 404


def test_link_and_unlink_update_act_list_counts(client):
    import_df14a(client, "1001,Ana,3001,Analisis,Por Certificar\n")
    learner_id = client.get("/api/learners").json()["items"][0]["id"]
    act_id = client.post("/api/acts", json={"number": "ACT-1", "act_date": "2026-10-01"}).json()["id"]

    client.post(f"/api/acts/{act_id}/learners", json={"learner_id": learner_id})
    assert client.get("/api/acts").json()["items"][0]["learners_count"] == 1
    client.delete(f"/api/acts/{act_id}/learners/{learner_id}")
    assert client.get("/api/acts").json()["items"][0]["learners_count"] == 0


def test_failed_act_creation_does_not_leave_records(client):
    client.post("/api/acts", json={"number": "ACT-1", "act_date": "2026-10-01"})

    duplicate = client.post("/api/acts", json={"number": "ACT-1", "act_date": "2026-10-02"})
    invalid_status = client.post(
        "/api/acts", json={"number": "ACT-2", "act_date": "2026-10-02", "review_status": "otro"}
    )
    missing_date = client.post("/api/acts", json={"number": "ACT-3"})

    assert (duplicate.status_code, invalid_status.status_code, missing_date.status_code) == (400, 400, 422)
    assert [a["number"] for a in client.get("/api/acts").json()["items"]] == ["ACT-1"]


# --- Contrato de la API que consume el frontend --------------------------------------------


def test_api_contract_matches_fields_used_by_frontend(client):
    validated = validate(client, "df14a.csv", csv_bytes(DF14A_HEADER + "1001,Ana,3001,Analisis,Por Certificar\n"))
    assert {"validation_id", "status", "message", "checks", "file_name", "information_type"} <= set(validated)
    assert {"label", "status"} <= set(validated["checks"][0])

    preview = client.get(f"/api/imports/{validated['validation_id']}/preview").json()
    assert {"new_records", "updated_records"} <= set(preview)

    confirmed = client.post(f"/api/imports/{validated['validation_id']}/confirm").json()
    assert {"new_records", "updated_records", "status"} <= set(confirmed)

    history_item = client.get("/api/imports/history").json()["items"][0]
    assert {"file_name", "information_type", "imported_at", "records_count"} <= set(history_item)

    learners = client.get("/api/learners").json()
    assert {"items", "total", "page", "pages", "statuses", "por_certificar_total"} <= set(learners)
    assert {"id", "name", "identification", "program", "group_code", "certification_status"} <= set(
        learners["items"][0]
    )

    act_id = client.post("/api/acts", json={"number": "ACT-1", "act_date": "2026-10-01"}).json()["id"]
    client.post(f"/api/acts/{act_id}/learners", json={"learner_id": learners["items"][0]["id"]})
    act_item = client.get("/api/acts").json()["items"][0]
    assert {"id", "number", "act_date", "act_type", "review_status", "learners_count"} <= set(act_item)
    act_detail = client.get(f"/api/acts/{act_id}").json()
    assert {"number", "act_date", "act_type", "review_status", "original_file", "observations", "learners"} <= set(
        act_detail
    )
    assert {"id", "name", "identification", "observations"} <= set(act_detail["learners"][0])


# --- Importar un "Acta de certificación" ---------------------------------------------------


def test_acta_import_creates_act_and_links_learners_by_document(client):
    """Confirmar un acta registra el acta y asocia aprendices por documento.

    La importación se conserva en el historial y no se deduce un estado de
    certificación: figurar en el acta no equivale a tener el certificado.
    """
    from tests.conftest import docx_bytes

    content = docx_bytes(
        "ACTA DE CERTIFICACION No. 41\n"
        "Fecha: 15 de marzo de 2026\n"
        "1 LAURA SOFIA PEREZ GOMEZ 1043000100"
    )
    validated = validate(client, "acta.docx", content, information_type="acta")
    assert client.post(f"/api/imports/{validated['validation_id']}/confirm").status_code == 200

    counts = table_counts(client)
    assert counts["import_history"] == 1
    assert (counts["acts"], counts["act_learners"], counts["learners"]) == (1, 1, 1)
    detail = client.get("/api/acts").json()["items"][0]
    assert detail["number"] == "41"
    assert detail["learners_count"] == 1

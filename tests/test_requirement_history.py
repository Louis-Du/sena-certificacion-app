from __future__ import annotations

from io import BytesIO

import pandas as pd
from fastapi.testclient import TestClient

from app.models import Learner

HEADERS = [
    "NÚMERO DE DOCUMENTO",
    "NOMBRE",
    "FICHA",
    "PROGRAMA",
    "ESTADO",
    "BIBLIOTECA",
    "ALMACEN",
]


def _actas_xlsx(rows: list[dict]) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rows, columns=HEADERS).to_excel(
            writer, sheet_name="CERTIFICADOS", index=False
        )
    return buffer.getvalue()


def _import_actas(client: TestClient, rows: list[dict]) -> None:
    validated = client.post(
        "/api/files/validate",
        data={"information_type": "actas_completo"},
        files={"file": ("ACTAS_2026.xlsx", _actas_xlsx(rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["status"] in {"ready", "warning"}, validated.text
    confirmed = client.post(f"/api/imports/{validated.json()['validation_id']}/confirm", json={"accept_missing_complementaria": True})
    assert confirmed.status_code == 200, confirmed.text


def _detailed_history(client: TestClient, learner_id: int) -> list[dict]:
    response = client.get(f"/api/learners/{learner_id}")
    assert response.status_code == 200
    return response.json()["requirement_history"]


def test_requirement_history_empty_for_learner_without_requirements(client: TestClient):
    with client.session_factory() as session:
        learner = Learner(
            identification="7001",
            name="Sin requisitos",
            certification_status="Por Certificar",
        )
        session.add(learner)
        session.commit()
        learner_id = learner.id

    assert _detailed_history(client, learner_id) == []


def test_requirement_history_first_import_and_same_status_is_not_duplicated(client: TestClient):
    row = {
        "NÚMERO DE DOCUMENTO": "7002",
        "NOMBRE": "Ana Historia",
        "FICHA": "5001",
        "PROGRAMA": "Software",
        "ESTADO": "CERTIFICADOS",
        "BIBLIOTECA": "X",
        "ALMACEN": "",
    }
    _import_actas(client, [row])
    learner_id = client.get("/api/learners").json()["items"][0]["id"]

    history = _detailed_history(client, learner_id)
    assert len(history) == 2
    by_type = {item["requirement_type"]: item for item in history}
    assert by_type["biblioteca"]["status"] == "Cumplido"
    assert by_type["almacen"]["status"] == "Pendiente"
    assert all(item["source"] == "import:actas_completo" for item in history)
    assert all(item["recorded_at"] for item in history)

    # Repetir exactamente la misma importacion no debe agregar eventos.
    _import_actas(client, [row])
    assert len(_detailed_history(client, learner_id)) == 2


def test_requisitos_import_records_history_with_its_own_source(client: TestClient):
    content = (
        "DOCUMENTO,NOMBRES,REQUISITO,ESTADO,OBSERVACIONES\n"
        "7004,Carlos Matriz,Saber TyT,Pendiente,Presenta en noviembre\n"
        "7005,Diana Matriz,APE,Pendiente,Inscripcion pendiente\n"
    ).encode("utf-8")

    for _ in range(2):
        validated = client.post(
            "/api/files/validate",
            data={"information_type": "requisitos"},
            files={"file": ("requisitos.csv", content, "text/csv")},
        )
        assert validated.status_code == 200, validated.text
        confirmed = client.post(f"/api/imports/{validated.json()['validation_id']}/confirm", json={"accept_missing_complementaria": True})
        assert confirmed.status_code == 200, confirmed.text

    learners = {
        item["identification"]: item["id"]
        for item in client.get("/api/learners").json()["items"]
    }
    history_carlos = _detailed_history(client, learners["7004"])
    history_diana = _detailed_history(client, learners["7005"])

    # El historial queda aislado por aprendiz y requirement_type.
    assert len(history_carlos) == 1
    assert history_carlos[0]["requirement_type"] == "saber_tyt"
    assert history_carlos[0]["requirement_label"] == "Saber TyT"
    assert history_carlos[0]["status"] == "Pendiente"
    assert history_carlos[0]["source"] == "import:requisitos"

    assert len(history_diana) == 1
    assert history_diana[0]["requirement_type"] == "ape"
    assert history_diana[0]["status"] == "Pendiente"


def test_requirement_history_change_via_import_and_manual_keeps_current_status(client: TestClient):
    row = {
        "NÚMERO DE DOCUMENTO": "7003",
        "NOMBRE": "Luis Historia",
        "FICHA": "5002",
        "PROGRAMA": "Software",
        "ESTADO": "CERTIFICADOS",
        "BIBLIOTECA": "X",
        "ALMACEN": "",
    }
    _import_actas(client, [row])
    learner_id = client.get("/api/learners").json()["items"][0]["id"]

    # Cambio por importacion: Pendiente -> Cumplido.
    row["ALMACEN"] = "X"
    _import_actas(client, [row])

    detail = client.get(f"/api/learners/{learner_id}").json()
    history = [
        item for item in detail["requirement_history"] if item["requirement_type"] == "almacen"
    ]
    assert [item["status"] for item in history] == ["Cumplido", "Pendiente"]
    assert history[0]["source"] == "import:actas_completo"
    assert next(
        item for item in detail["requirements"] if item["requirement_type"] == "almacen"
    )["status"] == "Cumplido"

    # Cambio manual: Cumplido -> No aplica; queda un tercer evento manual.
    requirement = next(
        item for item in detail["requirements"] if item["requirement_type"] == "almacen"
    )
    updated = client.patch(
        f"/api/learners/{learner_id}/requirements/{requirement['id']}",
        json={
            "requirement_type": "almacen",
            "status": "No aplica",
            "observations": "Cambio manual de prueba.",
        },
    )
    assert updated.status_code == 200

    detail = client.get(f"/api/learners/{learner_id}").json()
    history = [
        item for item in detail["requirement_history"] if item["requirement_type"] == "almacen"
    ]
    assert len(history) == 3
    assert [item["status"] for item in history] == ["No aplica", "Cumplido", "Pendiente"]
    assert history[0]["source"] == "manual"
    assert history[0]["requirement_label"] == "Paz y salvo almacén"
    assert next(
        item for item in detail["requirements"] if item["requirement_type"] == "almacen"
    )["status"] == "No aplica"

    # Repetir el mismo estado manual no genera un evento duplicado.
    repeated = client.patch(
        f"/api/learners/{learner_id}/requirements/{requirement['id']}",
        json={"requirement_type": "almacen", "status": "No aplica"},
    )
    assert repeated.status_code == 200
    assert (
        len(
            [
                item
                for item in _detailed_history(client, learner_id)
                if item["requirement_type"] == "almacen"
            ]
        )
        == 3
    )

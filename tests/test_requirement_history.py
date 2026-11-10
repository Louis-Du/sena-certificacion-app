from __future__ import annotations

from datetime import datetime, timezone
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

HEADERS_CON_FECHAS = [
    "NÚMERO DE DOCUMENTO",
    "NOMBRE",
    "FICHA",
    "PROGRAMA",
    "ESTADO",
    "BIBLIOTECA",
    "FECHA DE RECIBIDO (PAZ Y SALVO BIBLIOTECA)",
    "BIENESTAR DEL APRENDIZ",
    "FECHA DE RECIBIDO (BIENESTAR DEL APRENDIZ)",
    "ALMACEN",
    "FECHA DE RECIBIDO (PAZ Y SALVO ALMACEN)",
    "FECHA DE RECIBIDO EN ADMON EDUCATIVA",
]


def _actas_xlsx(rows: list[dict], columns: list[str] | None = None) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rows, columns=columns or HEADERS).to_excel(
            writer, sheet_name="CERTIFICADOS", index=False
        )
    return buffer.getvalue()


def _import_actas(
    client: TestClient, rows: list[dict], columns: list[str] | None = None
) -> None:
    validated = client.post(
        "/api/files/validate",
        data={"information_type": "actas_completo"},
        files={"file": ("ACTAS_2026.xlsx", _actas_xlsx(rows, columns), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
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
    # Una celda vacía no se interpreta como Pendiente: queda Sin información.
    assert by_type["almacen"]["status"] == "Sin información"
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

    # Cambio por importacion: Sin información -> Cumplido.
    row["ALMACEN"] = "X"
    _import_actas(client, [row])

    detail = client.get(f"/api/learners/{learner_id}").json()
    history = [
        item for item in detail["requirement_history"] if item["requirement_type"] == "almacen"
    ]
    assert [item["status"] for item in history] == ["Cumplido", "Sin información"]
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
    assert [item["status"] for item in history] == [
        "No aplica",
        "Cumplido",
        "Sin información",
    ]
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


def _history_by_type(history: list[dict]) -> dict[str, dict]:
    return {item["requirement_type"]: item for item in history}


def test_actas_import_uses_received_dates_for_requirement_history(client: TestClient):
    """Las fechas del consolidado alimentan el historial, no la fecha de carga."""
    row = {
        "NÚMERO DE DOCUMENTO": "79889414",
        "NOMBRE": "JESUS ADRIAN",
        "FICHA": "2374476",
        "PROGRAMA": "ADSI",
        "ESTADO": "PENDIENTE",
        "BIBLIOTECA": "X",
        "FECHA DE RECIBIDO (PAZ Y SALVO BIBLIOTECA)": "28/02/2025",
        "BIENESTAR DEL APRENDIZ": "X",
        # Fecha real de Excel (se guarda como fecha, no como texto).
        "FECHA DE RECIBIDO (BIENESTAR DEL APRENDIZ)": pd.Timestamp("2025-03-03"),
        "ALMACEN": "X",
        "FECHA DE RECIBIDO (PAZ Y SALVO ALMACEN)": "2025-03-05",
        # No es un requisito de la matriz: no debe aparecer en el historial.
        "FECHA DE RECIBIDO EN ADMON EDUCATIVA": "26/02/2025",
    }
    _import_actas(client, [row], columns=HEADERS_CON_FECHAS)
    learner_id = client.get("/api/learners").json()["items"][0]["id"]

    detail = client.get(f"/api/learners/{learner_id}").json()
    history = detail["requirement_history"]
    by_type = _history_by_type(history)

    # La fecha administrativa se conserva en seguimiento, no como requisito.
    assert detail["basic_info"]["administrative_receipt_date"] == "2025-02-26"
    assert all(
        item["requirement_type"] != "fecha_recibido_admon_educativa"
        for item in detail["requirements"]
    )

    assert by_type["biblioteca"]["status"] == "Cumplido"
    assert by_type["biblioteca"]["recorded_at"].startswith("2025-02-28T12:00:00")
    assert by_type["biblioteca"]["source"] == "import:actas_completo"
    assert by_type["biblioteca"]["note"] == "Fecha de recibido según consolidado"

    assert by_type["bienestar"]["status"] == "Cumplido"
    assert by_type["bienestar"]["recorded_at"].startswith("2025-03-03T12:00:00")

    assert by_type["almacen"]["status"] == "Cumplido"
    assert by_type["almacen"]["recorded_at"].startswith("2025-03-05T12:00:00")

    # La fecha administrativa no se convierte en requisito ni en evento.
    assert "fecha_recibido_admon_educativa" not in by_type
    assert all(
        "admon" not in (item["requirement_type"] or "")
        for item in history
    )


def test_actas_import_without_received_date_does_not_invent_one(client: TestClient):
    row = {
        "NÚMERO DE DOCUMENTO": "79889415",
        "NOMBRE": "SIN FECHA",
        "FICHA": "2374476",
        "PROGRAMA": "ADSI",
        "ESTADO": "PENDIENTE",
        "BIBLIOTECA": "X",
        "FECHA DE RECIBIDO (PAZ Y SALVO BIBLIOTECA)": "",
        "BIENESTAR DEL APRENDIZ": "",
        "FECHA DE RECIBIDO (BIENESTAR DEL APRENDIZ)": "",
        "ALMACEN": "",
        "FECHA DE RECIBIDO (PAZ Y SALVO ALMACEN)": "",
        "FECHA DE RECIBIDO EN ADMON EDUCATIVA": "26/02/2025",
    }
    _import_actas(client, [row], columns=HEADERS_CON_FECHAS)
    learner_id = client.get("/api/learners").json()["items"][0]["id"]

    biblioteca = _history_by_type(_detailed_history(client, learner_id))["biblioteca"]
    assert biblioteca["status"] == "Cumplido"
    assert biblioteca["note"] is None
    # Se conserva la marca de la importacion; no se fabrica una fecha recibida.
    assert biblioteca["recorded_at"].startswith(
        datetime.now(timezone.utc).date().isoformat()
    )


def test_actas_import_date_without_mark_does_not_mark_fulfilled(client: TestClient):
    row = {
        "NÚMERO DE DOCUMENTO": "79889416",
        "NOMBRE": "FECHA SIN MARCA",
        "FICHA": "2374476",
        "PROGRAMA": "ADSI",
        "ESTADO": "PENDIENTE",
        "BIBLIOTECA": "",
        "FECHA DE RECIBIDO (PAZ Y SALVO BIBLIOTECA)": "",
        "BIENESTAR DEL APRENDIZ": "",
        "FECHA DE RECIBIDO (BIENESTAR DEL APRENDIZ)": "",
        "ALMACEN": "",
        "FECHA DE RECIBIDO (PAZ Y SALVO ALMACEN)": "28/02/2025",
        "FECHA DE RECIBIDO EN ADMON EDUCATIVA": "",
    }
    _import_actas(client, [row], columns=HEADERS_CON_FECHAS)
    learner_id = client.get("/api/learners").json()["items"][0]["id"]

    detail = client.get(f"/api/learners/{learner_id}").json()
    requirements = {
        item["requirement_type"]: item["status"] for item in detail["requirements"]
    }
    # La fecha aislada no convierte una celda vacía en Pendiente ni en Cumplido.
    assert requirements["almacen"] == "Sin información"

    almacen_events = [
        item
        for item in detail["requirement_history"]
        if item["requirement_type"] == "almacen"
    ]
    assert [item["status"] for item in almacen_events] == ["Sin información"]
    assert not almacen_events[0]["recorded_at"].startswith("2025-02-28")
    assert almacen_events[0]["note"] is None


def test_reimport_with_received_dates_does_not_duplicate_history(client: TestClient):
    row = {
        "NÚMERO DE DOCUMENTO": "79889417",
        "NOMBRE": "REIMPORTADO",
        "FICHA": "2374476",
        "PROGRAMA": "ADSI",
        "ESTADO": "PENDIENTE",
        "BIBLIOTECA": "X",
        "FECHA DE RECIBIDO (PAZ Y SALVO BIBLIOTECA)": "28/02/2025",
        "BIENESTAR DEL APRENDIZ": "",
        "FECHA DE RECIBIDO (BIENESTAR DEL APRENDIZ)": "",
        "ALMACEN": "",
        "FECHA DE RECIBIDO (PAZ Y SALVO ALMACEN)": "",
        "FECHA DE RECIBIDO EN ADMON EDUCATIVA": "",
    }
    _import_actas(client, [row], columns=HEADERS_CON_FECHAS)
    _import_actas(client, [row], columns=HEADERS_CON_FECHAS)
    learner_id = client.get("/api/learners").json()["items"][0]["id"]

    biblioteca_events = [
        item
        for item in _detailed_history(client, learner_id)
        if item["requirement_type"] == "biblioteca"
    ]
    assert len(biblioteca_events) == 1
    assert biblioteca_events[0]["recorded_at"].startswith("2025-02-28T12:00:00")

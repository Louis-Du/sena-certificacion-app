from __future__ import annotations

import json
from io import BytesIO

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.models import ImportHistory, ImportedRecord, Learner, Requirement
from app.services.imports import confirm_import, stage_file
from app.services.indicadores import compute_indicadores_2026
from tests.conftest import csv_bytes, docx_bytes, xlsx_bytes


def _multi_sheet_actas_xlsx(
    certificados: list[dict] | None = None,
    pendientes: list[dict] | None = None,
    complementaria: list[list] | None = None,
    meta: list[list] | None = None,
) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        if certificados is not None:
            pd.DataFrame(certificados).to_excel(writer, sheet_name="CERTIFICADOS", index=False)
        if pendientes is not None:
            pd.DataFrame(pendientes).to_excel(writer, sheet_name="PENDIENTES", index=False)
        if complementaria is not None:
            pd.DataFrame(complementaria).to_excel(writer, sheet_name="COMPLEMENTARIA", header=False, index=False)
        if meta is not None:
            pd.DataFrame(meta).to_excel(writer, sheet_name="META", header=False, index=False)
    return buffer.getvalue()


def test_information_types_exposes_three_main_sources_plus_secondary(client: TestClient):
    response = client.get("/api/information-types")
    assert response.status_code == 200
    data = response.json()

    assert "categories" in data
    category_ids = [cat["id"] for cat in data["categories"]]
    assert category_ids == [
        "actas_oficiales",
        "df14a",
        "actas_2026",
        "requisitos_aprendices",
    ]

    # Las tres fuentes principales mapean al tipo interno que las procesa.
    main_types = {
        cat["id"]: cat["types"]
        for cat in data["categories"]
        if not cat.get("secondary")
    }
    assert main_types == {
        "actas_oficiales": ["acta"],
        "df14a": ["df14a"],
        "actas_2026": ["actas_completo"],
    }

    # Requisitos se conserva como carga secundaria.
    secundaria = next(cat for cat in data["categories"] if cat["id"] == "requisitos_aprendices")
    assert secundaria.get("secondary") is True
    assert secundaria["types"] == ["requisitos"]


def test_excel_institucional_multi_sheet_upload_flow(client: TestClient):
    cert_rows = [
        {
            "NIVEL": "TECNÓLOGO",
            "NÚMERO DE DOCUMENTO": "1001",
            "NOMBRE": "Ana",
            "APELLIDOS": "Perez",
            "FICHA": "3001",
            "ESTADO": "CERTIFICADOS",
            "MES DE CERTIFICACION": "JUNIO",
            "ACTA": "36",
        }
    ]
    pend_rows = [
        {
            "NIVEL": "TÉCNICO",
            "NÚMERO DE DOCUMENTO": "2001",
            "NOMBRE": "Carlos",
            "APELLIDOS": "Gomez",
            "FICHA": "3002",
            "ESTADO": "PENDIENTE",
            "MOTIVO DE NO CERTIFICACIÓN": "Falta etapa productiva",
        }
    ]
    comp_rows = [
        ["2026-03-10", 50, None, "2026-04-10", 30, None, None, None, None, None, None, None],
    ]
    meta_rows = [
        ["METAS DE CERTIFICACIÓN"],
        [
            "TECNICO LABORAL Y OTROS",
            "ARTICULACION CON LA MEDIA",
            "EDUCACIÓN SUPERIOR",
            "TOTAL TITULADA",
            "TOTAL COMPLEMENTARIA",
            "TOTAL FORMACIÓN PROFESIONAL",
        ],
        [200, 50, 100, 350, 1000, 1350],
    ]

    excel_content = _multi_sheet_actas_xlsx(cert_rows, pend_rows, comp_rows, meta_rows)

    val_res = client.post(
        "/api/files/validate",
        data={"information_type": "actas_completo"},
        files={"file": ("ACTAS 2026.xlsx", excel_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["status"] == "ready"
    assert any("Hoja CERTIFICADOS detectada" in c["label"] for c in val_data["checks"])
    assert any("Hoja PENDIENTES detectada" in c["label"] for c in val_data["checks"])
    assert any("Hoja COMPLEMENTARIA detectada" in c["label"] for c in val_data["checks"])
    assert any("Hoja META detectada" in c["label"] for c in val_data["checks"])

    validation_id = val_data["validation_id"]
    confirm_res = client.post(f"/api/imports/{validation_id}/confirm")
    assert confirm_res.status_code == 200

    # Comprobar que los aprendices se sincronizaron en SQLite
    learners_res = client.get("/api/learners")
    assert learners_res.status_code == 200
    identifications = {item["identification"] for item in learners_res.json()["items"]}
    assert "1001" in identifications
    assert "2001" in identifications

    # Comprobar que los indicadores se calcularon sin error
    indicadores_res = client.get("/api/indicadores")
    assert indicadores_res.status_code == 200
    ind_data = indicadores_res.json()
    metricas = {m["category"]: m for m in ind_data["metricas"]}
    assert metricas["superior"]["certificados"] == 1
    assert metricas["complementaria"]["certificados"] == 80
    assert ind_data["total_certificados"] == 81
    assert ind_data["total_pendientes"] == 1
    assert ind_data["total_meta"] == 1350


def test_csv_alternativo_autodetects_certificados_and_pendientes(client: TestClient):
    # 1. Probar CSV de pendientes
    pend_csv = (
        "NIVEL,FICHA,PROGRAMA,NÚMERO DE DOCUMENTO,NOMBRE,APELLIDOS,ESTADO,MOTIVO DE NO CERTIFICACIÓN\n"
        "TÉCNICO,4001,Sistemas,3001,Laura,Torres,PENDIENTE,Pendiente paz y salvo\n"
    ).encode("utf-8")

    val_pend = client.post(
        "/api/files/validate",
        data={"information_type": "csv_certificacion"},
        files={"file": ("pendientes.csv", pend_csv, "text/csv")},
    )
    assert val_pend.status_code == 200
    assert val_pend.json()["status"] == "ready"
    assert any("Listado de pendientes" in c["label"] for c in val_pend.json()["checks"])

    # 2. Probar CSV de certificados
    cert_csv = (
        "NIVEL,FICHA,PROGRAMA,NÚMERO DE DOCUMENTO,NOMBRE,APELLIDOS,ESTADO,MES DE CERTIFICACION,ACTA\n"
        "TECNÓLOGO,4002,Contabilidad,4001,Mario,Luna,CERTIFICADOS,MAYO,36\n"
    ).encode("utf-8")

    val_cert = client.post(
        "/api/files/validate",
        data={"information_type": "csv_certificacion"},
        files={"file": ("certificados.csv", cert_csv, "text/csv")},
    )
    assert val_cert.status_code == 200
    assert val_cert.json()["status"] == "ready"
    assert any("Listado de certificados" in c["label"] for c in val_cert.json()["checks"])


def test_csv_alternativo_deduplicates_against_excel_and_does_not_increment_indicators(client: TestClient):
    # Paso 1: Importar ACTAS 2026.xlsx con aprendiz 5001 certificado
    cert_rows = [
        {
            "NIVEL": "TECNÓLOGO",
            "NÚMERO DE DOCUMENTO": "5001",
            "NOMBRE": "Camila",
            "APELLIDOS": "Rios",
            "FICHA": "3001",
            "ESTADO": "CERTIFICADOS",
            "MES DE CERTIFICACION": "JUNIO",
            "ACTA": "36",
        }
    ]
    excel_content = _multi_sheet_actas_xlsx(certificados=cert_rows)

    val_excel = client.post(
        "/api/files/validate",
        data={"information_type": "actas_completo"},
        files={"file": ("ACTAS 2026.xlsx", excel_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    client.post(f"/api/imports/{val_excel.json()['validation_id']}/confirm")

    ind_before = client.get("/api/indicadores").json()
    assert ind_before["total_certificados"] == 1

    # Paso 2: Importar CSV alternativo que contiene exactamente los mismos datos del aprendiz 5001
    csv_content = (
        "NIVEL,FICHA,PROGRAMA,NÚMERO DE DOCUMENTO,NOMBRE,APELLIDOS,ESTADO,MES DE CERTIFICACION,ACTA\n"
        "TECNÓLOGO,3001,Software,5001,Camila,Rios,CERTIFICADOS,JUNIO,36\n"
    ).encode("utf-8")

    val_csv = client.post(
        "/api/files/validate",
        data={"information_type": "csv_certificacion"},
        files={"file": ("ACTAS 2026(CERTIFICADOS).csv", csv_content, "text/csv")},
    )
    assert val_csv.status_code == 200
    preview_res = client.get(f"/api/imports/{val_csv.json()['validation_id']}/preview").json()

    # Debe detectar que el registro ya existe y actualizar, no sumar nuevo
    assert preview_res["new_records"] == 0
    assert preview_res["updated_records"] == 1

    confirm_csv = client.post(f"/api/imports/{val_csv.json()['validation_id']}/confirm").json()
    assert confirm_csv["new_records"] == 0
    assert confirm_csv["updated_records"] == 1

    # Paso 3: Los indicadores NO deben incrementarse indebidamente
    ind_after = client.get("/api/indicadores").json()
    assert ind_after["total_certificados"] == 1

    # La tabla de aprendices tampoco debe duplicarse
    learners_res = client.get("/api/learners").json()
    assert learners_res["total"] == 1


def test_csv_imported_first_then_excel_does_not_duplicate(client: TestClient):
    # Paso 1: Importar CSV primero con aprendiz 7001
    csv_content = (
        "NIVEL,FICHA,PROGRAMA,NÚMERO DE DOCUMENTO,NOMBRE,APELLIDOS,ESTADO,MES DE CERTIFICACION,ACTA\n"
        "TECNÓLOGO,3001,Software,7001,David,Vargas,CERTIFICADOS,JUNIO,36\n"
    ).encode("utf-8")

    val_csv = client.post(
        "/api/files/validate",
        data={"information_type": "csv_certificacion"},
        files={"file": ("certificados.csv", csv_content, "text/csv")},
    )
    client.post(f"/api/imports/{val_csv.json()['validation_id']}/confirm")

    assert client.get("/api/indicadores").json()["total_certificados"] == 1

    # Paso 2: Importar Excel que contiene ese mismo aprendiz 7001
    cert_rows = [
        {
            "NIVEL": "TECNÓLOGO",
            "NÚMERO DE DOCUMENTO": "7001",
            "NOMBRE": "David",
            "APELLIDOS": "Vargas",
            "FICHA": "3001",
            "ESTADO": "CERTIFICADOS",
            "MES DE CERTIFICACION": "JUNIO",
            "ACTA": "36",
        }
    ]
    excel_content = _multi_sheet_actas_xlsx(certificados=cert_rows)

    val_excel = client.post(
        "/api/files/validate",
        data={"information_type": "actas_completo"},
        files={"file": ("ACTAS 2026.xlsx", excel_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    preview = client.get(f"/api/imports/{val_excel.json()['validation_id']}/preview").json()
    assert preview["new_records"] == 0
    assert preview["updated_records"] == 1

    client.post(f"/api/imports/{val_excel.json()['validation_id']}/confirm")
    assert client.get("/api/indicadores").json()["total_certificados"] == 1
    assert client.get("/api/learners").json()["total"] == 1


def test_requisitos_matrix_updates_learner_and_requirement_entities(client: TestClient):
    matrix_csv = (
        "DOCUMENTO,NOMBRES,REQUISITO,ESTADO,OBSERVACIONES\n"
        "8001,Carlos Ruiz,Etapa Productiva,Cumplido,Aprobado en empresa\n"
        "8002,Diana Gomez,Saber TyT,Pendiente,Presenta en noviembre\n"
    ).encode("utf-8")

    val_res = client.post(
        "/api/files/validate",
        data={"information_type": "requisitos"},
        files={"file": ("requisitos.csv", matrix_csv, "text/csv")},
    )
    assert val_res.status_code == 200
    assert val_res.json()["status"] == "ready"

    confirm_res = client.post(f"/api/imports/{val_res.json()['validation_id']}/confirm")
    assert confirm_res.status_code == 200

    # Verificar que los aprendices existen
    learners_res = client.get("/api/learners")
    items = {item["identification"]: item for item in learners_res.json()["items"]}
    assert "8001" in items
    assert "8002" in items

    # Verificar que Diana tiene requisito pendiente y aparece en el listado de pendientes
    pending_res = client.get("/api/learners/with-pending-requirements")
    pending_items = pending_res.json()["items"]
    assert any(p["identification"] == "8002" for p in pending_items)

    # Consultar detalle de Diana
    diana_id = items["8002"]["id"]
    detail_res = client.get(f"/api/learners/{diana_id}")
    assert detail_res.status_code == 200
    reqs = {r["requirement_type"]: r for r in detail_res.json()["requirements"]}
    assert reqs["saber_tyt"]["status"] == "Pendiente"
    assert "Presenta en noviembre" in (reqs["saber_tyt"]["observations"] or "")

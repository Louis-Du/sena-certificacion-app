from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.models import ImportedRecord, Learner
from tests.conftest import csv_bytes, xlsx_bytes


ROOT = Path(__file__).resolve().parents[1]
INCORRECTOS = ROOT / "archivos_prueba" / "incorrectos"
CORRECTOS = ROOT / "archivos_prueba" / "correctos"


def _file(path: Path) -> bytes:
    return path.read_bytes()


def _validate(client: TestClient, path: Path, information_type: str) -> dict:
    response = client.post(
        "/api/files/validate",
        data={"information_type": information_type},
        files={"file": (path.name, _file(path), "application/octet-stream")},
    )
    assert response.status_code == 200
    return response.json()


def _multi_sheet_xlsx(
    certificados: list[dict] | None = None,
    pendientes: list[dict] | None = None,
    complementaria: list[list] | None = None,
    meta: list[list] | None = None,
) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        if certificados is not None:
            pd.DataFrame(certificados).to_excel(
                writer, sheet_name="CERTIFICADOS", index=False
            )
        if pendientes is not None:
            pd.DataFrame(pendientes).to_excel(
                writer, sheet_name="PENDIENTES", index=False
            )
        if complementaria is not None:
            pd.DataFrame(complementaria).to_excel(
                writer, sheet_name="COMPLEMENTARIA", header=False, index=False
            )
        if meta is not None:
            pd.DataFrame(meta).to_excel(
                writer, sheet_name="META", header=False, index=False
            )
    return buffer.getvalue()


def _labels(body: dict) -> str:
    return " ".join(check["label"] for check in body["checks"])


@pytest.mark.parametrize(
    "name",
    [
        "Requisitos_incorrecto_sin_columnas_clave.xlsx",
        "Requisitos_pendientes_demo_incorrecto.xlsx",
    ],
)
def test_requisitos_file_uses_requisitos_rules_and_not_actas_rules(
    client: TestClient, name: str
):
    path = INCORRECTOS / name

    body = _validate(client, path, "requisitos")
    labels = _labels(body)

    assert body["status"] == "error"
    assert body["records_found"] == 2
    assert body["valid_records"] == 0
    assert body["rejected_records"] == 2
    assert body["missing_columns"] == ["DOCUMENTO", "NOMBRES", "REQUISITO", "ESTADO"]
    for column in body["missing_columns"]:
        assert column in labels
    # Hallazgo 1: un archivo de requisitos no debe evaluarse con las hojas de ACTAS.
    assert "CERTIFICADOS" not in labels
    assert "PENDIENTES" not in labels
    assert "COMPLEMENTARIA" not in labels


@pytest.mark.parametrize(
    "name",
    [
        "Requisitos_incorrecto_sin_columnas_clave.xlsx",
        "Requisitos_pendientes_demo_incorrecto.xlsx",
    ],
)
def test_requisitos_file_cannot_be_confirmed_without_importable_records(
    client: TestClient, name: str
):
    path = INCORRECTOS / name
    body = _validate(client, path, "requisitos")
    validation_id = body["validation_id"]

    assert client.get(f"/api/imports/{validation_id}/preview").status_code == 400
    assert client.post(f"/api/imports/{validation_id}/confirm").status_code == 400
    assert client.get("/api/imports/history").json()["items"] == []


@pytest.mark.parametrize(
    "name,information_type",
    [
        ("Acta_certificacion_incorrecto_vacio.pdf", "acta"),
        ("Acta_certificacion_23_demo_incorrecto_vacio.docx", "acta"),
    ],
)
def test_unreadable_pdf_and_docx_are_rejected_without_records(
    client: TestClient, name: str, information_type: str
):
    path = INCORRECTOS / name

    body = _validate(client, path, information_type)

    assert body["status"] == "error"
    assert body["records_found"] == 0
    assert body["valid_records"] == 0
    assert "No se pudo leer" in body["message"]
    # Hallazgo 1: un archivo ilegible no debe mostrar indicadores positivos de
    # apertura junto al estado NO APTO.
    labels = _labels(body)
    assert "abierto correctamente" not in labels
    assert "Contenido legible" in labels
    validation_id = body["validation_id"]
    assert client.get(f"/api/imports/{validation_id}/preview").status_code == 400
    assert client.post(f"/api/imports/{validation_id}/confirm").status_code == 400
    assert client.get("/api/imports/history").json()["items"] == []


def test_csv_without_required_columns_has_zero_valid_records(client: TestClient):
    path = INCORRECTOS / "ACTAS_2026_PENDIENTES_incorrecto_sin_documento.csv"

    body = _validate(client, path, "csv_certificacion")

    assert body["status"] == "error"
    assert body["records_found"] == 2
    assert body["valid_records"] == 0
    assert body["rejected_records"] == 2
    assert {"NÚMERO DE DOCUMENTO", "NOMBRE"}.issubset(set(body["missing_columns"]))
    assert "Falta NUMERO DE DOCUMENTO" in _labels(body)
    validation_id = body["validation_id"]
    assert client.get(f"/api/imports/{validation_id}/preview").status_code == 400
    assert client.post(f"/api/imports/{validation_id}/confirm").status_code == 400


def test_df14a_without_ficha_has_zero_importable_records(client: TestClient):
    path = INCORRECTOS / "DF14A_incorrecto_sin_ficha_y_nivel_invalido.xlsx"

    body = _validate(client, path, "df14a")

    assert body["status"] == "error"
    assert body["records_found"] == 2
    assert body["valid_records"] == 0
    assert body["rejected_records"] == 2
    assert "FICHA" in body["missing_columns"]
    labels = _labels(body)
    assert "Falta FICHA" in labels
    # El nivel sin clasificar se informa, pero no se inventa una equivalencia.
    assert "OPERARIO" in labels
    assert "CURSO_NO_FORMAL" in labels
    # Hallazgo 3: con 0 registros importables, la advertencia de nivel no debe
    # afirmar que esas filas se van a importar.
    assert "en filas rechazadas" in labels
    assert "no seran importadas" in labels
    assert "se importan" not in labels
    validation_id = body["validation_id"]
    assert client.get(f"/api/imports/{validation_id}/preview").status_code == 400
    assert client.post(f"/api/imports/{validation_id}/confirm").status_code == 400


def test_partial_import_saves_only_valid_unique_records(client: TestClient, tmp_path):
    path = tmp_path / "df14a_parcial.csv"
    path.write_bytes(
        csv_bytes(
            "FICHA,nombre,estado\n"
            "3001,Ana,Por Certificar\n"
            ",Luis,Por Certificar\n"
        )
    )

    body = _validate(client, path, "df14a")
    assert body["status"] == "warning"
    assert body["records_found"] == 2
    assert body["valid_records"] == 1
    assert body["rejected_records"] == 1

    preview = client.get(f"/api/imports/{body['validation_id']}/preview").json()
    assert preview["parsed_records"] == 2
    assert preview["records_count"] == 1
    assert preview["new_records"] == 1
    assert preview["rejected_records"] == 1

    confirmed = client.post(f"/api/imports/{body['validation_id']}/confirm").json()
    assert confirmed["records_count"] == 1
    assert confirmed["new_records"] == 1
    with client.session_factory() as session:
        rows = session.query(ImportedRecord).all()
        assert len(rows) == 1
        payload = json.loads(rows[0].payload)
        assert payload.get("FICHA") == "3001"


def test_duplicate_rows_are_counted_once_in_valid_records(client: TestClient, tmp_path):
    path = tmp_path / "df14a_duplicado.csv"
    path.write_bytes(
        csv_bytes(
            "FICHA,nombre,estado\n3001,Ana,Por Certificar\n3001,Ana,Por Certificar\n"
        )
    )

    body = _validate(client, path, "df14a")

    assert body["status"] == "warning"
    assert body["records_found"] == 2
    assert body["valid_records"] == 1
    assert body["duplicate_records"] == 1
    assert body["breakdown"]["df14a"]["valid_records"] == 1
    preview = client.get(f"/api/imports/{body['validation_id']}/preview").json()
    assert preview["records_count"] == 1
    assert preview["new_records"] == 1


def test_incorrect_actas_counters_match_preview_and_saved_records(client: TestClient):
    path = INCORRECTOS / "ACTAS_2026_incorrecto_conflictos_y_meses.xlsx"

    body = _validate(client, path, "actas_completo")

    assert body["status"] == "warning"
    assert body["records_found"] == 10
    assert body["valid_records"] == 10
    assert body["rejected_records"] == 0
    assert body["breakdown"]["certificados"]["valid_records"] == 4
    assert body["breakdown"]["pendientes"]["valid_records"] == 5
    assert body["breakdown"]["meta"]["valid_records"] == 1
    labels = _labels(body)
    assert "figuran simultáneamente en CERTIFICADOS y PENDIENTES" in labels
    assert "Elija el estado final" in labels
    assert "fuera del período" in labels
    conflicts = body["coherence_conflicts"]
    assert conflicts
    assert all(item["in_certificados"] and item["in_pendientes"] for item in conflicts)

    validation_id = body["validation_id"]
    preview = client.get(f"/api/imports/{validation_id}/preview")
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["parsed_records"] == 10
    assert preview_body["records_count"] == 10
    assert preview_body["new_records"] == 10
    assert preview_body["updated_records"] == 0
    assert preview_body["rejected_records"] == 0
    assert preview_body["coherence_conflicts"] == conflicts

    blocked = client.post(f"/api/imports/{validation_id}/confirm")
    assert blocked.status_code == 400
    assert "resolucion" in blocked.json()["detail"].lower()

    resolutions = [
        {"identification": item["identification"], "status": "CERTIFICADOS"}
        for item in conflicts
    ]
    confirmed = client.post(
        f"/api/imports/{validation_id}/confirm",
        json={"conflict_resolutions": resolutions},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["records_count"] == 10
    assert confirmed.json()["new_records"] == 10
    with client.session_factory() as session:
        assert session.query(ImportedRecord).count() == 10


def test_conflict_does_not_auto_change_existing_learner_status(client: TestClient, tmp_path):
    seed_path = tmp_path / "df14a_conflicto.csv"
    seed_path.write_bytes(
        csv_bytes(
            "DOCUMENTO,NOMBRES,FICHA,ESTADO_ASPIRANTE\n"
            "5555,Aprendiz En Conflicto,99999,Por Certificar\n"
        )
    )
    seed = _validate(client, seed_path, "df14a")
    assert client.post(f"/api/imports/{seed['validation_id']}/confirm").status_code == 200

    with client.session_factory() as session:
        learner = session.query(Learner).filter_by(identification="5555").one()
        assert learner.certification_status == "Por Certificar"

    conflict_path = tmp_path / "actas_conflicto.xlsx"
    conflict_path.write_bytes(
        _multi_sheet_xlsx(
            certificados=[
                {
                    "DOCUMENTO": "5555",
                    "NOMBRES": "Aprendiz En Conflicto",
                    "FICHA": "99999",
                    "ESTADO": "Certificado",
                }
            ],
            pendientes=[
                {
                    "DOCUMENTO": "5555",
                    "NOMBRES": "Aprendiz En Conflicto",
                    "FICHA": "99999",
                    "ESTADO": "Pendiente Documento",
                }
            ],
        )
    )
    body = _validate(client, conflict_path, "actas_completo")
    assert body["status"] == "warning"
    assert body["coherence_conflicts"] == [
        {
            "identification": "5555",
            "group_code": "99999",
            "name": "Aprendiz En Conflicto",
            "in_certificados": True,
            "in_pendientes": True,
        }
    ]
    blocked = client.post(f"/api/imports/{body['validation_id']}/confirm")
    assert blocked.status_code == 400

    confirmed = client.post(
        f"/api/imports/{body['validation_id']}/confirm",
        json={
            "conflict_resolutions": [
                {"identification": "5555", "status": "PENDIENTE"}
            ]
        },
    )
    assert confirmed.status_code == 200

    with client.session_factory() as session:
        learner = session.query(Learner).filter_by(identification="5555").one()
        assert learner.certification_status == "PENDIENTE"
        assert "Conflicto resuelto: Pendiente" in learner.tracking_notes
        assert "ACTAS 2026 · CERTIFICADOS" in learner.data_sources
        assert "ACTAS 2026 · PENDIENTES" in learner.data_sources
        assert session.query(ImportedRecord).filter_by(information_type="certificados").count() == 1
        assert session.query(ImportedRecord).filter_by(information_type="pendientes").count() == 1


def test_new_conflicted_learner_is_not_assigned_an_invented_status(
    client: TestClient, tmp_path
):
    conflict_path = tmp_path / "actas_conflicto_nuevo.xlsx"
    conflict_path.write_bytes(
        _multi_sheet_xlsx(
            certificados=[
                {
                    "DOCUMENTO": "7777",
                    "NOMBRES": "Nuevo En Conflicto",
                    "FICHA": "88888",
                    "ESTADO": "Certificado",
                }
            ],
            pendientes=[
                {
                    "DOCUMENTO": "7777",
                    "NOMBRES": "Nuevo En Conflicto",
                    "FICHA": "88888",
                    "ESTADO": "Pendiente Documento",
                }
            ],
        )
    )
    body = _validate(client, conflict_path, "actas_completo")
    assert body["status"] == "warning"
    assert [item["identification"] for item in body["coherence_conflicts"]] == ["7777"]
    confirmed = client.post(
        f"/api/imports/{body['validation_id']}/confirm",
        json={
            "conflict_resolutions": [
                {"identification": "7777", "status": "CERTIFICADOS"}
            ]
        },
    )
    assert confirmed.status_code == 200

    with client.session_factory() as session:
        learner = session.query(Learner).filter_by(identification="7777").one()
        assert learner.certification_status == "CERTIFICADOS"
        assert "Conflicto resuelto: Certificado" in learner.tracking_notes
        assert "ACTAS 2026 · CERTIFICADOS" in learner.data_sources
        assert "ACTAS 2026 · PENDIENTES" in learner.data_sources


def test_correct_actas_expands_complementaria_and_reports_the_breakdown(client: TestClient):
    path = CORRECTOS / "ACTAS_2026_correcto.xlsx"

    body = _validate(client, path, "actas_completo")

    assert body["status"] == "ready"
    assert body["records_found"] == 21
    assert body["valid_records"] == 21
    assert body["breakdown"] == {
        "certificados": {"records_found": 4, "valid_records": 4, "rejected_records": 0},
        "pendientes": {"records_found": 4, "valid_records": 4, "rejected_records": 0},
        "complementaria": {
            "records_found": 12,
            "valid_records": 12,
            "rejected_records": 0,
        },
        "meta": {"records_found": 1, "valid_records": 1, "rejected_records": 0},
    }

    validation_id = body["validation_id"]
    preview = client.get(f"/api/imports/{validation_id}/preview").json()
    assert preview["parsed_records"] == 21
    assert preview["records_count"] == 21
    assert preview["new_records"] == 21

    confirmed = client.post(f"/api/imports/{validation_id}/confirm").json()
    assert confirmed["records_count"] == 21
    assert confirmed["new_records"] == 21
    with client.session_factory() as session:
        assert session.query(ImportedRecord).count() == 21


def test_missing_complementaria_remains_an_explicit_warning(client: TestClient, tmp_path):
    content = _multi_sheet_xlsx(
        certificados=[
            {
                "DOCUMENTO": "1001",
                "NOMBRES": "Ana",
                "FICHA": "3001",
                "ESTADO": "Certificado",
            }
        ],
        pendientes=[],
        meta=[["METAS DE CERTIFICACION"], ["EDUCACION SUPERIOR"], [10]],
    )
    path = tmp_path / "ACTAS_sin_complementaria.xlsx"
    path.write_bytes(content)

    body = _validate(client, path, "actas_completo")
    labels = _labels(body)

    assert body["status"] == "warning"
    assert body["valid_records"] == 2
    assert "Hoja COMPLEMENTARIA no encontrada" in labels
    assert "decision administrativa pendiente" in labels


def test_unclassified_level_is_importable_but_reported_as_warning(client: TestClient, tmp_path):
    content = xlsx_bytes(
        [
            {
                "DOCUMENTO": "1001",
                "NOMBRES": "Ana",
                "FICHA": "3001",
                "NIVEL_FORMACION": "OPERARIO",
                "ESTADO_ASPIRANTE": "Por Certificar",
            }
        ]
    )
    path = tmp_path / "DF14A_nivel_sin_clasificar.xlsx"
    path.write_bytes(content)

    body = _validate(client, path, "df14a")
    labels = _labels(body)

    assert body["status"] == "warning"
    assert body["valid_records"] == 1
    assert "OPERARIO" in labels
    assert "no se asignan automaticamente" in labels


@pytest.mark.parametrize(
    "path,information_type",
    [
        (INCORRECTOS / "Acta_certificacion_correcto.pdf", "requisitos"),
        (CORRECTOS / "ACTAS_2026_PENDIENTES_correcto.csv", "acta"),
        (CORRECTOS / "DF14A_correcto.xlsx", "informe"),
        (CORRECTOS / "Requisitos_correcto.xlsx", "actas_completo"),
    ],
)
def test_category_and_format_mismatches_are_rejected(
    client: TestClient, path: Path, information_type: str
):
    if not path.exists():
        path = CORRECTOS / path.name

    body = _validate(client, path, information_type)

    assert body["status"] == "error"
    assert body["valid_records"] == 0
    if information_type == "actas_completo":
        assert "parece ser una matriz de requisitos" in body["message"]
    else:
        assert "no es compatible" in body["message"]


@pytest.mark.parametrize(
    "name,information_type",
    [
        ("DF14A_correcto.xlsx", "df14a"),
        ("DF14A_correcto.xls", "df14a"),
        ("DF14A_demo_correcto.xlsx", "df14a"),
        ("DF_14A_1_correcto.xml", "df14a"),
        ("ACTAS_2026_PENDIENTES_correcto.csv", "csv_certificacion"),
        ("ACTAS_2026_PENDIENTES_completo_correcto.csv", "csv_certificacion"),
        ("Acta_certificacion_correcto.pdf", "acta"),
        ("Acta_certificacion_23_demo_correcto.docx", "acta"),
        ("ACTAS_2026_correcto.xlsx", "actas_completo"),
        ("Requisitos_correcto.xlsx", "requisitos"),
        ("Requisitos_pendientes_demo_correcto.xlsx", "requisitos"),
    ],
)
def test_positive_files_are_importable(
    client: TestClient, name: str, information_type: str
):
    path = CORRECTOS / name

    body = _validate(client, path, information_type)

    assert body["status"] in {"ready", "warning"}
    assert body["valid_records"] and body["valid_records"] > 0
    validation_id = body["validation_id"]
    preview = client.get(f"/api/imports/{validation_id}/preview")
    assert preview.status_code == 200
    assert preview.json()["records_count"] == body["valid_records"]


# --- Actas oficiales: extraccion, registro del acta y vinculos --------------


def _acta_docx(
    number: str | None,
    act_date: str | None,
    learners: list[dict],
) -> bytes:
    """Construye un DOCX de acta con una tabla de aprendices."""
    from docx import Document

    document = Document()
    if number:
        document.add_paragraph(f"ACTA DE CERTIFICACION No. {number}")
    if act_date:
        document.add_paragraph(f"Fecha: {act_date}")
    table = document.add_table(rows=1, cols=5)
    for index, value in enumerate(["No.", "Documento", "Nombre", "Ficha", "Programa"]):
        table.rows[0].cells[index].text = value
    for index, learner in enumerate(learners, start=1):
        cells = table.add_row().cells
        values = [
            str(index),
            learner.get("documento", ""),
            learner.get("nombre", ""),
            learner.get("ficha", ""),
            learner.get("programa", ""),
        ]
        for column, value in enumerate(values):
            cells[column].text = value
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _acta_docx_text(number: str, act_date: str, learner_lines: list[str]) -> bytes:
    """Construye un DOCX de acta sin tabla (aprendices en parrafos de texto)."""
    from docx import Document

    document = Document()
    document.add_paragraph(f"ACTA DE CERTIFICACION No. {number}")
    document.add_paragraph(f"Fecha: {act_date}")
    for line in learner_lines:
        document.add_paragraph(line)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _acta_pdf(lines: list[str]) -> bytes:
    """Construye un PDF con una linea de texto por elemento."""
    import fitz

    document = fitz.open()
    page = document.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line)
        y += 16
    content = document.tobytes()
    document.close()
    return content


def _upload_bytes(
    client: TestClient, name: str, content: bytes, information_type: str = "acta"
) -> dict:
    response = client.post(
        "/api/files/validate",
        data={"information_type": information_type},
        files={"file": (name, content, "application/octet-stream")},
    )
    assert response.status_code == 200
    return response.json()


def _preview(client: TestClient, validation_id: str) -> dict:
    response = client.get(f"/api/imports/{validation_id}/preview")
    assert response.status_code == 200
    return response.json()


def _confirm(client: TestClient, validation_id: str) -> dict:
    response = client.post(f"/api/imports/{validation_id}/confirm")
    assert response.status_code == 200
    return response.json()


def _act_by_number(client: TestClient, number: str) -> dict | None:
    items = client.get("/api/acts").json()["items"]
    return next((item for item in items if item["number"] == number), None)


def _learners_by_identification(client: TestClient) -> dict[str, dict]:
    items = client.get("/api/learners").json()["items"]
    return {item["identification"]: item for item in items}


def test_acta_docx_with_table_registers_act_and_links_learners(client: TestClient):
    content = _acta_docx(
        "101",
        "02 de octubre de 2026",
        [
            {
                "documento": "1001001001",
                "nombre": "GOMEZ PEREZ LAURA SOFIA",
                "ficha": "3001",
                "programa": "ADSO",
            },
            {
                "documento": "1001001002",
                "nombre": "RUIZ DIAZ CARLOS",
                "ficha": "3001",
                "programa": "ADSO",
            },
        ],
    )

    body = _upload_bytes(client, "acta.docx", content)
    assert body["status"] == "ready"
    assert any("Acta identificada: No. 101" in check["label"] for check in body["checks"])

    preview = _preview(client, body["validation_id"])
    assert preview["acta"]["number"] == "101"
    assert preview["acta"]["exists"] is False
    assert preview["acta"]["learners_found"] == 2
    assert preview["acta"]["learners_to_link"] == 2
    assert preview["acta"]["learners_not_registered"] == ["1001001001", "1001001002"]

    _confirm(client, body["validation_id"])

    act = _act_by_number(client, "101")
    assert act is not None
    assert act["learners_count"] == 2
    detail = client.get(f"/api/acts/{act['id']}").json()
    assert detail["act_date"] == "2026-10-02"
    assert detail["original_file"] == "acta.docx"
    assert {learner["identification"] for learner in detail["learners"]} == {
        "1001001001",
        "1001001002",
    }

    # Figurar en un acta oficial marca al aprendiz como "Por Certificar" (apto
    # para certificacion), nunca como "Certificado": el certificado expedido solo
    # consta en el consolidado ACTAS 2026.
    learners = _learners_by_identification(client)
    assert learners["1001001001"]["certification_status"] == "Por Certificar"


def test_acta_docx_without_table_reads_learners_from_text(client: TestClient):
    content = _acta_docx_text(
        "102",
        "02 de octubre de 2026",
        [
            "- C.C. 1001002001 - TORRES MEZA ANA MARIA",
            "- C.C. 1001002002 - DIAZ LUNA PEDRO",
        ],
    )

    body = _upload_bytes(client, "acta_texto.docx", content)
    assert body["status"] == "ready"

    preview = _preview(client, body["validation_id"])
    assert preview["acta"]["learners_found"] == 2


def test_acta_pdf_reads_number_date_and_learners(client: TestClient):
    content = _acta_pdf(
        [
            "ACTA ORDINARIA No. 103",
            "Fecha: 15 de marzo de 2026",
            "- C.C. 1001003001 - MORENO SILVA LUIS",
        ]
    )

    body = _upload_bytes(client, "acta.pdf", content)
    assert body["status"] == "ready"

    preview = _preview(client, body["validation_id"])
    assert preview["acta"]["number"] == "103"
    assert preview["acta"]["act_date"] == "2026-03-15"
    assert preview["acta"]["learners_found"] == 1


def test_acta_without_number_is_rejected_and_not_registered(client: TestClient):
    content = _acta_docx_text(
        "",
        "02 de octubre de 2026",
        ["- C.C. 1001004001 - PRUEBA SIN NUMERO"],
    )

    body = _upload_bytes(client, "acta_sin_numero.docx", content)
    assert body["status"] == "error"
    assert body["valid_records"] == 0
    assert any(
        "no se registra un acta sin numero" in check["label"] for check in body["checks"]
    )

    # Sin registros importables la confirmacion queda bloqueada y no hay acta.
    confirm = client.post(f"/api/imports/{body['validation_id']}/confirm")
    assert confirm.status_code == 400
    assert client.get("/api/acts").json()["items"] == []


def test_acta_without_date_is_warning_but_still_importable(client: TestClient):
    content = _acta_docx(
        "104",
        None,
        [{"documento": "1001005001", "nombre": "SIN FECHA APRENDIZ"}],
    )

    body = _upload_bytes(client, "acta_sin_fecha.docx", content)
    assert body["status"] == "warning"
    assert any(
        "No se pudo identificar la fecha del acta" == check["label"]
        for check in body["checks"]
    )

    _confirm(client, body["validation_id"])
    act = _act_by_number(client, "104")
    assert act is not None
    assert act["act_date"] is None


def test_acta_reimport_does_not_duplicate_act_or_links(client: TestClient):
    content = _acta_docx(
        "105",
        "02 de octubre de 2026",
        [{"documento": "1001006001", "nombre": "REPETIDO APRENDIZ"}],
    )

    first = _upload_bytes(client, "acta.docx", content)
    _confirm(client, first["validation_id"])

    second = _upload_bytes(client, "acta.docx", content)
    preview = _preview(client, second["validation_id"])
    assert preview["acta"]["exists"] is True
    assert preview["acta"]["learners_to_link"] == 0
    assert preview["acta"]["learners_already_linked"] == 1

    _confirm(client, second["validation_id"])

    acts = [item for item in client.get("/api/acts").json()["items"] if item["number"] == "105"]
    assert len(acts) == 1
    assert acts[0]["learners_count"] == 1
    assert len(client.get("/api/learners").json()["items"]) == 1


def test_acta_reimport_does_not_overwrite_existing_fields_with_empty_values(
    client: TestClient,
):
    seeded = _upload_bytes(
        client,
        "acta.docx",
        _acta_docx("106", "02 de octubre de 2026", []),
    )
    _confirm(client, seeded["validation_id"])

    # Reimportar la misma acta sin fecha no debe borrar la fecha ya guardada.
    without_date = _upload_bytes(
        client,
        "acta.docx",
        _acta_docx("106", None, []),
    )
    _confirm(client, without_date["validation_id"])

    act = _act_by_number(client, "106")
    assert act is not None
    assert act["act_date"] == "2026-10-02"


def test_acta_links_existing_learner_imported_by_df14a(client: TestClient):
    df14a = (
        "DOCUMENTO,NOMBRES,FICHA,PROGRAMA,ESTADO_ASPIRANTE\n"
        "1001007001,APRENDIZ PREVIO,3001,ADSO,Por Certificar\n"
    ).encode("utf-8")
    seeded = _upload_bytes(client, "df14a.csv", df14a, information_type="df14a")
    _confirm(client, seeded["validation_id"])

    content = _acta_docx(
        "107",
        "02 de octubre de 2026",
        [{"documento": "1001007001", "nombre": "APRENDIZ PREVIO"}],
    )
    body = _upload_bytes(client, "acta.docx", content)
    preview = _preview(client, body["validation_id"])
    assert preview["acta"]["learners_to_link"] == 1
    assert preview["acta"]["learners_not_registered"] == []

    _confirm(client, body["validation_id"])

    # El aprendiz no se duplica y conserva su estado original.
    learners = _learners_by_identification(client)
    assert len(learners) == 1
    assert learners["1001007001"]["certification_status"] == "Por Certificar"


def test_acta_marks_learners_por_certificar_and_registers_source(client: TestClient):
    content = _acta_pdf(
        [
            "ACTA DE CERTIFICACION No. 41",
            "Fecha: 15 de marzo de 2026",
            "- C.C. 1001009001 - MARTINEZ LOPEZ ANA",
        ]
    )
    body = _upload_bytes(client, "acta_41.pdf", content)
    preview = _preview(client, body["validation_id"])
    assert preview["acta"]["learners_por_certificar"] == 1

    _confirm(client, body["validation_id"])

    listing = client.get("/api/learners").json()
    learners = {item["identification"]: item for item in listing["items"]}
    item = learners["1001009001"]
    # El acta lo marca apto para certificacion ("Por Certificar"), no certificado.
    assert item["certification_status"] == "Por Certificar"
    assert "certificado" not in item["certification_status"].lower()
    # La procedencia queda registrada con el numero de acta.
    assert item["data_sources"] == ["Acta 41"]
    # El contador y el filtro «Por Certificar» incluyen al aprendiz.
    assert listing["por_certificar_total"] == 1
    filtered = client.get("/api/learners", params={"status": "Por Certificar"}).json()
    assert [entry["identification"] for entry in filtered["items"]] == ["1001009001"]


def test_acta_does_not_demote_a_certified_learner(client: TestClient):
    with client.session_factory() as session:
        session.add(
            Learner(
                identification="1001009002",
                name="CERTIFICADO PREVIO",
                certification_status="CERTIFICADOS",
            )
        )
        session.commit()

    content = _acta_pdf(
        [
            "ACTA DE CERTIFICACION No. 42",
            "Fecha: 15 de marzo de 2026",
            "- C.C. 1001009002 - CERTIFICADO PREVIO",
        ]
    )
    body = _upload_bytes(client, "acta_42.pdf", content)
    preview = _preview(client, body["validation_id"])
    # Ya esta CERTIFICADO: no entra en el conteo de los que quedaran Por Certificar.
    assert preview["acta"]["learners_por_certificar"] == 0

    confirmed = _confirm(client, body["validation_id"])
    assert "conservan su estado del consolidado" in confirmed["message"]

    learners = _learners_by_identification(client)
    assert learners["1001009002"]["certification_status"] == "CERTIFICADOS"
    # El acta se registra igual como origen adicional.
    assert "Acta 42" in learners["1001009002"]["data_sources"]


def test_acta_keeps_pendiente_status_from_consolidado(client: TestClient):
    with client.session_factory() as session:
        session.add(
            Learner(
                identification="1001009003",
                name="PENDIENTE PREVIO",
                certification_status="PENDIENTE",
            )
        )
        session.commit()

    content = _acta_pdf(
        [
            "ACTA DE CERTIFICACION No. 43",
            "Fecha: 15 de marzo de 2026",
            "- C.C. 1001009003 - PENDIENTE PREVIO",
        ]
    )
    body = _upload_bytes(client, "acta_43.pdf", content)
    _confirm(client, body["validation_id"])

    learners = _learners_by_identification(client)
    # PENDIENTE del consolidado no se borra en silencio al figurar en el acta.
    assert learners["1001009003"]["certification_status"] == "PENDIENTE"
    assert "Acta 43" in learners["1001009003"]["data_sources"]


def test_acta_without_learner_identifications_does_not_associate_by_name(
    client: TestClient,
):
    # Una fila sin documento no se asocia aunque tenga nombre: solo se vincula la
    # persona cuya identificacion esta presente en el documento.
    content = _acta_docx(
        "109",
        "02 de octubre de 2026",
        [
            {"documento": "1001011001", "nombre": "CON DOCUMENTO APRENDIZ"},
            {"documento": "", "nombre": "SOLO NOMBRE APRENDIZ"},
        ],
    )

    body = _upload_bytes(client, "acta.docx", content)
    assert body["status"] == "ready"

    preview = _preview(client, body["validation_id"])
    assert preview["acta"]["learners_found"] == 1
    assert preview["acta"]["learners_to_link"] == 1

    _confirm(client, body["validation_id"])

    act = _act_by_number(client, "109")
    assert act is not None
    assert act["learners_count"] == 1
    learners = _learners_by_identification(client)
    assert set(learners) == {"1001011001"}


def test_acta_without_any_learner_is_registered_but_reports_the_gap(
    client: TestClient,
):
    content = _acta_docx(
        "110",
        "02 de octubre de 2026",
        [{"documento": "", "nombre": "SIN IDENTIFICACION"}],
    )

    body = _upload_bytes(client, "acta.docx", content)
    # Falta informacion de aprendices: es una advertencia, no un error.
    assert body["status"] == "warning"
    assert any(
        "no aporta aprendices con numero de documento" in check["label"]
        for check in body["checks"]
    )

    _confirm(client, body["validation_id"])

    act = _act_by_number(client, "110")
    assert act is not None
    assert act["learners_count"] == 0
    # No se crea ningun aprendiz ficticio.
    assert client.get("/api/learners").json()["items"] == []


def test_acta_persistence_failure_leaves_no_partial_records(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    from app.models import Act

    import app.services.imports as imports_module

    def failing_import(session, extraction, original_file, import_id):
        # Simula una escritura parcial que luego falla: el flujo debe revertirla.
        session.add(
            Act(
                number=extraction["number"],
                original_file=original_file,
                review_status="pending",
                import_id=import_id,
            )
        )
        session.flush()
        raise RuntimeError("fallo simulado de persistencia")

    monkeypatch.setattr(imports_module, "import_act_from_document", failing_import)

    body = _upload_bytes(
        client,
        "acta.docx",
        _acta_docx(
            "111",
            "02 de octubre de 2026",
            [{"documento": "1001012001", "nombre": "FALLO APRENDIZ"}],
        ),
    )

    with pytest.raises(RuntimeError):
        client.post(f"/api/imports/{body['validation_id']}/confirm")

    # La confirmacion es atomica: no quedan actas, aprendices ni historial a medias.
    assert client.get("/api/acts").json()["items"] == []
    assert client.get("/api/learners").json()["items"] == []
    assert client.get("/api/imports/history").json()["items"] == []


# --- Consolidacion de aprendices entre fuentes ------------------------------


def test_df14a_and_actas_2026_do_not_duplicate_the_same_learner(client: TestClient):
    df14a = (
        "DOCUMENTO,NOMBRES,FICHA,PROGRAMA,ESTADO_ASPIRANTE\n"
        "1001008001,APRENDIZ COMPARTIDO,3001,ADSO,Por Certificar\n"
    ).encode("utf-8")
    seeded = _upload_bytes(client, "df14a.csv", df14a, information_type="df14a")
    _confirm(client, seeded["validation_id"])

    excel = _multi_sheet_xlsx(
        certificados=[
            {
                "NIVEL": "TECNÓLOGO",
                "NÚMERO DE DOCUMENTO": "1001008001",
                "NOMBRE": "APRENDIZ COMPARTIDO",
                "FICHA": "3001",
                "ESTADO": "CERTIFICADOS",
                "MES DE CERTIFICACION": "JUNIO",
                "ACTA": "36",
            }
        ]
    )
    actas = _upload_bytes(
        client, "ACTAS 2026.xlsx", excel, information_type="actas_completo"
    )

    _confirm(client, actas["validation_id"])

    # El aprendiz se consolida: existe una sola persona aunque llegue por dos
    # fuentes distintas, y el ultimo estado valido queda registrado.
    learners = _learners_by_identification(client)
    assert len(learners) == 1
    assert learners["1001008001"]["certification_status"] == "CERTIFICADOS"


def test_df14a_without_status_does_not_erase_an_existing_one(client: TestClient):
    df14a = (
        "DOCUMENTO,NOMBRES,FICHA,PROGRAMA,ESTADO_ASPIRANTE\n"
        "1001009001,APRENDIZ ESTADO,3001,ADSO,Certificado\n"
    ).encode("utf-8")
    seeded = _upload_bytes(client, "df14a.csv", df14a, information_type="df14a")
    _confirm(client, seeded["validation_id"])

    # Segundo DF14A del mismo aprendiz sin la columna de estado: no debe borrar
    # el estado ya registrado.
    sin_estado = (
        "DOCUMENTO,NOMBRES,FICHA,PROGRAMA\n"
        "1001009001,APRENDIZ ESTADO,3002,ADSO\n"
    ).encode("utf-8")
    second = _upload_bytes(client, "df14a_sin_estado.csv", sin_estado, information_type="df14a")
    _confirm(client, second["validation_id"])

    learners = _learners_by_identification(client)
    assert learners["1001009001"]["certification_status"] == "Certificado"
    # Los datos presentes si se actualizan.
    assert learners["1001009001"]["group_code"] == "3002"


# --- Normalizacion del nombre de programa (#53) -----------------------------


def test_df14a_program_with_line_breaks_is_stored_in_one_line(client: TestClient):
    df14a = (
        "DOCUMENTO,NOMBRES,FICHA,PROGRAMA\n"
        '1001014001,APRENDIZ PROGRAMA,3001,"OPERACIONES\nCOMERCIALES"\n'
    ).encode("utf-8")
    seeded = _upload_bytes(client, "df14a.csv", df14a, information_type="df14a")
    _confirm(client, seeded["validation_id"])

    learners = _learners_by_identification(client)
    # El salto de linea del archivo queda como un unico espacio, en una sola linea.
    assert learners["1001014001"]["program"] == "OPERACIONES COMERCIALES"


def test_acta_pdf_program_is_stored_in_a_single_line(client: TestClient):
    content = _acta_docx(
        "112",
        "02 de octubre de 2026",
        [
            {
                "documento": "1001015001",
                "nombre": "PROGRAMA PARTIDO APRENDIZ",
                "ficha": "3001",
                "programa": "OPERACIONES\nCOMERCIALES",
            }
        ],
    )
    body = _upload_bytes(client, "acta.docx", content)
    _confirm(client, body["validation_id"])

    learners = _learners_by_identification(client)
    assert learners["1001015001"]["program"] == "OPERACIONES COMERCIALES"


def test_reimport_never_degrades_a_cleaner_program(client: TestClient):
    first = (
        "DOCUMENTO,NOMBRES,FICHA,PROGRAMA\n"
        "1001016001,LIMPIO APRENDIZ,3001,OPERACIONES COMERCIALES\n"
        "1001016002,FRAGMENTADO APRENDIZ,3001,OPERACION ES COMERCIAL ES\n"
    ).encode("utf-8")
    seeded = _upload_bytes(client, "df14a.csv", first, information_type="df14a")
    _confirm(client, seeded["validation_id"])

    # Segunda carga con las formas intercambiadas: la fuente fragmentada no debe
    # pisar el programa consolidado, y la forma limpia si corrige la partida.
    second = (
        "DOCUMENTO,NOMBRES,FICHA,PROGRAMA\n"
        "1001016001,LIMPIO APRENDIZ,3001,OPERACION ES COMERCIAL ES\n"
        "1001016002,FRAGMENTADO APRENDIZ,3001,OPERACIONES COMERCIALES\n"
    ).encode("utf-8")
    reimported = _upload_bytes(client, "df14a_2.csv", second, information_type="df14a")
    _confirm(client, reimported["validation_id"])

    learners = _learners_by_identification(client)
    assert learners["1001016001"]["program"] == "OPERACIONES COMERCIALES"
    assert learners["1001016002"]["program"] == "OPERACIONES COMERCIALES"


def test_acta_does_not_degrade_program_of_existing_learner(client: TestClient):
    df14a = (
        "DOCUMENTO,NOMBRES,FICHA,PROGRAMA,ESTADO_ASPIRANTE\n"
        "1001017001,APRENDIZ PREVIO,3001,OPERACIONES COMERCIALES,Por Certificar\n"
    ).encode("utf-8")
    seeded = _upload_bytes(client, "df14a.csv", df14a, information_type="df14a")
    _confirm(client, seeded["validation_id"])

    content = _acta_docx(
        "113",
        "02 de octubre de 2026",
        [
            {
                "documento": "1001017001",
                "nombre": "APRENDIZ PREVIO",
                "ficha": "3001",
                "programa": "OPERACION ES COMERCIAL ES",
            }
        ],
    )
    body = _upload_bytes(client, "acta.docx", content)
    _confirm(client, body["validation_id"])

    learners = _learners_by_identification(client)
    # El acta no degrada el programa ya consolidado por DF14A.
    assert learners["1001017001"]["program"] == "OPERACIONES COMERCIALES"

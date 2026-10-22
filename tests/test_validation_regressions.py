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
    assert "No se resuelve automaticamente" in labels
    assert "fuera del período" in labels

    validation_id = body["validation_id"]
    preview = client.get(f"/api/imports/{validation_id}/preview")
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["parsed_records"] == 10
    assert preview_body["records_count"] == 10
    assert preview_body["new_records"] == 10
    assert preview_body["updated_records"] == 0
    assert preview_body["rejected_records"] == 0

    confirmed = client.post(f"/api/imports/{validation_id}/confirm")
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
    assert client.post(f"/api/imports/{body['validation_id']}/confirm").status_code == 200

    with client.session_factory() as session:
        learner = session.query(Learner).filter_by(identification="5555").one()
        # No se elige CERTIFICADOS ni PENDIENTES: se conserva el estado previo.
        assert learner.certification_status == "Por Certificar"
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
    assert client.post(f"/api/imports/{body['validation_id']}/confirm").status_code == 200

    with client.session_factory() as session:
        learner = session.query(Learner).filter_by(identification="7777").one()
        assert learner.certification_status is None


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

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_validation_regressions import _multi_sheet_xlsx, _validate


def test_missing_complementaria_requires_explicit_acceptance(client: TestClient, tmp_path):
    content = _multi_sheet_xlsx(
        certificados=[{"DOCUMENTO": "1001", "NOMBRES": "Ana", "FICHA": "3001", "ESTADO": "Certificado"}],
        pendientes=[],
        meta=[["METAS DE CERTIFICACION"], ["EDUCACION SUPERIOR"], [10]],
    )
    path = tmp_path / "ACTAS_sin_complementaria.xlsx"
    path.write_bytes(content)

    body = _validate(client, path, "actas_completo")
    assert body["missing_complementaria"] is True
    assert body["status"] == "warning"

    blocked = client.post(f"/api/imports/{body['validation_id']}/confirm")
    assert blocked.status_code == 400
    assert "COMPLEMENTARIA" in blocked.json()["detail"]

    accepted = client.post(
        f"/api/imports/{body['validation_id']}/confirm",
        json={"accept_missing_complementaria": True},
    )
    assert accepted.status_code == 200
    with client.session_factory() as session:
        from app.models import ImportedRecord

        assert session.query(ImportedRecord).filter_by(information_type="complementaria").count() == 0
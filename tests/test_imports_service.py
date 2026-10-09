from app.services.imports import (
    confirm_import,
    get_staged,
    parse_records,
    record_key,
    stage_file,
)
from app.services.learners import upsert_learners_from_records
from app.models import ImportedRecord, Learner

from tests.conftest import csv_bytes, pdf_bytes, xlsx_bytes


def test_parse_records_from_csv_skips_empty_rows():
    records = parse_records(
        "archivo.csv",
        csv_bytes("nombre,estado\nAna,Activo\n,\nLuis,Activo\n"),
    )

    names = [record.get("nombre") for record in records]
    assert names == ["Ana", "Luis"]


def test_parse_records_from_xlsx():
    records = parse_records(
        "archivo.xlsx",
        xlsx_bytes([{"DOCUMENTO": "1001", "NOMBRES": "Ana"}]),
    )

    assert records[0]["DOCUMENTO"] == 1001 or records[0]["DOCUMENTO"] == "1001"
    assert records[0]["NOMBRES"] == "Ana"


def test_parse_records_from_pdf_returns_file_placeholder():
    records = parse_records("acta.pdf", pdf_bytes())

    assert records == [{"file_name": "acta.pdf", "format": "pdf"}]


def test_parse_records_unknown_extension_returns_empty_list():
    assert parse_records("notas.txt", b"hola") == []


def test_record_key_is_stable_for_same_payload():
    record = {"nombre": "Ana", "documento": "1001"}

    assert record_key("df14a", record) == record_key("df14a", record)
    assert record_key("df14a", record) != record_key("acta", record)


def test_stage_file_keeps_validation_in_memory_only(db_session):
    staged = stage_file("df14a.csv", csv_bytes("nombre\nAna\n"), "df14a")

    assert get_staged(staged.validation_id) is not None
    assert db_session.query(ImportedRecord).count() == 0
    assert db_session.query(Learner).count() == 0


def test_confirm_import_raises_when_validation_is_missing(db_session):
    try:
        confirm_import("no-existe", db_session)
    except KeyError as error:
        assert "ya no esta disponible" in str(error)
    else:
        raise AssertionError("Se esperaba KeyError")


def test_confirm_import_raises_when_file_has_errors(db_session):
    staged = stage_file("acta.pdf", pdf_bytes(), "df14a")

    try:
        confirm_import(staged.validation_id, db_session)
    except ValueError as error:
        assert "errores que impiden" in str(error)
    else:
        raise AssertionError("Se esperaba ValueError")


def test_upsert_learners_does_not_duplicate_identification(db_session):
    upsert_learners_from_records(db_session, [{"DOCUMENTO": "CC_555", "NOMBRES": "Ana"}])
    upsert_learners_from_records(db_session, [{"DOCUMENTO": "555", "NOMBRES": "Ana Maria"}])
    db_session.commit()

    learners = db_session.query(Learner).all()
    assert len(learners) == 1
    assert learners[0].identification == "555"
    assert learners[0].name == "Ana Maria"

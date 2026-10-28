from io import BytesIO
import json
import pandas as pd
import pytest

from app.models import ImportedRecord, ImportHistory, Learner
from app.services.imports import (
    confirm_import,
    record_key,
    stage_file,
)
from app.services.indicadores import compute_indicadores_2026
from app.services.learners import upsert_learners_from_records
from app.services.validation import (
    check_dates_and_periods,
    check_formation_levels,
    validate_file,
)
from tests.conftest import xlsx_bytes


def multi_sheet_xlsx_bytes(sheets_data: dict[str, list[dict]]) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet_name, rows in sheets_data.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name, index=False)
    return buffer.getvalue()


def _seed(session, information_type: str, records: list[dict]) -> None:
    history = ImportHistory(
        file_name="prueba.xlsx",
        information_type=information_type,
        records_count=len(records),
    )
    session.add(history)
    session.flush()
    for index, record in enumerate(records, start=2):
        session.add(
            ImportedRecord(
                import_id=history.id,
                information_type=information_type,
                record_key=f"{information_type}-{index}",
                row_number=index,
                payload=json.dumps(record),
            )
        )
    session.commit()


# -------------------------------------------------------------------------
# Área 1: Integridad de las importaciones (Rollback y no sobrescritura con None)
# -------------------------------------------------------------------------

def test_confirm_import_atomic_rollback_on_failure(db_session, monkeypatch):
    """
    Verifica que si ocurre un error inesperado durante confirm_import,
    se ejecute rollback atómico y no se persista ningún registro en
    ImportHistory, ImportedRecord ni Learner.
    """
    content = xlsx_bytes([
        {"DOCUMENTO": "9001", "NOMBRES": "Aprendiz Test", "PROGRAMA": "Sistemas", "FICHA": "11111"}
    ])
    staged = stage_file("df14a.xlsx", content, "df14a")

    # Simulamos fallo inesperado en upsert_learners_from_records
    def fake_upsert(*args, **kwargs):
        raise RuntimeError("Fallo simulado en base de datos")

    monkeypatch.setattr("app.services.imports.upsert_learners_from_records", fake_upsert)

    with pytest.raises(RuntimeError, match="Fallo simulado en base de datos"):
        confirm_import(staged.validation_id, db_session)

    # Verificar que no quedaron registros huérfanos
    assert db_session.query(ImportHistory).count() == 0
    assert db_session.query(ImportedRecord).count() == 0
    assert db_session.query(Learner).count() == 0


def test_upsert_learners_preserves_valid_fields_against_none(db_session):
    """
    Verifica que al actualizar un aprendiz con datos parciales o nulos,
    los campos ya existentes y válidos (programa, ficha, nivel, nombre real)
    no sean sobrescritos por None ni por 'Aprendiz sin nombre'.
    """
    # 1. Inserción inicial con datos completos
    initial_records = [
        {
            "DOCUMENTO": "88888",
            "NOMBRES": "Ana Maria Torres",
            "PROGRAMA": "Analisis y Desarrollo de Software",
            "FICHA": "2500001",
            "NIVEL": "TECNOLOGO",
            "ESTADO": "Certificado",
        }
    ]
    upsert_learners_from_records(db_session, initial_records)
    db_session.commit()

    learner = db_session.query(Learner).filter_by(identification="88888").first()
    assert learner is not None
    assert learner.name == "Ana Maria Torres"
    assert learner.program == "Analisis y Desarrollo de Software"
    assert learner.group_code == "2500001"
    assert learner.training_type == "TECNOLOGO"
    assert learner.certification_status == "Certificado"

    # 2. Actualización posterior con valores nulos, vacíos y nombre por defecto
    partial_records = [
        {
            "DOCUMENTO": "88888",
            "NOMBRES": "Aprendiz sin nombre",
            "PROGRAMA": None,
            "FICHA": "",
            "NIVEL": None,
            "ESTADO": "Por Certificar",  # Este sí tiene un valor válido nuevo
        }
    ]
    upsert_learners_from_records(db_session, partial_records)
    db_session.commit()

    db_session.refresh(learner)
    # Deben preservarse los datos originales válidos
    assert learner.name == "Ana Maria Torres"
    assert learner.program == "Analisis y Desarrollo de Software"
    assert learner.group_code == "2500001"
    assert learner.training_type == "TECNOLOGO"
    # El estado válido nuevo sí debe actualizarse
    assert learner.certification_status == "Por Certificar"


# -------------------------------------------------------------------------
# Área 2: Clasificación de niveles de formación
# -------------------------------------------------------------------------

def test_check_formation_levels_warns_on_unclassified_level():
    """
    Verifica que check_formation_levels detecte niveles desconocidos
    y emita la advertencia correspondiente.
    """
    df = pd.DataFrame([
        {"NIVEL DE FORMACION": "TECNOLOGO", "DOCUMENTO": "1"},
        {"NIVEL DE FORMACION": "OPERARIO", "DOCUMENTO": "2"},
        {"NIVEL DE FORMACION": "DOCTORADO", "DOCUMENTO": "3"},
    ])
    count, unclass = check_formation_levels(df)
    assert count == 1
    assert "DOCTORADO" in unclass
    assert "OPERARIO" not in unclass


def test_check_formation_levels_passes_on_valid_levels():
    """
    Verifica que check_formation_levels no alerte si todos los niveles
    pertenecen a las categorías misionales conocidas.
    """
    df = pd.DataFrame([
        {"NIVEL": "TECNOLOGO"},
        {"NIVEL": "TECNICO"},
        {"NIVEL": "MEDIA TECNICA"},
        {"NIVEL": "AUXILIAR"},
    ])
    count, unclass = check_formation_levels(df)
    assert count == 0
    assert unclass == []


# -------------------------------------------------------------------------
# Área 3 y 6: Validación de fechas y períodos
# -------------------------------------------------------------------------

def test_check_dates_and_periods_detects_out_of_period():
    """
    Verifica que se detecten fechas fuera de rango o meses fuera del
    período operativo (Ene-Sep 2026).
    """
    df = pd.DataFrame([
        {"MES": "OCTUBRE", "FECHA": "2026-10-15"},
        {"MES": "DICIEMBRE", "FECHA": "2026-12-01"},
    ])
    warnings = check_dates_and_periods(df, "certificados")
    assert len(warnings) > 0
    labels = " ".join(w["label"] for w in warnings)
    assert "fuera del período" in labels


def test_check_dates_and_periods_accepts_valid_period():
    """
    Verifica que fechas de enero a septiembre de 2026 sean aceptadas sin advertencia.
    """
    df = pd.DataFrame([
        {"MES": "ENERO", "FECHA": "2026-01-20"},
        {"MES": "MARZO", "FECHA": "2026-03-10"},
        {"MES": "SEPTIEMBRE", "FECHA": "2026-09-30"},
    ])
    warnings = check_dates_and_periods(df, "certificados")
    assert len(warnings) == 0


# -------------------------------------------------------------------------
# Área 4: Detección de duplicados entre importaciones (Claves naturales estables)
# -------------------------------------------------------------------------

def test_record_key_composite_for_df14a_and_requirements():
    """
    Verifica que las claves de deduplicación para df14a usen (tipo + doc + ficha)
    y para requisitos usen (tipo + doc + requisito), siendo estables ante cambios en otros campos.
    """
    df14a_rec1 = {"DOCUMENTO": "1001", "FICHA": "2500001", "ESTADO": "Activo"}
    df14a_rec2 = {"DOCUMENTO": "1001", "FICHA": "2500001", "ESTADO": "Por Certificar"}
    df14a_rec3 = {"DOCUMENTO": "1001", "FICHA": "2500002", "ESTADO": "Activo"}

    # Mismo doc y ficha producen la misma clave aunque cambie el estado
    assert record_key("df14a", df14a_rec1) == record_key("df14a", df14a_rec2)
    # Diferente ficha produce diferente clave
    assert record_key("df14a", df14a_rec1) != record_key("df14a", df14a_rec3)

    req_rec1 = {"DOCUMENTO": "1001", "REQUISITO": "Fotocopia Cedula", "ESTADO": "Pendiente"}
    req_rec2 = {"DOCUMENTO": "1001", "REQUISITO": "Fotocopia Cedula", "ESTADO": "Aprobado"}
    req_rec3 = {"DOCUMENTO": "1001", "REQUISITO": "Pruebas Saber Pro", "ESTADO": "Pendiente"}

    assert record_key("requisitos", req_rec1) == record_key("requisitos", req_rec2)
    assert record_key("requisitos", req_rec1) != record_key("requisitos", req_rec3)


def test_df14a_reimport_updates_existing_record_without_duplication(db_session):
    """
    Verifica que importar un DF14A con el mismo documento y ficha actualice el registro
    existente en imported_records en vez de duplicarlo.
    """
    # 1. Primera importación
    content_v1 = xlsx_bytes([
        {"DOCUMENTO": "777", "FICHA": "33333", "ESTADO": "Por Certificar", "PROGRAMA": "ADSO"}
    ])
    staged_v1 = stage_file("df14a.xlsx", content_v1, "df14a")
    confirm_import(staged_v1.validation_id, db_session)

    assert db_session.query(ImportedRecord).filter_by(information_type="df14a").count() == 1
    rec1 = db_session.query(ImportedRecord).filter_by(information_type="df14a").first()
    payload1 = json.loads(rec1.payload)
    assert payload1.get("ESTADO") == "Por Certificar"

    # 2. Segunda importación con estado actualizado
    content_v2 = xlsx_bytes([
        {"DOCUMENTO": "777", "FICHA": "33333", "ESTADO": "Certificado", "PROGRAMA": "ADSO"}
    ])
    staged_v2 = stage_file("df14a.xlsx", content_v2, "df14a")
    confirm_import(staged_v2.validation_id, db_session)

    # Debe seguir habiendo 1 solo registro para esta clave natural
    assert db_session.query(ImportedRecord).filter_by(information_type="df14a").count() == 1
    rec2 = db_session.query(ImportedRecord).filter_by(information_type="df14a").first()
    payload2 = json.loads(rec2.payload)
    assert payload2.get("ESTADO") == "Certificado"


# -------------------------------------------------------------------------
# Área 5: Coherencia entre certificados y pendientes
# -------------------------------------------------------------------------

def test_validation_detects_contradiction_between_certificados_and_pendientes():
    """
    Verifica que al validar un archivo de actas completo (con hojas CERTIFICADOS y PENDIENTES),
    si un mismo aprendiz aparece en ambas hojas para la misma ficha, el validador emita
    una advertencia de conflicto de estados.
    """
    content = multi_sheet_xlsx_bytes({
        "CERTIFICADOS": [
            {"DOCUMENTO": "5555", "FICHA": "99999", "NOMBRES": "Aprendiz En Conflicto", "ESTADO": "Certificado"}
        ],
        "PENDIENTES": [
            {"DOCUMENTO": "5555", "FICHA": "99999", "NOMBRES": "Aprendiz En Conflicto", "ESTADO": "Pendiente Documento"}
        ]
    })

    result = validate_file("ACTAS_2026.xlsx", content, "actas_completo")
    assert result.status == "warning"
    conflict_checks = [c for c in result.checks if "figuran simultáneamente en CERTIFICADOS y PENDIENTES" in c["label"]]
    assert len(conflict_checks) == 1
    assert conflict_checks[0]["status"] == "warning"


def test_compute_indicadores_reports_conflictos_certificados_pendientes(db_session):
    """
    Verifica que compute_indicadores_2026 detecte el conflicto y agregue la advertencia
    al diccionario de resultados sin modificar ni descartar registros.
    """
    _seed(db_session, "certificados", [
        {"nivel": "TECNOLOGO", "numero de documento": "5555", "ficha": "99999", "mes de certificacion": "MARZO", "estado": "CERTIFICADOS"},
        {"nivel": "TECNOLOGO", "numero de documento": "6666", "ficha": "99999", "mes de certificacion": "MARZO", "estado": "CERTIFICADOS"},
    ])
    _seed(db_session, "pendientes", [
        {"nivel": "TECNOLOGO", "numero de documento": "5555", "ficha": "99999", "motivo de no certificacion": "Documento", "estado": "PENDIENTE"},
    ])
    res = compute_indicadores_2026(db_session)
    assert res.get("conflictos_certificados_pendientes") == 1
    assert any("simultáneamente como certificados y pendientes" in adv or "simultaneamente como certificados y pendientes" in adv for adv in res.get("advertencias", []))

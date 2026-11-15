from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import NoSuchTableError

from app.database import _upgrade_sqlite_schema


OLD_IMPORT_HISTORY_SCHEMA = """
CREATE TABLE import_history (
    id INTEGER PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    information_type VARCHAR(50) NOT NULL,
    imported_at DATETIME,
    records_count INTEGER DEFAULT 0,
    new_records INTEGER DEFAULT 0,
    updated_records INTEGER DEFAULT 0,
    warning_count INTEGER DEFAULT 0,
    status VARCHAR(30) DEFAULT 'completed',
    message TEXT
)
"""

OLD_REQUIREMENTS_SCHEMA = """
CREATE TABLE requirements (
    id INTEGER PRIMARY KEY,
    learner_id INTEGER NOT NULL,
    learning_outcome VARCHAR(200),
    documentation_status VARCHAR(50),
    productive_stage_status VARCHAR(50),
    clearance_status VARCHAR(50),
    saber_tyt_status VARCHAR(50),
    status VARCHAR(50),
    observations TEXT
)
"""

# Esquema anterior de anexos: un anexo = un archivo y código manual.
OLD_ANEXOS_SCHEMA = """
CREATE TABLE informe_gestion_anexos (
    id INTEGER PRIMARY KEY,
    anio INTEGER NOT NULL,
    trimestre VARCHAR(2) NOT NULL,
    codigo VARCHAR(40),
    titulo VARCHAR(255) NOT NULL,
    descripcion TEXT,
    nombre_archivo VARCHAR(255) NOT NULL,
    content_type VARCHAR(120) NOT NULL,
    ruta_archivo VARCHAR(255) NOT NULL,
    tamano INTEGER DEFAULT 0,
    orden INTEGER DEFAULT 0,
    created_at DATETIME,
    updated_at DATETIME
)
"""


def _old_schema_engine(tmp_path):
    db_path = tmp_path / "old_schema.db"
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        connection.execute(text(OLD_IMPORT_HISTORY_SCHEMA))
        connection.execute(text(OLD_REQUIREMENTS_SCHEMA))
    return engine


def _columns(engine, table_name):
    try:
        return {column["name"] for column in inspect(engine).get_columns(table_name)}
    except NoSuchTableError:
        return set()


def test_migration_adds_missing_columns_to_import_history(tmp_path):
    engine = _old_schema_engine(tmp_path)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO import_history (file_name, information_type, records_count) "
                "VALUES ('legacy.csv', 'DF14A', 5)"
            )
        )

    _upgrade_sqlite_schema(engine)

    columns = _columns(engine, "import_history")
    assert "error_count" in columns
    assert "user_name" in columns

    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT error_count, user_name, records_count FROM import_history")
        ).fetchone()
    assert row[0] == 0
    assert row[1] is None
    assert row[2] == 5


def test_migration_adds_requirement_type_to_requirements(tmp_path):
    engine = _old_schema_engine(tmp_path)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO requirements (learner_id, status) "
                "VALUES (1, 'Pendiente')"
            )
        )

    _upgrade_sqlite_schema(engine)

    assert "requirement_type" in _columns(engine, "requirements")

    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT requirement_type, status FROM requirements")
        ).fetchone()
    assert row[0] is None
    assert row[1] == "Pendiente"


def test_migration_is_idempotent(tmp_path):
    engine = _old_schema_engine(tmp_path)

    _upgrade_sqlite_schema(engine)
    columns_before = _columns(engine, "import_history")

    _upgrade_sqlite_schema(engine)
    columns_after = _columns(engine, "import_history")

    assert columns_before == columns_after


def test_migration_does_not_touch_existing_columns(tmp_path):
    engine = _old_schema_engine(tmp_path)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO import_history (file_name, information_type, records_count, warning_count) "
                "VALUES ('data.csv', 'DF14A', 3, 1)"
            )
        )

    _upgrade_sqlite_schema(engine)

    with engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT file_name, information_type, records_count, warning_count "
                "FROM import_history"
            )
        ).fetchone()
    assert row == ("data.csv", "DF14A", 3, 1)


def test_migration_preserves_data_after_repeated_runs(tmp_path):
    engine = _old_schema_engine(tmp_path)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO import_history (file_name, information_type, records_count) "
                "VALUES ('a.csv', 'DF14A', 1), ('b.csv', 'acta', 2)"
            )
        )

    _upgrade_sqlite_schema(engine)
    _upgrade_sqlite_schema(engine)

    with engine.begin() as connection:
        rows = connection.execute(
            text("SELECT file_name, records_count FROM import_history ORDER BY id")
        ).fetchall()
    assert rows == [("a.csv", 1), ("b.csv", 2)]


def test_migration_moves_legacy_annex_files_to_child_table(tmp_path):
    engine = _old_schema_engine(tmp_path)
    with engine.begin() as connection:
        connection.execute(text(OLD_ANEXOS_SCHEMA))
        connection.execute(
            text(
                "INSERT INTO informe_gestion_anexos "
                "(id, anio, trimestre, codigo, titulo, descripcion, "
                "nombre_archivo, content_type, ruta_archivo, tamano, orden, "
                "created_at, updated_at) VALUES "
                "(1, 2026, 'T3', 'A-1', 'Captura', 'Detalle', "
                "'captura.png', 'image/png', '2026-T3-uno.png', 10, 1, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP), "
                "(2, 2026, 'T3', 'A-2', 'Documento', NULL, "
                "'soporte.pdf', 'application/pdf', '2026-T3-dos.pdf', 20, 2, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )

    _upgrade_sqlite_schema(engine)

    columns = _columns(engine, "informe_gestion_anexos")
    assert "codigo" not in columns
    assert "ruta_archivo" not in columns
    assert "nombre_archivo" not in columns
    assert "content_type" not in columns
    assert "titulo" in columns

    with engine.begin() as connection:
        padres = connection.execute(
            text(
                "SELECT id, anio, trimestre, titulo, descripcion, orden "
                "FROM informe_gestion_anexos ORDER BY id"
            )
        ).fetchall()
        hijos = connection.execute(
            text(
                "SELECT anexo_id, nombre_archivo, content_type, ruta_archivo, "
                "tamano, orden FROM informe_gestion_anexo_archivos "
                "ORDER BY anexo_id"
            )
        ).fetchall()

    assert padres == [
        (1, 2026, "T3", "Captura", "Detalle", 1),
        (2, 2026, "T3", "Documento", None, 2),
    ]
    assert hijos == [
        (1, "captura.png", "image/png", "2026-T3-uno.png", 10, 0),
        (2, "soporte.pdf", "application/pdf", "2026-T3-dos.pdf", 20, 0),
    ]


def test_migration_of_annexes_is_idempotent(tmp_path):
    engine = _old_schema_engine(tmp_path)
    with engine.begin() as connection:
        connection.execute(text(OLD_ANEXOS_SCHEMA))
        connection.execute(
            text(
                "INSERT INTO informe_gestion_anexos "
                "(id, anio, trimestre, titulo, nombre_archivo, content_type, "
                "ruta_archivo, tamano, orden) VALUES "
                "(1, 2026, 'T3', 'Captura', 'captura.png', 'image/png', "
                "'2026-T3-uno.png', 10, 1)"
            )
        )

    _upgrade_sqlite_schema(engine)
    _upgrade_sqlite_schema(engine)

    with engine.begin() as connection:
        total = connection.execute(
            text("SELECT COUNT(*) FROM informe_gestion_anexo_archivos")
        ).scalar_one()
    assert total == 1


def test_migration_handles_database_without_target_tables(tmp_path):
    import pytest

    db_path = tmp_path / "empty.db"
    engine = create_engine(f"sqlite:///{db_path}")

    with pytest.raises(NoSuchTableError):
        _upgrade_sqlite_schema(engine)

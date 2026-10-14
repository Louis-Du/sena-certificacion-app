"""Migración de esquemas SQLite antiguos (`init_db` / `_upgrade_sqlite_schema`).

Cada prueba usa un archivo SQLite temporal; nunca data/sena_certificacion.db.
El esquema antiguo se reproduce con DDL explícito: `import_history` sin
`error_count`/`user_name` y `requirements` sin `requirement_type`, que son las
únicas columnas que la migración actual sabe incorporar. `learners` usa el esquema actual.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.orm import sessionmaker

from app import database
from app.main import app
from app.models import ImportHistory, Learner, Requirement

LEGACY_DDL = [
    """CREATE TABLE import_history (
        id INTEGER NOT NULL PRIMARY KEY,
        file_name VARCHAR(255) NOT NULL,
        information_type VARCHAR(50) NOT NULL,
        imported_at DATETIME NOT NULL,
        records_count INTEGER NOT NULL,
        new_records INTEGER NOT NULL,
        updated_records INTEGER NOT NULL,
        warning_count INTEGER NOT NULL,
        status VARCHAR(30) NOT NULL,
        message TEXT
    )""",
    """CREATE TABLE requirements (
        id INTEGER NOT NULL PRIMARY KEY,
        learner_id INTEGER NOT NULL,
        learning_outcome VARCHAR(200),
        documentation_status VARCHAR(50),
        productive_stage_status VARCHAR(50),
        clearance_status VARCHAR(50),
        saber_tyt_status VARCHAR(50),
        status VARCHAR(50),
        observations TEXT
    )""",
    "INSERT INTO import_history VALUES (1, 'viejo.csv', 'df14a', '2026-09-01 10:00:00', 3, 2, 1, 0, 'completed', 'ok')",
    "INSERT INTO requirements (id, learner_id, documentation_status, status, observations) "
    "VALUES (1, 1, 'Pendiente', 'Pendiente', 'dato anterior')",
]


def columns(engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


@pytest.fixture
def legacy_engine(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", connect_args={"check_same_thread": False})
    # `learners` conserva el esquema actual: la migración solo conoce tres columnas.
    Learner.__table__.create(engine)
    with engine.begin() as connection:
        for statement in LEGACY_DDL:
            connection.execute(text(statement))
        connection.execute(
            text(
                "INSERT INTO learners (id, identification, name, program, group_code, certification_status) "
                "VALUES (1, '1001', 'Ana Ficticia', 'Programa', '3001', 'Por Certificar')"
            )
        )
    monkeypatch.setattr(database, "engine", engine)
    yield engine
    engine.dispose()


def test_legacy_schema_really_lacks_the_new_columns(legacy_engine):
    assert not {"error_count", "user_name"} & columns(legacy_engine, "import_history")
    assert "requirement_type" not in columns(legacy_engine, "requirements")


def test_init_db_adds_missing_columns_and_keeps_existing_data(legacy_engine):
    database.init_db()

    assert {"error_count", "user_name"} <= columns(legacy_engine, "import_history")
    assert "requirement_type" in columns(legacy_engine, "requirements")
    with legacy_engine.connect() as connection:
        history = connection.execute(text("SELECT file_name, records_count, new_records, error_count, user_name "
                                          "FROM import_history")).one()
        learner = connection.execute(text("SELECT name, certification_status FROM learners")).one()
        requirement = connection.execute(
            text("SELECT documentation_status, observations, requirement_type FROM requirements")
        ).one()
    assert tuple(history) == ("viejo.csv", 3, 2, 0, None)  # error_count toma su DEFAULT 0
    assert tuple(learner) == ("Ana Ficticia", "Por Certificar")
    assert tuple(requirement) == ("Pendiente", "dato anterior", None)


def test_init_db_creates_tables_that_did_not_exist_in_old_schema(legacy_engine):
    database.init_db()

    assert {"acts", "act_learners", "imported_records"} <= set(inspect(legacy_engine).get_table_names())


def test_running_migration_twice_is_idempotent(legacy_engine):
    database.init_db()
    snapshot = {
        table: (columns(legacy_engine, table), legacy_engine.connect().execute(text(f"SELECT COUNT(*) FROM {table}")).scalar())
        for table in ("import_history", "learners", "requirements")
    }

    database.init_db()
    database.init_db()

    for table, (cols, count) in snapshot.items():
        assert columns(legacy_engine, table) == cols
        with legacy_engine.connect() as connection:
            assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == count


def test_migrated_database_is_usable_through_orm_and_api(legacy_engine):
    database.init_db()
    factory = sessionmaker(bind=legacy_engine, autoflush=False, autocommit=False)

    with factory() as session:
        session.add(ImportHistory(file_name="nuevo.csv", information_type="df14a", error_count=2, user_name="demo"))
        session.add(Requirement(learner_id=1, requirement_type="documentation", status="Cumplido"))
        session.commit()
        assert session.query(ImportHistory).count() == 2
        assert session.query(Requirement).count() == 2
        assert session.get(Learner, 1).name == "Ana Ficticia"

    def override_get_db():
        with factory() as session:
            yield session

    app.dependency_overrides[database.get_db] = override_get_db
    try:
        with TestClient(app) as client:
            history = client.get("/api/imports/history").json()["items"]
            assert {item["file_name"] for item in history} == {"viejo.csv", "nuevo.csv"}
            assert client.get("/api/learners").json()["total"] == 1
            assert client.get("/api/learners/1/requirements").status_code == 200
            assert client.get("/api/learners/1").status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_current_schema_is_left_untouched(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'current.db'}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(database, "engine", engine)
    database.init_db()
    before = {table: columns(engine, table) for table in inspect(engine).get_table_names()}

    database.init_db()

    assert {table: columns(engine, table) for table in inspect(engine).get_table_names()} == before
    engine.dispose()


def test_upgrade_is_skipped_for_non_sqlite_dialects(monkeypatch):
    class FakeDialect:
        name = "postgresql"

    class FakeEngine:
        dialect = FakeDialect()

        def begin(self):  # pragma: no cover - no debe invocarse
            raise AssertionError("No se debe migrar fuera de SQLite")

    monkeypatch.setattr(database, "engine", FakeEngine())

    assert database._upgrade_sqlite_schema() is None


def test_upgrade_without_tables_fails_loudly_instead_of_hiding_the_problem(tmp_path, monkeypatch):
    """Caracterización: `_upgrade_sqlite_schema` por sí sola exige que las tablas existan
    (init_db ejecuta create_all antes). El error no se silencia."""
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    monkeypatch.setattr(database, "engine", engine)

    with pytest.raises(NoSuchTableError):
        database._upgrade_sqlite_schema()
    engine.dispose()

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/sena_certificacion.db")

if DATABASE_URL == "sqlite:///./data/sena_certificacion.db":
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    with SessionLocal() as session:
        yield session


def init_db() -> None:
    from app import models

    Base.metadata.create_all(bind=engine)
    _upgrade_sqlite_schema()


def _upgrade_sqlite_schema() -> None:
    if engine.dialect.name != "sqlite":
        return

    inspector = inspect(engine)
    import_history_columns = {
        column["name"] for column in inspector.get_columns("import_history")
    }
    requirement_columns = {
        column["name"] for column in inspector.get_columns("requirements")
    }
    migrations = {
        "error_count": (
            "error_count",
            "ALTER TABLE import_history ADD COLUMN error_count INTEGER NOT NULL DEFAULT 0",
            import_history_columns,
        ),
        "user_name": (
            "user_name",
            "ALTER TABLE import_history ADD COLUMN user_name VARCHAR(150)",
            import_history_columns,
        ),
        "requirement_type": (
            "requirement_type",
            "ALTER TABLE requirements ADD COLUMN requirement_type VARCHAR(100)",
            requirement_columns,
        ),
    }
    with engine.begin() as connection:
        for column, (_, statement, existing_columns) in migrations.items():
            if column not in existing_columns:
                connection.execute(text(statement))

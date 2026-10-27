# Importamos el módulo os para interactuar con el sistema operativo, como obtener variables de entorno y manipular rutas de archivos.
import os
# Importamos la clase Path del módulo pathlib para trabajar con rutas de archivos y directorios de manera más conveniente.
from pathlib import Path

# Importamos varias clases y funciones de SQLAlchemy para manejar la base de datos, como crear motores de conexión, inspeccionar esquemas, ejecutar consultas y manejar sesiones.
from sqlalchemy import Engine, create_engine, inspect, text
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


def init_db(bind: Engine | None = None) -> None:
    from app import models

    target = bind or engine
    Base.metadata.create_all(bind=target)
    _upgrade_sqlite_schema(target)


def _table_columns(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}

# Esta función privada `_upgrade_sqlite_schema` se encarga de actualizar el esquema de la base de datos SQLite si es necesario. 
# Verifica si la base de datos es SQLite y luego inspecciona las columnas existentes en las tablas `import_history` y `requirements`. 
# Si faltan ciertas columnas, ejecuta las sentencias SQL correspondientes para agregarlas. Esto asegura que la base de datos esté actualizada con las columnas necesarias para 
# el correcto funcionamiento de la aplicación.
def _upgrade_sqlite_schema(bind: Engine | None = None) -> None:
    target = bind or engine
    if target.dialect.name != "sqlite":
        return

    inspector = inspect(target)
    import_history_columns = _table_columns(inspector, "import_history")
    requirement_columns = _table_columns(inspector, "requirements")
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
    with target.begin() as connection:
        for column, (_, statement, existing_columns) in migrations.items():
            if existing_columns and column not in existing_columns:
                connection.execute(text(statement))

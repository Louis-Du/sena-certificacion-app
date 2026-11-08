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

connect_args = (
    {"check_same_thread": False, "timeout": 30}
    if DATABASE_URL.startswith("sqlite")
    else {}
)
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
    # `learners` puede no existir en esquemas muy antiguos; en ese caso se omite su
    # migracion (create_all ya la habra creado con las columnas al dia).
    learner_columns = _table_columns(inspector, "learners") if inspector.has_table("learners") else set()
    imported_columns = (
        _table_columns(inspector, "imported_records")
        if inspector.has_table("imported_records")
        else set()
    )
    sheet_sync_columns = (
        _table_columns(inspector, "sheet_sync_config")
        if inspector.has_table("sheet_sync_config")
        else set()
    )
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
        # Tipo interno de la carga. Permite identificar el lote vigente de
        # ACTAS 2026 sin depender de la etiqueta visible del historial.
        "source_type": (
            "source_type",
            "ALTER TABLE import_history ADD COLUMN source_type VARCHAR(50)",
            import_history_columns,
        ),
        "requirement_type": (
            "requirement_type",
            "ALTER TABLE requirements ADD COLUMN requirement_type VARCHAR(100)",
            requirement_columns,
        ),
        # Seguimiento de certificacion del aprendiz (motivo y datos de contacto/acta).
        "non_certification_reason": (
            "non_certification_reason",
            "ALTER TABLE learners ADD COLUMN non_certification_reason TEXT",
            learner_columns,
        ),
        "certification_month": (
            "certification_month",
            "ALTER TABLE learners ADD COLUMN certification_month VARCHAR(50)",
            learner_columns,
        ),
        "instructor": (
            "instructor",
            "ALTER TABLE learners ADD COLUMN instructor VARCHAR(200)",
            learner_columns,
        ),
        "act_number": (
            "act_number",
            "ALTER TABLE learners ADD COLUMN act_number VARCHAR(100)",
            learner_columns,
        ),
        "email": (
            "email",
            "ALTER TABLE learners ADD COLUMN email VARCHAR(200)",
            learner_columns,
        ),
        "phone": (
            "phone",
            "ALTER TABLE learners ADD COLUMN phone VARCHAR(50)",
            learner_columns,
        ),
        # Fecha de recibido del expediente en administracion educativa (dato de
        # seguimiento, no requisito de la matriz).
        "administrative_receipt_date": (
            "administrative_receipt_date",
            "ALTER TABLE learners ADD COLUMN administrative_receipt_date DATE",
            learner_columns,
        ),
        # Procedencia de los datos del aprendiz (lista JSON de fuentes).
        "data_sources": (
            "data_sources",
            "ALTER TABLE learners ADD COLUMN data_sources TEXT",
            learner_columns,
        ),
        # Resolucion manual de un conflicto CERTIFICADOS/PENDIENTES. Sin esta
        # columna, las bases existentes no podrian distinguir una resolucion
        # explicita de un estado asignado automaticamente por la importacion.
        "conflict_resolution": (
            "conflict_resolution",
            "ALTER TABLE learners ADD COLUMN conflict_resolution VARCHAR(30)",
            learner_columns,
        ),
        # Fechas del aprendiz que ya existian en el modelo pero no estaban en la
        # migracion. En bases antiguas su ausencia hacia que todo quedara "Sin
        # fecha"; se agregan de forma compatible hacia adelante.
        "termination_date": (
            "termination_date",
            "ALTER TABLE learners ADD COLUMN termination_date DATE",
            learner_columns,
        ),
        "start_date": (
            "start_date",
            "ALTER TABLE learners ADD COLUMN start_date DATE",
            learner_columns,
        ),
        # Estado recuperable del lote detenido por conflictos
        # CERTIFICADOS/PENDIENTES detectados por la sincronizacion automatica.
        "pending_validation_id": (
            "pending_validation_id",
            "ALTER TABLE sheet_sync_config ADD COLUMN pending_validation_id VARCHAR(64)",
            sheet_sync_columns,
        ),
        "pending_conflict_count": (
            "pending_conflict_count",
            "ALTER TABLE sheet_sync_config ADD COLUMN pending_conflict_count INTEGER NOT NULL DEFAULT 0",
            sheet_sync_columns,
        ),
        "pending_conflict_fingerprint": (
            "pending_conflict_fingerprint",
            "ALTER TABLE sheet_sync_config ADD COLUMN pending_conflict_fingerprint VARCHAR(64)",
            sheet_sync_columns,
        ),
        "pending_hash": (
            "pending_hash",
            "ALTER TABLE sheet_sync_config ADD COLUMN pending_hash VARCHAR(64)",
            sheet_sync_columns,
        ),
        "pending_file_name": (
            "pending_file_name",
            "ALTER TABLE sheet_sync_config ADD COLUMN pending_file_name VARCHAR(255)",
            sheet_sync_columns,
        ),
        "pending_content": (
            "pending_content",
            "ALTER TABLE sheet_sync_config ADD COLUMN pending_content BLOB",
            sheet_sync_columns,
        ),
        "pending_conflicts_json": (
            "pending_conflicts_json",
            "ALTER TABLE sheet_sync_config ADD COLUMN pending_conflicts_json TEXT",
            sheet_sync_columns,
        ),
        "pending_preview_json": (
            "pending_preview_json",
            "ALTER TABLE sheet_sync_config ADD COLUMN pending_preview_json TEXT",
            sheet_sync_columns,
        ),
        "notified_at": (
            "notified_at",
            "ALTER TABLE sheet_sync_config ADD COLUMN notified_at DATETIME",
            sheet_sync_columns,
        ),
    }
    with target.begin() as connection:
        for column, (_, statement, existing_columns) in migrations.items():
            if existing_columns and column not in existing_columns:
                connection.execute(text(statement))
        # Backfill para bases creadas antes de ``source_type``: el historial
        # guardaba la etiqueta visible del tipo ACTAS completo.
        connection.execute(
            text(
                "UPDATE import_history SET source_type = 'actas_completo' "
                "WHERE source_type IS NULL AND information_type = :label"
            ),
            {"label": "Excel institucional (ACTAS 2026)"},
        )

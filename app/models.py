from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Esta clase representa el historial de importaciones de archivos en la base de datos. 
# Contiene información sobre el archivo importado, el tipo de información, la fecha de importación, el número de registros, el estado de la importación y otros detalles relevantes. 
# Además, establece una relación con la clase ImportedRecord para almacenar los registros importados asociados a cada historial de importación.
class ImportHistory(Base):
    __tablename__ = "import_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255))
    information_type: Mapped[str] = mapped_column(String(50))
    # Tipo interno real de la carga ("actas_completo", "df14a", "certificados",
    # ...). ``information_type`` conserva la etiqueta visible historica; este
    # campo permite identificar de forma estable el lote vigente del consolidado.
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    records_count: Mapped[int] = mapped_column(Integer, default=0)
    new_records: Mapped[int] = mapped_column(Integer, default=0)
    updated_records: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    user_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="completed")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    records: Mapped[list["ImportedRecord"]] = relationship(
        back_populates="import_history", cascade="all, delete-orphan"
    )

# Esta clase representa un registro importado en la base de datos. 
# Contiene información sobre el historial de importación al que pertenece, el tipo de información, la clave del registro, el número de fila y el contenido del registro en formato de texto.
class ImportedRecord(Base):
    __tablename__ = "imported_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import_history.id"))
    information_type: Mapped[str] = mapped_column(String(50))
    record_key: Mapped[str] = mapped_column(String(64), index=True)
    row_number: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[str] = mapped_column(Text)

    import_history: Mapped[ImportHistory] = relationship(back_populates="records")

# Esta clase representa un aprendiz en la base de datos.
class Learner(Base):
    __tablename__ = "learners"

    id: Mapped[int] = mapped_column(primary_key=True)
    identification: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    program: Mapped[str | None] = mapped_column(String(200), nullable=True)
    group_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    training_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    certification_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Decision explicita del usuario cuando un documento aparece a la vez en
    # CERTIFICADOS y PENDIENTES del consolidado. Guarda "CERTIFICADOS" o
    # "PENDIENTE"; None significa que el conflicto no se ha resuelto. El motor de
    # indicadores lo usa para no contar a la misma persona en ambos universos.
    # Es un desempate CONDICIONAL: solo vale mientras el documento siga en la
    # interseccion CERTIFICADOS/PENDIENTES. Al dejar de estar en ambas hojas se
    # limpia este campo.
    conflict_resolution: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Ultima decision manual de desempate, conservada como historial para
    # reaplicarla en silencio si el documento vuelve a aparecer en ambas hojas.
    # No se usa para forzar el estado cuando la hoja ya lo dejo en una sola.
    last_conflict_resolution: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )
    # Motivo de no certificacion (hoja PENDIENTES de ACTAS 2026.xlsx). Es el
    # "porque" resumido del aprendiz y alimenta el indicador de causas; NO es un
    # requisito ni un estado.
    non_certification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    certification_month: Mapped[str | None] = mapped_column(String(50), nullable=True)
    instructor: Mapped[str | None] = mapped_column(String(200), nullable=True)
    act_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Fecha de recibido del expediente en administracion educativa (columna
    # FECHA DE RECIBIDO EN ADMON EDUCATIVA de ACTAS 2026). Es un dato de
    # seguimiento, no un requisito de la matriz ni un evento de historial.
    administrative_receipt_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tracking_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Procedencia de los datos del aprendiz: lista JSON de las fuentes que lo
    # alimentaron (por ejemplo ["ACTAS 2026 · PENDIENTES", "DF14A"]). Se acumula
    # entre importaciones; nunca se borra un origen previo.
    data_sources: Mapped[str | None] = mapped_column(Text, nullable=True)

    requirements: Mapped[list["Requirement"]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return self.name
    requirement_status_history: Mapped[list["RequirementStatusHistory"]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )
    acts: Mapped[list["ActLearner"]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )


# Esta clase representa la configuracion de sincronizacion automatica desde
# Google Sheets. Solo existe una fila activa (id=1).
class SheetSyncConfig(Base):
    __tablename__ = "sheet_sync_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(500))
    information_type: Mapped[str] = mapped_column(String(50), default="actas_completo")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60)
    last_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_import_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Lote descargado que quedo detenido porque CERTIFICADOS y PENDIENTES
    # contienen el mismo documento. El hash de la hoja NO se actualiza hasta
    # resolverlo e importarlo, de modo que el siguiente ciclo no lo descarte.
    pending_validation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pending_conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    # Huella estable del conjunto de documentos en conflicto. Evita repetir la
    # notificacion nativa en cada ciclo de 60 segundos.
    pending_conflict_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    # Hash del XLSX que produjo el conflicto pendiente. Permite reconocer el
    # mismo lote sin volver a validarlo en cada ciclo.
    pending_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pending_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Contenido del lote y resumen serializado para que la resolucion funcione
    # incluso si la aplicacion se reinicia y ``_staged_imports`` (memoria) se
    # vacia. ``deferred`` evita cargar el BLOB en cada polling de estado.
    pending_content: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True, deferred=True
    )
    pending_conflicts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_preview_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

# Esta clase representa un requisito asociado a un aprendiz en la base de datos.
class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learners.id"), index=True)
    requirement_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    learning_outcome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    documentation_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    productive_stage_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    clearance_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    saber_tyt_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)

    learner: Mapped[Learner] = relationship(back_populates="requirements")


# Esta clase representa un evento del historial de cambios de estado de los
# requisitos de un aprendiz (RF-19). Es complemento del estado actual que vive
# en la tabla ``requirements``: cada alta o cambio de estado genera un evento.
class RequirementStatusHistory(Base):
    __tablename__ = "requirement_status_history"
    __table_args__ = (
        Index("ix_requirement_status_history_learner_recorded", "learner_id", "recorded_at"),
        Index(
            "ix_requirement_status_history_learner_type_recorded",
            "learner_id",
            "requirement_type",
            "recorded_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learners.id"), index=True)
    requirement_type: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(50))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    learner: Mapped["Learner"] = relationship(back_populates="requirement_status_history")


# Esta clase representa un acta asociada a un aprendiz en la base de datos.
class Act(Base):
    __tablename__ = "acts"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    act_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    act_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    original_file: Mapped[str] = mapped_column(String(255))
    review_status: Mapped[str] = mapped_column(String(50), default="pending")
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_history.id"), nullable=True, index=True
    )

    learners: Mapped[list["ActLearner"]] = relationship(
        back_populates="act", cascade="all, delete-orphan"
    )

# Esta clase representa la relación entre un acta y un aprendiz en la base de datos.
class ActLearner(Base):
    __tablename__ = "act_learners"
    __table_args__ = (UniqueConstraint("act_id", "learner_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    act_id: Mapped[int] = mapped_column(ForeignKey("acts.id"), index=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learners.id"), index=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)

    act: Mapped[Act] = relationship(back_populates="learners")
    learner: Mapped[Learner] = relationship(back_populates="acts")

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ImportHistory(Base):
    __tablename__ = "import_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255))
    information_type: Mapped[str] = mapped_column(String(50))
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


class ImportedRecord(Base):
    __tablename__ = "imported_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("import_history.id"))
    information_type: Mapped[str] = mapped_column(String(50))
    record_key: Mapped[str] = mapped_column(String(64), index=True)
    row_number: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[str] = mapped_column(Text)

    import_history: Mapped[ImportHistory] = relationship(back_populates="records")


class Learner(Base):
    __tablename__ = "learners"

    id: Mapped[int] = mapped_column(primary_key=True)
    identification: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    program: Mapped[str | None] = mapped_column(String(200), nullable=True)
    group_code: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    training_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    certification_status: Mapped[str | None] = mapped_column(String(100), nullable=True)
    termination_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tracking_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    requirements: Mapped[list["Requirement"]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )
    acts: Mapped[list["ActLearner"]] = relationship(
        back_populates="learner", cascade="all, delete-orphan"
    )


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


class ActLearner(Base):
    __tablename__ = "act_learners"
    __table_args__ = (UniqueConstraint("act_id", "learner_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    act_id: Mapped[int] = mapped_column(ForeignKey("acts.id"), index=True)
    learner_id: Mapped[int] = mapped_column(ForeignKey("learners.id"), index=True)
    observations: Mapped[str | None] = mapped_column(Text, nullable=True)

    act: Mapped[Act] = relationship(back_populates="learners")
    learner: Mapped[Learner] = relationship(back_populates="acts")

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
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

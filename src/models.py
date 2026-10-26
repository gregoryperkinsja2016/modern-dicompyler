"""SQLAlchemy ORM models for the Modern Dicompyler analysis store."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class AnalysisRecord(Base):
    """One persisted analysis (upload or synthetic demo case run)."""

    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    rt_object_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    source: Mapped[str] = mapped_column(String(32), default="upload")
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    warnings_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    errors_json: Mapped[list[Any]] = mapped_column(JSON, default=list)
    trace_id: Mapped[str] = mapped_column(String(64), default="")


class AuditEvent(Base):
    """Immutable audit trail entry for lifecycle events of an analysis."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    analysis_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    detail_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    trace_id: Mapped[str] = mapped_column(String(64), default="")

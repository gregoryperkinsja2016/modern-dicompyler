"""SQLite persistence layer for Modern Dicompyler.

Provides the engine/session, schema initialisation, health check, and small
service functions used by the API. Every analysis (including failed parse
attempts) is persisted together with an audit event. Repeated demo-case runs
create separate records.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from math import ceil
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from src.config import DATABASE_URL
from src.engine import DatabaseUnavailableError
from src.models import AnalysisRecord, AuditEvent, Base
from src.telemetry import DATABASE_UP, get_logger

logger = get_logger("db")

_engine: Engine | None = None
_session_factory: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        kwargs: dict[str, Any] = {}
        if DATABASE_URL.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(DATABASE_URL, **kwargs)
        _session_factory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def init_db() -> None:
    """Create the schema and the SQLite data directory when required."""
    if DATABASE_URL.startswith("sqlite:///"):
        db_path = DATABASE_URL.removeprefix("sqlite:///")
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(get_engine())


def check_database_health() -> bool:
    """Return True when the database accepts a trivial query."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        DATABASE_UP.set(1)
        return True
    except SQLAlchemyError as exc:
        DATABASE_UP.set(0)
        logger.warning("database_health_check_failed", extra={"error_class": type(exc).__name__})
        return False


@contextmanager
def get_session() -> Iterator[Session]:
    get_engine()
    assert _session_factory is not None  # noqa: S101 - invariant after get_engine()
    session = _session_factory()
    try:
        yield session
    finally:
        session.close()


def _iso(timestamp: datetime | None) -> str | None:
    if timestamp is None:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return timestamp.isoformat()


def create_analysis(
    *,
    rt_object_type: str,
    status: str,
    source: str,
    result_json: dict[str, Any] | None,
    warnings: list[str],
    errors: list[str],
    trace_id: str,
) -> str:
    """Persist one analysis plus its audit event; return the analysis id."""
    analysis_id = uuid.uuid4().hex
    event_type = "ANALYSIS_CREATED" if status == "completed" else "ANALYSIS_FAILED"
    detail = {
        "rt_object_type": rt_object_type,
        "source": source,
        "status": status,
        "warning_count": len(warnings),
        "error_count": len(errors),
    }
    try:
        with get_session() as session:
            session.add(
                AnalysisRecord(
                    id=analysis_id,
                    rt_object_type=rt_object_type,
                    status=status,
                    source=source,
                    result_json=result_json,
                    warnings_json=list(warnings),
                    errors_json=list(errors),
                    trace_id=trace_id,
                )
            )
            session.add(
                AuditEvent(
                    analysis_id=analysis_id,
                    event_type=event_type,
                    detail_json=detail,
                    trace_id=trace_id,
                )
            )
            session.commit()
    except SQLAlchemyError as exc:
        logger.error("analysis_persistence_failed", extra={"error_class": type(exc).__name__})
        raise DatabaseUnavailableError(
            f"Database is unavailable ({type(exc).__name__}); analysis could not be persisted."
        ) from exc
    DATABASE_UP.set(1)
    return analysis_id


def _record_to_history(record: AnalysisRecord) -> dict[str, Any]:
    return {
        "analysis_id": record.id,
        "created_at": _iso(record.created_at),
        "rt_object_type": record.rt_object_type,
        "status": record.status,
        "source": record.source,
        "warning_count": len(record.warnings_json or []),
        "error_count": len(record.errors_json or []),
        "trace_id": record.trace_id,
    }


def list_analyses(page: int, page_size: int) -> tuple[list[dict[str, Any]], int, int]:
    """Return ``(items, total, total_pages)`` for the paginated history."""
    try:
        with get_session() as session:
            total = int(session.scalar(select(func.count()).select_from(AnalysisRecord)) or 0)
            rows = session.scalars(
                select(AnalysisRecord)
                .order_by(AnalysisRecord.created_at.desc(), AnalysisRecord.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            items = [_record_to_history(row) for row in rows]
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError(
            f"Database is unavailable ({type(exc).__name__}); history could not be read."
        ) from exc
    DATABASE_UP.set(1)
    return items, total, max(1, ceil(total / page_size))


def get_analysis(analysis_id: str) -> dict[str, Any] | None:
    """Return the full analysis detail (including audit events) or None."""
    try:
        with get_session() as session:
            record = session.get(AnalysisRecord, analysis_id)
            if record is None:
                return None
            events = session.scalars(
                select(AuditEvent)
                .where(AuditEvent.analysis_id == analysis_id)
                .order_by(AuditEvent.id)
            ).all()
            audit_events = [
                {
                    "id": event.id,
                    "created_at": _iso(event.created_at),
                    "analysis_id": event.analysis_id,
                    "event_type": event.event_type,
                    "detail": event.detail_json or {},
                    "trace_id": event.trace_id,
                }
                for event in events
            ]
            return {
                "analysis_id": record.id,
                "created_at": _iso(record.created_at),
                "rt_object_type": record.rt_object_type,
                "status": record.status,
                "source": record.source,
                "trace_id": record.trace_id,
                "warnings": list(record.warnings_json or []),
                "errors": list(record.errors_json or []),
                "result": record.result_json,
                "audit_events": audit_events,
            }
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError(
            f"Database is unavailable ({type(exc).__name__}); analysis could not be read."
        ) from exc


def get_analysis_plan(analysis_id: str) -> dict[str, Any] | None:
    """Return the RTPLAN payload for one analysis, or None when unknown."""
    try:
        with get_session() as session:
            record = session.get(AnalysisRecord, analysis_id)
    except SQLAlchemyError as exc:
        raise DatabaseUnavailableError(
            f"Database is unavailable ({type(exc).__name__}); plan could not be read."
        ) from exc
    if record is None:
        return None
    plan = record.result_json.get("plan") if record.result_json else None
    return {
        "analysis_id": record.id,
        "rt_object_type": record.rt_object_type,
        "available": plan is not None,
        "plan": plan,
    }

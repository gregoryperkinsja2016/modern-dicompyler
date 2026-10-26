"""Observability: structured JSON logging, request/trace context, Prometheus metrics.

Logging rules enforced here:
- Logs carry trace_id, request_id, route, status_code, duration_ms, outcome
  and error_class where available.
- Raw stack traces are never emitted; only the exception class name is kept.
- DICOM contents, PHI, credentials and raw uploaded file contents are never
  logged (the domain layer simply never passes them to the logger).
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from prometheus_client import Counter, Gauge, Histogram

# --- Request/trace context -------------------------------------------------
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

# --- Prometheus metrics -------------------------------------------------------
ANALYSIS_REQUESTS_TOTAL = Counter(
    "rtqa_analysis_requests_total",
    "Total DICOM-RT analysis API requests.",
    ["route", "outcome"],
)
ANALYSIS_DURATION_SECONDS = Histogram(
    "rtqa_analysis_duration_seconds",
    "Duration of analysis API requests in seconds.",
    ["route"],
)
ANALYSIS_FAILURES_TOTAL = Counter(
    "rtqa_analysis_failures_total",
    "Total failed analysis API requests labelled by error class.",
    ["error_class"],
)
DATABASE_UP = Gauge(
    "rtqa_database_up",
    "1 when the database is reachable, 0 otherwise.",
)

_LOG_FIELDS = (
    "trace_id",
    "request_id",
    "route",
    "status_code",
    "duration_ms",
    "outcome",
    "error_class",
    "event",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"dicomrt.{name}")


class JsonLogFormatter(logging.Formatter):
    """Format every log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _LOG_FIELDS:
            value = getattr(record, field, None)
            if value is None:
                if field == "trace_id":
                    value = trace_id_var.get() or None
                elif field == "request_id":
                    value = request_id_var.get() or None
            if value not in (None, ""):
                payload[field] = value
        if record.exc_info and record.exc_info[1] is not None:
            payload["exception_class"] = type(record.exc_info[1]).__name__
        return json.dumps(payload, ensure_ascii=False, default=str)


_logging_configured = False


def setup_logging(level: str = "INFO") -> None:
    """Install the JSON formatter once; uvicorn loggers inherit it."""
    global _logging_configured
    if _logging_configured:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(uvicorn_logger_name).handlers = []
    _logging_configured = True

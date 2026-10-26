"""FastAPI application for Modern Dicompyler.

Endpoints
---------
- POST /api/v1/analyses              parse an uploaded DICOM-RT file
- GET  /api/v1/analyses              paginated analysis history
- GET  /api/v1/analyses/{id}         one analysis (with audit events)
- GET  /api/v1/analyses/{id}/plan    RTPLAN data for an analysis
- POST /api/v1/demo-case             run + persist the synthetic demo case
- GET  /api/v1/demo-case             also runs the synthetic demo case
- GET  /api/v1/demo-case/plan        synthetic RTPLAN inspection data
- GET  /health                       application + database health
- GET  /metrics                      Prometheus metrics

Cross-cutting concerns (structured JSON logging, request/trace ids, metrics,
alerting) are implemented in an observability middleware.
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import APIRouter, FastAPI, File, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

from src import alerting, db
from src.config import (
    API_DESCRIPTION,
    API_TITLE,
    API_VERSION,
    DEFAULT_PAGE_SIZE,
    ENVIRONMENT,
    MAX_PAGE_SIZE,
    MAX_UPLOAD_BYTES,
)
from src.engine import (
    DatabaseUnavailableError,
    InvalidDICOMError,
    MissingRequiredAttributeError,
    RTQAError,
    UnsupportedRTObjectError,
    parse_dataset_bytes,
    parse_rtplan,
    run_synthetic_demo_case,
)
from src.schemas import AnalysisDetail, HealthResponse, HistoryPage
from src.synthetic_data import build_synthetic_rtplan
from src.telemetry import (
    ANALYSIS_DURATION_SECONDS,
    ANALYSIS_FAILURES_TOTAL,
    ANALYSIS_REQUESTS_TOTAL,
    get_logger,
    request_id_var,
    setup_logging,
    trace_id_var,
)

logger = get_logger("api")


def _error_payload(error_class: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "class": error_class,
                "message": message,
                "trace_id": trace_id_var.get() or None,
            }
        },
    )


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Request/trace ids, JSON access logs, metrics and alerting hooks."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
        request_token = request_id_var.set(request_id)
        trace_token = trace_id_var.set(trace_id)
        request.state.request_id = request_id
        request.state.trace_id = trace_id

        start = time.perf_counter()
        route = request.url.path
        status_code = 500
        response = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Trace-ID"] = trace_id
        except Exception as exc:  # noqa: BLE001 - converted to a structured 500
            error_class = type(exc).__name__
            request.state.error_class = error_class
            logger.error(
                "unhandled_exception",
                extra={"route": route, "error_class": error_class, "outcome": "error"},
            )
            response = _error_payload("InternalServerError", "Internal server error.", 500)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Trace-ID"] = trace_id
            status_code = response.status_code

        duration_ms = round((time.perf_counter() - start) * 1000, 3)
        matched_route = request.scope.get("route")
        route_template = getattr(matched_route, "path", route)
        if status_code < 400:
            outcome = "success"
        elif status_code < 500:
            outcome = "failure"
        else:
            outcome = "error"
        error_class = getattr(request.state, "error_class", None)

        try:
            logger.info(
                "http_request",
                extra={
                    "route": route_template,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "outcome": outcome,
                    "error_class": error_class,
                    "request_id": request_id,
                    "trace_id": trace_id,
                },
            )
            if route_template.startswith("/api/v1"):
                ANALYSIS_REQUESTS_TOTAL.labels(route=route_template, outcome=outcome).inc()
                ANALYSIS_DURATION_SECONDS.labels(route=route_template).observe(duration_ms / 1000.0)
                if outcome != "success":
                    ANALYSIS_FAILURES_TOTAL.labels(
                        error_class=error_class or f"HTTP{status_code}"
                    ).inc()
                alerting.record_analysis_outcome(route_template, outcome == "success")
        finally:
            request_id_var.reset(request_token)
            trace_id_var.reset(trace_token)
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    try:
        db.init_db()
        db.check_database_health()
        logger.info("application_started", extra={"event": "startup", "environment": ENVIRONMENT})
    except Exception as exc:  # noqa: BLE001 - startup must not crash on a dead DB
        logger.error(
            "startup_database_init_failed", extra={"error_class": type(exc).__name__}
        )
    yield
    logger.info("application_stopped", extra={"event": "shutdown"})


router = APIRouter()


@router.get("/")
async def root() -> dict:
    return {
        "name": API_TITLE,
        "version": API_VERSION,
        "description": API_DESCRIPTION,
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
    }


@router.post("/api/v1/analyses", status_code=201)
async def create_analysis(file: UploadFile = File(...)) -> Response:
    data = await file.read()
    trace_id = trace_id_var.get()
    if not data:
        return _error_payload("InvalidDICOMError", "Uploaded file is empty.", 400)
    if len(data) > MAX_UPLOAD_BYTES:
        return _error_payload(
            "PayloadTooLargeError",
            f"Uploaded file exceeds the maximum size of {MAX_UPLOAD_BYTES} bytes.",
            413,
        )
    try:
        rt_object_type, result = parse_dataset_bytes(data)
    except (InvalidDICOMError, UnsupportedRTObjectError, MissingRequiredAttributeError) as exc:
        # Failed parses are persisted too, for audit purposes.
        db.create_analysis(
            rt_object_type="UNKNOWN",
            status="failed",
            source="upload",
            result_json=None,
            warnings=[],
            errors=[f"{exc.error_class}: {exc}"],
            trace_id=trace_id,
        )
        logger.warning(
            "upload_parse_failed",
            extra={"route": "/api/v1/analyses", "error_class": exc.error_class, "outcome": "failure"},
        )
        return _error_payload(exc.error_class, str(exc), 400)

    analysis_id = db.create_analysis(
        rt_object_type=rt_object_type,
        status="completed",
        source="upload",
        result_json=result.model_dump(mode="json"),
        warnings=result.warnings,
        errors=[],
        trace_id=trace_id,
    )
    logger.info(
        "analysis_created",
        extra={"route": "/api/v1/analyses", "event": "analysis_created", "outcome": "success"},
    )
    return db.get_analysis(analysis_id)


@router.get("/api/v1/analyses", response_model=HistoryPage)
def list_analyses(
    page: int = Query(1, ge=1, description="Page number."),
    page_size: int = Query(
        DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="Records per page."
    ),
) -> dict:
    items, total, total_pages = db.list_analyses(page=page, page_size=page_size)
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
    }


@router.get("/api/v1/analyses/{analysis_id}", response_model=AnalysisDetail)
def get_analysis(analysis_id: str) -> Response:
    detail = db.get_analysis(analysis_id)
    if detail is None:
        return _error_payload("NotFoundError", f"Analysis '{analysis_id}' was not found.", 404)
    return detail


@router.get("/api/v1/analyses/{analysis_id}/plan")
def get_analysis_plan(analysis_id: str) -> Response:
    plan_payload = db.get_analysis_plan(analysis_id)
    if plan_payload is None:
        return _error_payload("NotFoundError", f"Analysis '{analysis_id}' was not found.", 404)
    return plan_payload


def _run_demo_case() -> Response:
    trace_id = trace_id_var.get()
    try:
        result = run_synthetic_demo_case()
    except Exception as exc:  # noqa: BLE001 - demo failures trigger on-call alerting
        alerting.alert_demo_case_failure(error_class=type(exc).__name__)
        logger.error(
            "demo_case_failed",
            extra={
                "route": "/api/v1/demo-case",
                "error_class": type(exc).__name__,
                "outcome": "error",
            },
        )
        raise
    analysis_id = db.create_analysis(
        rt_object_type="DEMO_CASE",
        status="completed",
        source="demo_case",
        result_json=result.model_dump(mode="json"),
        warnings=result.warnings,
        errors=[],
        trace_id=trace_id,
    )
    return db.get_analysis(analysis_id)


@router.post("/api/v1/demo-case", status_code=201, response_model=AnalysisDetail)
def run_demo_case_post() -> Response:
    return _run_demo_case()


@router.get("/api/v1/demo-case", response_model=AnalysisDetail)
def run_demo_case_get() -> Response:
    return _run_demo_case()


@router.get("/api/v1/demo-case/plan")
def demo_case_plan() -> dict:
    plan = parse_rtplan(build_synthetic_rtplan())
    return {
        "rt_object_type": "RTPLAN",
        "source": "demo_case",
        "plan": plan.model_dump(mode="json"),
        "warnings": plan.warnings,
    }


@router.get("/health", response_model=HealthResponse)
def health() -> dict:
    database_ok = db.check_database_health()
    alerting.record_health(database_ok)
    return {
        "status": "ok" if database_ok else "unhealthy",
        "database": database_ok,
        "environment": ENVIRONMENT,
        "version": API_VERSION,
        "time": datetime.now(UTC).isoformat(),
    }


@router.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def create_app() -> FastAPI:
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        lifespan=lifespan,
    )
    app.add_middleware(ObservabilityMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RTQAError)
    async def rtqa_error_handler(request: Request, exc: RTQAError) -> JSONResponse:
        status_code = 503 if isinstance(exc, DatabaseUnavailableError) else 400
        request.state.error_class = exc.error_class
        logger.warning(
            "analysis_request_failed",
            extra={
                "route": request.url.path,
                "error_class": exc.error_class,
                "status_code": status_code,
                "outcome": "failure",
            },
        )
        return _error_payload(exc.error_class, str(exc), status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request.state.error_class = "RequestValidationError"
        logger.warning(
            "request_validation_failed",
            extra={
                "route": request.url.path,
                "error_class": "RequestValidationError",
                "status_code": 422,
                "outcome": "failure",
            },
        )
        details = [
            {"loc": error.get("loc"), "msg": error.get("msg"), "type": error.get("type")}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "class": "RequestValidationError",
                    "message": "Request validation failed.",
                    "details": details,
                    "trace_id": trace_id_var.get() or None,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request.state.error_class = type(exc).__name__
        logger.error(
            "unhandled_exception",
            extra={
                "route": request.url.path,
                "error_class": type(exc).__name__,
                "outcome": "error",
            },
        )
        return _error_payload("InternalServerError", "Internal server error.", 500)

    app.include_router(router)
    return app


app = create_app()

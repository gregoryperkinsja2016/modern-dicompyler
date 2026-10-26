# CHANGELOG

All notable changes to Modern Dicompyler are documented here.

## [1.1.0] - 2026-10-26

Submission-readiness pass: closes the remaining course rubric gaps (deployment, full CD, observability UI, public task tracker).

### Added

- **Observability UI** (`observability/`): Prometheus (scrape + store), Loki + Promtail (log collection + storage with JSON parsing of `trace_id`/`level`/`event`), and Grafana with auto-provisioned datasources and a pre-built "Modern Dicompyler - User Journey" dashboard (request rate, p95 duration, failures by error class, DB up, trace-id-correlated logs). Included in `docker compose up` (single command, six services).
- **Hugging Face Spaces deployment** (`deploy/hf/Dockerfile.api`, `deploy/hf/Dockerfile.dashboard`, `scripts/deploy_hf.sh`): `PORT`-aware Dockerfiles (`app_port: 7860`), Space card generation, force-push deploy of each service; dashboard Space consumes an `API_URL` variable.
- **Full CD + manual production gate** (`.github/workflows/`): `deploy-dev.yml` now deploys both services to the dev Spaces on every push to main/develop and smoke-tests `/health`; new `deploy-prod.yml` performs manual production deploys (`workflow_dispatch` + typed confirmation + protected `production` environment).
- **Public task tracker** (`scripts/create_issues.sh`, `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md`): idempotent bootstrap of one GitHub Issue per backlog epic with acceptance criteria; PR template enforces `Closes #N` linkage as tracker evidence.
- **Makefile**: `make up/down/test/lint/demo/logs/dev-api/dev-ui` single-command developer UX.

### Changed

- Root `Dockerfile` honours the `PORT` environment variable (defaults to 8000) so the same image runs on Compose and on platforms that inject the port.
- Compose services get deterministic `container_name`s (`modern-dicompyler-api`, ...) used by Promtail's relabel/keep rules.
- On-call responder now probes the deployment via the `DEV_API_URL` secret (was `DEPLOYMENT_URL`).
- `deploy-dev.yml` triggers on `main` and `develop`; smoke test retries 10×30s to accommodate Space image builds.

## [1.0.0] - 2026-10-26

Project 1 submission for the DataTalks AI Dev Tools Zoomcamp.

### Added

- **Domain engine** (`src/engine.py`): `detect_rt_object`, `parse_rtplan`, `parse_rtstruct`, `parse_rtdose`, `run_synthetic_demo_case`; warning-aware parsing (missing fields become `null` + warning), typed error taxonomy (`InvalidDICOMError`, `UnsupportedRTObjectError`, `MissingRequiredAttributeError`, `DatabaseUnavailableError`).
- **dicompyler-core integration**: DVH statistics via `dvh.DVH.from_dicom_dvh` and RTSTRUCT type enrichment via `DicomParser.GetStructures`, both with graceful pydicom fallback when dicompyler-core is unavailable or incompatible. pydicom pinned to 2.4.x for compatibility.
- **Deterministic synthetic case** (`src/synthetic_data.py`): synthetic RTPLAN (2 beams, 30 fx, 60 Gy), RTSTRUCT (3 ROIs with contours), RTDOSE (16x16x4 grid + cumulative DVH) built from named constants with deterministic UIDs; no randomness.
- **FastAPI backend** (`src/main.py`): all required endpoints (`/api/v1/analyses`, `/api/v1/demo-case`, `/api/v1/demo-case/plan`, `/health`, `/metrics`), structured error bodies, request-size limits.
- **SQLite persistence** (`src/db.py`, `src/models.py`): `AnalysisRecord` + `AuditEvent`; every analysis persisted, including failed parses; repeated demo runs create separate records.
- **Streamlit dashboard** (`src/dashboard.py`): Python-only UI with title, safety notice, Load demo case, `.dcm` uploader, and Overview / Structures / Plan / Dose-DVH / History tabs with explicit empty states.
- **Observability** (`src/telemetry.py`): structured JSON logging (trace_id, request_id, route, status_code, duration_ms, outcome, error_class), Prometheus metrics (`rtqa_analysis_requests_total`, `rtqa_analysis_duration_seconds`, `rtqa_analysis_failures_total`, `rtqa_database_up`).
- **Alerting** (`src/alerting.py`): consecutive `/health` failures, demo-case failures, and >20%/5-minute failure rates raise GitHub Issues labelled `on-call` (cooldown-guarded, no PHI/secrets).
- **On-call responder** (`scripts/on_call_diagnose.py` + `.github/workflows/on-call-responder.yml`): diagnostics (uv sync, Ruff, pytest, optional /health probe), incident classification, structured issue comment; rollback only proposed for human approval.
- **Docker**: multi-stage `Dockerfile` (python:3.12-slim, uv, non-root, HEALTHCHECK) and `docker-compose.yml` (api :8000 + dashboard :8501 with `API_URL=http://api:8000`, SQLite in named volume).
- **CI/CD**: `ci.yml` (Ruff + pytest), `deploy-dev.yml` (Docker build validation, optional platform deploy hook, /health smoke test).
- **Tests**: 37 unit + integration tests covering determinism, all three parsers, null+warning behaviour, malformed/unsupported inputs, typed errors, persistence, pagination, health, and metrics.
- **Documentation**: `README.md`, `AGENTS.md`, `backlog.md`, and `docs/{spec,architecture,agents,testing,deployment,observability,incident-response}.md`.

### Fixed

- pydicom 3.0.x incompatibility with dicompyler-core 0.5.6 (`pydicom.pixel_data_handlers` removed) by pinning `pydicom>=2.4.4,<3`; `dataset_to_bytes` supports both pydicom 2.x and 3.x write APIs.
- DVH Sequence item dose units/type now use the standard `DoseUnits`/`DoseType` keywords (there are no `DVHDoseUnits`/`DVHDoseType` tags in the DICOM dictionary).
- In-memory datasets carry a valid file meta so `dicomparser.DicomParser` can run its `validate_file_meta` step.

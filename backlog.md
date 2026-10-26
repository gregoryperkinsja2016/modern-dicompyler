# backlog.md

Status legend: `[x]` completed, `[ ]` pending. Dates refer to the 1.0.0 implementation sprint.

## Specification

- [x] Problem statement, user stories, acceptance criteria, non-goals (`docs/spec.md`)
- [x] Repository structure fixed to the required layout
- [x] Safety notice wording agreed ("Read-only demonstration viewer. Not for clinical plan verification.")

## Agent team

- [x] `AGENTS.md` with roles, constraints, commands, supervision workflow, definition of done
- [x] `docs/agents.md` with per-role responsibilities and hand-off artefacts

## Full-stack app

- [x] FastAPI app factory with lifespan, CORS, observability middleware (`src/main.py`)
- [x] `POST /api/v1/analyses` upload + parse + persist + audit
- [x] `GET /api/v1/analyses` paginated history
- [x] `GET /api/v1/analyses/{id}` and `GET /api/v1/analyses/{id}/plan`
- [x] `POST /api/v1/demo-case`, `GET /api/v1/demo-case`, `GET /api/v1/demo-case/plan`
- [x] `GET /health` (application + database) and `GET /metrics` (Prometheus)
- [x] Domain engine: `detect_rt_object`, `parse_rtplan`, `parse_rtstruct`, `parse_rtdose`, `run_synthetic_demo_case`
- [x] Deterministic synthetic RTPLAN/RTSTRUCT/RTDOSE with named constants (`src/synthetic_data.py`)
- [x] dicompyler-core integration (DVH stats + RTSTRUCT type enrichment) with pydicom fallback
- [x] Typed error taxonomy + structured 4xx/5xx error bodies
- [x] SQLite models `AnalysisRecord` + `AuditEvent`; every analysis persisted (including failed parses)
- [x] Python-only Streamlit dashboard with Overview / Structures / Plan / Dose-DVH / History tabs
- [x] Load demo case button, `.dcm` uploader, empty states, history pagination

## Testing

- [x] Unit: synthetic determinism, UID stability, constant consistency
- [x] Unit: RTPLAN / RTSTRUCT / RTDOSE parsing (values match constants)
- [x] Unit: missing fields -> null + warnings (plan, struct, dose)
- [x] Unit: malformed bytes, empty bytes -> `InvalidDICOMError`
- [x] Unit: unsupported object (CT) -> `UnsupportedRTObjectError`
- [x] Unit: typed error hierarchy
- [x] Integration: demo case creates analysis + audit record
- [x] Integration: demo-case plan endpoint returns beam data
- [x] Integration: history returns persisted records; pagination shape
- [x] Integration: repeated demo runs create separate records
- [x] Integration: invalid upload -> structured 400; failed parse persisted
- [x] Integration: health checks DB; metrics expose all four metric families

## Docker

- [x] Multi-stage Dockerfile (python:3.12-slim, uv install, non-root, HEALTHCHECK on /health)
- [x] `docker-compose.yml` with `api` (:8000, named volume) and `dashboard` (:8501, `API_URL=http://api:8000`)
- [x] `.dockerignore`

## Deployment

- [x] Local Docker Compose documented as the verified runtime (`docs/deployment.md`)
- [x] Cloud deploy path via platform hook secrets (Render/Railway/Fly.io/HF Spaces)
- [x] Rollback procedure documented
- [ ] Public cloud URL (optional; requires human to create platform account and set secrets)

## CI/CD

- [x] `ci.yml`: uv install, Ruff, pytest on PRs and pushes to main
- [x] `deploy-dev.yml`: Docker build validation, optional deploy hook, `/health` smoke test
- [x] Secrets documented; no secrets committed

## Observability

- [x] Structured JSON logging with trace_id/request_id/route/status_code/duration_ms/outcome/error_class
- [x] Prometheus metrics: `rtqa_analysis_requests_total{route,outcome}`, `rtqa_analysis_duration_seconds`, `rtqa_analysis_failures_total{error_class}`, `rtqa_database_up`
- [x] No-PHI/no-secrets logging rules documented and enforced

## Alerting

- [x] Consecutive `/health` failure alert (>= 2)
- [x] Demo-case failure alert
- [x] Analysis failure rate alert (> 20% over 5 minutes, cooldown-guarded)
- [x] GitHub Issue creation labelled `on-call` with checklist, metrics snapshot, no PHI/secrets

## On-call agent

- [x] `on-call-responder.yml` triggered by `on-call` label
- [x] `scripts/on_call_diagnose.py`: parse issue, uv sync + Ruff + pytest, optional /health probe, classification, structured comment
- [x] Hard boundaries: never deploys/pushes/deletes without human approval; rollback PR only if `KNOWN_GOOD_IMAGE_TAG` exists

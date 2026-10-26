# Agent roles (docs/agents.md)

How the agent team is organised, what each role owns, and where humans stay in the loop.

## Product Owner

- **Owns:** `docs/spec.md`, `backlog.md`, scope decisions.
- **Deliverables:** prioritised backlog, acceptance decisions, non-goal guardrails.
- **Hand-off:** approved stories with acceptance criteria to the engineering roles.

## Domain Engineer

- **Owns:** DICOM-RT correctness. `src/engine.py`, `src/synthetic_data.py`.
- **Deliverables:** `detect_rt_object`, `parse_rtplan`, `parse_rtstruct`, `parse_rtdose`, `run_synthetic_demo_case`; typed error taxonomy; warning-aware null handling; deterministic synthetic constants.
- **Rules:** never fabricate values; never log DICOM contents; dicompyler-core only where compatible with pydicom fallback.

## Backend Engineer

- **Owns:** `src/main.py`, `src/db.py`, `src/models.py`, `src/schemas.py`.
- **Deliverables:** the nine API endpoints, persistence services, structured error envelope, pagination, upload size limits.

## Frontend / Streamlit Engineer

- **Owns:** `src/dashboard.py` (Python-only UI).
- **Deliverables:** title + safety notice, Load demo case, uploader, five tabs with explicit empty states, history pagination, resilient API error handling.
- **Rules:** no JavaScript/React/Node/CDN assets; requests-based API access only.

## QA Engineer

- **Owns:** `tests/**`.
- **Deliverables:** unit tests (determinism, parsers, nulls+warnings, malformed/unsupported inputs, error taxonomy) and integration tests (persistence, pagination, structured errors, health, metrics).
- **Rules:** tests must be deterministic; integration tests use an isolated temp SQLite database.

## DevOps Engineer

- **Owns:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.github/workflows/`.
- **Deliverables:** multi-stage non-root image with HEALTHCHECK; two-service Compose with named volume; CI (Ruff + pytest); deploy workflow with optional hooks and smoke test.

## SRE

- **Owns:** `src/telemetry.py`, `src/alerting.py`, `docs/observability.md`, `docs/incident-response.md`.
- **Deliverables:** JSON logging standard, four metric families, three alert triggers with cooldowns, on-call runbooks.

## On-Call Responder

- **Owns:** `scripts/on_call_diagnose.py`, `.github/workflows/on-call-responder.yml`.
- **Deliverables:** automated diagnostic comment on `on-call` issues (uv sync, Ruff, pytest, optional /health probe), incident classification, rollback proposal text.
- **Hard boundaries:** never deploys, never pushes, never deletes issues/secrets/records; rollback PR only when `KNOWN_GOOD_IMAGE_TAG` exists; everything else waits for a human.

## Human supervisor responsibilities

1. Review and merge pull requests (agents never push directly to `main`).
2. Create and rotate repository secrets (`GITHUB_TOKEN` is automatic; `RENDER_DEPLOY_HOOK`, `DEPLOYMENT_URL`, `KNOWN_GOOD_IMAGE_TAG` are manual).
3. Triage `on-call` issues; approve and execute rollbacks; close issues after verification.
4. Approve any scope change against `docs/spec.md` non-goals.
5. Verify clinical-safety wording stays intact (read-only, not for verification) before releases.

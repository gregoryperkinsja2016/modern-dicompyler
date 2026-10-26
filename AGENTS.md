# AGENTS.md

## Project purpose

Modern Dicompyler is a read-only, web-based modernisation of the legacy Dicompyler DICOM-RT desktop app. It lets a user inspect RTSTRUCT ROIs, RTPLAN plan/beam metadata, RTDOSE dose metadata and DVH data, and previous analysis history - either from a deterministic synthetic demo case or from an uploaded `.dcm` file. It is Project 1 of the DataTalks AI Dev Tools Zoomcamp.

## Non-negotiable constraints

1. The frontend is **Python-only Streamlit**. No JavaScript, React, Next.js, Vite, npm, Node, Tailwind CDN, Chart.js CDN, or custom HTML/JS frontend files.
2. No real patient data or PHI - ever. The demo case is deterministic and synthetic.
3. Never fabricate dose values, angles, ROI names, volumes, dates, or beam parameters. Missing DICOM fields are `null` plus a warning.
4. Parsing failures raise typed exceptions (`InvalidDICOMError`, `UnsupportedRTObjectError`, `MissingRequiredAttributeError`, `DatabaseUnavailableError`). No bare `except`, no `try/except pass`.
5. Never log DICOM contents, PHI, credentials, or raw uploaded file contents. Never return raw stack traces in API responses.
6. Never delete issues, modify secrets, or delete database records.
7. Never deploy to production or push directly to `main` without human approval.
8. Backend is FastAPI + Pydantic v2 + SQLite (SQLAlchemy). Dependencies are managed with `uv` and `pyproject.toml`.

## Commands

```bash
uv sync                                   # install/update dependencies + uv.lock
uv run ruff check .                       # lint (must pass)
uv run pytest                             # unit + integration tests (must pass)
uv run uvicorn src.main:app --reload      # API on http://localhost:8000
uv run streamlit run src/dashboard.py     # UI on http://localhost:8501
docker compose up --build                 # full stack (API :8000, UI :8501)
```

## Agent roles

| Role | Responsibility | Primary files |
| --- | --- | --- |
| Product Owner | Scope guard; accepts/rejects features against `docs/spec.md` | `docs/spec.md`, `backlog.md` |
| Domain Engineer | DICOM-RT parsing, synthetic case, typed errors | `src/engine.py`, `src/synthetic_data.py` |
| Backend Engineer | FastAPI endpoints, persistence, request handling | `src/main.py`, `src/db.py`, `src/models.py`, `src/schemas.py` |
| Frontend/Streamlit Engineer | Dashboard tabs, empty states, API client | `src/dashboard.py` |
| QA Engineer | Unit + integration tests, structured-error coverage | `tests/**` |
| DevOps Engineer | Docker, Compose, GitHub Actions CI/CD | `Dockerfile`, `docker-compose.yml`, `.github/workflows/` |
| SRE | Logging, metrics, health, alert rules | `src/telemetry.py`, `src/alerting.py`, `docs/observability.md` |
| On-Call Responder | Diagnose `on-call` issues, propose (never execute) rollbacks | `scripts/on_call_diagnose.py`, `.github/workflows/on-call-responder.yml` |

## Human supervision workflow

1. Agents work on feature branches; humans review and merge pull requests into `main`.
2. Every automated alert (GitHub Issue labelled `on-call`) is triaged by a human; the responder workflow only comments diagnostics.
3. Rollbacks are proposed as exact commands; a human runs and approves them.
4. Secrets are added only by humans via GitHub repository settings; agents never touch them.
5. CI must pass (Ruff + pytest) before any merge.

## Definition of done

A change is done when:

- `uv sync`, `uv run ruff check .`, and `uv run pytest` all pass locally;
- the Streamlit dashboard works against the API (demo case, upload path, history);
- Docker Compose still builds and both services come up healthy;
- no PHI, no secrets, no fabricated clinical values are introduced;
- relevant docs (`README.md`, `docs/*`, `backlog.md`, `CHANGELOG.md`) are updated;
- a pull request exists and CI is green.

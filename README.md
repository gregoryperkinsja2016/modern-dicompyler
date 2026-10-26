# Modern Dicompyler

**Project 1 - DataTalks AI Dev Tools Zoomcamp**

Modern Dicompyler is a web-based modernisation of the legacy [Dicompyler](https://github.com/dicompyler/dicompyler) DICOM-RT desktop application. It lets a user inspect DICOM-RT information in a browser - RTSTRUCT structures/ROIs, RTPLAN plan and beam metadata, RTDOSE dose metadata and DVH information where available, and previous analysis history.

> **Safety notice:** Read-only demonstration viewer. **Not for clinical plan verification.**

The user can either:

1. Click **Load demo case** to analyse a deterministic synthetic DICOM-RT case (no upload required, no PHI); or
2. Upload a DICOM-RT file (`.dcm`).

## What it modernises

Compared with the legacy Dicompyler desktop workflow, this project improves:

| Aspect | How |
| --- | --- |
| **Accessibility** | Runs in any browser via Streamlit - no desktop installation, no Python knowledge needed for the demo case. |
| **Maintainability** | Small typed modules (`engine`, `db`, `telemetry`, `alerting`), a typed error taxonomy, `uv`-managed dependencies, Ruff lint, pytest suites. |
| **Auditability** | Every analysis (including failed parses) is persisted in SQLite with an `AuditEvent`, trace ids, and warnings - queryable through the API. |
| **Deployability** | Multi-stage Docker image (non-root, health-checked) + one-command `docker compose up`. |
| **Integrability** | Clean REST API (`/api/v1/...`), Prometheus metrics, structured JSON logs, GitHub Issue alerting with an on-call responder workflow. |

**Honesty note:** this project does **not** claim to make low-level DICOM parsing or DVH computation faster than `dicompyler-core`. Parsing uses pydicom (warning-aware, null-safe); `dicompyler-core` is used only where compatible - DVH statistics and RTSTRUCT type enrichment - with graceful degradation to pure pydicom when unavailable.

## Architecture (one paragraph)

The **Streamlit dashboard** (`src/dashboard.py`, Python-only UI) talks to the **FastAPI API** (`src/main.py`) over HTTP using `requests`. The API parses DICOM-RT objects with the **domain engine** (`src/engine.py` + `src/synthetic_data.py`), persists every analysis + audit event in **SQLite** via SQLAlchemy (`src/db.py`, `src/models.py`), and exposes Prometheus metrics and structured JSON logs (`src/telemetry.py`). Alerting (`src/alerting.py`) raises GitHub Issues labelled `on-call`; a GitHub Actions responder runs diagnostics and comments on the issue.

## Safety and privacy

- Read-only demonstration viewer; **not for clinical plan verification**.
- No dose calculation, no clinical plan verification, no 3D rendering, no MLC animation.
- No real patient data or PHI: the demo case is fully synthetic (`SYNTH-0001`).
- DICOM contents, PHI, credentials, and raw uploaded files are never logged.

## Quickstart (local, with uv)

Requires Python 3.11 or 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                # install dependencies (creates .venv and uv.lock)
uv run uvicorn src.main:app --reload   # terminal 1: API on port 8000
uv run streamlit run src/dashboard.py  # terminal 2: dashboard on port 8501
```

Then open:

- Streamlit dashboard: <http://localhost:8501>
- API docs (Swagger): <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>
- Prometheus metrics: <http://localhost:8000/metrics>

Click **Load demo case** in the dashboard, then browse the Overview / Structures / Plan / Dose-DVH / History tabs. History persists in SQLite (`data/dicomrt.db`) across browser refreshes and restarts.

## Quickstart (Docker Compose)

```bash
docker compose up --build
```

This starts two services:

| Service | Port | Notes |
| --- | --- | --- |
| `api` | 8000 | FastAPI + uvicorn; SQLite persisted in the named volume `dicomrt-data`. |
| `dashboard` | 8501 | Streamlit; uses `API_URL=http://api:8000`; waits for the API health check. |

Same URLs as above. Stop with `Ctrl+C`; remove data with `docker compose down -v`.

## Tests

```bash
uv run pytest          # 37 unit + integration tests
uv run ruff check .    # lint
```

## API

Interactive docs at <http://localhost:8000/docs>. Main endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/analyses` | Upload + parse a DICOM-RT file |
| GET | `/api/v1/analyses` | Paginated analysis history |
| GET | `/api/v1/analyses/{id}` | One analysis (with audit events) |
| GET | `/api/v1/analyses/{id}/plan` | RTPLAN data for an analysis |
| POST / GET | `/api/v1/demo-case` | Run the synthetic demo case (persisted) |
| GET | `/api/v1/demo-case/plan` | Synthetic RTPLAN inspection data |
| GET | `/health` | Application + database health |
| GET | `/metrics` | Prometheus metrics |

## CI/CD and operations

- `.github/workflows/ci.yml` - Ruff + pytest on every pull request and push to main.
- `.github/workflows/deploy-dev.yml` - Docker build validation on merge to main, optional platform deploy hook (Render/Railway/Fly.io/HF Spaces via secrets), post-deploy `/health` smoke test.
- `.github/workflows/on-call-responder.yml` - triggered by an issue labelled `on-call`; runs diagnostics and comments a structured report. It never deploys or pushes without human approval.
- Alerts (GitHub Issues labelled `on-call`) fire when: `/health` fails twice consecutively, a demo-case analysis fails, or the analysis failure rate exceeds 20% over five minutes.

## Deployment URL

The verified runtime for this submission is the **local Docker Compose setup** (see `docs/deployment.md`). A public cloud URL is optional; set the `RENDER_DEPLOY_HOOK` and `DEPLOYMENT_URL` repository secrets to enable automated deploys and smoke tests. Current deployment URL: *not configured at submission time*.

## Non-goals

- Dose calculation, optimisation, or clinical plan verification.
- 3D rendering, MLC animation, or advanced visualisation.
- Multi-user authentication, authorisation, or tenancy.
- Any use of real patient data or PHI.
- Kubernetes, microservice meshing, or horizontal scaling.
- Outperforming `dicompyler-core` at low-level DICOM/DVH computation.

## Project structure

```
modern-dicompyler/
├── AGENTS.md, README.md, CHANGELOG.md, backlog.md
├── pyproject.toml, uv.lock, Dockerfile, docker-compose.yml, .dockerignore
├── .github/workflows/{ci.yml, deploy-dev.yml, on-call-responder.yml}
├── docs/{spec,architecture,agents,testing,deployment,observability,incident-response}.md
├── src/{main,config,schemas,engine,synthetic_data,db,models,telemetry,alerting,dashboard}.py
├── scripts/on_call_diagnose.py
└── tests/{unit/{test_engine,test_synthetic_data}.py, integration/test_api_workflow.py}
```

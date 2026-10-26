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

## Quickstart (Docker Compose - one command, full stack incl. database + observability)

```bash
docker compose up --build        # or: make up
```

This starts six services:

| Service | Port | Notes |
| --- | --- | --- |
| `api` | 8000 | FastAPI + uvicorn; SQLite persisted in the named volume `dicomrt-data`. |
| `dashboard` | 8501 | Streamlit; uses `API_URL=http://api:8000`; waits for the API health check. |
| `prometheus` | 9090 | Scrapes the API's `/metrics` every 15s. |
| `loki` | 3100 | Stores the structured JSON logs shipped by Promtail. |
| `promtail` | - | Ships api/dashboard container logs to Loki (parses `trace_id`, `level`, `event`). |
| `grafana` | 3000 | UI for metrics + logs; pre-provisioned "Modern Dicompyler - User Journey" dashboard. |

Same URLs as above, plus:

- Grafana UI: <http://localhost:3000> (anonymous Admin access for the local demo)
- Prometheus UI: <http://localhost:9090>

Stop with `Ctrl+C` (or `docker compose down`); remove data with `docker compose down -v`.

## Observability (metrics + traces + structured logs, viewable in a UI)

The key user journey ("analyse a case") is instrumented end to end:

- **Structured logs** - every request emits one JSON line with `trace_id`, `request_id`, `route`, `status_code`, `duration_ms`, `outcome`, and `error_class`. No PHI, no credentials, no DICOM contents.
- **Metrics** - `rtqa_analysis_requests_total{route,outcome}`, `rtqa_analysis_duration_seconds` (histogram), `rtqa_analysis_failures_total{error_class}`, `rtqa_database_up`.
- **Trace correlation** - the same `trace_id` appears in the API error envelope, in the JSON logs, and can be grepped in Grafana: open the pre-provisioned dashboard, read p95 latency / failure rate / DB status, then filter the logs panel by `trace_id` to see exactly what happened for one request.
- **Collected, stored, viewable** - Prometheus scrapes and stores metrics; Loki stores logs; Grafana (port 3000) is the UI, provisioned automatically on first start (`observability/grafana/`).

## Alerting on user impact

Alerts fire on **user-visible impact** (not CPU graphs), as GitHub Issues labelled `on-call` (see `src/alerting.py`):

1. `/health` fails **twice consecutively**;
2. a **demo-case** analysis fails;
3. analysis **failure rate > 20%** over 5 minutes (cooldown-guarded).

The on-call responder workflow (below) wakes up on the `on-call` label.

## Task tracker and agent process

- **Specification:** `docs/spec.md` (problem, user stories, acceptance criteria, non-goals).
- **Public task tracker:** the backlog is mirrored to GitHub Issues by an idempotent script:

  ```bash
  bash scripts/create_issues.sh   # creates one issue per epic, each with acceptance criteria
  ```

- **Evidence agents use the tracker:** every pull request is linked to an issue with `Closes #N` (see `.github/PULL_REQUEST_TEMPLATE.md`); runtime alerts open issues automatically; agent roles and hand-offs are defined in `AGENTS.md` + `docs/agents.md`; `AGENTS.md` is the entry point to the modular docs.

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
- `.github/workflows/deploy-dev.yml` - on every push to main/develop: Docker build validation, **automatic deploy of both services to the dev Hugging Face Spaces** (`scripts/deploy_hf.sh`), post-deploy `/health` smoke test. Degrades gracefully when the HF secrets are not set.
- `.github/workflows/deploy-prod.yml` - **manual deploy to production**: `workflow_dispatch` only, requires typing a confirmation and passes through the protected `production` environment (configure required reviewers in repo settings).
- `.github/workflows/on-call-responder.yml` - triggered by an issue labelled `on-call`; runs diagnostics and comments a structured report. It never deploys or pushes without human approval.

Required repository secrets (all optional until you deploy): `HF_TOKEN`, `HF_API_SPACE_DEV`, `HF_DASHBOARD_SPACE_DEV`, `DEV_API_URL`, `HF_API_SPACE_PROD`, `HF_DASHBOARD_SPACE_PROD`, `PROD_API_URL`.

## Deployment URL (Hugging Face Spaces)

The application deploys to **Hugging Face Spaces** (free, Docker SDK, `app_port: 7860`):

| Service | URL pattern | Notes |
| --- | --- | --- |
| API | `https://huggingface.co/spaces/<owner>/modern-dicompyler-api` | Swagger at `.../docs`, health at `.../health`. |
| Dashboard | `https://huggingface.co/spaces/<owner>/modern-dicompyler-dashboard` | Needs the `API_URL` Space variable pointing at the API Space URL. |

Deploy automatically (CD on push, via `deploy-dev.yml` once secrets are set) or manually:

```bash
HF_TOKEN=hf_xxx bash scripts/deploy_hf.sh api        <owner>/modern-dicompyler-api
HF_TOKEN=hf_xxx API_URL=https://<owner>-modern-dicompyler-api.hf.space \
               bash scripts/deploy_hf.sh dashboard   <owner>/modern-dicompyler-dashboard
```

Live deployment URLs for this submission: **<paste-your-API-space-url>** and **<paste-your-dashboard-space-url>** (or run the stack locally with the single `docker compose up --build` command - see `docs/deployment.md`). SQLite storage on free Spaces is ephemeral; the demo case re-populates history in one click. Local Docker Compose keeps data in a named volume.

## Grading criteria map (for peer reviewers)

| Course criterion | Where to look |
| --- | --- |
| Problem description | `README.md` (top) + `docs/spec.md` |
| Product spec + public task tracker | `docs/spec.md`, `backlog.md`, `scripts/create_issues.sh` -> GitHub Issues |
| Agent team specification | `AGENTS.md` (roles, supervision workflow) + `docs/agents.md` |
| Context management | `AGENTS.md` -> modular docs in `docs/` |
| Application end to end | Streamlit -> FastAPI -> SQLite; single command `docker compose up --build` |
| Unit + integration tests, one command | `uv run pytest` (37 tests) |
| Containerization incl. database | `Dockerfile`, `docker-compose.yml`, named volume |
| Deployment at a public URL | Hugging Face Spaces section above |
| CI runs tests, CD deploys, manual prod | `ci.yml`, `deploy-dev.yml`, `deploy-prod.yml` |
| Observability (metrics/logs/traces in a UI) | Grafana at `localhost:3000` via Compose; `docs/observability.md` |
| Alerting on user impact | `src/alerting.py` (3 triggers -> `on-call` issues) |
| On-call agent | `on-call-responder.yml` + `scripts/on_call_diagnose.py` |

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
├── AGENTS.md, README.md, CHANGELOG.md, backlog.md, Makefile
├── pyproject.toml, uv.lock, Dockerfile, docker-compose.yml, .dockerignore
├── .github/{workflows/{ci,deploy-dev,deploy-prod,on-call-responder}.yml, ISSUE_TEMPLATE/, PULL_REQUEST_TEMPLATE.md}
├── docs/{spec,architecture,agents,testing,deployment,observability,incident-response}.md
├── observability/           # Prometheus, Loki, Promtail, Grafana provisioning + dashboard
├── deploy/hf/               # Hugging Face Space Dockerfiles (api, dashboard)
├── src/{main,config,schemas,engine,synthetic_data,db,models,telemetry,alerting,dashboard}.py
├── scripts/{on_call_diagnose,deploy_hf,create_issues}.sh|.py
└── tests/{unit/{test_engine,test_synthetic_data}.py, integration/test_api_workflow.py}
```

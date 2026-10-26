# Specification (spec.md)

## Problem statement

The legacy Dicompyler desktop application makes DICOM-RT inspection hard to access in modern workflows: it requires a local desktop install, offers no API for integration, keeps no auditable history of what was inspected, and is difficult to deploy or observe. Radiotherapy teams and students need a lightweight, read-only way to look inside RTSTRUCT/RTPLAN/RTDOSE objects - including from machines where installing desktop software is impractical.

## Product goal

A web-based, read-only DICOM-RT inspection platform ("Modern Dicompyler") with two entry points: a deterministic synthetic demo case (zero setup, zero PHI) and a file upload path. Every inspection is persisted with an audit trail and is observable (metrics, logs, alerts).

## User stories

1. **As a student**, I click "Load demo case" and immediately see synthetic structures, plan/beam metadata, dose metadata and a DVH in my browser, so I can learn what RT objects contain without any DICOM file.
2. **As a physicist/engineer**, I upload a `.dcm` file and see its RT object type, warnings for missing attributes, and structured tables - without installing a desktop application.
3. **As a reviewer**, I open the History tab after a browser refresh and still see all previous analyses, so my session is auditable.
4. **As an integrator**, I call `POST /api/v1/analyses` or `GET /api/v1/demo-case` from other tools and receive structured JSON with stable schema.
5. **As an SRE**, I scrape `/metrics`, watch `/health`, and receive a GitHub `on-call` issue when the service degrades.
6. **As a maintainer**, I run `uv run pytest` and `uv run ruff check .` and trust the result.

## Functional requirements

- Streamlit dashboard: title "Modern Dicompyler", safety notice "Read-only demonstration viewer. Not for clinical plan verification.", "Load demo case" button, `.dcm` uploader, tabs: Overview, Structures, Plan, Dose / DVH, History (with empty states).
- Overview: analysis ID, timestamp, detected RT object type, warnings, full JSON response.
- Structures: ROI number/name/type, contour count where available.
- Plan: plan metadata + beam table (number, name, machine, radiation type, beam type, energy, gantry/collimator/couch angles, dose-reference linkage). Missing fields are `null` + warning; never invented.
- Dose / DVH: dose metadata, dose units, dose-grid information, safely derivable statistics, DVH data where available; explicit empty state otherwise.
- History: `GET /api/v1/analyses`; persists across refreshes (SQLite).
- API: the nine endpoints listed in `README.md`.
- Domain engine: separate parser functions; pydicom-based; dicompyler-core only where compatible.
- Synthetic demo case: no upload required, deterministic, named constants, realistic shape.
- Observability: structured JSON logs with trace/request ids; the four Prometheus metric families.
- Alerting: three triggers (health x2, demo failure, >20%/5min failure rate) creating GitHub Issues labelled `on-call`; on-call responder workflow with diagnostics and structured comment.
- Database: SQLite; `AnalysisRecord` + `AuditEvent`; every analysis persisted; repeated demo runs are separate records.

## Non-goals

- Dose calculation, optimisation, clinical plan verification.
- 3D rendering, MLC animation, advanced visualisation.
- Authentication/authorisation or multi-tenancy.
- Real patient data or PHI.
- Kubernetes; making DICOM parsing or DVH computation faster than dicompyler-core.

## Acceptance criteria

1. `uv sync` installs a working environment from the lockfile.
2. `uv run ruff check .` passes with zero findings.
3. `uv run pytest` passes (37 tests at submission).
4. `uv run uvicorn src.main:app --reload` serves `/health`, `/docs`, `/metrics`, and the demo-case endpoints.
5. `uv run streamlit run src/dashboard.py` shows the dashboard; demo case and history work.
6. `docker compose up --build` starts api + dashboard; both are reachable and healthy.
7. Invalid uploads return structured 400 errors (`error.class`), and the failed attempt is persisted.
8. Two consecutive demo-case runs produce two distinct analysis records.
9. A GitHub Issue labelled `on-call` triggers the responder workflow, which comments a diagnostic report without deploying anything.

## Definition of done

All acceptance criteria verified, documentation current (`README.md`, `docs/*`, `backlog.md`, `CHANGELOG.md`), backlog items ticked, and the local Docker Compose setup documented as the verified runtime.

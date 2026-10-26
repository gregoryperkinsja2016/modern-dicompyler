# Architecture

## Component diagram

```
                +-------------------------------+
                |   Browser (any device)        |
                +---------------+---------------+
                                |
                                v
                +-------------------------------+
                |  Streamlit dashboard (8501)   |  src/dashboard.py  [Python-only UI]
                |  tabs: Overview / Structures  |
                |  / Plan / Dose-DVH / History  |
                +---------------+---------------+
                                |  HTTP (requests), API_URL env
                                v
+-------------+   +-------------------------------+   +--------------------------+
| Prometheus  |<--|      FastAPI API (8000)       |-->|  GitHub Issues (on-call) |
| scraper     |   |  src/main.py                  |   |  via src/alerting.py     |
+-------------+   |  - observability middleware   |   +--------------------------+
                  |  - /api/v1/... endpoints      |
                  +-------+---------------+-------+
                          |               |
                          v               v
              +---------------+   +---------------------------+
              | Domain engine |   | SQLite (SQLAlchemy)       |
              | src/engine.py |   | src/db.py + src/models.py |
              | synthetic case|   | analyses + audit_events   |
              +-------+-------+   +---------------------------+
                      |
                      v
          +------------------------+
          | pydicom (parsing)      |
          | dicompyler-core (DVH,  |
          |  structure types) with |
          |  pydicom fallback      |
          +------------------------+
```

## Repository structure

```
modern-dicompyler/
├── AGENTS.md              # agent roles, constraints, commands
├── README.md              # product overview + quickstart
├── CHANGELOG.md           # implementation history
├── backlog.md             # task groups with completion status
├── pyproject.toml         # dependencies, ruff, pytest config
├── uv.lock                # locked dependency graph
├── Dockerfile             # multi-stage, non-root, health-checked
├── docker-compose.yml     # api (:8000) + dashboard (:8501)
├── .github/workflows/     # ci.yml, deploy-dev.yml, on-call-responder.yml
├── docs/                  # this documentation set
├── src/
│   ├── main.py            # FastAPI app: routes, middleware, handlers
│   ├── config.py          # env-driven configuration constants
│   ├── schemas.py         # Pydantic v2 payload/response models
│   ├── engine.py          # RT detection/parsing + typed errors
│   ├── synthetic_data.py  # deterministic synthetic DICOM-RT datasets
│   ├── db.py              # engine/session + persistence services
│   ├── models.py          # AnalysisRecord, AuditEvent (SQLAlchemy)
│   ├── telemetry.py       # JSON logging, context vars, Prometheus metrics
│   ├── alerting.py        # GitHub Issues alerting + failure windows
│   └── dashboard.py       # Streamlit UI (Python-only)
├── scripts/
│   └── on_call_diagnose.py
└── tests/
    ├── conftest.py        # temp SQLite env, TestClient, dataset fixtures
    ├── unit/              # test_engine.py, test_synthetic_data.py
    └── integration/       # test_api_workflow.py
```

## API contract

All errors use one envelope:

```json
{ "error": { "class": "InvalidDICOMError", "message": "...", "trace_id": "..." } }
```

| Method | Path | Request | Success response |
| --- | --- | --- | --- |
| POST | `/api/v1/analyses` | multipart `file` (.dcm) | 201 `AnalysisDetail` |
| GET | `/api/v1/analyses` | `page`, `page_size` query | 200 `HistoryPage` |
| GET | `/api/v1/analyses/{id}` | - | 200 `AnalysisDetail` (incl. `audit_events`) |
| GET | `/api/v1/analyses/{id}/plan` | - | 200 `{analysis_id, rt_object_type, available, plan}` |
| POST | `/api/v1/demo-case` | - | 201 `AnalysisDetail` |
| GET | `/api/v1/demo-case` | - | 200 `AnalysisDetail` |
| GET | `/api/v1/demo-case/plan` | - | 200 `{rt_object_type, source, plan, warnings}` |
| GET | `/health` | - | 200 `HealthResponse` (503 never; unhealthy reported via `status`) |
| GET | `/metrics` | - | 200 Prometheus text |

Status codes: 400 for `InvalidDICOMError`/`UnsupportedRTObjectError`/`MissingRequiredAttributeError`, 404 `NotFoundError`, 413 `PayloadTooLargeError`, 422 `RequestValidationError`, 500 `InternalServerError`, 503 `DatabaseUnavailableError`.

### `AnalysisResult` payload (embedded in `AnalysisDetail.result`)

```json
{
  "rt_object_type": "DEMO_CASE | RTPLAN | RTSTRUCT | RTDOSE",
  "source": "demo_case | upload",
  "structures": {"structure_set_label": "...", "rois": [{"roi_number": 1, "roi_name": "...", "roi_type": "...", "contour_count": 4}], "roi_count": 3, "parser": "...", "warnings": []},
  "plan": {"plan_label": "...", "beams": [{"beam_number": 1, "gantry_angle": 0.0, "referenced_beam_number": 1, "beam_dose": 1.0, "beam_meterset": 100.0}], "warnings": []},
  "dose": {"dose_units": "GY", "grid": {...}, "has_dvh": true, "dvh": [{"roi_number": 2, "dose_bins": [...], "volumes": [...], "min_dose": ..., "max_dose": ..., "mean_dose": ...}], "warnings": []},
  "warnings": [], "errors": []
}
```

Missing DICOM attributes are `null` and described in the relevant `warnings` array. Values are never invented.

## Data model

```
analyses                                   audit_events
+ id (uuid hex, PK)                        + id (autoincrement PK)
+ created_at (UTC)                         + created_at (UTC)
+ rt_object_type (indexed)                 + analysis_id (indexed, FK-like)
+ status: completed | failed               + event_type: ANALYSIS_CREATED | ANALYSIS_FAILED
+ source: upload | demo_case               + detail_json (counts only, no PHI)
+ result_json (parsed payload or null)     + trace_id
+ warnings_json (list)
+ errors_json (list)
+ trace_id
```

Invariants: one `AuditEvent` per analysis creation (success or failure); repeated demo-case runs produce distinct `analyses` rows; failed uploads are stored with `status="failed"`, `rt_object_type="UNKNOWN"`.

## Key design decisions

1. **pydicom primary, dicompyler-core complementary.** Warning-aware null-safe parsing needs attribute-level control, so the engine parses with pydicom and uses dicompyler-core where it is strong (DVH stats, structure types) with a tested fallback. No performance claims are made.
2. **pydicom pinned `<3`.** dicompyler-core 0.5.6 imports `pydicom.pixel_data_handlers`, removed in pydicom 3. `dataset_to_bytes` supports both write APIs so a future upgrade is one edit.
3. **Failures are data.** Invalid uploads still create `AnalysisRecord(status="failed")` + `AuditEvent`, giving a complete audit trail without storing any file content.
4. **One error envelope everywhere** simplifies both the Streamlit client and third-party integrators.
5. **Cardinality-safe metrics:** route labels use route templates (e.g. `/api/v1/demo-case`), never raw paths or ids.

# Observability (docs/observability.md)

## Logs

All application logs are single-line JSON objects on stdout, emitted through `src/telemetry.py` (`JsonLogFormatter`). Uvicorn's default handlers are removed so every line is JSON.

Standard fields:

| Field | Meaning |
| --- | --- |
| `timestamp` | UTC ISO-8601 |
| `level`, `logger`, `message` | standard logging attributes |
| `trace_id` | per-request trace id (header `X-Trace-ID` or generated) |
| `request_id` | per-request id (header `X-Request-ID` or generated) |
| `route` | matched route template (e.g. `/api/v1/demo-case`) |
| `status_code` | HTTP status |
| `duration_ms` | server-side handling duration |
| `outcome` | `success` (<400), `failure` (4xx), `error` (5xx) |
| `error_class` | exception class name when a failure occurred |
| `event` | lifecycle markers (`startup`, `shutdown`, `analysis_created`, ...) |

Example:

```json
{"timestamp": "2026-10-26T18:00:00.000000+00:00", "level": "INFO", "logger": "dicomrt.api", "message": "http_request", "trace_id": "a1b2...", "request_id": "c3d4...", "route": "/api/v1/demo-case", "status_code": 201, "duration_ms": 12.4, "outcome": "success"}
```

Responses carry `X-Request-ID` and `X-Trace-ID` headers so a browser session can be correlated with logs.

### Never logged

- DICOM contents, pixel data, or raw uploaded file bytes;
- PHI (patient identifiers never enter logs, records, or responses - the parser never extracts them);
- credentials or secrets;
- raw stack traces (only the exception class name is recorded; responses never contain stack traces).

## Trace IDs

- `trace_id`/`request_id` are ContextVars set by `ObservabilityMiddleware`, so every log line inside a request - including from `db` or `alerting` - carries them automatically.
- `trace_id` is stored on `AnalysisRecord` and `AuditEvent`, linking an analysis in the database to its request logs.
- Alert issue bodies include the trace id so GitHub issues can be joined with logs.

## Metrics

Exposed at `GET /metrics` (Prometheus text format), defined in `src/telemetry.py`:

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `rtqa_analysis_requests_total` | counter | `route`, `outcome` | all `/api/v1` requests by route template and outcome |
| `rtqa_analysis_duration_seconds` | histogram | `route` | request duration distribution |
| `rtqa_analysis_failures_total` | counter | `error_class` | failed analysis requests (typed errors, validation, HTTP classes) |
| `rtqa_database_up` | gauge | - | 1 when the database accepts queries, 0 otherwise |

Route labels use **route templates** (never raw ids/paths) to keep cardinality bounded.

## Alert rules

Implemented in `src/alerting.py` (cooldown: 300s per alert key; issues labelled `on-call`):

| Trigger | Condition | Issue title |
| --- | --- | --- |
| Health failing | 2 consecutive `/health` checks with `database: false` | "Health endpoint failing consecutively" |
| Demo failure | any exception from the synthetic demo case | "Synthetic demo-case analysis failed" |
| Failure rate | > 20% failures over a rolling 5-minute window (>= 10 samples) | "Analysis failure rate above 20% over five minutes" |

Issue bodies contain: timestamp (UTC), environment, affected endpoint, error class, trace id, metric snapshot (`rtqa_analysis_requests_total`, `rtqa_analysis_failures_total`, `rtqa_database_up`), and a diagnostic checklist. No PHI or secrets.

If `GITHUB_TOKEN`/`GITHUB_REPO` are unset (local development), alerts are logged as `alert_github_disabled` warnings instead of raising issues.

## Dashboards

Any Prometheus instance can scrape `/metrics`. Minimal useful queries:

```promql
rate(rtqa_analysis_requests_total[5m])
sum by (outcome) (rate(rtqa_analysis_requests_total[5m]))
histogram_quantile(0.95, sum by (le, route) (rate(rtqa_analysis_duration_seconds_bucket[5m])))
topk(5, sum by (error_class) (rate(rtqa_analysis_failures_total[5m])))
min(rtqa_database_up)
```

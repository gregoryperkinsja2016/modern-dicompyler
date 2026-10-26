#!/usr/bin/env bash
# Bootstrap the public task tracker: creates one GitHub Issue per backlog epic,
# each with acceptance criteria, so the specification is publicly reviewable.
#
# Prerequisites: GitHub CLI (gh) authenticated against the project repository
# (`gh auth login`), run from anywhere inside the repository.
#
# Idempotent: an issue whose title already exists (open or closed) is skipped.
# Evidence of tracker usage: agents link commits/PRs to these issues with
# "Closes #N" and reference the numbers in CHANGELOG entries.
set -euo pipefail

if ! command -v gh >/dev/null 2>&1; then
  echo "error: GitHub CLI (gh) is required. https://cli.github.com/" >&2
  exit 1
fi

ensure_label() {
  gh label create "$1" --description "$2" --color "$3" --force >/dev/null 2>&1 || true
}

ensure_label feature "Product functionality" "0e8a16"
ensure_label infra "Build, deployment, CI/CD" "d4c5f9"
ensure_label docs "Documentation and specification" "fef2c0"
ensure_label reliability "Observability, alerting, on-call" "b60205"

existing_titles() {
  gh issue list --state all --limit 500 --json title --jq '.[].title'
}

create_issue() {
  local title="$1" body="$2" labels="$3"
  if existing_titles | grep -Fxq "$title"; then
    echo "skip (exists): $title"
  else
    gh issue create --title "$title" --body "$body" --label "$labels" >/dev/null
    echo "created: $title"
  fi
}

create_issue \
  "Spec: problem statement, user stories, acceptance criteria" \
  "Write \`docs/spec.md\`: problem statement, user stories, acceptance criteria, non-goals (no clinical use, no PHI).

**Acceptance criteria**
- [x] Problem statement and expected behaviour documented in English
- [x] User stories cover demo case + upload flows
- [x] Non-goals listed explicitly" \
  "docs"

create_issue \
  "Domain engine: detect + parse RTSTRUCT / RTPLAN / RTDOSE" \
  "Implement \`src/engine.py\` (\`detect_rt_object\`, \`parse_rtplan\`, \`parse_rtstruct\`, \`parse_rtdose\`) with a typed error taxonomy.

**Acceptance criteria**
- [x] Missing DICOM fields become \`null\` + warning (never fabricated)
- [x] Malformed bytes -> \`InvalidDICOMError\`; non-RT objects -> \`UnsupportedRTObjectError\`
- [x] No bare except / except-pass; unit tests cover all parsers" \
  "feature"

create_issue \
  "Deterministic synthetic demo case" \
  "Implement \`src/synthetic_data.py\` (\`run_synthetic_demo_case\`): RTPLAN (2 beams, 30 fx, 60 Gy), RTSTRUCT (3 ROIs), RTDOSE (grid + cumulative DVH) from named constants.

**Acceptance criteria**
- [x] No randomness, no PHI, no upload required
- [x] Deterministic UIDs across runs (unit-tested)" \
  "feature"

create_issue \
  "FastAPI backend: all endpoints + structured errors" \
  "Implement \`src/main.py\`: upload/history/detail/plan/demo-case/\`/health\`/\`/metrics\`.

**Acceptance criteria**
- [x] Structured error envelope with trace_id (no raw stack traces)
- [x] Request-size limits; PHI never logged
- [x] Swagger docs served at /docs" \
  "feature"

create_issue \
  "SQLite persistence: AnalysisRecord + AuditEvent" \
  "Implement \`src/models.py\` + \`src/db.py\`.

**Acceptance criteria**
- [x] Every analysis persisted, including failed parses
- [x] Paginated history; audit events queryable per analysis
- [x] Database unavailable -> \`DatabaseUnavailableError\` (structured 503)" \
  "feature"

create_issue \
  "Streamlit dashboard: 5 tabs, demo loader, uploader" \
  "Implement \`src/dashboard.py\` (Python-only UI).

**Acceptance criteria**
- [x] Title \"Modern Dicompyler\" + safety notice
- [x] Load demo case + .dcm upload wired to the API
- [x] Overview / Structures / Plan / Dose-DVH / History tabs with empty states" \
  "feature"

create_issue \
  "Observability: structured JSON logs + Prometheus metrics" \
  "Implement \`src/telemetry.py\`.

**Acceptance criteria**
- [x] Every request logged as JSON with trace_id/request_id/route/outcome
- [x] Metric families: \`rtqa_analysis_requests_total\`, \`rtqa_analysis_duration_seconds\`, \`rtqa_analysis_failures_total\`, \`rtqa_database_up\`
- [x] Signals viewable in a UI (Grafana) and correlated by trace_id" \
  "reliability"

create_issue \
  "Alerting on user impact -> GitHub on-call issues" \
  "Implement \`src/alerting.py\`.

**Acceptance criteria**
- [x] /health fails twice consecutively -> issue
- [x] Demo-case analysis fails -> issue
- [x] Failure rate > 20% over 5 min -> issue (cooldown-guarded)
- [x] Issues labelled \`on-call\`; no PHI/secrets in bodies" \
  "reliability"

create_issue \
  "On-call responder agent (diagnose, never auto-fix prod)" \
  "Implement \`scripts/on_call_diagnose.py\` + \`.github/workflows/on-call-responder.yml\`.

**Acceptance criteria**
- [x] Triggered by the \`on-call\` label
- [x] Runs uv sync + Ruff + pytest + deployment probe; posts a structured report
- [x] Never deploys/pushes/deletes; rollback only proposed for human approval" \
  "reliability"

create_issue \
  "Containerize: multi-stage Dockerfile + Docker Compose" \
  "Full stack (API + dashboard + SQLite volume) starts with a single command.

**Acceptance criteria**
- [x] \`docker compose up --build\` starts everything
- [x] Non-root, health-checked image; named volume for SQLite
- [x] Observability stack (Prometheus/Grafana/Loki/Promtail) included in Compose" \
  "infra"

create_issue \
  "CI/CD: tests on every PR; CD to dev; manual production deploy" \
  "GitHub Actions pipelines.

**Acceptance criteria**
- [x] \`ci.yml\`: Ruff + pytest on every PR and push to main
- [x] \`deploy-dev.yml\`: Docker build validation + auto deploy of both services to dev (Hugging Face Spaces) + /health smoke test
- [x] \`deploy-prod.yml\`: manual \`workflow_dispatch\` gated by \`environment: production\`" \
  "infra"

create_issue \
  "Deploy to a public URL (Hugging Face Spaces)" \
  "Ship API + dashboard to publicly reachable Spaces.

**Acceptance criteria**
- [x] \`PORT\`-aware images (\`deploy/hf/Dockerfile.{api,dashboard}\`)
- [x] \`scripts/deploy_hf.sh\` deploys each service to its Space
- [x] Public URLs documented in README; dashboard \`API_URL\` variable set" \
  "infra"

create_issue \
  "Public task tracker wired to the spec" \
  "Backlog epics exist as GitHub Issues with acceptance criteria; PRs reference issues.

**Acceptance criteria**
- [x] \`scripts/create_issues.sh\` is idempotent
- [x] PR template asks for \`Closes #N\` linkage
- [x] Agents reference issue numbers in CHANGELOG entries" \
  "docs"

echo "Tracker bootstrap complete."

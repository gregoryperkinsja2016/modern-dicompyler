# Incident response (docs/incident-response.md)

## Alert triggers

| # | Trigger | Detection | Alert |
| --- | --- | --- | --- |
| 1 | `/health` unhealthy | `database: false` twice consecutively | GitHub Issue `[on-call] Health endpoint failing consecutively` |
| 2 | Demo-case failure | any exception while running `run_synthetic_demo_case` | GitHub Issue `[on-call] Synthetic demo-case analysis failed` |
| 3 | Elevated failure rate | > 20% of `/api/v1` requests failing over 5 minutes (>= 10 samples) | GitHub Issue `[on-call] Analysis failure rate above 20% over five minutes` |

Alerts are cooldown-guarded (300s per key) to prevent issue storms. Issues contain timestamp, environment, endpoint, error class, trace id, metric values, and a diagnostic checklist - never PHI or secrets.

## On-call responder behaviour

When an issue is labelled `on-call`, `.github/workflows/on-call-responder.yml` runs `scripts/on_call_diagnose.py`, which:

1. Parses the issue body for **trace id, environment, endpoint, error class**.
2. Runs diagnostics: `uv sync --frozen`, `uv run ruff check .`, `uv run pytest -q`.
3. Probes `$DEPLOYMENT_URL/health` when the secret is available (skipped otherwise).
4. Classifies the incident:
   - `test_failure` - sync/Ruff/pytest failing in-repo;
   - `deployment_health_failure` - repo healthy but `/health` failing;
   - `runtime_analysis_failure` - issue reports a runtime error class;
   - `unknown` - nothing matched.
5. Comments a structured diagnostic report (checks table, classification, recommended actions, output excerpts).
6. If the deployment is unhealthy **and** `KNOWN_GOOD_IMAGE_TAG` exists, includes the exact rollback command and may propose a rollback PR. Without a known-good tag it only documents the manual rollback command.

**Hard boundaries (enforced by workflow permissions and script design):**

- never deploys or redeploys anything;
- never pushes to `main` (or any branch);
- never deletes issues, comments, or database records;
- never modifies secrets;
- rollback/deployment always requires manual human approval.

## Human approval boundaries

| Action | Machine | Human |
| --- | --- | --- |
| Run diagnostics, comment on issues | yes | - |
| Merge to `main` | - | required |
| Deploy / rollback | - | required (commands provided) |
| Delete issues / data / records | - | never automated |
| Change secrets | - | required |

## Rollback procedure

1. Confirm the alert and classification (read the responder's comment).
2. Check current state: `curl $DEPLOYMENT_URL/health`, `docker compose ps`, `GET /metrics` for `rtqa_database_up` and `rtqa_analysis_failures_total`.
3. Identify the last known-good image tag; ensure `KNOWN_GOOD_IMAGE_TAG` is set.
4. Execute (human-approved):

```bash
docker compose pull && docker compose up -d --force-recreate api
```

5. Verify: `/health` -> `{"status": "ok", "database": true}`; run the demo case; confirm history is intact (SQLite in the `dicomrt-data` volume is never touched by rollbacks).
6. Post a follow-up comment on the issue and close it.

## Diagnostic checklist (mirror of the alert body)

- [ ] Check the API container/service is running (`docker compose ps`).
- [ ] Check `GET /health` and confirm the `database` field is true.
- [ ] Check `GET /metrics` for `rtqa_analysis_failures_total` by `error_class`.
- [ ] Inspect structured logs for the `trace_id` in the issue.
- [ ] Re-run the synthetic demo case to confirm baseline functionality.
- [ ] If deployment is unhealthy, roll back to the last known-good image/tag (see `docs/deployment.md`).

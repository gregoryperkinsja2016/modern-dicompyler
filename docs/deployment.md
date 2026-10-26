# Deployment (docs/deployment.md)

## Verified runtime (this submission)

The **verified runtime for this project is local Docker Compose**. No public cloud URL is attached to the submission.

```bash
docker compose up --build
```

| Service | URL | Notes |
| --- | --- | --- |
| API | <http://localhost:8000> | uvicorn, reads `RTQA_DATA_DIR=/app/data` |
| API docs | <http://localhost:8000/docs> | Swagger UI |
| Dashboard | <http://localhost:8501> | Streamlit, `API_URL=http://api:8000` |
| Health | <http://localhost:8000/health> | also used by the container HEALTHCHECK |
| Metrics | <http://localhost:8000/metrics> | Prometheus text format |

The SQLite database lives in the named volume `dicomrt-data` mounted at `/app/data`, so analyses survive container restarts. Stop with `Ctrl+C`; reset data with `docker compose down -v`.

Local (non-Docker) run:

```bash
uv sync
uv run uvicorn src.main:app --reload    # terminal 1
uv run streamlit run src/dashboard.py   # terminal 2
```

## Cloud deployment (optional)

`deploy-dev.yml` runs on every merge to `main` and supports any simple platform that offers an HTTP deploy hook (Render, Railway, Fly.io, Hugging Face Spaces). Without secrets configured the workflow still validates the Docker build and skips remote steps with a warning.

### Required repository secrets

| Secret | Purpose | Required? |
| --- | --- | --- |
| `RENDER_DEPLOY_HOOK` | Deploy-hook URL (POST) to trigger a platform deploy | optional |
| `DEPLOYMENT_URL` | Public base URL used by the post-deploy `/health` smoke test and the on-call responder | optional |
| `KNOWN_GOOD_IMAGE_TAG` | Last known-good image/tag; enables a rollback PR proposal | optional |

`GITHUB_TOKEN` is provided automatically by Actions. **Never commit secrets** - they are read from the environment only, and nothing in the codebase logs them.

### Deploy flow

1. Push/merge to `main`.
2. `build-and-deploy` job: `docker build` validation, then POSTs the deploy hook if configured.
3. `smoke-test` job: polls `$DEPLOYMENT_URL/health` every 15s (8 attempts); fails the workflow if unhealthy.

## Rollback procedure

1. Identify the last known-good tag (e.g. from the platform dashboard or the container registry).
2. Set/verify `KNOWN_GOOD_IMAGE_TAG` in repository secrets.
3. Roll back (human-executed, human-approved):

```bash
docker compose pull && docker compose up -d --force-recreate api
```

Or pin the image explicitly:

```bash
docker compose down api
docker run -d --name api-rollback modern-dicompyler:$KNOWN_GOOD_IMAGE_TAG
```

4. Verify `GET /health` returns `{"status": "ok"}` and the demo case runs.
5. The on-call responder proposes (never executes) these commands in its diagnostic report; a rollback PR is only opened when a known-good tag exists, and deployment always requires manual approval.

## Health semantics

- `GET /health` returns 200 with `status: "ok"` and `database: true` when the database accepts queries, and 200 with `status: "unhealthy"` / `database: false` otherwise. The Docker HEALTHCHECK fails on non-200, which marks the container unhealthy and lets Compose gate the dashboard on API health.

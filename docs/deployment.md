# Deployment (docs/deployment.md)

## Verified runtime (this submission)

The **verified runtime for this project is local Docker Compose**. One command starts the whole stack (application + SQLite volume + observability UI):

```bash
docker compose up --build      # or: make up
```

| Service | URL | Notes |
| --- | --- | --- |
| API | <http://localhost:8000> | uvicorn, reads `RTQA_DATA_DIR=/app/data` |
| API docs | <http://localhost:8000/docs> | Swagger UI |
| Dashboard | <http://localhost:8501> | Streamlit, `API_URL=http://api:8000` |
| Grafana UI | <http://localhost:3000> | pre-provisioned "Modern Dicompyler - User Journey" dashboard |
| Prometheus UI | <http://localhost:9090> | metric browser |
| Health | <http://localhost:8000/health> | also used by the container HEALTHCHECK |
| Metrics | <http://localhost:8000/metrics> | Prometheus text format |

The SQLite database lives in the named volume `dicomrt-data` mounted at `/app/data`, so analyses survive container restarts. Stop with `Ctrl+C`; reset data with `docker compose down -v`.

Local (non-Docker) run:

```bash
uv sync
uv run uvicorn src.main:app --reload    # terminal 1
uv run streamlit run src/dashboard.py   # terminal 2
```

## Cloud deployment (Hugging Face Spaces - free public URL)

The application ships first-class **Hugging Face Spaces** support (Docker SDK, `app_port: 7860`). Two Spaces make up the deployment: one for the API, one for the dashboard.

### One-time setup (human, ~10 minutes)

1. Create a Hugging Face **write token**: <https://huggingface.co/settings/tokens>.
2. Create two empty Docker Spaces: `modern-dicompyler-api` and `modern-dicompyler-dashboard` (New Space -> SDK: Docker -> blank template). Creating them up front is optional - the script can push to new names and HF creates them on first push.
3. In the **dashboard Space**: Settings -> Variables and secrets -> add variable `API_URL` = the public URL of the API Space (e.g. `https://<owner>-modern-dicompyler-api.hf.space`).

### Deploy manually (either service, any time)

```bash
HF_TOKEN=hf_xxx bash scripts/deploy_hf.sh api        <owner>/modern-dicompyler-api
HF_TOKEN=hf_xxx API_URL=https://<owner>-modern-dicompyler-api.hf.space \
               bash scripts/deploy_hf.sh dashboard   <owner>/modern-dicompyler-dashboard
```

The script stages a minimal Space repo (Space card + `Dockerfile` + `src/` + lockfile), commits it, and pushes it to the Space's git remote; HF builds the image. Spaces sleep after ~48h of inactivity on the free tier and their filesystem is ephemeral (the demo case re-populates history in one click).

### Deploy automatically (CD, via GitHub Actions)

`deploy-dev.yml` runs on every push to `main`/`develop`: it validates the Docker build, deploys **both services** to the dev Spaces with `scripts/deploy_hf.sh`, and smoke-tests `/health`.

Required repository secrets:

| Secret | Purpose | Required? |
| --- | --- | --- |
| `HF_TOKEN` | Hugging Face write token used to push to the Spaces | optional (needed for CD) |
| `HF_API_SPACE_DEV` / `HF_DASHBOARD_SPACE_DEV` | `<owner>/space-name` targets for the dev deployment | optional |
| `DEV_API_URL` | public base URL of the dev API Space (smoke test + dashboard `API_URL`) | optional |
| `HF_API_SPACE_PROD` / `HF_DASHBOARD_SPACE_PROD` | `<owner>/space-name` targets for production | optional |
| `PROD_API_URL` | public base URL of the production API Space | optional |
| `KNOWN_GOOD_IMAGE_TAG` | Last known-good tag; enables a rollback proposal by the on-call responder | optional |

`GITHUB_TOKEN` is provided automatically by Actions. **Never commit secrets** - they are read from the environment only, and nothing in the codebase logs them.

### Deploy flow (dev)

1. Push/merge to `main` or `develop`.
2. `build-and-validate`: `docker build` must succeed.
3. `deploy-api-dev` -> `deploy-dashboard-dev`: push each service to its Space via `scripts/deploy_hf.sh` (skipped with a warning when secrets are unset).
4. `smoke-test`: polls `$DEV_API_URL/health` every 30s (10 attempts; Space image builds take a few minutes); fails the workflow if unhealthy.

### Deploy to production (manual gate)

Production is never deployed automatically. Run `deploy-prod.yml` by hand:

1. Actions -> **Deploy (production)** -> *Run workflow*.
2. Type `deploy` in the confirmation input.
3. The job runs under the `production` **environment**; configure required reviewers in Settings -> Environments -> production so a second human must approve.

This satisfies the course's CI -> CD(dev) -> manual production gate.

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

# Pull request checklist

Before merging, an agent or human confirms:

- [ ] `uv run ruff check .` passes
- [ ] `uv run pytest` passes (unit + integration)
- [ ] Streamlit dashboard works against the API (demo case, upload, history)
- [ ] No PHI, secrets, or fabricated clinical values introduced
- [ ] Docs updated when behaviour changed (`README.md`, `docs/*`, `CHANGELOG.md`)
- [ ] This PR is linked to its task tracker issue via `Closes #N`

Tracker evidence: every PR must close at least one GitHub Issue created by
`scripts/create_issues.sh` (or the runtime alerting in `src/alerting.py`).

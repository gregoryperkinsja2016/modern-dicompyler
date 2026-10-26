# Modern Dicompyler - single-command developer UX.
.PHONY: help up down build test lint demo logs grafana clean dev-api dev-ui

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Start the full stack (API :8000, UI :8501, Grafana :3000) in the background
	docker compose up --build -d
	@echo ""
	@echo "  API (Swagger):  http://localhost:8000/docs"
	@echo "  Dashboard:      http://localhost:8501"
	@echo "  Grafana UI:     http://localhost:3000  (pre-provisioned 'Modern Dicompyler' dashboard)"
	@echo "  Prometheus:     http://localhost:9090"

down: ## Stop the stack (keeps SQLite volume)
	docker compose down

clean: ## Stop the stack and delete the SQLite volume
	docker compose down -v

build: ## Validate the Docker image builds
	docker build -t modern-dicompyler:local .

test: ## Run unit + integration tests
	uv run pytest

lint: ## Lint with Ruff
	uv run ruff check .

sync: ## Install/sync dependencies with uv
	uv sync

demo: ## Run the deterministic demo case against a running API
	curl -fsS -X POST http://localhost:8000/api/v1/demo-case | head -c 400; echo ""

logs: ## Tail API + dashboard logs
	docker compose logs -f api dashboard

dev-api: ## Run the API locally (uv, hot reload, port 8000)
	uv run uvicorn src.main:app --reload

dev-ui: ## Run the dashboard locally (uv, port 8501)
	uv run streamlit run src/dashboard.py

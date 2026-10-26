"""Application configuration for Modern Dicompyler.

All runtime configuration is environment-driven with safe defaults.
No secrets are hard-coded; secrets are only ever read from the environment
and are never logged.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

# --- Storage ---------------------------------------------------------------
DATA_DIR = Path(os.getenv("RTQA_DATA_DIR", str(BASE_DIR / "data")))
DATABASE_URL = os.getenv("RTQA_DATABASE_URL", f"sqlite:///{DATA_DIR / 'dicomrt.db'}")

# --- API ---------------------------------------------------------------------
API_TITLE = "Modern Dicompyler API"
API_VERSION = "1.0.0"
API_DESCRIPTION = (
    "Read-only DICOM-RT inspection microservice (RTSTRUCT / RTPLAN / RTDOSE). "
    "Not for clinical plan verification."
)

# --- Runtime environment -------------------------------------------------------
ENVIRONMENT = os.getenv("RTQA_ENVIRONMENT", "development")
LOG_LEVEL = os.getenv("RTQA_LOG_LEVEL", "INFO")
DEPLOYMENT_URL = os.getenv("RTQA_DEPLOYMENT_URL", "")

# --- Pagination / upload limits --------------------------------------------------
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100
MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB

# --- Alerting (GitHub Issues) -------------------------------------------------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO = os.getenv("GITHUB_REPO", "")  # "owner/repo"
GITHUB_API_BASE = "https://api.github.com"
ONCALL_LABEL = "on-call"

# Alert tuning constants (named, not magic numbers).
ALERT_COOLDOWN_SECONDS = 300
FAILURE_RATE_WINDOW_SECONDS = 300  # five minutes
FAILURE_RATE_THRESHOLD = 0.2  # 20 percent
FAILURE_RATE_MIN_SAMPLES = 10
HEALTH_FAILURE_ALERT_THRESHOLD = 2  # alert after two consecutive /health failures

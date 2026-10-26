#!/usr/bin/env python3
"""On-call diagnostic responder for Modern Dicompyler.

Reads a GitHub ``on-call`` issue body, runs repository diagnostics
(uv sync, Ruff, pytest), optionally probes the deployed /health endpoint,
classifies the incident, and prints (or posts) a structured report.

Boundaries honoured by this script and its workflow:
- never deploys or pushes code;
- never deletes issues, modifies secrets, or deletes database records;
- rollback is only *proposed* as text for a human to run and approve.

Usage:
    python scripts/on_call_diagnose.py [--post-comment]

Environment:
    GITHUB_TOKEN, GITHUB_REPOSITORY, ISSUE_NUMBER, ISSUE_BODY,
    DEPLOYMENT_URL (optional), KNOWN_GOOD_IMAGE_TAG (optional)
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]

FIELD_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "trace_id": [re.compile(r"trace[_ -]?id[^A-Za-z0-9]*([A-Za-z0-9][A-Za-z0-9-]{4,})", re.IGNORECASE)],
    "environment": [re.compile(r"environment[^A-Za-z0-9]*([A-Za-z0-9._-]+)", re.IGNORECASE)],
    "endpoint": [re.compile(r"endpoint[^A-Za-z0-9]*(/[\w{}./-]+)", re.IGNORECASE)],
    "error_class": [re.compile(r"error[_ -]?class[^A-Za-z0-9]*([A-Za-z][A-Za-z0-9_.]*)", re.IGNORECASE)],
}


def parse_issue_body(body: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for field, patterns in FIELD_PATTERNS.items():
        for pattern in patterns:
            match = pattern.search(body or "")
            if match:
                parsed[field] = match.group(1).strip()
                break
    return parsed


def run_command(command: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=600, check=False
        )
        output = ((completed.stdout or "") + (completed.stderr or "")).strip()
        return completed.returncode == 0, output[-4000:]
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"{type(exc).__name__}: {exc}"


def check_deployment_health() -> tuple[bool | None, str]:
    """Returns (healthy, detail); healthy is None when the check is skipped."""
    deployment_url = os.getenv("DEPLOYMENT_URL", "").rstrip("/")
    if not deployment_url:
        return None, "DEPLOYMENT_URL not configured; deployment health check skipped."
    try:
        response = requests.get(f"{deployment_url}/health", timeout=10)
        if response.status_code == 200 and response.json().get("status") == "ok":
            return True, "Deployment /health returned ok."
        return False, f"Deployment /health returned HTTP {response.status_code}."
    except (requests.RequestException, ValueError) as exc:
        return False, f"Deployment /health request failed ({type(exc).__name__})."


def classify_issue(
    *,
    sync_ok: bool,
    ruff_ok: bool,
    pytest_ok: bool,
    deployment_healthy: bool | None,
    error_class: str,
) -> str:
    if not pytest_ok or not ruff_ok or not sync_ok:
        return "test_failure"
    if deployment_healthy is False:
        return "deployment_health_failure"
    if error_class:
        return "runtime_analysis_failure"
    return "unknown"


def build_report(
    *,
    issue_fields: dict[str, str],
    checks: list[tuple[str, str]],
    classification: str,
    outputs: dict[str, str],
    deployment_detail: str,
    deployment_healthy: bool | None,
) -> str:
    timestamp = datetime.now(UTC).isoformat()
    lines = [
        "## On-call diagnostic report",
        "",
        f"- **Timestamp (UTC):** {timestamp}",
        f"- **Environment:** {issue_fields.get('environment', 'unknown')}",
        f"- **Endpoint:** {issue_fields.get('endpoint', 'unknown')}",
        f"- **Error class:** {issue_fields.get('error_class', 'unknown')}",
        f"- **Trace ID:** `{issue_fields.get('trace_id', 'unknown')}`",
        "",
        "### Diagnostics",
        "",
        "| Check | Result |",
        "| --- | --- |",
    ]
    for name, result in checks:
        lines.append(f"| {name} | {result} |")

    lines += ["", "### Classification", "", f"**{classification}**", ""]

    if classification == "test_failure":
        lines += [
            "The repository itself is failing its own quality gates. Recommended actions:",
            "- Review the failing test/lint output below.",
            "- Fix the regression on a feature branch and open a pull request (never push to main directly).",
        ]
    elif classification == "deployment_health_failure":
        lines += [
            "The repository passes locally but the deployment is unhealthy. Recommended actions:",
            "- Check platform logs for the API service.",
            "- Verify environment variables and secrets on the platform.",
            f"- Deployment health detail: {deployment_detail}",
        ]
    elif classification == "runtime_analysis_failure":
        lines += [
            f"A runtime analysis failure was reported (error class `{issue_fields.get('error_class', 'unknown')}`).",
            "- Search structured logs for the trace id above.",
            "- Re-run the synthetic demo case (`POST /api/v1/demo-case`) to confirm baseline behaviour.",
            "- Confirm the failure rate in GET /metrics (`rtqa_analysis_failures_total`).",
        ]
    else:
        lines += [
            "The incident could not be classified automatically.",
            "- Review the issue body, application logs, and GET /metrics manually.",
        ]

    if deployment_healthy is False:
        known_good = os.getenv("KNOWN_GOOD_IMAGE_TAG", "").strip()
        if known_good:
            rollback_command = (
                "```bash\n"
                f"docker compose pull && docker compose up -d --force-recreate api  # pin {known_good}\n"
                "```"
            )
            lines += [
                "",
                "### Rollback (requires manual approval)",
                "",
                "A known-good previous image/tag exists. Exact rollback command:",
                "",
                rollback_command,
                "",
                "A rollback PR may be opened against this tag, but **deployment requires manual "
                "human approval**. Never push directly to main.",
            ]
        else:
            lines += [
                "",
                "### Rollback (requires manual approval)",
                "",
                "No known-good previous image/tag is configured (`KNOWN_GOOD_IMAGE_TAG` secret is "
                "unset), so no automatic rollback PR can be proposed. Pin the last known-good tag "
                "in repository secrets, then a human can run:",
                "",
                "```bash",
                "docker compose pull && docker compose up -d --force-recreate api",
                "```",
            ]

    for name, output in outputs.items():
        excerpt = output if output else "(no output)"
        lines += ["", f"<details><summary>{name} output (tail)</summary>", "", "```text", excerpt, "```", "</details>"]

    lines += [
        "",
        "_No PHI or secrets are included in this report. Generated by the Modern Dicompyler "
        "on-call responder._",
    ]
    return "\n".join(lines)


def post_comment(issue_number: int, body: str) -> None:
    token = os.getenv("GITHUB_TOKEN", "")
    repository = os.getenv("GITHUB_REPOSITORY", "")
    if not (token and repository):
        print("GITHUB_TOKEN or GITHUB_REPOSITORY not configured; skipping comment posting.")
        return
    url = f"https://api.github.com/repos/{repository}/issues/{issue_number}/comments"
    response = requests.post(
        url,
        json={"body": body},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        timeout=15,
    )
    if response.status_code >= 300:
        print(f"Failed to post comment: HTTP {response.status_code}", file=sys.stderr)
        sys.exit(1)
    print(f"Diagnostic comment posted to issue #{issue_number}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run on-call diagnostics for an on-call issue.")
    parser.add_argument(
        "--post-comment", action="store_true", help="Post the report as a GitHub issue comment."
    )
    args = parser.parse_args()

    issue_body = os.getenv("ISSUE_BODY", "")
    issue_fields = parse_issue_body(issue_body)
    print(f"Parsed issue fields: {issue_fields}")

    sync_ok, sync_output = run_command(["uv", "sync", "--frozen"], ROOT)
    ruff_ok, ruff_output = run_command(["uv", "run", "ruff", "check", "."], ROOT)
    pytest_ok, pytest_output = run_command(["uv", "run", "pytest", "-q"], ROOT)
    deployment_healthy, deployment_detail = check_deployment_health()

    checks = [
        ("uv sync", "pass" if sync_ok else "fail"),
        ("ruff check .", "pass" if ruff_ok else "fail"),
        ("pytest", "pass" if pytest_ok else "fail"),
        (
            "deployment /health",
            {True: "ok", False: "fail", None: "skipped"}[deployment_healthy],
        ),
    ]
    classification = classify_issue(
        sync_ok=sync_ok,
        ruff_ok=ruff_ok,
        pytest_ok=pytest_ok,
        deployment_healthy=deployment_healthy,
        error_class=issue_fields.get("error_class", ""),
    )
    report = build_report(
        issue_fields=issue_fields,
        checks=checks,
        classification=classification,
        outputs={"uv sync": sync_output, "ruff": ruff_output, "pytest": pytest_output},
        deployment_detail=deployment_detail,
        deployment_healthy=deployment_healthy,
    )

    print(report)
    if args.post_comment:
        issue_number = os.getenv("ISSUE_NUMBER", "")
        if issue_number.isdigit():
            post_comment(int(issue_number), report)
        else:
            print("ISSUE_NUMBER not set or not numeric; skipping comment posting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

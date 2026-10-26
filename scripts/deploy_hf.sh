#!/usr/bin/env bash
# Deploy Modern Dicompyler to a Hugging Face Space (Docker SDK).
#
# Usage:
#   HF_TOKEN=hf_xxx scripts/deploy_hf.sh api        owner/modern-dicompyler-api
#   HF_TOKEN=hf_xxx API_URL=https://... scripts/deploy_hf.sh dashboard owner/modern-dicompyler-dashboard
#
# Environment:
#   HF_TOKEN   (required) Hugging Face write token (https://huggingface.co/settings/tokens)
#   API_URL    (required only for `dashboard`) public base URL of the API Space
#
# The script stages a minimal Space repo (Dockerfile + src + lockfile + Space card),
# commits it, and force-pushes it to the Space's git remote. The Space then builds
# the image on HF's infrastructure.
set -euo pipefail

usage() {
  echo "usage: HF_TOKEN=... scripts/deploy_hf.sh <api|dashboard> <owner/space-name>" >&2
  exit 2
}

TARGET="${1:?$(usage)}"
SPACE="${2:?$(usage)}"
: "${HF_TOKEN:?HF_TOKEN must be set (a Hugging Face write token)}"

if [ "$TARGET" != "api" ] && [ "$TARGET" != "dashboard" ]; then
  usage
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKERFILE="$ROOT/deploy/hf/Dockerfile.$TARGET"
if [ ! -f "$DOCKERFILE" ]; then
  echo "missing Dockerfile: $DOCKERFILE" >&2
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# --- Stage the Space repository -------------------------------------------------
cp -R "$ROOT/src" "$WORK/src"
cp "$ROOT/pyproject.toml" "$ROOT/uv.lock" "$WORK/"
cp "$DOCKERFILE" "$WORK/Dockerfile"

cat > "$WORK/README.md" <<EOF
---
title: Modern Dicompyler (${TARGET})
emoji: "\U0001FA7B"
colorFrom: gray
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

Modern Dicompyler (${TARGET} service) - Project 1, DataTalks AI Dev Tools Zoomcamp.

Read-only DICOM-RT demonstration viewer. **Not for clinical plan verification.**
EOF

if [ "$TARGET" = "dashboard" ]; then
  : "${API_URL:?API_URL must be set to the public URL of the API Space (e.g. https://owner-modern-dicompyler-api.hf.space)}"
  cat >> "$WORK/README.md" <<EOF

Backend: \`API_URL\` Space variable must point at the API Space (${API_URL}).
Set it in Space Settings -> Variables and secrets before or after this push.
EOF
fi

# --- Commit and push to the Space git remote ------------------------------------
git -C "$WORK" init -q -b main
git -C "$WORK" add -A
git -C "$WORK" -c user.name="deploy-hf-script" -c user.email="deploy@modern-dicompyler.local" \
  commit -qm "chore: deploy ${TARGET} build to Space ${SPACE}"

git -C "$WORK" remote add space "https://user:${HF_TOKEN}@huggingface.co/spaces/${SPACE}"
git -C "$WORK" push -q --force space main

echo "OK: pushed ${TARGET} to https://huggingface.co/spaces/${SPACE} (image builds on HF)."

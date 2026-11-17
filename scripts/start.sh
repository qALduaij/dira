#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
command -v uv >/dev/null || { echo 'Install uv first: https://docs.astral.sh/uv/'; exit 1; }
command -v npm >/dev/null || { echo 'Install Node.js 22+ first.'; exit 1; }
# Preserve operator-installed perception/semantic extras in the shared native environment.
uv sync --frozen --inexact
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build
mkdir -p .data
printf '\nDira command center: http://127.0.0.1:8000\nCtrl-C stops the server.\n\n'
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
exec uv run --frozen --no-sync uvicorn dira.api:app --host 127.0.0.1 --port 8000 --workers 1

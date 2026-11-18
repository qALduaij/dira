#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs

# Use provisioned environments; never install or download while starting live feeds.
for executable in .venv/bin/python .venv-asr/bin/python; do
  test -x "$executable" || { echo "Missing $executable; see docs/PERCEPTION_PROFILES.md"; exit 1; }
done
.venv/bin/python - <<'PY'
import socket
from dira.config import Settings
settings = Settings()
if settings.mode != 'live':
    raise SystemExit('Set DIRA_MODE=live in .env before using make live.')
for port in (8000, 8001, 8003):
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1', port)) == 0:
            raise SystemExit(f'Port {port} already in use. Stop that Dira/ASR instance first.')
PY
docker compose -f docker-compose.mac.yml up -d

children=()
cleanup() {
  for pid in "${children[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done
  for pid in "${children[@]}"; do wait "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
# PyTorch/FAISS ship separate OpenMP runtimes on arm64; parallel CPU kernels crashed in validation.
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
export DIRA_OCR_CPU_THREADS=1
export DIRA_ASR_MODEL_DIR="${DIRA_ASR_MODEL_DIR:-$PWD/models/qwen3-asr-0.6b}"
export DIRA_ASR_DEVICE="${DIRA_ASR_DEVICE:-mps}"
DIRA_ASR_LANGUAGE=ar DIRA_ASR_PORT=8001 DIRA_ASR_AUDIO_BACKEND=windowed DIRA_ASR_CHUNK_SEC=4 \
  .venv-asr/bin/python scripts/start_asr.py > >(.venv/bin/python scripts/rotate_log.py logs/asr-ar.log) 2>&1 &
children+=("$!")
DIRA_ASR_LANGUAGE=en DIRA_ASR_PORT=8003 DIRA_ASR_AUDIO_BACKEND=causal \
  DIRA_ASR_TOWER_CHECKPOINT="$PWD/models/qwen3-causal/tower.safetensors" \
  .venv-asr/bin/python scripts/start_asr.py > >(.venv/bin/python scripts/rotate_log.py logs/asr-en.log) 2>&1 &
children+=("$!")

.venv/bin/python -u - <<'PY'
import time, urllib.request
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
for port in (8001, 8003):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            with opener.open(f'http://127.0.0.1:{port}/health', timeout=2) as response:
                if response.status == 200:
                    print(f'ASR {port} ready', flush=True)
                    break
        except OSError:
            pass
        time.sleep(1)
    else:
        raise SystemExit(f'ASR {port} did not become ready; inspect logs/asr-*.log')
PY
.venv/bin/python -m uvicorn dira.api:app --host 127.0.0.1 --port 8000 --workers 1 \
  > >(.venv/bin/python scripts/rotate_log.py logs/api-live.log) 2>&1 &
api_pid=$!
children+=("$api_pid")
# Host sleep silently removes coverage (audit 2026-11-18, N-01). Hold a sleep assertion for the API's lifetime.
if command -v caffeinate >/dev/null; then
  caffeinate -dims -w "$api_pid" &
  children+=("$!")
  echo 'Sleep prevented while Dira runs (closing a laptop lid without an external display still sleeps).'
fi
echo 'Dira is starting at http://127.0.0.1:8000 — logs in logs/. Ctrl-C stops API and ASR.'
while true; do
  for pid in "${children[@]}"; do
    kill -0 "$pid" 2>/dev/null || { echo 'A service exited; inspect logs/.'; exit 1; }
  done
  sleep 2
done

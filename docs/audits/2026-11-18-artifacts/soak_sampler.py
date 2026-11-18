"""Read-only soak sampler (audit artifact; scripts/verify_live.py is unchanged).

Differences from verify_live.py, each motivated by the 2026-11-18 audit:
- Records wall-clock AND monotonic time per sample. On macOS, time.monotonic() stops during sleep, so a soak
  timed only by monotonic time can claim "2 h" across a lid-closed night. Any sample where the wall clock moved
  more than 5 s further than the monotonic clock is flagged `host_sleep_suspected`.
- Records the OCR-lifecycle fields needed to accept the P-08/P-09 fix (ocr_worker_pid / _restarts / _started_at,
  last_frame_error_type) and counts distinct OCR worker PIDs.
- Optionally probes the WebSocket every N samples (connect, send empty auth, receive snapshot, close) and records
  its latency. Never sends a token, never triggers briefs, never writes to Dira.
- `--wall-seconds` is the duration criterion; sleep time does not count toward the soak.

Usage (backend already running on 127.0.0.1:8000):
  .venv/bin/python docs/audits/2026-11-18-artifacts/soak_sampler.py --wall-seconds 7200 \
      --output docs/audits/2026-11-18-artifacts/soak-7200.json
"""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

CHANNEL_KEYS = (
    "id", "status", "asr_status", "ocr_status", "asr_lag_seconds", "asr_resets", "asr_skipped_seconds",
    "last_pcm_at", "last_transcript_at", "last_ocr_observation_at", "ocr_unchanged_skips", "last_error_type",
    "last_frame_error_type", "ocr_worker_pid", "ocr_worker_restarts", "ocr_worker_started_at",
)
METRIC_KEYS = (
    "evidence", "pending", "processed", "latency_p95_ms", "asr_lag_max_seconds", "asr_max_lag", "disk_free_gb",
    "disk_guard_active", "llm", "cloud_auto_briefs", "warm_status", "active_alerts", "hot_horizon_seconds",
    "uptime_seconds", "ws_resyncs", "jobs_pending",
)


async def ws_probe(url):
    import websockets  # available in the project venv

    started = time.perf_counter()
    async with websockets.connect(url, max_size=2**25, open_timeout=10) as ws:
        await ws.send(json.dumps({"token": ""}))
        message = json.loads(await asyncio.wait_for(ws.recv(), 10))
    return {"ok": message.get("type") == "snapshot", "ms": round((time.perf_counter() - started) * 1000, 1)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wall-seconds", type=int, default=7200, help="awake wall-clock seconds to cover")
    parser.add_argument("--interval", type=float, default=10)
    parser.add_argument("--ws-every", type=int, default=30, help="WebSocket probe every N samples; 0 disables")
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    samples, errors, pids = [], [], {}
    awake, last_wall, last_mono = 0.0, time.time(), time.monotonic()
    with httpx.Client(base_url=args.base, timeout=10, trust_env=False) as client:
        while awake < args.wall_seconds:
            wall, mono = time.time(), time.monotonic()
            slept = (wall - last_wall) - (mono - last_mono) > 5
            if not slept:
                awake += wall - last_wall
            last_wall, last_mono = wall, mono
            sample = {"at": datetime.now(UTC).isoformat(), "awake_seconds": round(awake, 1),
                      "host_sleep_suspected": slept}
            try:
                t = time.perf_counter()
                response = client.get("/api/snapshot")
                response.raise_for_status()
                sample["snapshot_ms"] = round((time.perf_counter() - t) * 1000, 1)
                state = response.json()
                sample["metrics"] = {k: state["metrics"].get(k) for k in METRIC_KEYS}
                sample["channels"] = [{k: c.get(k) for k in CHANNEL_KEYS} for c in state["channels"]]
                for c in sample["channels"]:
                    if c.get("ocr_worker_pid"):
                        pids.setdefault(c["id"], set()).add(c["ocr_worker_pid"])
                t = time.perf_counter()
                gaps = client.get("/api/gaps")
                gaps.raise_for_status()
                sample["gaps_ms"], sample["gaps_returned"] = round((time.perf_counter() - t) * 1000, 1), len(gaps.json())
                if args.ws_every and len(samples) % args.ws_every == 0:
                    ws_url = args.base.replace("http", "ws", 1) + "/api/ws"
                    sample["ws"] = asyncio.run(ws_probe(ws_url))
            except Exception as exc:  # record the type only; never echo response bodies
                errors.append({"at": sample["at"], "type": type(exc).__name__})
            samples.append(sample)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({
                "samples": samples, "errors": errors, "awake_seconds": awake,
                "distinct_ocr_worker_pids": {k: len(v) for k, v in pids.items()},
                "sleep_samples": sum(s["host_sleep_suspected"] for s in samples),
            }, indent=1))
            print(json.dumps({"awake": round(awake), "errors": len(errors), "sleep": slept,
                              "lag": (sample.get("metrics") or {}).get("asr_lag_max_seconds")}), flush=True)
            time.sleep(args.interval)
    if errors:
        raise SystemExit(f"{len(errors)} sampling errors; inspect {args.output}")


if __name__ == "__main__":
    main()

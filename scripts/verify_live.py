"""Read-only live soak: local REST only; no inference requests or feed mutations."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import time

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    samples, errors = [], []
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10, trust_env=False) as client:
        deadline = time.monotonic() + 180
        while True:
            try:
                response = client.get("/health")
                response.raise_for_status()
                break
            except httpx.HTTPError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Local API did not become healthy") from None
                time.sleep(2)
        started = time.monotonic()
        while True:
            try:
                response = client.get("/api/snapshot")
                response.raise_for_status()
                state = response.json()
                metrics = state["metrics"]
                sample = {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "elapsed_seconds": round(time.monotonic() - started, 1),
                    "metrics": {key: metrics.get(key) for key in (
                        "evidence", "pending", "processed", "latency_p95_ms", "asr_lag_max_seconds",
                        "asr_max_lag", "disk_free_gb", "disk_guard_active", "llm", "cloud_auto_briefs",
                        "warm_status", "active_alerts", "hot_horizon_seconds", "uptime_seconds")},
                    "channels": [{key: channel.get(key) for key in (
                        "id", "status", "asr_status", "ocr_status", "asr_lag_seconds", "asr_resets",
                        "asr_skipped_seconds", "last_pcm_at", "last_transcript_at", "last_ocr_observation_at",
                        "ocr_stats", "ocr_unchanged_skips", "last_error_type")} for channel in state["channels"]],
                }
                samples.append(sample)
                print(json.dumps({"seconds": sample["elapsed_seconds"],
                                  "evidence": metrics["evidence"], "lag": metrics.get("asr_lag_max_seconds"),
                                  "channels": {c["id"]: c["status"] for c in sample["channels"]}}), flush=True)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                errors.append({"elapsed_seconds": time.monotonic() - started, "type": type(exc).__name__})
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps({"samples": samples, "errors": errors,
                                              "elapsed_seconds": time.monotonic() - started}, indent=2))
            if time.monotonic() - started >= args.seconds:
                break
            time.sleep(min(10, max(0, args.seconds - (time.monotonic() - started))))
    if not samples or errors:
        raise SystemExit("Verification had REST failures; inspect the report")


if __name__ == "__main__":
    main()

"""Offline analysis of soak_sampler.py output (no network). Usage: python analyze_soak.py soak-7200.json"""

import json
import statistics as st
import sys
from collections import Counter, defaultdict


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * q))] if values else None


data = json.load(open(sys.argv[1]))
samples = [s for s in data["samples"] if "metrics" in s]
first, last = samples[0], samples[-1]
print(f"window {first['at']} -> {last['at']}; awake {data['awake_seconds']:.0f}s; samples {len(data['samples'])}; "
      f"errors {len(data['errors'])}; sleep samples {data['sleep_samples']}")
print("distinct OCR worker PIDs per channel:", data["distinct_ocr_worker_pids"])
m0, m1 = first["metrics"], last["metrics"]
hours = data["awake_seconds"] / 3600
print(f"evidence +{m1['evidence'] - m0['evidence']} ({(m1['evidence'] - m0['evidence']) / hours:.0f}/h); "
      f"processed +{m1['processed'] - m0['processed']}")
pending = [s["metrics"]["pending"] for s in samples]
print(f"outbox pending median {st.median(pending)} max {max(pending)} last {pending[-1]}")
warm = Counter(s["metrics"]["warm_status"] for s in samples)
print("warm status:", dict(warm))
lat = [s["metrics"]["latency_p95_ms"] for s in samples]
print(f"ingest p95 (ms): median {st.median(lat):.1f} max {max(lat):.1f}")
snap = [s["snapshot_ms"] for s in samples if "snapshot_ms" in s]
gaps_ms = [s["gaps_ms"] for s in samples if "gaps_ms" in s]
print(f"/api/snapshot ms: median {st.median(snap):.0f} p95 {pct(snap, .95):.0f} max {max(snap):.0f}; "
      f"/api/gaps ms median {st.median(gaps_ms):.0f} max {max(gaps_ms):.0f}")
ws = [s["ws"] for s in data["samples"] if "ws" in s]
print(f"websocket probes {len(ws)} ok {sum(w['ok'] for w in ws)} ms median {st.median(w['ms'] for w in ws):.0f} "
      f"max {max(w['ms'] for w in ws):.0f}")
glob = [s["metrics"]["asr_lag_max_seconds"] for s in samples if s["metrics"]["asr_lag_max_seconds"] is not None]
print(f"worst-channel lag: median {st.median(glob):.1f} p95 {pct(glob, .95):.1f} max {max(glob):.1f}")
print(f"active_alerts {m0['active_alerts']} -> {m1['active_alerts']}; ws_resyncs {m1.get('ws_resyncs')}")
start = {c["id"]: c for c in first["channels"]}
per = defaultdict(lambda: {"n": 0, "connected": 0, "lags": [], "stale": 0, "ocr_degraded": 0})
for s in samples:
    for c in s["channels"]:
        p = per[c["id"]]
        p["n"] += 1
        p["connected"] += c["status"] == "connected"
        p["ocr_degraded"] += c.get("ocr_status") not in ("connected", None)
        if c["asr_lag_seconds"] is not None:
            p["lags"].append(c["asr_lag_seconds"])
print("channel | connected | lag median/p95/max | resets in soak | est. loss s (% of soak) | OCR restarts | "
      "OCR not-connected samples | last_error_type")
for c in last["channels"]:
    p, s0 = per[c["id"]], start[c["id"]]
    resets = c["asr_resets"] - s0["asr_resets"]
    loss = c["asr_skipped_seconds"] - s0["asr_skipped_seconds"]
    print(f"{c['id']} | {100 * p['connected'] / p['n']:.1f}% | {st.median(p['lags']):.0f}/{pct(p['lags'], .95):.0f}/"
          f"{max(p['lags']):.0f} | {resets} | {loss:.0f} ({100 * loss / data['awake_seconds']:.1f}%) | "
          f"{c.get('ocr_worker_restarts')} | {p['ocr_degraded']} | {c.get('last_error_type')}")

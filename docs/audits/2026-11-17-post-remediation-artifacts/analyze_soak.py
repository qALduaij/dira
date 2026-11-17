"""Summarise verify-live-7200.json + resources-7200.json (read-only, offline)."""
import json, statistics as st, sys
from pathlib import Path
from datetime import datetime
here = Path(__file__).parent
v = json.loads((here / "verify-live-7200.json").read_text())
r = json.loads((here / "resources-7200.json").read_text())
S = v["samples"]
print(f"samples={len(S)} elapsed={v['elapsed_seconds']} errors={len(v['errors'])}")
for e in v["errors"][:5]: print("  err", str(e)[:160])
m0, m1 = S[0]["metrics"], S[-1]["metrics"]
hrs = (S[-1]["elapsed_seconds"] - S[0]["elapsed_seconds"]) / 3600
print(f"evidence {m0['evidence']} -> {m1['evidence']} (+{m1['evidence']-m0['evidence']}, {(m1['evidence']-m0['evidence'])/hrs:.0f}/h)")
print(f"processed {m0['processed']} -> {m1['processed']}; alerts {m0['active_alerts']} -> {m1['active_alerts']} (+{(m1['active_alerts']-m0['active_alerts'])/hrs:.0f}/h)")
pend = [s["metrics"]["pending"] for s in S]; p95 = [s["metrics"]["latency_p95_ms"] for s in S if s["metrics"].get("latency_p95_ms") is not None]
print(f"pending max={max(pend)} last={pend[-1]}  ingest p95 median={st.median(p95):.1f} max={max(p95):.1f}")
print(f"disk {m0['disk_free_gb']} -> {m1['disk_free_gb']}  guard_ever={any(s['metrics']['disk_guard_active'] for s in S)}  warm_not_connected={sum(s['metrics']['warm_status']!='connected' for s in S)}")
lagmax = [s["metrics"]["asr_lag_max_seconds"] or 0 for s in S]
print(f"global lag max={max(lagmax)} median={st.median(lagmax)} p95={sorted(lagmax)[int(.95*len(lagmax))]}")
ids = [c["id"] for c in S[0]["channels"]]
print("channel | connected% | lag med/p95/max | resets d | skipped d (s) | skipped % | asr_age>60s samples | unchanged skips | ocr frames | errors")
for cid in ids:
    rows = [next(c for c in s["channels"] if c["id"] == cid) for s in S]
    con = sum(c["status"] == "connected" for c in rows) / len(rows) * 100
    lags = [c.get("asr_lag_seconds") or 0 for c in rows]
    rs = (rows[-1].get("asr_resets") or 0) - (rows[0].get("asr_resets") or 0)
    sk = (rows[-1].get("asr_skipped_seconds") or 0) - (rows[0].get("asr_skipped_seconds") or 0)
    stale = 0
    for s, c in zip(S, rows):
        t = c.get("last_transcript_at")
        if t and (datetime.fromisoformat(s["at"]) - datetime.fromisoformat(t)).total_seconds() > 60: stale += 1
    errs = {c.get("last_error_type") for c in rows} - {None}
    print(f"{cid:11} | {con:5.1f} | {st.median(lags):.0f}/{sorted(lags)[int(.95*len(lags))]:.0f}/{max(lags):.0f} | {rs} | {sk:.0f} | {sk/ (hrs*3600)*100:.1f} | {stale} | {rows[-1].get('ocr_unchanged_skips')} | {rows[-1].get('ocr_stats')} | {errs}")
# outages: samples where any channel not connected
bad = [(s["at"][11:19], [c["id"] for c in s["channels"] if c["status"] != "connected"]) for s in S if any(c["status"] != "connected" for c in s["channels"])]
print(f"samples with any non-connected channel: {len(bad)}; first/last: {bad[:1]} {bad[-1:]}")
# evidence stall windows (no growth over >=60 s)
stalls, start = [], None
for a, b in zip(S, S[1:]):
    if b["metrics"]["evidence"] == a["metrics"]["evidence"]:
        start = start or a
    elif start:
        d = a["elapsed_seconds"] - start["elapsed_seconds"]
        if d >= 60: stalls.append((start["at"][11:19], round(d)))
        start = None
print("evidence stalls >=60s:", stalls)
R = r["samples"]
print(f"resource samples={len(R)} disk {R[0]['disk_free_gb']}->{R[-1]['disk_free_gb']} db_mb {R[0]['evidence_db_mb']}->{R[-1]['evidence_db_mb']} fds {R[0]['api_fds']}->{R[-1]['api_fds']} max={max(x['api_fds'] for x in R)}")
for kind in sorted({p["kind"] for x in R for p in x["processes"]}):
    tot = [sum(p["rss_mb"] for p in x["processes"] if p["kind"] == kind) for x in R]
    cnt = [sum(p["kind"] == kind for p in x["processes"]) for x in R]
    print(f"  {kind:7} rss_total first={tot[0]} last={tot[-1]} max={max(tot)}  count first={cnt[0]} last={cnt[-1]} min={min(cnt)} max={max(cnt)}")
pids = {p["pid"] for x in R for p in x["processes"] if p["kind"] == "ocr"}
print(f"  distinct OCR worker pids over soak: {len(pids)}")
new = [c for c in R[-1].get("crash_reports", []) if c not in r["baseline_crash_reports"]] if "crash_reports" in R[-1] else R[-1].get("new_crash_reports")
print("new crash reports:", new)

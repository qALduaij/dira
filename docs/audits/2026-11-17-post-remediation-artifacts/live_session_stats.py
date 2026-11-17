"""Read-only (sqlite mode=ro) statistics for the live session that started at SESSION (UTC ISO)."""
import collections, datetime as dt, json, sqlite3, statistics as st, sys
SESSION = sys.argv[1] if len(sys.argv) > 1 else "2026-11-17T12:00:59+00:00"
db = sqlite3.connect("file:/Users/qusaial-duaij/Desktop/Dira/.data-live/evidence.db?mode=ro", uri=True)
P = lambda s: dt.datetime.fromisoformat(s).timestamp()
t0 = P(SESSION)
ev = [json.loads(p) for (p,) in db.execute("select payload from evidence where start >= ?", (t0 - 600,))]
ev = [e for e in ev if P(e["received_at"]) >= t0]
now = max(P(e["received_at"]) for e in ev); span = now - t0
print(f"session span {span/60:.1f} min, observations {len(ev)}")
by = collections.Counter((e["channel_id"], e["source"]) for e in ev)
for c in sorted({e["channel_id"] for e in ev}):
    asr = [P(e["received_at"]) - P(e["end"]) for e in ev if e["channel_id"] == c and e["source"] == "whisperlivekit"]
    q = sorted(asr)
    print(f"  {c:11} asr={by[(c,'whisperlivekit')]:4} ocr={by[(c,'local-perception')]:4} "
          f"asr_age median={st.median(q) if q else 0:5.1f}s p95={q[int(.95*(len(q)-1))] if q else 0:5.1f}s max={max(q) if q else 0:5.1f}s")
ocr = [e for e in ev if e["source"] == "local-perception"]
dup = collections.Counter((e["channel_id"], " ".join(e["ocr"].split())) for e in ocr)
rep = sum(n - 1 for n in dup.values() if n > 1)
print(f"OCR: {len(ocr)} obs, repeats of same (channel,text) within session: {rep} ({rep/max(1,len(ocr)):.0%})")
print("speaker non-null:", sum(e["speaker"] is not None for e in ev), " confidence non-null:", sum(e["confidence"] is not None for e in ev))
objs = lambda k: [json.loads(p) for (p,) in db.execute("select payload from objects where kind=?", (k,))]
alerts = [a for a in objs("alert") if P(a["timestamp"]) >= t0]
print(f"alerts: {len(alerts)} ({len(alerts)/(span/3600):.0f}/h)", collections.Counter((a["kind"], a["severity"]) for a in alerts))
crit = collections.Counter(" ".join(a["detail"].split())[:60] for a in alerts if a["severity"] == "critical")
print("  top critical details:", crit.most_common(4))
spk = [a for a in alerts if a["kind"] == "spike"]
idx = {e["id"]: e for e in ev}
print("  spike alerts by source:", collections.Counter(idx.get(a["tdo_id"], {}).get("source", "?") for a in spk))
gaps = [g for g in objs("gap") if P(g["detected_at"]) >= t0]
lost = collections.defaultdict(float); cnt = collections.Counter()
for g in gaps:
    cnt[(g["channel_id"], g["reason"])] += 1
    lost[g["channel_id"]] += g["estimated_lost_seconds"] or 0
print("gaps:", dict(cnt))
for c, s in sorted(lost.items()):
    print(f"  {c:11} estimated ASR coverage loss {s:6.0f}s = {s/span:.0%} of session")
briefs = [b for b in objs("brief") if P(b["created_at"]) >= t0]
jobs = [j for j in objs("job")]
print("briefs since session:", len(briefs), collections.Counter((b["kind"], b["mode"]) for b in briefs))
print("jobs by trigger/status:", collections.Counter((j.get("trigger"), j["status"]) for j in jobs if j.get("trigger")))
print("feed_health:", objs("feed_health"))

"""Read-only analysis of a COPY of the live evidence DB for one API session window."""
import json
import sqlite3
import statistics as st
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta, timezone

db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
T0 = datetime(2026, 11, 17, 12, 0, 59, tzinfo=UTC).timestamp()   # 15:00:59 Kuwait API start
T1 = db.execute("SELECT MAX(start) FROM evidence").fetchone()[0]
print("window", datetime.fromtimestamp(T0, UTC), "->", datetime.fromtimestamp(T1, UTC), round((T1 - T0) / 3600, 2), "h")
rows = db.execute("SELECT rowid,start,channel,payload,pending FROM evidence WHERE start>=? ORDER BY rowid", (T0,)).fetchall()
print("rows", len(rows), "pending_at_end", sum(r[4] for r in rows), "pending_total", db.execute("select sum(pending) from evidence").fetchone()[0])
hour = lambda t: datetime.fromtimestamp(t, timezone(timedelta(hours=3))).strftime("%m-%dT%H")
per = defaultdict(Counter); kinds = Counter(); src = Counter()
asr_times = defaultdict(list); ocr_texts = defaultdict(list); asr_texts = defaultdict(list)
speaker = conf = 0
for rowid, start, ch, payload, pending in rows:
    p = json.loads(payload)
    kind = "asr" if p.get("transcript") else ("ocr" if p.get("ocr") else "other")
    per[hour(start)][kind] += 1; kinds[(ch, kind)] += 1; src[p.get("source")] += 1
    speaker += p.get("speaker") is not None; conf += p.get("confidence") is not None
    if kind == "asr": asr_times[ch].append(start); asr_texts[ch].append((start, p["transcript"]))
    if kind == "ocr": ocr_texts[ch].append((start, p["ocr"]))
print("sources", dict(src), "speaker_nonnull", speaker, "confidence_nonnull", conf)
print("hourly (Kuwait) asr/ocr:")
for h in sorted(per): print(" ", h, per[h]["asr"], per[h]["ocr"])
print("per channel asr/ocr:", {c: (kinds[(c,'asr')], kinds[(c,'ocr')]) for c in sorted({c for c, _ in kinds})})
print("ASR inter-arrival (capture clock) max gaps >120s per channel:")
for ch, ts in sorted(asr_times.items()):
    ts.sort(); gaps = [b - a for a, b in zip(ts, ts[1:])]
    big = [g for g in gaps if g > 120]
    print(f"  {ch}: n={len(ts)} median_gap={st.median(gaps):.1f}s p99={sorted(gaps)[int(len(gaps)*.99)]:.0f}s gaps>120s={len(big)} sum={sum(big)/60:.0f}min max={max(gaps)/60:.1f}min")
def dup_rate(items, window):
    last, dup = {}, 0
    for t, text in sorted(items):
        key = " ".join(text.split())
        if key in last and t - last[key] <= window: dup += 1
        last[key] = t
    return dup
for label, d in (("ASR exact-dup<=60s", asr_texts), ("OCR exact-repeat<=1h", ocr_texts)):
    w = 60 if label.startswith("ASR") else 3600
    print(label, {ch: f"{dup_rate(v, w)}/{len(v)}" for ch, v in sorted(d.items())})
# objects
objs = defaultdict(list)
for kind, payload in db.execute("SELECT kind,payload FROM objects"):
    objs[kind].append(json.loads(payload))
def ts(s): return datetime.fromisoformat(s).timestamp()
gaps = [g for g in objs["gap"] if ts(g["detected_at"]) >= T0]
print("gaps in session", len(gaps), Counter((g["channel_id"], g["reason"]) for g in gaps).most_common(40))
lost = defaultdict(float)
for g in gaps:
    if g["estimated_lost_seconds"]: lost[g["channel_id"]] += g["estimated_lost_seconds"]
print("estimated lost s (lag-limit only):", {k: f"{v:.0f}s={100*v/(T1-T0):.1f}%" for k, v in sorted(lost.items())})
alerts = [a for a in objs["alert"] if ts(a["created_at"]) >= T0] if objs["alert"] and "created_at" in objs["alert"][0] else []
print("alert keys", sorted(objs["alert"][0]) if objs["alert"] else None, "total alerts", len(objs["alert"]))
print("feed_health", objs["feed_health"])
print("jobs", [(j["status"], j.get("trigger"), j.get("kind")) for j in objs["job"]][-10:], "briefs", len(objs["brief"]))
print("config ids", [c["id"] for c in objs["config"]], "schedule", [s["id"] for s in objs["schedule"]][-5:])

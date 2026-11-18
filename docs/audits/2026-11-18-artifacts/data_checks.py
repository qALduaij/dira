"""Read-only checks on a COPY of the live DB using production code paths (no writes to the copy's evidence)."""
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "backend")
from dira.mechanics import SpikeDetector
from dira.store import EvidenceStore, decode_vectors

K = timezone(timedelta(hours=3))
src = sys.argv[1]
ro = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
f = lambda t: datetime.fromtimestamp(t, K).strftime("%m-%d %H:%M")
# 1. Lexical window (newest 10,000 rows) and hot tier (4,000 rows / 2 h) horizons at three moments.
for label, at in (("18:50 (awake, busy)", datetime(2026,11,17,18,50,tzinfo=K)), ("17:20", datetime(2026,11,17,17,20,tzinfo=K))):
    t = at.timestamp()
    rows = ro.execute("SELECT start FROM evidence WHERE start<=? ORDER BY start DESC LIMIT 10000", (t,)).fetchall()
    hot = ro.execute("SELECT start FROM evidence WHERE start<=? AND start>=? ORDER BY start DESC LIMIT 4000", (t, t-7200)).fetchall()
    print(f"[{label}] lexical 10k window spans {(t-rows[-1][0])/3600:.2f} h; hot 4k spans {(t-hot[-1][0])/60:.0f} min")
# 2. Brief sampling on the real data with the production method (copy, so the store may create no rows).
store = EvidenceStore(src)
for hours in (1, 4, 24):
    until = datetime(2026,11,17,18,50,tzinfo=K); since = until - timedelta(hours=hours)
    events, cov = store.brief_sample(since, until, 80)
    mins = sorted({e.start.astimezone(K).strftime("%H:%M") for e in events})
    span = (max(e.start for e in events) - min(e.start for e in events)).total_seconds()/3600
    per_ch = Counter(e.channel_id for e in events)
    print(f"brief {hours}h: total={cov['total_observations']} sampled={len(events)} distinct_minutes={len(mins)} span={span:.2f}h channels={dict(per_ch)} first..last={mins[0]}..{mins[-1]}")
    if hours == 24:
        # how many of the 80 fall in the final minute of each bucket?
        print("   sample minute histogram:", Counter(m[:4]+'x' for m in mins).most_common(12))
# 3. Spike detector replay in arrival (rowid) order with a monotone arrival clock, using stored vectors.
rows = ro.execute("SELECT start,vectors,channel FROM evidence WHERE start>=? AND start<? ORDER BY rowid",
    (datetime(2026,11,17,15,1,tzinfo=K).timestamp(), datetime(2026,11,17,18,54,tzinfo=K).timestamp())).fetchall()
det = SpikeDetector(); clock = 0; spikes = []; new_topics = 0
for start, vec, ch in rows:
    clock = max(clock, start)
    v = next(iter(decode_vectors(vec).values()))
    n = len(det.topics); first = det.topics[0]["centroid"] if det.topics else None
    r = det.observe(v, clock)
    if det.topics and (len(det.topics) > n or (first is not None and det.topics[0]["centroid"] is not first)):
        new_topics += 1
    if r: spikes.append((datetime.fromtimestamp(clock, K).strftime('%H:%M'), ch, r))
span = rows[-1][0] - rows[0][0]
print(f"spike replay: obs={len(rows)} new_topics={new_topics} (one per {span/new_topics:.1f}s; 128-topic memory ~{128*span/new_topics/60:.1f} min) spikes={len(spikes)}")
# 4. Alerts in the awake phase.
alerts = [json.loads(p) for (p,) in ro.execute("SELECT payload FROM objects WHERE kind='alert'")]
aw = [a for a in alerts if "2026-11-17T12:00:59" <= a["timestamp"] <= "2026-11-17T15:54:37"]
print("alerts awake 3.9h:", len(aw), Counter((a["severity"], a["kind"]) for a in aw).most_common(8))
crit = [a for a in aw if a["severity"] == "critical"]
texts = Counter(" ".join(a["detail"].split())[:50] for a in crit)
print("critical:", len(crit), "distinct 50-char prefixes:", len(texts), "top:", texts.most_common(2))
print("unacknowledged (active_alerts):", sum(not a.get("acknowledged") for a in alerts), "of", len(alerts))

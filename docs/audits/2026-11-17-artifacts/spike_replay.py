# Replays stored live vectors through the production SpikeDetector, in ingest (received_at) order.
import sqlite3, json, collections, datetime as dt, sys
sys.path.insert(0, "/Users/qusaial-duaij/Desktop/Dira/backend")
from dira.mechanics import SpikeDetector
db = sqlite3.connect("file:/Users/qusaial-duaij/Desktop/Dira/.data-live/evidence.db?mode=ro", uri=True)
rows = [(json.loads(p), json.loads(v)) for p, v in db.execute("select payload, vectors from evidence")]
P = lambda s: dt.datetime.fromisoformat(s).timestamp()
sess = dt.datetime(2026,11,17,12,22).timestamp()
rows = sorted([r for r in rows if P(r[0]["received_at"]) >= sess], key=lambda r: P(r[0]["received_at"]))
d = SpikeDetector(); skipped = collections.Counter(); seen = collections.Counter(); spikes = collections.Counter()
for e, vecs in rows:
    v = next(iter(vecs.values()))
    ts = P(e["start"])
    if ts < d.latest: skipped[e["source"]] += 1
    seen[e["source"]] += 1
    if d.observe(v, ts): spikes[e["source"]] += 1
print("observed", dict(seen)); print("silently ignored (older than latest)", dict(skipped)); print("spikes", dict(spikes))

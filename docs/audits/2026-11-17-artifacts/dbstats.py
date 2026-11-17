import sqlite3, json, sys, statistics as st, collections, datetime as dt
db = sqlite3.connect("file:/Users/qusaial-duaij/Desktop/Dira/.data-live/evidence.db?mode=ro", uri=True)
rows = db.execute("select payload, pending from evidence").fetchall()
print("evidence rows", len(rows), "pending", sum(p for _,p in rows))
ev = [json.loads(r[0]) for r in rows]
P = lambda s: dt.datetime.fromisoformat(s).timestamp()
src = collections.Counter((e["source"], e["channel_id"]) for e in ev)
for k,v in sorted(src.items()): print(k, v)
print("simulated", sum(e["simulated"] for e in ev), "conf not null", sum(e["confidence"] is not None for e in ev))
first = min(P(e["received_at"]) for e in ev); last = max(P(e["received_at"]) for e in ev)
print("received span", dt.datetime.fromtimestamp(first), dt.datetime.fromtimestamp(last))
# ASR delay = received_at - end, per channel per 15-min bucket (only current API session start 12:22)
sess = dt.datetime(2026,11,17,12,22).timestamp()
by = collections.defaultdict(list)
for e in ev:
    if e["source"]=="whisperlivekit" and P(e["received_at"])>=sess:
        b = int((P(e["received_at"])-sess)//900)
        by[(e["channel_id"], b)].append(P(e["received_at"]) - P(e["end"]))
chans = sorted({c for c,_ in by})
print("\nASR delay (received_at - end) seconds, median/max per 15-min bucket since 12:22")
for c in chans:
    print(c.ljust(11), " ".join(f"{st.median(by[(c,b)]):6.0f}/{max(by[(c,b)]):<5.0f}" if by.get((c,b)) else "   -/-    " for b in range(9)))
for c in chans:
    print(c, "n per bucket", [len(by.get((c,b),[])) for b in range(9)])

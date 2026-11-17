import sqlite3, json, collections, datetime as dt, statistics as st
db = sqlite3.connect("file:/Users/qusaial-duaij/Desktop/Dira/.data-live/evidence.db?mode=ro", uri=True)
ev = [json.loads(r[0]) for r in db.execute("select payload from evidence")]
P = lambda s: dt.datetime.fromisoformat(s).timestamp()
ocr = [e for e in ev if e["source"]=="local-perception"]
# duplicate OCR lines per channel
dup = collections.Counter((e["channel_id"], e["ocr"]) for e in ocr)
total = len(ocr); repeated = sum(c for c in dup.values() if c>1); distinct=len(dup)
print(f"OCR obs {total}, distinct (channel,text) {distinct}, obs whose text repeats {repeated} ({repeated/total:.0%})")
for (c,t),n in dup.most_common(8): print(n, c, t[:90])
# alerts
alerts = [json.loads(r[0]) for r in db.execute("select payload from objects where kind='alert'")]
print("\nalerts", len(alerts), collections.Counter((a['kind'],a['rule_name'],a['severity']) for a in alerts))
crit = [a for a in alerts if a['severity']=='critical']
cd = collections.Counter((a['channel_id'], a['detail']) for a in crit)
print("critical alerts", len(crit), "distinct (channel,detail)", len(cd))
for (c,d),n in cd.most_common(6): print(n, c, d[:80])
print("acknowledged", sum(a['acknowledged'] for a in alerts))
# alerts on evidence by source
idx = {e['id']: e for e in ev}
print("alert source mix", collections.Counter(idx.get(a['tdo_id'],{}).get('source','?') for a in alerts))
spk = [a for a in alerts if a['kind']=='spike']
print("spike alerts", len(spk), "by source", collections.Counter(idx.get(a['tdo_id'],{}).get('source','?') for a in spk))
# briefs
briefs = [json.loads(r[0]) for r in db.execute("select payload from objects where kind='brief' order by rowid")]
print("\nbriefs", len(briefs), collections.Counter((b['kind'], b['mode'], bool(b['error'])) for b in briefs))
for b in briefs[-6:]:
    ids = b['evidence_ids']; es=[idx[i] for i in ids if i in idx]
    span = (max(P(e['start']) for e in es)-min(P(e['start']) for e in es)) if es else 0
    import re
    cited = set(re.findall(r"\[([0-9a-f-]{36})\]", b['content']))
    print(b['created_at'][:19], b['kind'], b['mode'], "evidence", len(ids), f"span {span:.0f}s", "cited", len(cited), "error", b['error'])
times=[P(b['created_at']) for b in briefs if b['created_at']>'2026-11-17T09:22']
print("brief created gaps (s):", [round(b-a) for a,b in zip(times,times[1:])][-15:])
jobs = [json.loads(r[0]) for r in db.execute("select payload from objects where kind='job'")]
print("jobs", collections.Counter(j['status'] for j in jobs), collections.Counter(j.get('error') for j in jobs if j.get('error')))

# Run from a scratch directory: writes a ~2 GB temporary copy (scale.db) and removes it at the end.
# Isolated copy of live evidence DB; measures O(n) work done on the event loop per ingest/search.
import sqlite3, time, sys, json, uuid
sys.path.insert(0, "/Users/qusaial-duaij/Desktop/Dira/backend")
from dira.store import EvidenceStore
from dira.models import SearchRequest
src = sqlite3.connect("file:/Users/qusaial-duaij/Desktop/Dira/.data-live/evidence.db?mode=ro", uri=True)
dst = sqlite3.connect("scale.db"); src.backup(dst); dst.close()
s = EvidenceStore("scale.db")
def t(f, n=5):
    a=time.perf_counter()
    for _ in range(n): f()
    return (time.perf_counter()-a)/n*1000
def report(label):
    n = s.counts()["evidence"]
    print(f"{label}: rows={n} counts()={t(s.counts):.1f}ms get()={t(lambda: s.get(str(uuid.uuid4()))):.2f}ms "
          f"lexical(no time filter)={t(lambda: s.lexical(SearchRequest(query='النفط')),2):.0f}ms recent(120)={t(lambda: s.recent(120)):.1f}ms")
report("live copy")
rows = s.db.execute("select id,start,end,channel,payload,vectors from evidence").fetchall()
for k in range(12):   # ~13x live volume ≈ 26 h at the observed ingest rate
    with s.db:
        s.db.executemany("insert into evidence values (?,?,?,?,?,?,0)", [(str(uuid.uuid4()), st - (k+1)*7200, en-(k+1)*7200, ch, p, v) for _, st, en, ch, p, v in rows])
report("~26h synthetic")

import os
s.close()
for f in ("scale.db", "scale.db-wal", "scale.db-shm"):
    if os.path.exists(f): os.remove(f)

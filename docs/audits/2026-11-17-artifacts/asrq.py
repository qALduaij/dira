import sqlite3, json, collections, regex, statistics as st
db = sqlite3.connect("file:/Users/qusaial-duaij/Desktop/Dira/.data-live/evidence.db?mode=ro", uri=True)
ev = [json.loads(r[0]) for r in db.execute("select payload from evidence order by start")]
asr = [e for e in ev if e["source"]=="whisperlivekit"]
for c in sorted({e["channel_id"] for e in asr}):
    xs = [e for e in asr if e["channel_id"]==c]
    txt = [e["transcript"] for e in xs]
    ar = sum(bool(regex.search(r"\p{Arabic}", t)) for t in txt); lat = sum(bool(regex.search(r"[A-Za-z]{3}", t)) for t in txt)
    words = [len(t.split()) for t in txt]
    rep = collections.Counter(t.strip() for t in txt).most_common(3)
    spk = collections.Counter(e["speaker"] for e in xs).most_common(3)
    print(f"{c}: n={len(xs)} arabic={ar} latin={lat} median_words={st.median(words)} one_word={sum(w<=1 for w in words)} top_repeats={rep} speakers={spk}")
print()
for e in [e for e in asr if e["channel_id"]=="sky_arabia"][-4:]: print("sky_arabia:", e["transcript"][:160])
for e in [e for e in asr if e["channel_id"]=="sky_uk"][-3:]: print("sky_uk:", e["transcript"][:160])

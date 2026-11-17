# Dira (ديرة) — Devil's-Advocate Audit

**Date:** 2026-11-17 (audit window ≈ 14:05–14:35 Asia/Kuwait)
**Scope:** whole system, from MediaMTX ingress to browser evidence, observed on the running installation plus isolated tests.
**Mode:** audit only. No production source was modified and nothing was committed, stopped, restarted or sent to a paid service.
**Artifacts:** [`2026-11-17-artifacts/`](2026-11-17-artifacts/) holds the audit tests and the read-only measurement scripts.

---

## 1. الملخص التنفيذي

**الخلاصة:** ديرة نموذج أولي متقدّم يعمل فعلاً على ست قنوات حيّة، لكنه ليس جاهزاً بعد ليعتمد عليه مسؤول تنفيذي في الوقت الفعلي.

**ما ثبت بالقياس المستقل:**
- استقبال القنوات الست وعرضها في المتصفح يعمل. تقدّمت مقاطع الفيديو الستة 30 ثانية كاملة خلال 30 ثانية من القياس.
- التخزين متّسق: SQLite وQdrant متطابقان (15,619 نقطة، و4 عناصر في الانتظار).
- لم يتكرر انهيار Python منذ تشغيل النسخة الحالية، أي لأكثر من ساعتين.
- اختبارات المشروع الـ76 ناجحة.

**ما لم يثبت أو ثبت عكسه:**
1. **التفريغ الصوتي العربي لا يواكب البث.** في تشغيل مدته ساعتان بلغ تأخّر قناة الجزيرة 674 ثانية (أكثر من 11 دقيقة). أكّد خادم التعرّف على الكلام هذا التأخّر في سجلّه (`lag=673s`). الواجهة لا تُظهر ذلك، وتعرض بدلاً منه "زمن المعالجة 40 مللي ثانية"، وهو رقم لا يشمل التفريغ.
2. **"الموجز الصباحي" لا يغطي 24 ساعة.** كل موجز، صباحياً كان أو سردياً، مبني على آخر 80 ملاحظة فقط، أي ما يعادل 41–60 ثانية من البث.
3. **التنبيهات غير صالحة للتشغيل الفعلي.** صدر 205 تنبيهات حرجة في ساعتين، منها 75 تنبيهاً لكلمة "عاجل" الثابتة نفسها على قناة الحدث. كاشف الطفرات يتجاهل 89.5% من التفريغ الصوتي.
4. **تُرسَل الأدلة تلقائياً إلى خدمة سحابية.** يُرسَل نحو 14 كيلوبايت من نصوص البث إلى OpenRouter كل خمس دقائق دون طلب من المشغّل، أي نحو 288 طلباً يومياً. في المقابل تقول الواجهة "معالجة محلية" و"يُعدّ محلياً". النظام ليس معزولاً عن الشبكة ولا سيادياً بالمعنى المعلن.
5. **القرص ممتلئ بنسبة 98%.** المتبقّي 22 غيغابايت، وقاعدة الأدلة تنمو بنحو 1.7 غيغابايت يومياً دون سياسة احتفاظ. 95% من حجم كل سجل تمثيل نصّي مكرّر للمتجهات المخزّنة أصلاً في Qdrant.

**ما يمكن الاعتماد عليه اليوم:** عرض الفيديو الحي، والبحث الدلالي عن أحداث مضت، وتفريغ القناة الإنجليزية (تأخّر لا يتجاوز 9 ثوانٍ)، واستخراج نصوص الشريط الإخباري كأدلة قابلة للتحقق يدوياً.

**أعلى أولوية هندسية:** قياس تأخّر التفريغ لكل قناة وعرضه، وفرض حدّ أقصى للتأخّر (القفز إلى البث الحي)، قبل أي استثمار في عتاد جديد.

---

## 2. Readiness verdict

| Use | Verdict |
|---|---|
| Live multiview monitoring (video) | **Ready for supervised use.** Verified on all six channels. |
| Near-real-time Arabic speech intelligence (5 channels) | **Not ready.** Lag is unbounded in practice: 674 s worst case, and five-minute-plus medians sustained for an hour. |
| English speech (1 channel) | **Usable.** Median 1–2 s, max 9 s over 2 h. |
| On-screen text (ticker OCR) | **Usable as raw evidence, not as an alert source.** 55% of records are re-emissions. |
| Deterministic alerts | **Not operationally usable.** Volume and duplication cause alert fatigue, and spike detection ignores most speech. |
| Executive briefs | **Misleading in scope.** They cover about a minute while labelled morning or narrative briefs. Citation checks are weak. |
| Retrospective semantic search | **Usable with caveats.** Cross-lingual retrieval works but is fragile to stop-words. Results carry no relevance floor. |
| Sovereign or air-gapped deployment | **Not met by the current configuration.** Automatic cloud egress is enabled. |
| Unattended multi-day operation | **Not demonstrated, and predictably fails** on disk within about 2 weeks. |

**Remaining uncertainty:**
- No reference transcripts exist, so ASR word error rate is unknown.
- The longest observation is one 2 h 03 min run. Nothing longer was observed.
- OCR accuracy was not compared against ground-truth frames.
- I did not measure true publisher-to-screen latency.

---

## 3. Requirements-to-implementation matrix

Legend: **VV** implemented and independently verified · **IV** implemented, not verified here · **P** partial · **S** scaffolding only · **M** missing · **X** incorrect or misleading.

| Requirement | Status | Evidence |
|---|---|---|
| 6 primary streams via MediaMTX | **VV** | `docker ps`; ffprobe of all six local RTSP paths: 1920×1080 H.264 25 fps plus AAC 48 kHz stereo |
| Browser live video | **VV** | Real browser: 6/6 videos advanced 30.0 s in 30 s; buffer-ahead median 1.1–4.7 s |
| FFmpeg 16 kHz mono PCM extraction | **IV** | `ingest.py:86-108` args; the live processes run them; PCM byte rate not re-measured |
| Cropped ticker frames (bottom 20%, 2 fps, VideoToolbox) | **IV** | `ingest.py:31-33,199-227`; live processes use `-hwaccel videotoolbox` |
| Sky News Arabia audio selection | **VV** | Single HLS rendition tagged `eng`; live transcripts are Arabic (1,012/1,027 lines contain Arabic script) |
| Reconnect / supervision | **P** | Restarts work (3 silent restarts in the run), but there is no stall watchdog and recovery is not published (F-06) |
| Stale-source detection | **M** | A hung source stays `connected` (F-06) |
| Token renewal / secondary extraction (yt-dlp, Streamlink) | **S** | Code and tests exist; every channel in `extractors.example.json` is disabled; `infra/extractors.json` is absent |
| Kuwaiti national channel (KTV) | **S** | `ktv1` exists only as a disabled extraction placeholder |
| Local Arabic ASR (WLK + Qwen3 windowed, MPS) | **VV functional / X real-time** | Running; ASR lag up to 673 s per the WLK log (F-01) |
| Local English ASR (causal) | **VV** | Lag ≤ 9 s over 2 h |
| PaddleOCR in isolated subprocesses | **VV** | 6 `dira.ocr_worker` children; API process does not run Paddle |
| Time-aligned TDOs | **P** | Session-relative clock; timestamps are capture-relative, so ASR rows lag wall time by minutes |
| Speaker diarization | **M (live)** | Every ASR row has speaker `<channel>:1` (F-12); pyannote unprovisioned |
| Entity extraction | **M** | No NER; `entities` empty in live data; graph empty in live mode |
| Visual detection | **M** | `DIRA_VISUAL_MODEL` unset; no detector weights |
| Confidence reporting | **P** | UI shows "Uncalibrated" for live sources; 181 earlier live rows still store `confidence=1.0` |
| Multilingual embeddings (MiniLM 384-d) | **VV** | Running encoder `multilingual-minilm`, CPU |
| FAISS hot tier | **VV / X horizon** | Full at 4,000 vectors, about 32 min of evidence at the live rate, not 2 h |
| Qdrant archive + durable outbox | **VV** | Qdrant count 15,619 = SQLite 15,623 − 4 pending |
| Keyword / regex gates (no LLM) | **VV** | `mechanics.py:25-74`; deterministic; no network |
| Statistical spike detection | **X** | Ignores 89.5% of ASR rows (F-03); all live spikes are OCR-driven |
| Semantic routing (Aurelio) | **P** | Returned no route for 5/5 audit queries (all weights 1.0) |
| RRF hybrid search | **P** | Works, but the lexical lane is polluted by stop-words (F-10) |
| Narrative synthesis / morning brief | **X** | 80-row scope (F-02); uncited claims pass (F-07) |
| Extractive fallback | **VV** | 12/25 narrative jobs fell back with an error label |
| Local / cloud / simulation labels | **P** | Brief badge says `cloud-llm`; surrounding UI says "prepared locally" (F-08) |
| Simulation separation | **P** | Live DB has 0 simulated rows; but clients can POST rows with `simulated:false` (F-11) |
| Bilingual RTL/LTR, mobile | **VV** | Arabic sets `dir=rtl`; no horizontal overflow at 375 px |
| AuthN on REST/WS | **IV, disabled** | Supported, but `DIRA_API_TOKEN` unset in live `.env` |

---

## 4. Findings (ordered by practical severity)

Each finding lists location, reproduction, expected vs observed behaviour, impact, confidence, smallest fix and the test that proves the fix. Audit tests are `xfail(strict=True)`: each states the correct behaviour, fails today, and flips once fixed.

### F-01 · Critical · Arabic ASR backlog grows to 11+ minutes and is invisible to the operator

- **Where:** `scripts/start-live.sh:38` (five Arabic sessions share one windowed Qwen3 server, chunk 4 s); `ingest.py:119-122` (audio is forwarded at line rate with no drop policy); `frontend/src/App.tsx` KPI "PIPELINE LATENCY · P95".
- **Repro:** run `docs/audits/2026-11-17-artifacts/dbstats.py` (read-only), then:
  ```
  grep -a -o 'lag=[0-9.]*' logs/asr-ar.log | cut -d= -f2 | sort -n | tail -1
  ```
- **Observed:** `received_at − end` median/max per 15-minute bucket since 12:22:

  | Channel | Worst bucket median | Max |
  |---|---|---|
  | aljazeera | 166 → 327 → 437 → **568 s** | **674 s** |
  | alhadath | 219 → 418 s | 532 s |
  | asharq | 74 s | 169 s |
  | sky_arabia | 71 s | 172 s |
  | sky_uk (English, separate server) | 1–2 s | 9 s |

  WhisperLiveKit's own log reports `lag=` peaking at **673 s**, so this is a real server-side backlog, not timestamp drift. Lag grows for an hour, then partially recovers; there is no evidence it is bounded by design.
- **Expected:** a bounded lag with a stated SLO, shown per channel.
- **Impact:** an executive sees "connected" and "40 ms" while Arabic speech evidence is up to 11 minutes old. Breaking statements arrive minutes after the ticker. Alerts and briefs silently reflect stale speech.
- **Confidence:** high (two independent sources agree). **Limits:** one 2 h run; contention with the six OCR processes for CPU was not separated from GPU contention.
- **Smallest fix:**
  1. Parse WLK's lag/`remaining_time_transcription` (or compute `now − end`) per channel and publish it with channel status.
  2. Replace the "pipeline latency" headline with end-to-end evidence age.
  3. Add a lag ceiling: above N s, restart that channel's ASR session at the live edge and record a gap observation.
- **Verify:** a 2 h soak where per-channel ASR evidence age p95 stays under the ceiling, plus a browser check that the UI shows lag and gaps.
- **Remediation status (2026-11-17, uncommitted):**
  - **Implemented:** lag tracking from `remaining_time_transcription` (`ingest.py` `ASRLag`); a speech-only jump-to-live reset above `DIRA_ASR_MAX_LAG` (default 90 s), with OCR left running; per-channel lag, reset and skipped-seconds badges; the live KPI is now "Speech lag · worst channel"; channel state is republished every metrics tick.
  - **Tests:** `tests/test_asr_lag.py`, 6 tests.
  - **Verified on an isolated instance (port 8010):** a fake WLK server with a growing backlog produced resets at about 21 s with a 20 s ceiling, evidence kept flowing, and the browser updated without a reload.
  - **Not yet verified:** a 2 h soak on the live stack, which needs a restart of the running installation.

### F-02 · Critical · "Morning" and "narrative" briefs summarise only the newest 80 observations (≈ 1 minute)

- **Where:** `runtime.py:237-239` (`db.recent(80, since=now−24h)`), `briefs.py:8`.
- **Repro:** `test_audit_findings.py::test_morning_brief_spans_reporting_window`. Live data: the last six briefs each have 80 evidence rows spanning **41–60 s** (`dbstats2.py`).
- **Expected:** a morning brief covers its 24 h window (sampled or clustered); a narrative brief covers its interval.
- **Observed:** the window bound is satisfied trivially, since 80 rows arrive in under a minute at about 2 rows/s. `evidence_ids` lists all 80 inputs, not the cited ones.
- **Impact:** the flagship executive product misrepresents its scope. A "24-hour" picture is really the last minute of whichever channels were noisiest.
- **Confidence:** high. **Smallest fix:** select evidence per channel and per time bucket over the window (for example the top-k by alert, novelty or deduplicated cluster), print the actual covered interval in the brief header, and store `cited_ids` separately from `input_ids`.
- **Verify:** the audit test passes, and the brief header shows a covered interval of at least 90% of the requested window.

### F-03 · High · Spike detector silently ignores 89.5% of speech observations

- **Where:** `mechanics.py:88-90` (`if timestamp < self.latest: return None`), fed from `runtime.py:171-172` across all channels.
- **Repro:** `spike_replay.py` replays stored live vectors through the production class: 6,275 of 7,010 ASR rows and 2,729 of 7,390 OCR rows ignored; all 16 reproduced spikes come from OCR. Unit test: `test_delayed_asr_burst_still_counts`, with control `test_control_in_order_burst_spikes`.
- **Cause:** one global monotonic watermark across six channels. Delayed ASR (F-01) is always older than the newest OCR frame.
- **Note:** the existing `tests/test_core.py:55` asserts this behaviour ("late data cannot rewind baseline"). The test mirrors the implementation rather than the requirement.
- **Impact:** "semantic volume spikes" are effectively a ticker-repetition detector. A story surging in speech across channels is not detected.
- **Smallest fix:** bucket by event time with an allowed-lateness window (for example 15 min), keyed per topic, and finalise buckets after the watermark minus lateness. Alternatively, count by `received_at` and label it as arrival-rate.
- **Verify:** the audit test passes, and a live replay shows less than 5% of rows ignored.

### F-04 · High · OCR re-emits recurring on-screen text, flooding evidence and critical alerts

- **Where:** `perception.py:64-71` (text absent for 3 frames, about 6 s, is treated as new); `runtime.py:170,185-187` (no alert dedup or cooldown).
- **Repro:** `test_rotating_headline_is_not_new_evidence` (one "عاجل" graphic shown three times gives three emissions). Live data (`dbstats2.py`):
  - 55% of OCR rows repeat earlier text: `£1 = €1.20` ×176, `غرينتش` ×113, `عاجل` ×75.
  - **205 critical alerts in ≈ 2 h**, 75 of them for the bare "عاجل" graphic on one channel. 0 acknowledged.
- **Impact:** alert fatigue makes the critical channel unusable. Duplicates also crowd search results and the 80-row briefs, and drive false spikes (F-03).
- **Smallest fix:** keep a per-channel TTL set of normalised emitted lines (for example 10–30 min), and add alert dedup keyed on (rule, channel, normalised text) with a cooldown. Treat a bare marker word ("عاجل", "BREAKING NEWS") as a modifier of the next headline, not an alert.
- **Verify:** the audit test passes; a 1 h live replay shows at least a 5× reduction in critical alerts with no loss of distinct headlines.

### F-05 · High · Disk will fill in about 2 weeks; no retention

- **Where:** `store.py:26,43` stores every vector as JSON text in SQLite after it is already in Qdrant.
- **Measured:**
  - The volume is 98% used with **22 GiB free**.
  - `evidence.db` is 144 MB after about 2 h (≈ 1.7 GB/day).
  - Average row: payload 398 B and vectors **8,443 B**.
  - A synthetic copy at 26 h equivalent was 1.85 GB (`scale.py`).
- **Impact:** SQLite writes fail when the disk fills, and ingest then stalls in the `deliver()` retry loop. Other software on the workstation also fails.
- **Smallest fix:** store float32 blobs (≈ 1.5 KB per modality, about 5× smaller) or null the `vectors` column after the Qdrant ack. Add a disk-free guard that degrades visibly, and an operator-approved retention policy.
- **Verify:** bytes per row below 2 KB, and a low-disk test fixture produces a visible degraded status instead of a silent stall.

### F-06 · High · Channel status misrepresents health: stalls never detected, recovery never published

- **Where:** `ingest.py:117` sets `connected` when the ASR WebSocket handshakes, independent of media. `ingest.py:120` has an unbounded `stdout.read`. The publish only happens at `ingest.py:290`, after a failure.
- **Repro:**
  - `stall.py`: the exact production FFmpeg arguments against a local RTSP endpoint that accepts and then goes silent stayed alive with zero output after 45 s.
  - `test_reconnected_channel_state_is_published`: browsers receive `degraded`, and the later `connected` is never broadcast.
  - Logs: three channels restarted (12:29, 12:37, 12:43), and the Sky Arabia restart left no log line.
- **Impact:** a frozen feed shows **CONNECTED** indefinitely. A recovered feed shows **DEGRADED/RECONNECTING** to every open browser until it reloads. Either way, the operator cannot trust the tile badge.
- **Smallest fix:** a per-session data watchdog (no PCM for 10 s → raise), FFmpeg `-rw_timeout`/`-timeout`, publish `channels` on every status change, and include last-observation age per channel.
- **Verify:** the audit test passes, and `stall.py` adapted to the adapter shows a reconnect within 15 s.

### F-07 · High · Citation validation lets uncited claims through; half of cloud syntheses fail

- **Where:** `briefs.py:75-77` requires only that *some* citation exist and that all cited IDs are valid.
- **Repro:** `test_uncited_claims_are_rejected`. A response with one valid citation plus two fabricated, uncited claims ("cabinet resigned", "oil exports halted") is accepted and labelled `local-llm`.
- **Live:** 12 of 25 narrative jobs failed validation (`ValueError`). The specific cause is not logged (hypothesis: citation format such as comma lists or upper case).
- **Impact:** valid-looking citations lend credibility to unsupported conclusions. Prompt-injected broadcast text could exploit this (not tested against a real model).
- **Smallest fix:** require a citation on every bullet or sentence, reject otherwise, log the rejection reason, and accept `[id, id]` lists.
- **Verify:** the audit test passes; a cloud or local trial with ≥ 20 briefs has at most 5% fallback, with reasons logged.

### F-08 · High · Automatic cloud egress contradicts "local" and "sovereign" UI claims

- **Where:** `runtime.py:268-272` enqueues a narrative every 300 s. `.env` sets an OpenRouter URL and `provider=cloud`.
  - UI copy says "Local processing · Private by design", "Prepared locally for your next decision", "SOVEREIGN WORKSPACE" and "LOCAL OPERATIONS" (`App.tsx:179,205,860,938`).
  - The System panel shows the reasoning worker only as "configured".
- **Measured:** one brief every 288–313 s (≈ 288/day). Each sends about 14 KB of broadcast-derived text (≈ 2.3 M input tokens/day by rough estimate). Nothing in the UI announces this.
- **Impact:** privacy and sovereignty claims are false for this configuration. Spend is unattended. Roughly half the calls are wasted (F-07).
- **Smallest fix:**
  - Disable automatic narratives when `provider=cloud` unless explicitly opted in, or raise the interval.
  - Show "Cloud: OpenRouter" persistently in the header and System panel.
  - Make the "local" copy conditional.
- **Verify:** a UI test with `provider=cloud` asserts the cloud banner, plus a scheduler test asserting no cloud jobs without opt-in.

### F-09 · Medium · The documented setup command destroys the live environment

- **Where:** `README.md:36` (`uv sync --frozen`).
- **Repro:** `uv sync --frozen --dry-run` reports **"Would uninstall 124 packages"**, including torch, paddlepaddle, paddleocr, sentence-transformers, semantic-router, yt-dlp and streamlink.
  - `uv sync` is exact by default; `uv run` is inexact, so `make test` is safe (checked against the uv documentation).
  - `start.sh` correctly uses `--inexact`.
- **Impact:** a routine developer step breaks `make live`. The live environment is not reproducible from one documented command.
- **Smallest fix:** document `uv sync --frozen --extra semantic --extra perception --extra extraction`, and add a `make live-env` target.
- **Verify:** that dry run reports 0 removals on the live environment.

### F-10 · Medium · Search ranking: stop-words dominate, no relevance floor, router inactive

- **Where:** `store.py:113-125` scores raw token overlap, stop-words included. `runtime.py:202` gives the lexical lane weight 1.5, above every vector lane.
- **Repro (live, read-only):**
  - `explosions Sanaa` returns 5/5 relevant Arabic Sanaa reports.
  - `explosions in Sanaa` returns 5/5 irrelevant English Sky UK lines ("In the last ten years.").
  - Unit test: `test_stopword_only_overlap_is_not_a_lexical_hit`.
- **Also observed:**
  - A query with no relevant evidence ("Kuwait parliament dissolved") returns confident-looking results, since RRF scores carry no absolute similarity.
  - The Aurelio router chose no route for 5/5 queries.
  - Duplicate OCR rows occupy several of the top results.
  - The lexical lane only scans the newest 10,000 rows (≈ 80 min at the live rate).
  - Search takes 300–420 ms, about 180 ms of it in the lexical scan.
- **Smallest fix:** a stop-word list (Arabic and English) or SQLite FTS5 with BM25; expose cosine similarity and suppress results below a floor; dedupe by normalised text.
- **Verify:** the audit test passes; a 20-query bilingual relevance set with precision@5 recorded before and after.

### F-11 · Medium · Unauthenticated live API: evidence forgery and DNS-rebinding reads

- **Where:** live `.env` has no `DIRA_API_TOKEN`. `api.py:110-119` accepts client-supplied `simulated` and `source`. `api.py:66-70` checks Origin only when present and has no Host allow-list.
- **Repro:** `test_client_cannot_forge_live_evidence` (a POST with `simulated:false, source:"whisperlivekit"` is stored as live ASR) and `test_foreign_host_header_is_rejected` (`Host: rebind.attacker.example` gives 200). `/docs` and `/openapi.json` return 200.
- **Impact:** any local process, or a web page via DNS rebinding (read-only GETs), can read all live evidence. A local process can also inject fabricated "live" evidence that triggers critical alerts and enters briefs. This also breaks simulation/live separation.
- **Mitigation already present:** loopback binding; Origin rejection for cross-site POST.
- **Smallest fix:** add TrustedHost (`127.0.0.1`, `localhost`); in live mode require the token for `/api/ingest` or disable it, and force `source="api"` on client records; generate a token in `make live`.
- **Verify:** both audit tests pass.

### F-12 · Medium · Speaker labels and fragments: no diarization, low-value records

- **Observed:**
  - All 7,550 live ASR rows have speaker `<channel>:1`, so the speaker filter and "speaker" field are meaningless.
  - Median ASR line is 5–11 words; 84–297 single-word rows per channel; `"."` alone stored 39 times on Al Hadath.
  - 181 rows from the 12:00 session store `confidence: 1.0` (UI masks them, while API, Qdrant payloads and exports do not).
- **Smallest fix:** hide the speaker field until diarization exists; merge ASR fragments into sentence-level TDOs (merge on silence or punctuation); drop punctuation-only lines; migrate legacy `confidence=1.0` rows to `null`.
- **Verify:** an ingest unit test rejects punctuation-only rows; a DB check finds 0 live rows with non-null confidence.

### F-13 · Medium · Crash mitigation holds, but the root conflict remains and OCR workers are bloated

- **Observed:**
  - Crash reports at 12:02–12:07 show SIGSEGV inside `libomp.dylib`.
  - No new Python crash report since the current API started (12:22, about 2 h 03 min). Memory was stable over the audit window (API RSS 684 → 698 MB; 332 file descriptors; 19 children).
  - The API process still loads **three** OpenMP runtimes (`faiss/.dylibs`, `sklearn/.dylibs`, `torch/lib`).
  - Each OCR worker loads the same three plus Paddle, using about 760 MB of resident memory (RSS) ×6 ≈ 4.6 GB, because `ocr_worker → perception → embeddings → mechanics` imports FAISS.
- **Assessment:** the mitigation (single-thread pools plus process isolation) survived passive verification of about 2 h. It avoids the conflict rather than removing it. Any code path that raises a thread count, or a library that ignores `OMP_NUM_THREADS`, can reintroduce it.
- **Smallest fix:** make `ocr_worker` import only Paddle and NumPy (move `sharpness` and `ChyronOCR` to a FAISS-free module); add a startup assertion logging the loaded `libomp` paths.
- **Verify:** `lsof -p <ocr pid> | grep libomp` shows one runtime; the RSS drop is recorded.

### F-14 · Medium · OCR saturates six CPU cores at an effective ≈ 0.5 fps

- **Observed:** six workers at 96–99% CPU each, continuously; documented 1.7–2.3 s per inference. With 2-of-3 voting, a line must persist about 4–6 s to be emitted.
- **Hypothesis (not tested):** scrolling tickers rarely produce identical reads in two sampled frames, so crawling text is largely lost.
- **Smallest fix:** skip inference when the cropped frame is unchanged (perceptual hash or difference threshold); most ticker frames are static, which frees cores for ASR pre-processing.
- **Verify:** CPU per worker and distinct-lines-per-hour, before and after, on recorded clips.

### F-15 · Low · Video tiles show false error overlays and never self-recover

- **Where:** `Visuals.tsx:148,151-153,169`.
- **Observed:** "Press play to start video" stays over Asharq and Sky UK while both play (30 s advanced in 30 s). The error is set on autoplay rejection and never cleared on `playing`. Fatal hls.js errors set "Playback unavailable" with no `recoverMediaError` or reload, so the tile stays dead until a page reload. A frozen-but-not-errored video has no stale indicator.
- **Fix:** clear the error on `playing`, retry or recover on fatal errors, and add a stalled-time badge (currentTime not advancing for over 10 s).

### F-16 · Low · Misleading counters and archive horizon

- "ACTIVE ALERTS 100" is the snapshot cap; 291 exist (`runtime.py:332`).
- Acknowledging re-inserts the row and reorders it to newest (`store.py:84`).
- Acknowledgement scans the latest 10,000 alerts.
- The "2 h" FAISS hot horizon holds about 32 min at the live rate (capacity 4,000 binds first).
- `COUNT(*)` runs on every ingest on the event loop: 0.4 ms now, 7 ms at 202 k rows (`scale.py`).

### F-17 · Low · Observability gaps

- Disconnect exceptions are swallowed without cause (`ingest.py:287-289`).
- FFmpeg stderr goes to `DEVNULL`.
- The brief-rejection reason is not logged.
- The API log is dominated by tqdm progress bars: 2.6 MB in 2 h, no rotation.
- No metrics exist for ASR lag, OCR frame drops, or per-channel last-observation age.

---

## 5. Test ledger

| # | Command / method | Environment | Result | Duration | Artifact |
|---|---|---|---|---|---|
| 1 | `.venv/bin/python -m pytest -q -p no:cacheprovider` | repo suite, `DIRA_*` env isolated by fixture | **76 passed** | 12.6 s | — |
| 2 | `npm test` (frontend) | node:test | **3 passed** | 0.09 s | — |
| 3 | Audit tests (see file header) | tmp_path, no network | **1 passed, 8 xfailed**; `--runxfail` shows each failing on its assertion, not on setup | 3.8 s | `test_audit_findings.py` |
| 4 | `dbstats.py` | read-only `mode=ro` on live DB | ASR lag table (F-01) | ~2 s | `dbstats.py` |
| 5 | `grep lag= logs/asr-ar.log` | live log | WLK lag max 673 s | <1 s | — |
| 6 | `dbstats2.py` | read-only live DB | OCR duplicates, alerts, brief spans, cloud cadence | ~2 s | `dbstats2.py` |
| 7 | `spike_replay.py` | read-only live vectors to production `SpikeDetector` | 89.5% of ASR ignored | ~3 s | `spike_replay.py` |
| 8 | `asrq.py` | read-only live DB | speaker labels, fragments, script | <1 s | `asrq.py` |
| 9 | `scale.py` | isolated DB copy in scratchpad (deleted after) | counts 0.4 → 7 ms; lexical 181 → 211 ms; 1.85 GB at 202 k rows | ~40 s | `scale.py` |
| 10 | `stall.py` | local silent TCP "RTSP" fixture | FFmpeg alive with 0 bytes after 45 s | 45 s | `stall.py` |
| 11 | ffprobe of 6 local RTSP paths | +1 short reader per path on MediaMTX | all 1080p25 H.264 + AAC 48 k stereo, one audio track | ~15 s | — |
| 12 | Real browser (in-app) on `127.0.0.1:8000` | live UI | 6/6 videos advance 30/30 s; false overlays on 2 tiles; RTL + 375 px OK | ~2 min | — |
| 13 | 7 `POST /api/search` queries | live API (read-only) | stop-word inversion; no relevance floor | 137–420 ms each | — |
| 14 | `GET /api/snapshot`, `/api/metrics` ×3 | live API | 14–21 ms / 3–4 ms; 213 KB snapshot | — | — |
| 15 | Qdrant `points/count` vs SQLite | live stores, read-only | 15,619 = 15,623 − 4 pending | — | — |
| 16 | Crash-report inspection | `~/Library/Logs/DiagnosticReports` | 4 libomp/SIGSEGV crashes 12:02–12:07; none after 12:22 | — | — |
| 17 | `lsof` / `ps` on live PIDs | live processes | 3 libomp copies; RSS stable; 19 children | — | — |
| 18 | `uv sync --frozen --dry-run` | live venv, dry run only | would uninstall 124 packages | 1 s | — |

---

## 6. Performance results (with measurement boundaries)

| Measurement | Boundary | Result | n / caveat |
|---|---|---|---|
| Ingest processing (`metrics.latency_p95_ms`) | `Runtime.ingest` only: embed, SQLite, FAISS, gates. **Excludes** acquisition, ASR, OCR, network, rendering. | p95 36–40 ms | last 500 ingests |
| Arabic ASR evidence age | `received_at − TDO.end`; capture-relative clock; includes WLK queueing and inference | per 15-min bucket medians 6–568 s, max 674 s | 71–228 rows per bucket per channel; 2 h |
| Arabic ASR server lag | WLK's own `lag=` log field | max 673 s | 45,910 log lines, unattributed to channel |
| English ASR evidence age | as above | median 1–2 s, max 9 s | 200–343 rows per bucket |
| OCR inference | per frame, CPU, 1 thread (from project docs, not re-measured) | 1.7–2.3 s | — |
| Browser playback | `video.currentTime` advance; buffer ahead of playhead | 30.0/30 s on all 6; buffer 1.1–4.7 s | 30 one-second samples |
| Snapshot API | localhost HTTP, 15 k rows | 14–21 ms | n = 3 (no percentiles) |
| Search API | localhost HTTP, hybrid + lexical scan | 137–420 ms | n = 7 (no percentiles) |
| Publisher-to-display, WebSocket-to-render | — | **not measured** | see §10 |

p50/p95/p99 are reported only where n ≥ 100.

---

## 7. Missing or misleadingly represented features

| Feature | Represented as | Actual |
|---|---|---|
| "Pipeline latency" KPI | System latency | Ingest-only; ASR minutes behind (F-01) |
| Morning brief | 24 h summary | Newest 80 rows, ≈ 1 min (F-02) |
| Semantic volume spikes | Cross-modal surge detection | OCR repetition detector (F-03) |
| "Local processing · Private by design" / "Prepared locally" | Sovereign operation | Automatic OpenRouter egress every 5 min (F-08) |
| Channel CONNECTED badge | Feed healthy | ASR WebSocket handshake; stalls undetected (F-06) |
| Speaker field / speaker filter | Diarization | Constant per channel (F-12) |
| Entity graph | Entity intelligence | No entity extractor in live mode; graph empty |
| Visual detection | Visual track | Not provisioned |
| Kuwaiti national coverage | KTV in example config | Disabled placeholder; no Kuwaiti channel live |
| Secondary extraction | Implemented sidecar | Scaffolding; no channel enabled |
| "ACTIVE ALERTS" count | Total open alerts | Capped at 100 (F-16) |
| Confidence | Uncalibrated (UI) | 181 stored rows say 1.0 (F-12) |

---

## 8. Prioritized improvements

**Immediate (correctness and stability, days):**
1. Per-channel ASR lag metric in the UI plus a lag ceiling with jump-to-live (F-01).
2. Time-stratified brief selection; show the covered interval; separate cited from input IDs (F-02).
3. OCR TTL dedup and alert cooldown (F-04).
4. Spike buckets with allowed lateness (F-03).
5. Stop storing JSON vectors in SQLite and add a disk guard (F-05). This is urgent at 22 GiB free.
6. Publish status on every change and add a data watchdog plus FFmpeg I/O timeouts (F-06).
7. Turn off automatic cloud narratives, or add a visible cloud banner (F-08).

**Near-term (performance and usability, weeks):**
- Skip OCR on unchanged frames (F-14); make the OCR worker FAISS-free (F-13).
- Merge ASR fragments to sentences; hide the speaker field (F-12).
- FTS5/BM25 or stop-words, a relevance floor, result dedup (F-10).
- Per-bullet citation enforcement with logged rejection reasons (F-07).
- Player recovery and stale-frame badge (F-15); a corrected README environment command (F-09); log hygiene (F-17).

**Before production deployment:**
- Token on by default, TrustedHost, ingest locked in live mode (F-11).
- Retention policy and backups.
- A 24 h and a 72 h soak with published lag, memory, file-descriptor and crash metrics.
- A reference-transcript WER set (Arabic Gulf/MSA, names, numbers, negation) and an OCR ground-truth set.
- A decision on cloud versus local synthesis, documented as the egress boundary.
- A Kuwaiti national channel.

---

## 9. Assessment of the existing Apple M2 Max (64 GB, 12 cores; verified with `sysctl`)

- **Demonstrated:**
  - 6 × 1080p HLS acquisition, routing and browser playback.
  - 6 concurrent CPU OCR workers (about 6 of 12 cores saturated).
  - 1 English causal ASR session in near real time.
  - Embedding and indexing at p95 below 40 ms.
  - About 2 h without a native crash under the current mitigation.
- **Not supported:**
  - 5 concurrent Arabic windowed Qwen3 sessions on one MPS server in real time. Lag reached 11 minutes.
  - Unattended multi-day storage on the current disk.
- **Unknown:**
  - How much of the Arabic lag is GPU-bound versus CPU contention from the six saturated OCR workers. The single-session Arabic real-time factor was not measured under isolation (§10).
- **Recommendation: software before hardware.** Three things should be measured before sizing new hardware, because each could change the answer by a large factor:
  - CPU freed by OCR change-detection.
  - A lag ceiling with jump-to-live.
  - The Arabic real-time factor per session at different chunk sizes, or with batched or MLX inference.

  Buying an M5 Max now would buy headroom against an unmeasured bottleneck. The decision is cheaper and more defensible after one isolated single-session benchmark.

---

## 10. Tests not performed, and why

| Test | Why not |
|---|---|
| ASR word error rate against reference transcripts | No reference transcripts exist; manual transcription of a sample needs a human Arabic listener |
| OCR accuracy against frame ground truth | No labelled frames; would need captured frames plus manual labels |
| Isolated single-session Arabic real-time-factor benchmark | Needs a second ASR server on the same GPU (contends with the live system) or stopping live; requires approval |
| Reproducing the libomp crash (multi-thread) | Prohibited by scope (known native crash on the user's active machine) |
| Real OpenRouter call or prompt injection against a live model | Paid external call with broadcast evidence; mocked instead (F-07) |
| Restart, graceful shutdown, durable-outbox recovery on the live stack | Would interrupt the running installation; covered only by the existing unit tests (`test_resilience.py`) |
| Long soak (24–72 h) | Out of the audit time window; the 2 h live run was analysed instead |
| Publisher-to-display and WebSocket-to-render latency | Needs a timing marker in the source (for example a burned-in clock comparison); not available on public feeds |
| Docker image build and compose profile | Large build; not required to assess the live path |
| Secondary extraction against real publishers | All placeholders disabled; avoided access-control or regional testing by scope |
| Accessibility audit with a screen reader / contrast tooling | Only an automated name/size scan was done (0 unnamed buttons, 4 small targets) |

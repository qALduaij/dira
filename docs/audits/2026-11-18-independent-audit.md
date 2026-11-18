# Dira: Independent Audit (third pass)

**Date:** 2026-11-18, 05:27–07:30 Asia/Kuwait.
**Scope:** current repository (commit `72bc4a7`, branch `feat/dira-platform`, working tree clean) and the live session that ran from 2026-11-17 15:00:59 until the host rebooted at 2026-11-18 04:38.
**Mode:** audit only.
- No production code changed. No restart, commit, push, deletion, paid call, `.env` disclosure or dependency sync.
- New files are confined to this report and [`2026-11-18-artifacts/`](2026-11-18-artifacts/).

**Conventions:** times are Asia/Kuwait (UTC+3) unless marked UTC. **Observed** = measured in this audit. **Hypothesis** = plausible, not proven. **Recommendation** = proposed change.

---

## الملخص التنفيذي (عربي)

**الحكم:** ديرة تعمل جيداً **حين يكون الجهاز مستيقظاً وغير مُثقَل**، لكنها لا تكشف للمستخدم متى تتوقف التغطية فعلياً. لا يُعدّ النظام جاهزاً للإنتاج.

**ما وجدته في التشغيل الحقيقي (13.6 ساعة، تحليل بأثر رجعي للقراءة فقط):**
- **أثناء اليقظة (15:01–18:54):** ظهر نص صوتي في 91–96% من دقائق كل قناة. التأخر العربي: الوسيط 11–20 ثانية، والمئين 95 بين 55 و72 ثانية. سقف الـ90 ثانية صمد.
- **18:54:** أُغلق غطاء الجهاز فدخل في **سكون لمدة 9 ساعات**. هبط الإنتاج إلى 2–8% من المعدل. استيقظ الجهاز عشرات المرات استيقاظاً جزئياً، و**دخل ثلاث مرات في سكون طارئ بسبب الحرارة**. لم يُسجّل النظام شيئاً اسمه «سكون الجهاز»، وحسب ساعات النوم «فقداً تقديرياً» حتى 1,061 ثانية في السجل الواحد.
- **بعد فتح الغطاء (03:51):** دخل التفريغ الصوتي في **عاصفة إعادة ضبط**: 121 إعادة في 47 دقيقة، وظهر النص في 22–64% فقط من الدقائق، والقنوات تبدو «متصلة». صُنّف كل ذلك «تأخراً»، ولم يُرفع أي تنبيه.
- **عمّال OCR:** أعاد الإصدار المُشغَّل تحميل نموذج OCR (≈1.2 غيغابايت) **428 مرة** في 13.6 ساعة. الإصلاح موجود في الشيفرة الحالية لكنه **لم يُشغَّل حياً بعد**.
- **الموجز الصباحي:** «موجز 24 ساعة» على البيانات الحقيقية أخذ عيّنته من **6 دقائق فقط**، بينما تعرض الواجهة نافذة الـ24 ساعة كاملة.
- **السحابة:** لم يُرسَل أي دليل إلى خدمة سحابية خلال 13.6 ساعة. الاشتراط الصريح للتفعيل صمد.

**تحديث 08:21 — اختبار الساعتين اكتمل** بعد أن أعاد المشغّل تشغيل النظام (§12):
- 7,204 ثانية والجهاز مستيقظ، دون أي خطأ.
- إصلاح OCR **ثبت حياً**: عامل واحد لكل قناة طوال الساعتين، دون أي إعادة تشغيل، ودون تقارير انهيار.
- **لكن** فقد التفريغ العربي التقديري ارتفع إلى 21–40% لكل قناة، والجهاز مُثقل جداً (متوسط الحِمل 43–72 على 12 نواة).

**أولويات:**
1. تشغيل حي لمدة ساعتين، والجهاز مستيقظ، لإثبات إصلاح OCR.
2. جعل صحة التغطية صادقة: التمييز بين سكون الجهاز وتعطل ASR والتأخر الحقيقي.
3. نزاهة الموجز وإظهار الفجوات للمحلل.

---

## 1. Baseline (observed)

| Item | Observation |
|---|---|
| Host | Apple M2 Max, 64 GiB, 12 cores, macOS 27.2.1. Uptime 48 min at audit start (rebooted 04:38/04:39). |
| Disk | 156 GiB free on the data volume. This changed externally: 17–48 GB on 17 Nov. |
| Runtime | Python 3.12.13 (`.venv`), Node 24.9.0, FFmpeg 9.0.2. |
| Live stack | **Not running.** No listeners on 8000, 8001, 8003, 6333 or 8554. Docker daemon down. Last API log line 04:38:48 ("Warm tier unavailable"); the API was killed by the reboot, with no graceful shutdown logged. |
| Loaded code | The API that ran 15:00:59 → 04:38 (pid 38453) started **before** the OCR-lifecycle change (files modified 17:28–17:29). The P-08/P-09 fix has therefore **never run live**. |
| Operator config | `DIRA_MODE=live`, `LLM_PROVIDER=cloud` (OpenRouter host), `CLOUD_AUTO_BRIEFS` unset (false), `ROUTER=aurelio`, `ENABLE_OCR=true`, **no `DIRA_API_TOKEN`**. Values of secret keys were not read. |
| Feeds | 6 feeds, all `rtsp://127.0.0.1:8554/...`, no userinfo or query strings. P-04 exposure is therefore structural, not a live credential leak. |
| Git | One commit holds the entire platform. There is no pre-remediation baseline in history; comparisons rely on the earlier audit documents. |
| Test isolation | `tests/conftest.py` strips `DIRA_*` and disables `.env`. Stat snapshots of `.data`, `.data-live`, `infra/` and `docs/*.png` were identical before and after the suite. |

Correction to an earlier audit: `2026-11-17-post-remediation-audit.md` §7 said the Aurelio router is "not on the measured search path". It is on that path (`runtime.py:97-99`, `runtime.py:243`). Its benefit is unmeasured.

---

## 2. Test and results matrix

| # | Check | Command / method | Outcome |
|---|---|---|---|
| T1 | Backend suite | `.venv/bin/python -m pytest -q -p no:cacheprovider` | **110 passed**, 14.27 s. That is 102 earlier tests plus 8 OCR-lifecycle tests. No protected file changed. |
| T2 | Frontend state tests | `node --test tests/*.test.mjs` | **4/4 passed** |
| T3 | Typecheck and build | `npx tsc -b --noEmit`; `npx vite build --outDir <scratch>` | Exit 0; built in 1.44 s, with a >500 kB chunk warning. The served `frontend/dist` was not touched. |
| T4 | Chrome acceptance | Isolated simulation API on **:8031** with scratch data, `DIRA_LLM_URL=http://127.0.0.1:9/v1` (closed port) and `DIRA_TEST_CLOUD=1`. Specs copied to `frontend/test-results/audit-specs/` with screenshot paths redirected. | **4/4 passed**, 4.9 s. The brief fell back on `ConnectError`, so there was no egress. `docs/dira-*.png` hashes were unchanged. |
| T5 | Live-player recovery specs | — | **Blocked:** no live MediaMTX. Not re-run. |
| T6 | Prior post-remediation reproductions | `pytest … 2026-11-17-post-remediation-artifacts/test_post_remediation_findings.py` | **8 xfailed.** P-01 to P-07 still reproduce. The P-08 stub is obsolete (old signature); its replacement is `tests/test_ocr_lifecycle.py`. |
| T7 | Original audit reproductions | `pytest … 2026-11-17-artifacts/test_audit_findings.py` | 6 strict XPASS (F-02, F-04, F-07, F-10, F-11 ×2 **no longer reproduce**), 2 xfailed (F-03 and F-06 encode superseded semantics), 1 passed |
| T8 | **New reproductions** | `pytest -o asyncio_mode=auto --rootdir=docs/audits/2026-11-18-artifacts docs/audits/2026-11-18-artifacts/test_2026_11_18_findings.py` | **3 passed** (characterizations), **5 xfailed**. With `--runxfail`, all 5 fail on their own assertions, not on setup. |
| T9 | API and WebSocket probes | curl and `websockets` against :8031 | Foreign Host → 400; `Host: testserver` → **200**; foreign or `null` Origin → 403; WebSocket with foreign Origin rejected at handshake; unauthenticated WebSocket closed after 5.0 s; chunked 2 MB body → 413. `(a+)+$` rule accepted; 5 ingests in 28 ms with 0 regex timeouts. |
| T10 | New soak sampler smoke | `soak_sampler.py --wall-seconds 25` against :8031 | 6 samples, 0 errors, WebSocket probe 4–45 ms. :8031 stopped afterwards. |
| T11 | **Two-hour live soak** | — | **Not performed:** the live stack is down (host reboot). Starting it would cross the "no restart" boundary. |
| T12 | Retrospective live session | `session_stats.py` on a **copy** of `.data-live/evidence.db` (SHA-256 identical to the source; `quick_check` = ok) | 13.62 h, 25,744 rows (§3) |
| T13 | Host power timeline | `pmset -g log` (read-only) | Clamshell sleep 18:54:37, 3× "Dark Wake Thermal Emergency", full wake 03:51:25, reboot 04:38 |
| T14 | Production code paths on real data | `data_checks.py` on the copy: `EvidenceStore.brief_sample`, horizon queries, `SpikeDetector` replay | The replay reproduced **exactly the 9** live spike alerts (§4) |
| T15 | Query cost on real data (copy) | timing harness | Lexical scan 140 ms median (10,000 rows parsed); `brief_sample` 24 h 135 ms; `active_alert_count` 1 ms |
| T16 | ASR server behaviour | Read WLK 0.2.26 source and `logs/asr-*.log` | WLK pushes only when its response changes (`audio_processor.py:968-975`). Its lag uses wall-clock `time()` (`audio_processor.py:428-431`). |
| T17 | uv sync semantics | Context7, uv docs | `uv run` syncs inexactly (keeps extras); `uv sync` syncs exactly (removes them). |

**Untested:** WER and OCR CER (no references); publisher-to-screen latency; Qdrant/SQLite consistency (Qdrant down); live WebSocket soak; prolonged-outage player recovery; native crash behaviour of the new OCR worker exit path.

---

## 3. Measured operation: retrospective of the 13.6 h live session (observed)

Source: read-only copy of the live database, `api-live.log`, `asr-*.log` and `pmset`. These are *adapter-relative* timestamps, not publisher-to-screen latency. Artifacts: `session_stats.out.txt`, `data_checks.out.txt`, `host_power_events.txt` and `ocr_model_loads_per_hour.txt`.

### 3.1 Three phases

| Phase | Host state | ASR rows/h | Lag-limit resets | Exception gaps (no duration estimate) |
|---|---|---|---|---|
| A. 15:01–18:54 (3.9 h) | Awake, AC power | ≈3,100–3,700 | 59 (each 90.1–90.6 s) | 66 |
| B. 18:54–03:51 (9.0 h) | **Lid closed**: dark-wake cycles, 3 thermal-emergency sleeps | 67–489 | 16 (5 over 120 s; **max 1,061.6 s**) | 197 |
| C. 03:51–04:38 (0.8 h) | Awake, AC power | ≈300 | **121** | 28 |

### 3.2 Phase A: the system at its best

**Evidence presence** (share of 1-minute windows with at least one observation)

| Channel | ASR | OCR |
|---|---|---|
| alarabiya | 93% | 97% |
| alhadath | 96% | 97% |
| aljazeera | 91% | 85% |
| asharq | 95% | 96% |
| sky_arabia | 91% | 94% |
| sky_uk | 94% | 84% |

**ASR delay** (`received_at − end`, adapter-relative)

| Channel | Median | p95 | Max |
|---|---|---|---|
| alarabiya | 13.9 s | 62.3 s | 87.5 s |
| alhadath | 13.6 s | 61.3 s | 88.9 s |
| aljazeera | 16.8 s | 72.3 s | 88.2 s |
| asharq | 11.2 s | 55.1 s | 83.9 s |
| sky_arabia | 20.2 s | 69.1 s | 89.0 s |
| sky_uk | 1.6 s | 7.8 s | 45.0 s |

**Estimated loss from lag-limit resets:** 1.48 channel-hours out of 23.3, or **6.3%**. This excludes the 66 exception gaps, which carry no estimate.

**Alerts:** 260 in 3.9 h (67/h): 190 warning, **59 critical**, 9 spike.
- **11 of the 59 criticals** are one station promo («تابعوا أحدث الأخبار … للأخبار العاجلة»).
- 7 of these were reported earlier (P-10); 11 is the total now.

**OCR model reloads:** 10–36 per hour, with 6 channels.

### 3.3 Phase B: host sleep (operational event, with application defects)

**Observed**
- The lid closed at 18:54:37.
- macOS ran roughly 60 dark-wake windows.
- Dira resumed in each window, produced bursts of evidence and logged 197 exception gaps.
- Three windows ended in **"Dark Wake Thermal Emergency"**.
- Per channel, ASR inter-arrival gaps over 120 s add up to about 9 h.

**Classification**
- The sleep itself is a host/operational event.
- **Application defects** around it:
  - No sleep prevention: `start-live.sh` has no `caffeinate`.
  - No sleep detection.
  - No "host asleep" gap.
  - **WLK's wall-clock lag includes the sleep, and Dira books it verbatim as estimated loss** (up to 1,061.6 s per record).

### 3.4 Phase C: post-wake ASR collapse

**Observed**
- **121 lag-limit resets in 47 min across all six channels, English included.**
- ASR minute-presence fell to **22–64%**, while OCR stayed at 76–100%.
- WLK's own log shows real backlog in this phase: 348 entries over 30 s in the last 6,000 Arabic lines, max 87.7 s.
- WLK logged 9 "backend produced no output" errors.
- The host was on AC power.

**Hypothesis:** thermal throttling after the emergencies, or post-sleep GPU or host contention. The cause is unproven.

**Application defect:** the system booked about 3 channel-hours as `asr_lag_limit` "estimates". It never marked a channel degraded and raised no alert. Tiles showed `connected` whenever PCM flowed (`ingest.py:175-176`).

### 3.5 Durability

- The abrupt kill at reboot left **4 pending outbox rows**.
- The database copy passes `quick_check`.
- Those rows will replay on the next start.
- **Verified:** SQLite and outbox durability under SIGKILL-class termination.

### 3.6 Cloud egress

**0 briefs and 0 jobs after 15:00:59**, with the scheduler running for 13.6 h. All 34 stored briefs predate the restart; 17 of them (50%) were extractive fallbacks.

### 3.7 Failure classification

| Class | Instances |
|---|---|
| Publisher / network | aljazeera recurring `ExceptionGroup`: 51 in session vs 26–32 on peers (hypothesis carried from the 17 Nov audit; no source-side proof) |
| Host capacity / power | Clamshell sleep; thermal emergencies; post-wake ASR running below real time (§3.4) |
| Application defects | N-01, N-02, N-07; P-09 churn (428 loads); P-01 to P-07 and P-10 still reproduce |
| Recognition quality | Unmeasured (no references). Station promos and OCR missing spaces («عاجلبدء») reach the alert gates. |
| Monitoring / labeling | N-02 (backlog, silence and failure share one label), N-08 (soak tool blind to sleep), P-11 (`active_alerts` 660/660), P-13 (gaps invisible) |

---

## 4. Findings

No **Critical** finding was confirmed: no corruption, no security breach, no unrecoverable state.

### High

**N-01: Host sleep silently removes about 9 h of coverage; sleep time is booked as ASR loss**
- **Where:**
  - `scripts/start-live.sh:63-72`: no sleep assertion.
  - `ingest.py:81-109`: `ASRLag` trusts the reported value.
  - `runtime.py:166-189`: gap estimate = reported lag.
  - WLK `audio_processor.py:428-431`: `time()` arithmetic.
- **Evidence:** §3.3; characterization `test_wall_clock_jump_reported_by_server_becomes_estimated_loss` (passes).
- **Impact:** a morning brief or search over the night covers about 5% of it, and nothing tells the reader. Thermal emergencies on a closed laptop are also a hardware-safety concern.
- **Fix:**
  - Hold a `caffeinate -dimsu -w <api pid>` assertion in `make live`, and disclose it.
  - Detect sleep: compare `time.time()` against `time.monotonic()` (monotonic stops during macOS sleep). Record one `host_sleep` gap per channel with measured bounds.
  - Clamp any lag-limit estimate to the session's elapsed monotonic time.

**N-02: ASR health conflates real backlog, server silence and backend failure**
- **Where:**
  - `ingest.py:108-109`: silence beyond 15 s counts as lag.
  - `ingest.py:421-430`: every case becomes `asr_lag_limit`.
  - WLK pushes only on change (`audio_processor.py:968-975`).
- **Evidence:** §3.4; characterization `test_server_silence_is_booked_as_backlog` (a server that never reports backlog still triggers a 90 s "loss" after 105 s of no change).
- **Impact:** the operator cannot tell "GPU too slow", "no speech on air" and "decoder dead" apart. A 47-minute collapse looked like routine resets.
- **Fix:**
  - Classify each reset by cause: `backlog` (reported ≥ ceiling), `silent` (no message), or `no_output` (PCM flowing and no new lines for N s).
  - After 3 resets in 10 min, set `asr_status=degraded` and raise an operator alert.

**P-09 (re-confirmed at larger scale): OCR worker churn on the deployed code**
- **Evidence:** 428 OCR model loads in 13.6 h (`ocr_model_loads_per_hour.txt`): 10–36/h awake, up to 61/h during dark wakes.
- **Status:** the fix (`ingest.py:270-327, 454-504`; `ocr_worker.py:42-55`; 8 tests) is in the repository but **never ran live**.
- **Unverifiable:** crash reports. The 11 `Python-*.ips` files cited on 17 Nov are no longer in `~/Library/Logs/DiagnosticReports`, so the absence of new reports proves nothing.

**P-07 (re-confirmed on real data): briefs sample a few minutes and the UI implies the whole window**
- **Where:** `store.py:125-163`; `frontend/src/App.tsx:1405-1418` shows `window_start → window_end`, not the sample span.
- **Evidence:** on live data, the 24 h brief took 80 samples from **6 distinct minutes**. The 4 h brief used 16 minutes; the 1 h brief used 17.
- **Fix:** midpoint/reservoir pick per bucket over the populated span; show first–last sample, buckets with no sample, and gap totals.

### Medium

**N-03: Spike detector forgets active topics after about 1.9 minutes**
- **Where:** `mechanics.py:117-122`: FIFO eviction by creation order, cap 128.
- **Evidence:** on 21,105 live observations, a new topic was created every 0.9 s. The documented 12-window (6 min) baseline is unreachable; all 9 spikes fired on baselines of 0.3–2.3. Reproduction: `test_active_spike_topic_survives_unrelated_topic_churn` (xfail).
- **Fix:** LRU eviction by last-seen; a higher similarity threshold or per-language centroids; disclose the baseline length in the alert.

**N-04: Search horizons are far shorter than documented**
- **Evidence:** at the live rate, the newest 10,000 rows (the lexical window) span **1.77–1.89 h**, and the hot FAISS tier holds 4,000 rows (**≈41 min**), while the README says "2 hours".
- **Impact:** an exact Arabic name more than about 2 h old is reachable only through semantic Qdrant search, which is weak on names. Characterization: `test_lexical_window_is_row_bounded_not_time_bounded`.
- **Fix:** SQLite FTS5 over normalized text (one virtual table, triggers); report each lane's horizon in search responses.

**N-05: Arabic lexical matching ignores clitics**
- **Where:** `store.py:212`, `text.py:4-6`.
- **Evidence:** «الكويت» does not match «بالكويت» (`test_lexical_matches_arabic_prefixed_forms`, xfail). Arabic-Indic digits are also not folded.
- **Fix:** light prefix stripping (و ف ب ل ك ال), ة→ه, digit folding; apply it identically to query and text.

**N-06 and P-10: Keyword gates match substrings; cooldown keys on exact text**
- **Where:** `mechanics.py:47-51` and `mechanics.py:70`.
- **Evidence:** `oil` fires on "turmoil" (`test_english_keyword_requires_word_boundary`); three one-character promo variants raise 3 criticals (`test_promo_variants_share_one_cooldown`); 11 live criticals from one promo.
- **Fix:** token-boundary matching for keyword rules; fuzzy cooldown key; per-channel suppression list for station chrome.

**N-08: The documented soak tool cannot prove the open acceptance criteria**
- **Where:** `scripts/verify_live.py:19,28` uses `time.monotonic()`, which on macOS stops during sleep, and omits `ocr_worker_*`, `last_frame_error_type`, gaps and WebSocket.
- **Impact:** a "2-hour soak" across a lid-closed night would report success. P-09 acceptance (distinct OCR PIDs) is unmeasurable.
- **Mitigation provided:** `2026-11-18-artifacts/soak_sampler.py`.

**Still open from 17 Nov (re-run in T6; code unchanged):**
- P-01: poison outbox row (`store.py:341-370`).
- P-02: "U.S." citation split (`briefs.py:84`).
- P-03: egress trusts the provider label (`runtime.py:286-292`).
- P-04: raw feed configuration in snapshot/WebSocket (`runtime.py:445-455`).
- P-12: lexical lane bypasses the cosine floor (`runtime.py:245-248`).
- P-13: gaps never shown; `App.tsx` never calls `/api/gaps`.

### Low

- **N-07:** a clean speech-session end (publisher EOF → `ready_to_stop`) records no gap (`ingest.py:471-473`); `test_clean_asr_session_end_records_coverage_gap` (xfail). The final minutes before the reboot show exactly this pattern in `asr-ar.log`.
- **P-05** (spawn-anchored ASR clock, `ingest.py:157`) and **P-06** (non-dict message tears down the session, `ingest.py:198-199`) are still open.
- **P-11:** `active_alerts` = 660 of 660 alerts unacknowledged (`store.py:170-174`), with no ageing and no bulk acknowledge.
- **P-14:** Playwright defaults to the live :8000 (`frontend/playwright.config.ts`), and `command-center.spec.ts:52,66` writes into `docs/`.
- **N-09:** the default `allowed_hosts` contains `testserver` (`config.py:13`); T9 accepted it.
- **F-09 (partial):** `docs/SECONDARY_INGESTION.md:103` and `docs/PRIMARY_INGESTION.md:41` still show `uv sync --frozen --extra …`. That is an exact sync, which removes the other installed extras (semantic/perception) from the live `.venv`.
- **N-10:** disk guard and ASR interact. When the reserve is hit, `deliver()` loops (`ingest.py:507-516`) until the lag ceiling fires, so a storage pause is booked as ASR lag. This is a hypothesis from code reading; untested.

---

## 5. Remediation verdicts

| Item | Verdict | Evidence |
|---|---|---|
| F-01 Arabic lag ceiling | **Verified (bound holds); cost under-reported** | Phase A: every reset ≤ 90.6 s, delay p95 55–72 s. Loss labeling is wrong under sleep and failure (N-01, N-02). |
| F-02 Brief scope | **Partially verified** | Spans channels, but 6 distinct minutes per 24 h (P-07). |
| F-03 Spike semantics | **Partially verified** | Arrival clock fine; topic memory about 1.9 min (N-03). |
| F-04 OCR repetition | **Partially verified** | Old-audit test now XPASS; on live data 16–37% of OCR texts recur within 1 h on 4 channels (15-min TTL plus worker respawns). |
| F-05 Storage | **Partially verified** | DV1 vectors; DB 256 MB after the session; no retention policy; disk pressure currently relieved externally. |
| F-06 Status freshness | **Partially verified** | Republished each tick; `connected` stays during a reset storm (N-02). |
| F-07 Citations | **Partially verified** | P-02 open; never exercised live after the restart. |
| F-08 Cloud egress | **Verified (opt-in)** | 0 briefs in 13.6 h live; T4 isolated. P-03 bypass still open. |
| F-09 Setup docs | **Partially verified** | README fixed; two docs still exact-sync. |
| F-10 Search | **Partially verified** | Stopword fix XPASS; P-12, N-04, N-05 open. |
| F-11 Host / ingest | **Verified** | T9 probes; old tests XPASS. Minor: N-09. |
| F-12 Speaker / confidence | **Verified** | 0 non-null in 25,744 session rows. |
| F-13 Native crash isolation | **Not resolved** | Isolation works (the API survived, workers were replaced). The native fault itself recurs: 3 SIGSEGV in `libphi_core` (ElementwiseAdd, im2col/Conv) at 08:34 and 09:04 (§12.4). |
| F-14 Unchanged-frame gate | **Unproven (this pass)** | Counters are not persisted; no live snapshot available. |
| F-15 Player recovery | **Unproven (this pass)** | Requires live MediaMTX. |
| F-16 Counters | **Regressed / misleading** | P-11: 660/660. |
| F-17 Log rotation | **Verified** | `asr-*.log` rotated at 10 MiB (`.1`, `.2`); `rotate_log.py:9` sets 10 MiB × 3 backups. |
| P-08/P-09 OCR lifecycle fix | **Verified for churn; native crashes remain** | §12: 6 distinct OCR PIDs in 2 h, 0 restarts despite 15 video failures. After the soak (§12.4), 3 OCR workers segfaulted **mid-inference** inside Paddle CPU kernels, and replacements started as designed. The Ctrl-C shutdown path was never exercised. |
| P-15 Skip counter | **Partially verified** | Initialised to 0 (`ingest.py:67`); ticker-region gate not implemented. |
| P-01 to P-07, P-10 to P-14 | **Open** | T6 and T8 reproductions; code unchanged. |

---

## 6. Prioritized engineering backlog

| # | Item | Findings | Effort | Expected benefit |
|---|---|---|---|---|
| 1 | Awake two-hour soak of the current code with `soak_sampler.py` (operator restart) | P-09 acceptance, N-08 | XS (ops) | Proves or refutes the OCR fix; first clean post-fix baseline |
| 2 | Coverage-health truthfulness: sleep assertion and detection, reset-cause classification, degraded state and alert, clean-end gaps, estimates for exception gaps | N-01, N-02, N-07, P-13 (backend half) | M (2–3 d) | Operators and briefs stop presenting missing coverage as silence |
| 3 | Brief integrity: populated-span sampling, sample-span and gap disclosure, abbreviation-safe citations | P-07, P-02 | S–M | The executive output represents its window |
| 4 | Outbox quarantine (P-01); egress by host (P-03); public channel DTO (P-04) | P-01, P-03, P-04 | S | Archive cannot stall; policy cannot be mislabelled |
| 5 | Alert hygiene: word-boundary keywords, fuzzy cooldown, chrome suppression, ageing count plus bulk acknowledge, LRU spike topics | N-03, N-06, P-10, P-11 | S–M | Fewer false criticals; spikes mean what the docs say |
| 6 | Search: FTS5 lexical index with Arabic light stemming; fused-score floor; per-lane horizons in responses | N-04, N-05, P-12 | M | Exact names searchable beyond 2 h; no unrelated hits |
| 7 | Hygiene: P-05, P-06, P-14, N-09, F-09 docs | — | XS each | Correct timestamps; safer tests and docs |

---

## 7. Recommended capabilities (at most five)

### C1: Coverage ledger with completeness on every brief, search and export (**build now**)

1. **Problem and workflow.** At 07:00 the minister's office asks "what did Al Arabiya say overnight?". Today search returns a handful of lines and the brief cites them. In reality the host slept 9 h. With C1, the answer carries: "Al Arabiya speech coverage 18:54–03:51: 6% (host asleep); OCR 9%".
2. **Why existing features fall short.** Gap rows exist, but sleep is not a gap, exception gaps have no duration, and nothing aggregates or displays them (P-13, N-01, N-02).
3. **Smallest version.**
   - Per channel and modality, a 1-minute bitmap derived from evidence presence plus gap records.
   - A `/api/coverage?from&to&channel` endpoint.
   - A strip on each tile.
   - One coverage line appended to every brief, plus a JSON export (brief + cited evidence + coverage).
4. **LLM?** No. Deterministic.
5. **Data and dependencies.** Existing evidence timestamps and gaps, plus N-01 sleep records. No new models or permissions.
6. **Cost.** One indexed range query, about 1–5 ms per channel-day. Storage: 1,440 bits per channel per day if materialized (negligible).
7. **Risks and acceptance.**
   - Risk: a silent broadcast is shown as a gap. Mitigation: label evidence absence separately from recorded interruptions.
   - Accept when replaying 17–18 Nov reproduces §3.1 within ±2%.
   - Accept when every brief carries a coverage line.
   - Accept when the export reproduces the cited IDs.
8. **Verdict:** **now** (with backlog item 2).

### C2: Capacity-aware ASR channel priority (**build after a clean soak**)

1. **Problem.** In Phase C all six channels lost 36–78% of ASR minutes equally. An analyst covering a Kuwait story would rather keep two channels whole.
2. **Why existing features fall short.** The ceiling bounds staleness but spreads the loss blindly.
3. **Smallest version.** A per-feed `priority`. When at least 3 channels reset within 10 min, pause ASR on the lowest-priority channels (OCR continues) and record `asr_paused` gaps. Use hysteresis with a 5-minute minimum dwell.
4. **LLM?** No.
5. **Dependencies.** N-02's cause classification, so failure is not mistaken for capacity.
6. **Cost.** Reduces GPU load; no memory added.
7. **Risks and acceptance.**
   - Risk: flapping.
   - Accept at ≥98% ASR minute-presence on priority channels over a 1 h loaded run.
   - Accept when paused channels show explicit gaps.
8. **Verdict:** **later**, once item 1's soak gives a clean capacity baseline.

### C3: Traceable brief export (**build now, as part of C1**)

Problem: briefs leave the system as text whose citations point at a local UUID. The smallest version is a Markdown/JSON bundle with the brief text, every cited TDO (channel, UTC time, modality, text, source), the coverage line, the provider (local or cloud) and the input sample IDs. It is deterministic, costs about 10 KB per brief, and its only risk is exporting evidence beyond the host, so it must be an explicit operator action. Accept when every bullet in the export resolves to an included TDO.

### C4: Story clustering and near-duplicate suppression (**later**)

This would solve OCR recurrence (16–37%) and identical cross-channel headlines crowding briefs and search. It is deterministic, reusing MiniLM vectors. It requires N-03's LRU index and a labelled pair set of about 200 pairs for the threshold. Do it after C1.

### C5: Analyst verification and correction (**later**)

Name errors in ASR keep being cited. It requires authentication; no `DIRA_API_TOKEN` is configured today. Defer until identity exists.

---

## 8. Do not build yet

| Proposal | Why not now |
|---|---|
| Claim-level contradiction tracking | Needs an LLM. Arabic ASR loses 6–64% of minutes depending on host state, and WER is unmeasured, so "contradictions" would mostly be coverage holes. |
| Arabic/Kuwait NER models | Another resident model on a host that already throttles; name accuracy is unmeasured. Light lexical normalization (N-05) is the cheaper first step. |
| Diarization and visual detection | GPU is the scarce resource (Phase C). Speaker labels are deliberately hidden. |
| New hardware purchase | Phase A shows the current load mostly keeps up when awake. Measure the fixed OCR lifecycle on a host that cannot sleep before sizing hardware. |
| Automatic cloud briefs | The opt-in held; P-03 must close first. |
| **Simplify:** dual "estimated loss" counters | `asr_skipped_seconds` is a lifetime, persisted sum shown on tiles without a time base (`runtime.py:128-136`). Replace it with C1's windowed coverage rather than adding more counters. |
| **Simplify:** Aurelio router | On the search path but with no measured benefit and an extra dependency. Evaluate on 20 labelled queries against the anchor router; remove it if it does not win. |

---

## 9. The three highest-value next actions

1. **Run the awake two-hour soak** of the current code. The operator restarts `make live` with the lid open and sleep prevented, then runs `soak_sampler.py --wall-seconds 7200`.
   - Accept: distinct OCR PIDs ≤ 6 + real worker crashes.
   - Accept: no new `Python-*.ips` after Ctrl-C.
   - Record: per-channel ASR minute-presence.
2. **Make coverage health truthful** (backlog item 2, prompt below).
3. **Fix brief integrity and show coverage** (P-07, P-02, C1 brief line).

---

## 10. Implementation prompt (action 2)

```text
Task: Make Dira's speech-coverage health truthful: prevent/detect host sleep, classify ASR resets by cause,
surface degraded ASR, and record every coverage interruption with honest bounds.

Context (verified in docs/audits/2026-11-18-independent-audit.md, findings N-01, N-02, N-07):
- Live 17-18 Nov: lid closed 18:54-03:51 -> ~9 h near-zero output; WhisperLiveKit's remaining_time_transcription
  is wall-clock based (whisperlivekit/audio_processor.py:428-431) so after a dark wake it reports the sleep
  (up to 1061.6 s) and Dira books it as asr_lag_limit "estimated loss" (runtime.py:166-189, ingest.py:421-430).
- WLK pushes only when its response changes (audio_processor.py:968-975). ASRLag counts >15 s of server silence as
  lag (ingest.py:108-109), so silence, backend failure ("ASR backend produced no output") and real backlog all
  become asr_lag_limit. Post-wake: 121 resets in 47 min, ASR present in 22-64% of minutes, tiles said connected.
- A clean session end (EOF -> ready_to_stop) records no gap (ingest.py:471-473).
- scripts/start-live.sh holds no sleep assertion.

Do:
1. ASRLagExceeded carries cause in {"backlog","silent","wall_clock_jump"}: backlog = server-reported value >=
   ceiling; silent = reported < ceiling but silence term pushed it over; wall_clock_jump = reported value grew by
   more than the monotonic time elapsed since the previous report + 5 s. Estimated loss = min(reported or synthetic
   lag, monotonic seconds since session start). Gap reason = f"asr_{cause}". Keep the 90 s ceiling behaviour.
2. Sleep detection in Runtime.metrics_loop: if (time.time() delta) - (time.monotonic() delta) > 10 s, record one
   gap per channel with reason "host_sleep", start/end from wall clock, bounds_estimated=False, and publish it.
3. Degraded ASR: if a channel has >= 3 asr_* resets within 600 s, set asr_status="degraded" and raise one warning
   Alert (kind "keyword" is wrong; add kind "health" to the Alert Literal) with a 30-min cooldown per channel.
   Clear when 10 min pass without a reset.
4. Record a gap ("asr_session_end") when speech_session returns normally; estimate = None.
5. scripts/start-live.sh: after starting uvicorn, run `caffeinate -dimsu -w <api pid> &` and add it to children;
   print one line saying sleep is prevented while Dira runs.

Tests first (TDD, isolated: tmp_path, fake WLK websocket servers on loopback, no live services):
- Move docs/audits/2026-11-18-artifacts/test_2026_11_18_findings.py::test_clean_asr_session_end_records_coverage_gap
  into tests/ without xfail and make it pass.
- Silent server (one message with zeros, then nothing) -> cause "silent", gap reason "asr_silent".
- Reported 1061.6 after 1 s of monotonic time -> cause "wall_clock_jump", estimate <= session monotonic age.
- Reported 120 growing ~1 s/s -> cause "backlog".
- metrics_loop with monkeypatched time.time jump of 900 s -> one host_sleep gap per channel.
- Three resets in 600 s -> asr_status degraded + exactly one health alert; recovery clears it.
Update the two characterization tests in the artifact file to the new contract.

Constraints: do not change OCR, numerical thread settings, or the 90 s default; no Paddle in the API process; no
dependency sync; do not restart the live installation; run `.venv/bin/python -m pytest -q` and ruff on changed
files. Acceptance on live (operator restart): during a lid-open 2 h soak with soak_sampler.py, zero
wall_clock_jump gaps, sleep_samples == 0, and any asr_backlog gaps <= 90.6 s each.
```

---

## 11. Limitations

- **The two-hour soak was completed after the operator restarted the stack** (§12). It covers one load condition on a heavily loaded shared host; it is not a production-readiness certification. The 13.6 h retrospective ran pre-lifecycle code and was dominated by host sleep.
- **Recognition accuracy is not measured** (no reference transcripts or labelled frames).
- **Delay figures** are adapter-relative (`received_at − end`), not publisher-to-screen latency.
- **Phase C cause is unproven** (thermal or contention).
- **Crash-report history is incomplete** on disk.
- **Qdrant could not be inspected** (Docker down).
- **Briefs were never generated live** after the restart, so citation behaviour against a real model is unexercised.

---

## خلاصة (عربي)

**ما اختبرته فعلاً:**
- 110 اختباراً خلفياً، و4 اختبارات واجهة، و4 اختبارات متصفح في بيئة معزولة دون أي اتصال سحابي.
- اختبارات الأمان على منفذ معزول.
- 8 اختبارات جديدة: 5 تثبت عيوباً جديدة أو قائمة، و3 توثّق السلوك الحالي.
- تحليل للقراءة فقط لنسخة من قاعدة الأدلة الحية (13.6 ساعة)، مع سجلات الخدمات وسجل طاقة الجهاز.
- إعادة تشغيل كاشف الطفرات على البيانات الحقيقية، فطابقت النتيجة التنبيهات الحية التسعة تماماً.

**ما اكتشفته:**
- ديرة جيدة حين يكون الجهاز مستيقظاً: تغطية صوتية 91–96% من الدقائق.
- لا تحمي نفسها من سكون الجهاز ولا تكشفه، ولا تميّز تعطل التفريغ عن تأخره.
- أعاد الإصدار المُشغَّل تحميل نموذج OCR 428 مرة.
- الموجز اليومي يأخذ عيّنته من 6 دقائق.
- ذاكرة كاشف الطفرات دقيقتان فقط.
- البحث النصي لا يرى أبعد من ساعتين تقريباً، ولا يفهم «بالكويت» حين تبحث عن «الكويت».

**ما بقي غير مؤكد:**
- استقرار ساعتين بالإصلاحات الأخيرة، فهي لم تُشغَّل حياً بعد.
- سبب انهيار التفريغ بعد الاستيقاظ.
- دقة التعرف على الكلام والنص.
- سلوك الموجز السحابي حياً.
- استعادة الفيديو بعد انقطاع طويل.

**بماذا نبدأ ولماذا:**
1. تشغيل حي لساعتين والجهاز مستيقظ، لأنه رخيص ويحسم إصلاح OCR.
2. صدق مؤشرات التغطية، لأن أخطر ما رأيته ليس الفقد نفسه، بل أن الفقد لا يظهر لصاحب القرار.
3. نزاهة الموجز، لأنه المنتج الذي يقرأه التنفيذي.

---

## 12. Live two-hour soak (2026-11-18, 06:21–08:21 Kuwait; observed)

**Setup**
- The operator restarted `make live` at about 06:15. The API was healthy at 06:20:29 and ran the current commit, including the OCR-lifecycle fix.
- `soak_sampler.py` ran for 7,204 s of awake wall-clock time, polling `/api/snapshot` and `/api/gaps` every 10 s, with a WebSocket probe every 30 samples.
- In parallel, the 17 Nov `resource_sampler.py` ran (`ps`/`lsof`/`statvfs`/crash reports every 60 s).
- Both ran under `caffeinate -i`. Both are read-only.
- Artifacts: `soak-7200.json`, `soak-7200.analysis.txt`, `resources-7800.json`, `analyze_soak.py`.

### 12.1 Results

| Metric | Result |
|---|---|
| Duration | **7,204 s awake**; 711 samples; **0 poller errors**; **0 host-sleep samples** |
| OCR lifecycle (P-08/P-09 acceptance) | **1 distinct OCR worker PID per channel (6 total)**; `ocr_worker_restarts` = 0 everywhere, although frame sessions failed 15× (`ExceptionGroup`) and restarted independently. `ps` confirms 6 distinct OCR PIDs. **Criterion met.** |
| Crash reports | **0 new `Python-*.ips`** during the run |
| Evidence | +8,223 (4,109/h; 5,254/h on 17 Nov); outbox pending median 1, max 17, final 0 |
| Archive | Qdrant `degraded` in 35 of 711 samples (4.9%), with short `ResponseHandlingException` bursts; recovered and drained each time |
| Ingest p95 | Median 71.5 ms, max 179 ms (17 Nov: 35.7 ms median). Ingest processing only, not end-to-end. |
| API | `/api/snapshot` median 34 ms, p95 124 ms, max 691 ms; `/api/gaps` median 12 ms; **WebSocket 24/24 probes OK**, median 40 ms, max 244 ms; 0 WebSocket resyncs |
| Resources | API: RSS ~1.2 GB, 318–331 file descriptors (no leak). ASR: 2 processes, ~2.1 GB. OCR: 6 processes, ~6.1 GB, **CPU median 437% (≈4.4 cores)**. FFmpeg: 12 processes. DB: 255.7 → 279.4 MB (~12 MB/h). |
| Host | **Load average 43–72 on 12 cores** at the end. The Docker VM used ~90% CPU and Docker's backend ~55%. Other user applications were active. |

**Per channel**

| Channel | Connected | ASR lag median / p95 / max (s) | Lag-limit resets | Estimated ASR loss | OCR restarts |
|---|---|---|---|---|---|
| aljazeera | 96.8% | 29 / 80 / 90 | 29 | 2,614 s (**36.3%**) | 0 |
| alarabiya | 99.4% | 29 / 78 / 90 | 17 | 1,532 s (21.3%) | 0 |
| alhadath | 99.0% | 34 / 81 / 90 | 26 | 2,343 s (32.5%) | 0 |
| sky_arabia | 98.0% | 31 / 82 / 90 | 32 | 2,883 s (**40.0%**) | 0 |
| asharq | 98.3% | 26 / 79 / 90 | 22 | 1,983 s (27.5%) | 0 |
| sky_uk | 96.8% | 8 / 65 / 90 | 9 | 811 s (11.3%) | 0 |

### 12.2 Interpretation

- **Verified:** the OCR lifecycle fix holds under live failures. The respawn storm (428 loads in 13.6 h on old code) is gone.
- **New concern (High): ASR coverage got worse.** Estimated Arabic loss is 21–40% per channel, against 6.3% in the 17 Nov awake phase.
  - **Real backlog, observed:** WLK's own Arabic log has 292 entries ≥ 80 s and 1,503 entries ≥ 60 s in this run.
  - **English resets mostly lack backlog evidence:** 9 resets, but only one WLK entry ≥ 80 s. This fits N-02 (silence or stall booked as backlog).
- **Hypothesis (unproven):** CPU oversubscription. Long-lived OCR workers now infer continuously (≈4.4 cores; previously they paused while reloading). Together with the Docker VM and other user workloads, this pushed the host to load 43–72. The windowed Arabic ASR needs CPU alongside the GPU, so its backlog grew.
- **What would settle it:** an A/B run of 30 min with OCR at 2 fps vs 1 fps (or OCR disabled on two channels), comparing WLK lag and resets, on a host with no other heavy applications.
- **Consequence for priorities:** backlog item 2 (cause-classified resets) and capacity-aware prioritization (C2) move up. Add **an OCR CPU budget**: a frame-rate cap per channel, and the existing unchanged-frame gate on the ticker region (P-15). Hardware sizing (Mac mini question) must use this run's numbers, not 17 Nov's.
- **Still pending:** the Ctrl-C shutdown check (no new crash reports after `make live` stops).

### 12.3 Updated next actions

1. **Operator:** stop with Ctrl-C, then confirm no new `Python-*.ips` (closes P-09 / F-13).
2. **A/B capacity run (30 min × 2):** OCR load vs ASR backlog on a quiet host. This decides between an OCR CPU budget and more hardware.
3. **Implement the §10 prompt** (coverage-health truthfulness), unchanged.

### خلاصة الاختبار الحي (عربي)

**ما ثبت:**
- اكتمل اختبار الساعتين دون أي خطأ، ودون سكون للجهاز.
- إصلاح عمّال OCR **نجح فعلياً**: عامل واحد لكل قناة، دون إعادة تشغيل، ودون انهيارات.
- الواجهة البرمجية والاتصال الحي (WebSocket) سليمان.

**المشكلة الجديدة:**
- التفريغ العربي فقد تقديرياً **21–40%** من التغطية، وكان الجهاز مُثقلاً جداً.
- الأرجح، وهو غير مثبت، أن عمّال OCR الدائمين باتوا يستهلكون نحو 4.4 نواة باستمرار، فزاحموا التفريغ الصوتي.

**التالي:** قياس مقارن قصير لحِمل OCR، ثم وضع ميزانية معالج لـOCR قبل التفكير في جهاز جديد.

### 12.4 After the soak: native crashes, host sleep and a kernel panic (observed)

| Time | Event | Source |
|---|---|---|
| 08:21 | Soak ends. The resource sampler ends at 08:31, which releases its `caffeinate -i` assertion. | sampler output |
| 08:33–08:36 | Host-wide stall: every feed's speech `TimeoutError` and video `ExceptionGroup`, Qdrant unavailable | `api-live.log` |
| **08:34:36** | **OCR worker pid 11816 (started 06:20) SIGSEGV mid-inference**: main thread in `phi::funcs::ElementwiseCompute<AddFunctor<float>>` (`libphi_core`), via `AnalysisPredictor::ZeroCopyRun`. Paddle's glog failure handler re-raised the signal. | `Python-2026-11-18-083436.ips` |
| 08:54:05 | Host enters "Low Power Sleep". Repeated dark wakes follow; **"Dark Wake Thermal Emergency" at 09:23 and 09:39** | `pmset -g log` |
| **09:04:24** | Host is in "DarkWake from Hibernate" (09:04:13). **Two replacement OCR workers (started 08:44 and 08:46) SIGSEGV simultaneously** in `phi::funcs::im2col_common<float>` / `ConvKernelImpl` | `Python-2026-11-18-090428(.000).ips` |
| 10:35:17 | Last evidence row written; afterwards only dark-wake failure logs | DB copy, log |
| 12:32 | Lid opened for 10 s, then clamshell sleep again | `pmset` |
| ~12:44–12:45 | **Kernel panic**: `busy timeout[1], (60s): 'IOMediaBSDClient'`, panicked task `watchdogd`. Reboot at 12:45. | `panic-full-2026-11-18-131659.0002.panic` |
| 13:18 | No Dira processes remain; ports free. DB copy `quick_check` = ok; 55,379 rows; **0 pending**. | audit check |

**Interpretation**
- **The Ctrl-C shutdown check was not performed.** No graceful shutdown was logged; the host panicked during sleep. P-09/F-13 shutdown acceptance stays open.
- **The OCR native fault persists** (F-13 not resolved). It happened in compute kernels while running, not at exit, so the `os._exit` change cannot address it. Two of three crashes coincided with a wake from hibernate, and one with a host-wide stall.
  - Hypothesis: memory or thread-pool corruption under resource starvation, or the two-`libomp` conflict already documented. Unproven.
  - Containment worked: the API survived and workers were replaced after backoff.
- **The kernel panic is an OS/storage-driver event** (`IOMediaBSDClient` busy for 60 s while sleeping). Dira's continuous disk and Docker I/O may have contributed; **causality is not established**.
- **Durability verified again:** two abrupt terminations in one day, and SQLite is intact with an empty outbox.
- **Operational rule this confirms:** the host must not be allowed to sleep while Dira runs. A laptop with its lid closed is not a valid deployment: three thermal emergencies and one panic in two sleep episodes. Reinforces N-01 (sleep assertion in `make live`) and the move to an always-on host.

**Additional next actions**
- Collect OCR crash diagnostics: record `ocr_worker_restarts` with timestamps and exit signals in metrics.
- Test a single-threaded Paddle inference setting (already `cpu_threads=1`; also check `FLAGS_` thread pools) in an isolated replay of captured ticker frames under CPU stress. Do not reproduce on the live host.

---

## 13. Remediation status: coverage-health truthfulness (§10 prompt), implemented 2026-11-18 afternoon

Implemented per the §10 prompt. **Not yet verified live** (needs an operator restart). Nothing committed.

| Change | Where |
|---|---|
| `ASRLagExceeded` carries `cause` (`backlog` / `silent` / `wall_clock_jump`) and an `estimate` bounded by the session's monotonic age. `ASRLag` flags a jump when the reported value grows more than 5 s faster than monotonic time. | `backend/dira/ingest.py` (`ASRLagExceeded`, `ASRLag.cause`, `check_lag`) |
| Gap reason is `asr_<cause>`; `asr_skipped_seconds` adds the bounded estimate; feeds expose `asr_last_reset_cause` | `speech_session` |
| **Degraded ASR:** ≥3 resets within 600 s sets `asr_degraded` and `asr_status=degraded` and raises **one** `health` warning alert per 30 min; it clears after 600 s without a reset | `ASRHealth`, `asr_recovered`; `Runtime.health_alert` |
| Clean speech-session end records an `asr_session_end` gap | `supervise_feed.speech` |
| **Host sleep detection:** each metrics tick compares wall-clock and monotonic deltas; more than 10 s asleep records one `host_sleep` gap per non-simulated channel with `bounds_estimated=false` | `Runtime.check_host_sleep`, `metrics_loop` |
| `Alert.tdo_id` is optional and `kind` allows `health`; the UI ignores evidence clicks for health alerts and shows ⚠ plus the last cause on the lag badge | `backend/dira/models.py`, `frontend/src/App.tsx`, `frontend/src/types.ts` |
| `make live` holds `caffeinate -dims -w <api pid>` and says so. **Limit:** closing a laptop lid without an external display still sleeps; `host_sleep` gaps then make it visible. | `scripts/start-live.sh` |

**Verification**
- New `tests/test_coverage_health.py`: 10 tests, written first and failing before the change (collection error on missing `ASRHealth`).
- **Full backend suite 120 passed** (110 earlier + 10 new), 14.0 s.
- Frontend: 4/4 state tests; `npm run build` (tsc + vite) passed and rebuilt `frontend/dist`.
- `bash -n scripts/start-live.sh` passed.
- Ruff (isolated, project line length) reports no new findings in changed production files compared with HEAD.
- Audit artifact tests updated to the new contract: N-02 characterizations now assert causes; N-07 is a passing regression. 4 xfails remain open: N-03, N-05, N-06, P-10.

**Live acceptance (to do after restart):** lid-open 2 h soak with `soak_sampler.py`.
- Gap reasons split into `asr_backlog`, `asr_silent` and `asr_wall_clock_jump`.
- Zero `asr_wall_clock_jump` and `host_sleep` gaps while awake.
- Any `health` alert matches a period of repeated resets.

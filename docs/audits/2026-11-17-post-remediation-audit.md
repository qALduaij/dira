# Dira: Post-Remediation Adversarial Audit

**Date:** 2026-11-17, 15:21–17:30 Asia/Kuwait.
**Scope:** the state after `2026-11-17-remediation.md`. Tested against the running live installation (API restarted at 15:00:59) and against isolated fixtures.
**Mode:** audit only.
- No production code was changed.
- No restart, commit, deletion, paid call or `.env` disclosure.
- One opt-in browser regression test was added: `frontend/tests/live-player-prolonged.spec.ts`.
- The two `docs/dira-*.png` screenshots that Playwright overwrote were restored from backup.

**Artifacts:** [`2026-11-17-post-remediation-artifacts/`](2026-11-17-post-remediation-artifacts/) holds the tests, samplers, soak JSON, analysis script and search evidence.

**Conventions:**
- Times are Asia/Kuwait (UTC+3) unless marked UTC.
- **Observed** = measured in this audit.
- **Hypothesis** = plausible but not proven.
- **Recommendation** = proposed change.

---

## الملخص التنفيذي (عربي)

**الحكم العام:** الإصلاحات حسّنت النظام فعلاً، لكنه ليس جاهزاً للإنتاج بعد. خلال ساعتين من التشغيل الحي:
- بقيت القنوات الست متصلة بنسبة **91–98%** من الوقت.
- لم يتجاوز تأخر التفريغ الصوتي العربي سقف الـ90 ثانية الجديد (كان سابقاً 674 ثانية).
- لم تتراكم طوابير الأرشفة (الحد الأقصى 7 ثم صفر).

**الثمن:** التفريغ الصوتي العربي يفقد تقديرياً **5–11%** من تغطية كل قناة. السبب أن النظام يُسقط الصوت المتأخر ليبقى «حياً»، وهذه الفجوات لا تظهر للمحلل في الواجهة.

**الحادثة:** بين 15:28 و15:40 اختنق الجهاز بالكامل (حِمل ≈ 397، والذاكرة البديلة ممتلئة تقريباً):
- انقطعت القنوات وقاعدة Qdrant.
- توقفت الأدلة نحو 4 دقائق.
- سُجّل **11 انهياراً** لعمليات OCR عند إغلاقها.
- تعافى النظام وحده، ولم يحدث أي انهيار بعد 15:33.

تزامنت الحادثة مع اختبارات الفيديو في المتصفح التي أجريتُها، لذلك لم تُثبت السببية. توقفت فوراً عن أي اختبار فيديو على النظام الحي.

**أهم ما اكتُشف:**
1. **دورة حياة عمّال OCR مرتبطة بجلسة الصوت.** أي عطل في الصوت يقتل عامل OCR (≈1.2 غيغابايت) ويعيد تحميله. ظهر **48 عاملاً مختلفاً** خلال ساعتين بدلاً من 6، والإغلاق ينتهي أحياناً بانهيار.
2. **سجل واحد تالف يوقف أرشفة Qdrant إلى الأبد** (P-01).
3. **عيّنة الموجزات «الطبقية» تتكدس في دقائق قليلة** عندما تكون البيانات كثيفة (P-07). كما أن اختصاراً مثل «U.S.» يُسقط موجزاً صحيحاً (P-02).
4. **سياسة منع الإرسال السحابي تعتمد على تسمية المزوّد لا على عنوان الخادم** (P-03). ولقطة القنوات تنشر عناوين البث كاملة (P-04).
5. **تنبيهات «حرجة» كاذبة:** عبارة ترويجية للقناة («...للأخبار العاجلة») أطلقت 7 تنبيهات حرجة، ولم يوقفها التبريد لأن نصها يختلف بحرف.

**أول ثلاث خطوات:**
1. فصل دورة حياة OCR عن جلسة الصوت، مع إغلاق آمن.
2. ميزانية تخزين وعزل السجلات التالفة.
3. إصلاح عيّنة الموجزات وإظهار الفجوات للمحلل.

---

## 1. Test and results matrix

All commands ran from the repository root. "Isolated" means:
- `tmp_path` storage;
- loopback or mocked endpoints;
- the operator `.env` removed by the test fixture.

| # | Test | Command / method | Outcome |
|---|---|---|---|
| T1 | Backend suite (isolated) | `.venv/bin/python -m pytest -q` | **102 passed**, 16.5 s |
| T2 | Frontend state tests | project frontend unit-test script | **4/4 passed** |
| T3 | Isolated Chrome acceptance, including the cloud-disclosure test | Playwright against a **separate API on :8020** with temp data. Cloud endpoint mocked as `http://127.0.0.1:9` (closed port, so no egress). | **4/4 passed**, 7.6 s. The brief fell back after `ConnectError`, as expected. The :8020 API was stopped afterwards. |
| T4 | Live player short-outage recovery (existing spec) | Browser-only request blocking for one channel | **Passed**, 36.5 s; recovered in about 18 s |
| T5 | Live player 150 s outage (new spec) | `DIRA_LIVE_PLAYER_TEST=1 npx playwright test live-player-prolonged` | **Inconclusive, 2 runs.** Run 1 failed the recovery assertion (line 26). Run 2: Sky UK never started. Both overlapped the host incident (§3.4). |
| T6 | Post-remediation defect tests (new, `xfail(strict)`) | `.venv/bin/python -m pytest -q -p no:cacheprovider -o asyncio_mode=auto --rootdir=docs/audits/2026-11-17-post-remediation-artifacts docs/audits/2026-11-17-post-remediation-artifacts/test_post_remediation_findings.py` | **8 xfailed**, 8.8 s. Each one asserts the correct behaviour and fails today: P-01 to P-08. |
| T7 | Previous audit's tests | `docs/audits/2026-11-17-artifacts/test_audit_findings.py` | 7 passed, 2 failed. This file encodes pre-remediation behaviour and is superseded by T6. The two failures were not re-triaged. |
| T8 | Live search relevance | 5 read-only `/api/search` queries | See `search-relevance-live.json`. Latency 300–470 ms. 4 of 5 lexical results for an unrelated query had cosine < 0.30. |
| T9 | Brief sampling query cost | `brief_sample` on a read-only copy, 24 h window | 105 ms for about 23,000 rows |
| T10 | **Two-hour read-only soak** | `scripts/verify_live.py --seconds 7200` (`/api/snapshot` every 10 s) | **7,107 s** (98.7% of 7,200 s; the script stops before the last poll). 702 samples, **0 poller errors**. Details in §3. |
| T11 | Resource sampler (read-only) | `resource_sampler.py` every 60 s: `ps`, `lsof`, `statvfs`, crash reports | 115 samples (§3.3) |
| T12 | Session statistics | `live_session_stats.py`: read-only SQLite over the 139-minute session | §3.2 |
| T13 | Soak analysis | `analyze_soak.py` (offline) | Figures in §3 |

**Not performed (boundaries):**
- No restart or fault injection on the live system.
- No paid or cloud brief.
- No reproduction of native crashes.
- No WER or recognition-accuracy measurement: there are no reference transcripts.
- No publisher-to-screen latency measurement.
- No WebSocket soak.
- After the incident, no further video-decoding browser tests against live.

---

## 2. Remediation verdicts

| Earlier finding | Verdict | Evidence |
|---|---|---|
| **F-01** Unbounded Arabic ASR lag | **Verified** | Lag stayed ≤ 90.2 s for 2 h; per-channel Arabic median 21–23 s (T10); 674 s before. **Cost:** an estimated **5–11%** ASR coverage loss per Arabic channel (§3.2). Gaps caused by `ExceptionGroup` and `TimeoutError` have no duration estimate, so real loss is higher than the estimate. |
| **F-02** Brief scope | **Partially verified** | Sampling now spans channels, but clusters in time (P-07). |
| **F-03** Spike detection | **Partially verified (semantics changed)** | The arrival clock (`runtime.py:218`) removes ASR-replay false spikes. Only 4 spike alerts in 139 minutes. Detection sensitivity on real events is unproven. |
| **F-04** OCR repetition | **Verified, with a caveat** | First 26 minutes: 3% repeats, versus 55% before. Over 139 minutes, 19% of OCR texts recur. The 15-minute dedup window permits later repeats by design. Worker respawns may also reset local state (hypothesis). |
| Alert volume | **Partially verified** | 71 alerts/h, versus about 145/h before. Exact-text cooldown misses OCR variants (P-10). |
| **F-05** Storage | **Partially verified** | Binary DV1 vectors confirmed. There is no retention policy or budget. The evidence DB grows about 15 MB/h; the Qdrant tier is excluded from that figure. |
| **F-06** Status freshness | **Verified** | Status is republished on every metrics tick. |
| **F-07** Citation validation | **Partially verified** | Stricter per-sentence checks, but they falsely reject abbreviations (P-02). **No cloud brief has run live since the restart**, so live behaviour is unproven. |
| **F-08** Cloud egress | **Partially verified** | Opt-in and disclosure are verified (T3; `cloud_auto_briefs=false` live). The policy can be bypassed through the provider label (P-03). |
| **F-09** Documentation | **Unproven** | Not re-checked. |
| **F-10** Search relevance | **Partially verified** | Stopwords fixed. The lexical lane bypasses the 0.30 cosine floor (P-12). Queries with no relevant evidence still return results. |
| **F-11** Host / ingest security | **Verified** | `TrustedHostMiddleware` at `api.py:63`; live ingest locked at `api.py:112–117`. New exposure found: P-04. |
| **F-12** Speaker / confidence labels | **Verified** | 0 non-null speaker or confidence values in 12,336 session observations. |
| **F-13** Native crash isolation | **Regressed** | 11 new `Python-*.ips` reports at 15:29–15:33 (P-09). PaddleOCR itself loads faiss, torch and sklearn in the worker (two libomp copies). The remediation test only proves that `dira.ocr` does not. |
| **F-14** Unchanged-frame OCR gate | **Partially verified** | Skips occurred on 5 channels (19–163 skips per channel). `alhadath` reported none in 4,086 frames, and the field stayed null (P-15). |
| **F-15** Player recovery | **Partially verified** | The 18 s outage recovery is verified (T4). Prolonged-outage recovery is unproven (T5). |
| **F-16** Counters | **Regressed (misleading)** | `active_alerts` grew from 363 to 515 and counts every historical unacknowledged alert. It has no ageing and no bulk acknowledge (P-11). |
| **F-17** Log rotation | **Unproven** | Claimed at 10 MiB × 3. Not re-checked. |

---

## 3. Measured operation (observed)

### 3.1 Soak: 12:21:40–14:20 UTC (15:21–17:20 local), 7,107 s

**Throughput**
- Evidence grew from 22,268 to 32,641: **+10,373, about 5,254 per hour**.
- Processed observations grew from 1,951 to 12,324.

**Archive outbox (pending writes)**
- Maximum 7, final 0.
- Qdrant was not connected in 11 samples (12:28:42–12:36:50 UTC). It recovered and drained without intervention.

**Ingest p95**
- Median 35.7 ms, maximum 68.6 ms.
- This is *ingest processing only*, not end-to-end transcription latency.

**Global ASR lag (maximum across channels, per sample)**

| Median | p95 | Max |
|---|---|---|
| 51.8 s | 84.5 s | 90.2 s |

**Evidence stalls of 60 s or longer:** two, both inside the incident:
- 223 s from 15:32:24;
- 93 s from 15:36:39.

**Disk:** free space rose from **17.37 GB to 48.09 GB** during the soak. This is an external change: neither the audit nor Dira deletes files. The guard never activated.

| Channel | Connected | ASR lag median / p95 / max (s) | Lag-limit resets in soak | Backlog dropped (s) | % of soak | Samples with last transcript > 60 s old | Unchanged-frame skips |
|---|---|---|---|---|---|---|---|
| aljazeera | **90.7%** | 22 / 74 / 90 | 6 | 541 | 7.6% | 46 / 702 | 40 |
| alarabiya | 95.4% | 21 / 72 / 89 | 7 | 631 | 8.9% | 53 | 163 |
| alhadath | 97.9% | 21 / 71 / 88 | 6 | 541 | 7.6% | 32 | — (null) |
| sky_arabia | 96.7% | 23 / 75 / 89 | 7 | 631 | 8.9% | 40 | 107 |
| asharq | 96.4% | 22 / 68 / 89 | 5 | 452 | 6.4% | 48 | 41 |
| sky_uk (EN) | 95.6% | 3 / 13 / 88 | 2 | 180 | 2.5% | 39 | 19 |

**Disconnection timing** (samples not connected, per 10-minute bucket):
- **12:30 UTC bucket:** all six channels were down for 14–28 samples. This was the incident.
- **Outside the incident:** **aljazeera** dropped repeatedly (3–12 samples per bucket at 12:20, 12:40, 13:00, 13:10, 13:30, 13:40 and 14:10 UTC). The other channels were down for only isolated samples.

Session gap records:
- 18 `ExceptionGroup` gaps on aljazeera, versus 2–5 on the other channels.
- **Hypothesis:** a publisher or path instability specific to Al Jazeera, not an application defect. There is no source-side evidence to confirm it.

### 3.2 Whole session since the API restart (139.3 minutes; `live_session_stats.py`)

**Output rates**
- 12,336 observations.
- ASR lines per channel: 910–1,171 (Arabic), 2,813 (sky_uk).
- OCR lines: 4,321 in total.

**ASR age (seconds from capture to transcript timestamp)**

| Channels | Median | p95 | Max |
|---|---|---|---|
| Arabic | 14.0–19.6 s | 55–71 s | ≤ 89 s |
| English | 3.8 s | 7.9 s | 45 s |

These are adapter-relative timestamps (see also P-05), not publisher-to-screen latency.

**Estimated ASR coverage loss** (sum of `asr_skipped_seconds`, divided by session length)

| alarabiya | alhadath | aljazeera | asharq | sky_arabia | sky_uk |
|---|---|---|---|---|---|
| 811 s (10%) | 541 s (6%) | 632 s (8%) | 452 s (5%) | 901 s (11%) | 180 s (2%) |

**Gaps:** 39 `asr_lag_limit`, 33 `ExceptionGroup`, 16 `TimeoutError`.

**Alerts:** 165 (71 per hour):
- keyword/warning 115;
- keyword/critical 44;
- spike 4;
- info 2.

**Briefs:** 0 since the restart. No jobs were triggered.

### 3.3 Resources (`resources-7200.json`, 115 samples)

**Open files and database**
- API file descriptors: 330 to 332 (max 343). **No descriptor leak.**
- Evidence DB: 186.9 MB to 216.5 MB, about 15 MB/h. The Qdrant volume was not measured.

**OCR workers**
- Total RSS 5.3–8.1 GB; the process count peaked at **7** (old and new overlapping).
- **48 distinct OCR worker PIDs over 2 h**, versus 6 in steady state. Each spawn reloads about 1.2 GB of Paddle models.

**Other processes**
- ASR: 2 processes, about 1.5 GB each.
- API: RSS fell from 1.6 GB to 0.59 GB. This most likely reflects swap or compression, not lower use (hypothesis).
- FFmpeg: 12–13 processes, about 35 MB each.

**Crash reports:** 11 new `Python-*.ips`, all between **15:29:21 and 15:33:52**; **none after**.

### 3.4 Incident: 15:28–15:40 (observed)

**Host state**
- Load average reached about **397**.
- Swap was about 7.1 of 8 GB used.
- The workstation was also running many unrelated heavy applications.

**Failure sequence**
1. Qdrant `ResponseHandlingException` and MediaMTX upstream timeouts hit every path. Both services run in the same Docker VM.
2. PCM `TimeoutError` and `ExceptionGroup` errors followed.
3. All six channels restarted.
4. Each restart killed and respawned that channel's OCR worker (P-08).
5. The workers then segfaulted at interpreter shutdown (P-09).

**Recovery**
- The system recovered without intervention by about 15:40.
- At 15:56: load 14.7 and 6/6 channels connected.

**Concurrency**
- My in-app browser was decoding the six-video dashboard, and the T5 Playwright run was active.
- Causality is not established. I moved the browser away from the dashboard, stopped the isolated :8020 API, and ran no further video tests against live.

### 3.5 Failure classification

| Class | Observed instances |
|---|---|
| Publisher or network | Recurrent aljazeera disconnects (hypothesis, §3.1); upstream timeouts during the incident |
| Application defects | P-01 to P-10 and P-12 (§4); OCR worker respawn churn and shutdown segfaults |
| Hardware or host capacity | Shared 64 GB host with swap near full. Five windowed Arabic ASR sessions exceed real-time on one GPU: 39 lag-limit resets in 139 minutes. MediaMTX and Qdrant share one Docker VM. |
| Recognition quality | Not measurable without references. Station self-promotion text was OCR'd and treated as news (P-10). |
| Monitoring or labeling | Gaps are invisible in the UI (P-13). The `active_alerts` count is misleading (P-11). Coverage loss for exception gaps is not estimated. The `alhadath` skip counter is null (P-15). |

---

## 4. Findings

No **Critical** finding was confirmed: no data corruption, no security breach, and no unrecoverable outage were observed.

### High

**P-09: OCR worker lifecycle causes respawn churn and native shutdown segfaults (F-13 regression)**
- **Where:**
  - `ingest.py:253–262`: the OCR worker starts inside each frame session.
  - `ingest.py:370–398`: `supervise_feed` cancels both sessions on any failure.
  - `ocr_process.py:57–69`: close sequence.
  - `ocr_worker.py`: on stdin EOF the worker returns normally; interpreter finalization then runs with the Paddle and OpenMP thread pools alive.
- **Evidence (observed):**
  - 48 distinct OCR PIDs in 2 h.
  - Up to 7 workers alive at once (about 1.2 GB each).
  - 11 `Python-*.ips` reports, all at worker shutdown during the incident.
  - The worker process loads faiss, torch, sklearn and two libomp copies through PaddleOCR's own imports.
- **Impact:**
  - Under stress, every transport hiccup adds a 1.2 GB model load, which amplifies memory pressure exactly when the host is already starved.
  - Crash reports accumulate.
  - OCR coverage pauses during each reload.
- **Fix:** Recommendation 1 (§7). This builds on P-08.

**P-01: One undecodable archive row blocks the warm-store outbox forever**
- **Where:** `store.py:341–370`. `VectorStore.flush` is all-or-nothing, and a decode error aborts the batch. The oldest row is always first, so the same poison row heads every retry.
- **Repro:** T6 `test_poison_row_does_not_block_outbox`. After 3 flushes, all 3 rows are still pending.
- **Impact:**
  - Qdrant archiving halts silently.
  - The hot FAISS tier ages out, so older evidence becomes semantically unsearchable.
  - Triggers include legacy or partial rows and disk-full writes. None was observed live; the trigger is hypothetical, but the defect is proven.
- **Fix:**
  - Decode per row.
  - Move failures to a `quarantined` state with the error text.
  - Expose the quarantine count in metrics.

### Medium

**P-08: Speech-side failure respawns the channel's OCR**
- **Where:** `ingest.py:370–398`.
- **Repro:** T6. Three speech failures caused three OCR session starts.
- **Impact:** this is the amplifier behind P-09.
- **Fix:** supervise the audio and frame sessions independently.

**P-07: The "stratified" brief sample collapses into a few minutes**
- **Where:** `store.py:125–163`.
  - Fixed buckets of `min(24, limit // channels)` span the *requested* window, not the populated span.
  - `ROW_NUMBER()` is ordered by `start DESC`, so every bucket's picks are its newest rows.
- **Repro:** T6. Over 4 h of dense data, 80 samples covered only 5–6 distinct minutes out of 240.
- **Impact:** a "24-hour" executive brief describes a few minutes, with no warning.
- **Fix:**
  - Compute buckets over `[min(start), max(start)]` of the matching rows.
  - Pick a row nearest each bucket's midpoint, or a random row.
  - Report how many buckets were empty.

**P-02: Per-sentence citation check rejects ordinary abbreviations**
- **Where:** `briefs.py:84`. The split regex breaks after any `.`.
- **Repro:** T6. `- U.S. officials met Kuwaiti ministers [id].` splits into the uncited fragment "U.S.", so the whole brief is rejected.
- **Impact:** valid cloud or local briefs fall back or fail, especially on English sources.
- **Fix:** validate citations per bullet or line instead of per sentence, or protect common abbreviations before splitting.

**P-03: The egress policy trusts a self-declared provider label**
- **Where:**
  - `runtime.py:286–292`: `job_allowed` checks `settings.llm_provider`.
  - `briefs.py:99`: the label.
- **Repro:** T6. `llm_url=https://openrouter.ai/...` with `llm_provider=local` passes the scheduled-job check.
- **Impact:** a misconfiguration sends evidence off-host without the opt-in.
- **Fix:** classify by URL host; anything other than loopback or RFC 1918 counts as cloud. Refuse to start when the label and the host disagree.

**P-04: Snapshot and WebSocket `channels` publish raw feed configuration, including `input_url`**
- **Where:** `runtime.py:445–455`.
- **Repro:** T6, with a URL containing a credential.
- **Impact:**
  - Any UI client sees stream URLs.
  - Credentials leak if the operator ever uses authenticated sources.
  - The current feeds were not inspected for secrets, per the boundaries.
- **Fix:** whitelist the public channel fields.

**P-10: Exact-text alert cooldown and substring keyword matching yield false critical alerts**
- **Where:**
  - `mechanics.py:70`: the cooldown key is the exact normalized text.
  - `mechanics.py:63–69`: the exemption covers only the bare badge.
- **Evidence:** the station promo «تابعوا أحدث الأخبار لحظة ورودها على حسابنا للأخبار العاجلة» raised **7 critical alerts** in 139 minutes as three OCR variants (a missing space, a trailing "1").
- **Fix:**
  - Use a fuzzy cooldown key (token-set or character n-gram similarity of at least 0.85).
  - Keep a per-channel suppression list for recurring station chrome.

**P-12: The lexical search lane bypasses the cosine floor**
- **Where:** `runtime.py:239–284`. The lexical weight of 1.5 is at line 248.
- **Evidence:** T8. For "North Macedonia Iranian network", 4 of 5 lexical hits had cosine < 0.30. Queries with no matching evidence still return results.
- **Fix:**
  - Apply the floor to the fused score, or require that a lexical hit match at least 2 non-stopword terms.
  - Return an explicit "no relevant evidence" state.

**P-13: Gaps are recorded but never shown**
- **Where:** `/api/gaps` exists, but `frontend/src/App.tsx` never calls it. Briefs do not mention gaps either.
- **Impact:** analysts cannot tell silence from missing coverage, even though coverage loss was 5–11% per Arabic channel.
- **Fix:** capability C1 (§6).

### Low

**P-05: ASR timestamps are anchored to FFmpeg spawn, not to first audio**
- **Where:** `ingest.py:151`.
- **Repro:** T6. A source that starts 3 s late is skewed by −3.08 s.
- **Fix:** set `base` when the first PCM chunk arrives.

**P-06: A malformed (non-object) ASR message tears down the channel**
- **Where:** `ingest.py:193`. `payload.get` on a JSON list raises `AttributeError`.
- **Repro:** T6.
- **Fix:** `if not isinstance(payload, dict): continue`.

**P-11: `active_alerts` counts every historical unacknowledged alert**
- **Where:** `runtime.py:406–443`.
- **Evidence:** grew from 363 to 515 and never falls.
- **Fix:** count only the last N hours, and add bulk acknowledge.

**P-14: The Playwright default `baseURL` is the live API, and a spec overwrites committed screenshots**
- **Where:** `frontend/playwright.config.ts`; `command-center.spec` writes `docs/dira-*.png`.
- **Impact:** a casual `npx playwright test` hits production and rewrites documentation images. Both happened in this audit, and the images were restored.
- **Fix:**
  - Default to an isolated port that the config starts itself.
  - Write screenshots to `test-results/`.

**P-15: The unchanged-frame gate never fires on `alhadath`, and its counter is null**
- **Evidence:** 4,086 frames, 0 skips, `ocr_unchanged_skips` null throughout the session.
- **Hypothesis:** motion graphics keep the mean-absolute-difference above 0.5, so the counter is never initialised.
- **Fix:** initialise the counter to 0. Gate on the ticker region rather than the whole frame.

---

## 5. Prioritized engineering backlog

| # | Item | Findings | Effort | Expected benefit |
|---|---|---|---|---|
| 1 | Decouple the OCR worker from transport sessions: one long-lived worker per channel, graceful exit, restart jitter | P-08, P-09 | M (1–2 days) | Removes the respawn storm and the shutdown segfaults; caps OCR memory at 6 workers |
| 2 | Outbox poison-row quarantine plus a retention and disk budget (evidence DB and Qdrant) | P-01, F-05 | M | Archive can no longer stall silently; disk growth is bounded |
| 3 | Fix brief sampling and abbreviation citations; disclose gaps in briefs | P-07, P-02, P-13 | S–M | Briefs represent the requested window and are not falsely rejected |
| 4 | Egress classification by host; public channel DTO | P-03, P-04 | S | Closes the policy bypass and the credential exposure |
| 5 | Fuzzy alert cooldown, station-chrome suppression, ageing alert count | P-10, P-11 | S | Fewer false critical alerts; a truthful counter |
| 6 | Search: fused-score floor plus a "no relevant evidence" state | P-12 | S | Analysts stop acting on unrelated hits |
| 7 | ASR robustness: first-audio clock, ignore non-dict messages, estimate coverage for exception gaps | P-05, P-06 | S | Correct timestamps; honest coverage figures |
| 8 | Test hygiene: isolated Playwright default, screenshots out of `docs/` | P-14 | XS | No accidental live load or document overwrites |
| 9 | Capacity: move Qdrant out of the MediaMTX Docker VM (or run it natively) and reserve host memory | §3.4 | S (operations) | One fewer shared failure domain |

---

## 6. Recommended capabilities (at most five)

### C1: Coverage and gap timeline, with completeness in briefs and exports (**build now**)

1. **Problem and workflow.** An executive reads "no statement from Al Arabiya on X between 13:00 and 14:00". In fact Arabic ASR dropped 811 s of that channel, and the analyst has no way to see it. Workflow: a timeline row per channel shows connected, ASR-dropped and exception spans. Each brief ends with "coverage: 92% (alarabiya 10% ASR loss)", and an export bundles the brief, its cited evidence and the gap list.
2. **Why existing features fall short.** `/api/gaps` and per-tile counters exist, but nothing aggregates them per time window, the UI never calls `/api/gaps`, and briefs never mention gaps.
3. **Smallest version.**
   - A `/api/coverage?from&to` endpoint that sums gaps per channel.
   - A strip of time segments per tile.
   - A coverage line appended to brief text and to a JSON or Markdown export.
4. **LLM?** No. Deterministic.
5. **Data and dependencies.** Existing gap records; an estimate for exception gaps (backlog item 7). No new models or permissions.
6. **Cost.** One indexed SQLite query (gaps are rare rows). Negligible memory, storage and latency.
7. **Risks and acceptance.**
   - Risk: estimates are presented as exact. Mitigation: label them "estimated".
   - Accept when coverage within 1% of the sum of `asr_skipped_seconds` and the gap durations for a replayed fixture day.
   - Accept when every brief carries a coverage line.
   - Accept when the export reproduces the cited evidence IDs.
8. **Verdict:** **Now.**

### C2: Retention controls and storage budgeting (**build now**)

1. **Problem.** At the start of the soak only 17 GB was free, with about 360 MB/day of DB growth plus the Qdrant tier and logs. The guard pauses ingestion at 2 GiB free and deletes nothing, so a full disk means a silent stop of evidence capture.
2. **Why existing features fall short.** The guard prevents corruption but not the outage. There is no age or size policy.
3. **Smallest version.**
   - `DIRA_RETENTION_DAYS` and `DIRA_STORAGE_BUDGET_GB`.
   - A daily job that archives (exports) and then deletes evidence older than N days from SQLite and Qdrant together.
   - Metrics show the projected days until the budget is reached.
4. **LLM?** No.
5. **Dependencies.** None new. It needs the operator's explicit retention decision, which may be a legal or policy question.
6. **Cost.** A short batch delete per day; runtime cost is negligible.
7. **Risks and acceptance.**
   - Risk: deleting evidence that a brief cites. Mitigation: never delete rows referenced by a stored brief or alert.
   - Accept when a fixture of N+1 days shrinks to N days.
   - Accept when cited rows survive.
   - Accept when SQLite and Qdrant counts agree after deletion.
8. **Verdict:** **Now.**

### C3: Capacity-aware Arabic ASR prioritization (**build soon**)

1. **Problem.** Five windowed Arabic sessions overrun one GPU: 39 lag-limit resets in 139 minutes, dropping audio on all channels roughly equally. During a crisis, the operator would rather have one or two channels at full coverage than five at about 90%.
2. **Why existing features fall short.** F-01 bounds staleness but distributes the loss blindly.
3. **Smallest version.**
   - A per-feed `priority` in `feeds.json`.
   - When aggregate lag exceeds a threshold, lower-priority channels drop to OCR-only (ASR paused, recorded as gaps) until lag recovers.
   - A UI toggle to promote a channel.
4. **LLM?** No.
5. **Dependencies.** The existing lag signal; ASR session pause and resume (WLK is reconnect-only, so this means closing and reopening a session).
6. **Cost.** Reduces GPU load; adds no memory.
7. **Risks and acceptance.**
   - Risk: flapping between modes. Mitigation: hysteresis plus a minimum dwell time.
   - Accept when, on a 1-hour live run, priority channels show at least 98% ASR coverage.
   - Accept when paused channels show explicit gaps.
   - Accept when there is no more than one mode switch per 5 minutes per channel.
8. **Verdict:** **Soon**, after C1, because C1 makes its effect visible.

### C4: Story clustering and near-duplicate suppression (**later, after C1–C3**)

1. **Problem.** The same headline appears as ASR on five channels and as repeated OCR (19% repeats over the session), which floods the search results and the brief sample.
2. **Why existing features fall short.** Dedup is per channel and exact-text within 15 minutes; search dedup is also exact-text.
3. **Smallest version.**
   - Online clustering on the existing 384-dimension embeddings: cosine ≥ 0.85 within 30 minutes.
   - A `story_id` column.
   - Search and briefs show one representative per story, with its channel list.
4. **LLM?** No; it reuses MiniLM vectors.
5. **Dependencies.** None new. A threshold calibration set (about 200 labelled pairs) is needed.
6. **Cost.** One FAISS lookup per observation: under 5 ms on CPU, plus about 8 bytes per row.
7. **Risks and acceptance.**
   - Risk: merging distinct stories, such as different casualty numbers. Mitigation: never merge texts whose numbers differ.
   - Accept at precision ≥ 0.9 on labelled pairs.
   - Accept when brief sample redundancy is cut by at least 30%.
8. **Verdict:** **Later.**

### C5: Analyst verification and correction (**later**)

1. **Problem.** ASR mistranscribes names, and analysts currently have no way to mark evidence as verified, wrong or corrected, so briefs keep citing bad lines.
2. **Why existing features fall short.** Evidence is immutable and has no review state.
3. **Smallest version.**
   - A `review_state` field plus `corrected_text` stored alongside (the original is never overwritten).
   - Briefs prefer verified rows and exclude rejected ones.
4. **LLM?** No.
5. **Dependencies.** Analyst identity, which today requires authentication that does not exist.
6. **Cost.** Negligible.
7. **Risks and acceptance.**
   - Risk: an audit trail without identity is weak.
   - Accept when corrections are reversible and attributed, and rejected rows never appear in briefs.
8. **Verdict:** **Later**, once authentication exists.

---

## 7. Do not build yet

| Proposal | Why not now |
|---|---|
| Claim-level contradiction tracking across channels | Needs an LLM. Arabic ASR accuracy is unmeasured, and 5–11% of audio is dropped. Contradictions would mostly be transcription noise or coverage holes. Do C1 and C4 first, plus a WER baseline. |
| Arabic/Kuwait NER and entity normalization models | Adds another CPU or ML process to a host that is already swapping. Value is unproven until ASR name accuracy is measured. |
| Visual detection and speaker diarization | Speaker labels are deliberately hidden (F-12); diarization is uncalibrated. Adds GPU contention to the one resource that is already short. |
| New hardware purchase | The incident and the respawn churn are partly software (P-08, P-09). Fix those, move Qdrant, then re-measure capacity on a *dedicated* host before buying. |
| **Remove:** Aurelio router and other unprovisioned paths | The router is not on the measured search path (`runtime.py:239–284`). Treat that as a hypothesis and confirm before deletion. Unused routing adds configuration surface and dependencies without measured benefit. |

---

## 8. The three highest-value next actions

1. **OCR worker lifecycle (P-08 and P-09).** This is the largest stability lever: it removes the respawn storm, the shutdown segfaults and about 1.2 GB reloads under stress.
2. **Storage safety (P-01 and C2).** Prevents a silent archive stall and a disk-full stop of capture.
3. **Brief integrity (P-07, P-02, P-13 and C1).** Makes the main executive output representative and honest about coverage.

---

## 9. Implementation prompt (action 1)

```text
Task: Decouple Dira's OCR worker lifecycle from transport sessions and make worker shutdown crash-free.

Context (verified in audit docs/audits/2026-11-17-post-remediation-audit.md, P-08/P-09):
- backend/dira/ingest.py:253-262 starts an OCR worker (ocr_process.py, ~1.2 GB Paddle models) inside each frame
  session; supervise_feed (ingest.py:370-398) cancels BOTH audio and frame sessions on any failure, so every PCM
  timeout respawns OCR. Live: 48 distinct OCR PIDs in 2 h for 6 channels, up to 7 alive at once.
- ocr_worker.py returns normally on stdin EOF; interpreter finalization with Paddle/OpenMP pools alive segfaults
  (11 macOS Python-*.ips reports at shutdown). PaddleOCR itself imports faiss/torch/sklearn (two libomp copies).

Do:
1. Supervise audio and frame sessions independently in supervise_feed: a failure in one restarts only that one,
   each with its own exponential backoff (+ random jitter 0-30%). Keep channel status = worst of the two.
2. Own one OCR worker per channel at the supervise_feed level (created once, reused across frame-session restarts);
   restart it only if the worker process itself dies or stops answering (existing 30 s exchange timeout), with
   backoff + jitter and a global cap of at most one concurrent OCR model load.
3. Worker exit: after flushing the final JSON response on stdin EOF or SIGTERM, flush stdout/stderr and call
   os._exit(0) so no native finalizers run. Parent close(): close stdin, wait up to 5 s, then terminate, then kill.
4. Expose per-channel metrics: ocr_worker_restarts, ocr_worker_pid, ocr_worker_started_at.
5. Initialise ocr_unchanged_skips to 0 for every channel (currently null on some).

Tests first (TDD), isolated (tmp_path, fake worker scripts, no Paddle, no live services):
- Make docs/audits/2026-11-17-post-remediation-artifacts/test_post_remediation_findings.py::
  test_speech_failure_does_not_respawn_ocr pass (move it into tests/ without xfail).
- Fake worker that exits on EOF: assert parent close() returns < 5 s and the worker exit code is 0.
- Fake worker that hangs: assert terminate/kill path, no zombie.
- Repeated frame-session failures with a live worker: assert worker PID unchanged.
- Worker crash: assert exactly one restart after backoff, metric incremented.

Constraints: do not change ASR behaviour, the F-01 lag ceiling, or numerical thread settings; do not import Paddle
in the API process; do not restart the live installation or run dependency sync; run the full backend suite
(.venv/bin/python -m pytest -q) and ruff before finishing. Acceptance on live (operator restarts): over a 2 h
soak, distinct OCR PIDs <= 6 + number of real worker crashes, and no new Python-*.ips at shutdown (make live, Ctrl-C).
```

---

## 10. Limitations of this audit

- The soak covered 7,107 s, 93 s short of 2 h because of poll granularity. It included one host-starvation incident, so it is neither a clean baseline nor a production-readiness certification.
- Coverage loss is *estimated*. Exception and timeout gaps carry no duration estimate.
- Recognition accuracy (WER and OCR CER) is unmeasured; there is no reference material.
- Live cloud-brief behaviour is unproven: 0 briefs since the restart.
- Incident causality is unresolved, and the audit's own browser video decoding may have contributed.
- Disk free space changed by about 31 GB from outside Dira during the soak, so storage-pressure observations apply only to its start.
- Feed configuration was not inspected for embedded credentials (P-04 is demonstrated on a fixture).

---

## خلاصة (عربي)

**ما اختبرتُه فعلاً:**
- تشغيل حي للقراءة فقط لمدة ≈ ساعتين، مع عيّنة كل 10 ثوانٍ ومراقبة الموارد كل دقيقة.
- 102 اختبار خلفي، و4 اختبارات واجهة، و4 اختبارات قبول معزولة.
- 8 اختبارات جديدة تُثبت 8 عيوب.
- اختبار استعادة مشغّل الفيديو.
- قياس جودة البحث وسرعة استعلام الموجزات.

**ما اكتشفتُه:**
- سقف تأخر التفريغ يعمل، ولكن بخسارة تغطية 5–11% لكل قناة عربية لا يراها أحد.
- عمّال OCR يُعاد تشغيلهم مع كل عطل صوتي (48 مرة)، وينهارون عند الإغلاق.
- سجل تالف واحد يمكنه إيقاف الأرشفة إلى الأبد.
- الموجزات تأخذ عيّنة من دقائق قليلة، وترفض الاختصارات.
- سياسة السحابة يمكن تجاوزها بالتسمية.
- تنبيهات حرجة كاذبة من عبارات ترويجية.

**ما بقي غير مؤكد:**
- سبب الحادثة (ضغط الجهاز المشترك أم اختباراتي في المتصفح).
- دقة التفريغ والـOCR (لا توجد نصوص مرجعية).
- سلوك الموجزات السحابية حياً.
- استعادة الفيديو بعد انقطاع طويل.
- هل انقطاعات الجزيرة من المصدر.

**ما يجب البدء به ولماذا:**
1. **فصل دورة حياة OCR:** أكبر مصدر لعدم الاستقرار والضغط على الذاكرة.
2. **أمان التخزين:** لتفادي توقف صامت للأرشفة أو الالتقاط.
3. **نزاهة الموجزات مع إظهار الفجوات:** لأن الموجز هو المنتج الذي يقرأه صاحب القرار.

---

## Remediation status: action 1 (P-08 / P-09), 2026-11-17 evening

Implemented in `backend/dira/ingest.py`, `ocr_process.py` and `ocr_worker.py`. Not yet verified live.

**What changed**
- `supervise_feed` now runs speech and frames as independent loops. Each has its own jittered exponential backoff, which resets after 60 s of healthy running.
- A video failure sets `ocr_status=degraded` and `last_frame_error_type`, and records a `frames:<Type>` gap. It no longer marks speech as degraded.
- `OCRWorker` keeps one OCR process per channel across frame-session restarts.
  - The worker is replaced only after its own failure, timeout or cancellation mid-exchange, and only after backoff.
  - Model loads are serialized (at most one at a time).
  - Each feed exposes `ocr_worker_restarts`, `ocr_worker_pid` and `ocr_worker_started_at`.
  - Because the worker survives, its 15-minute OCR dedup memory now also survives transport restarts.
- The OCR worker exits through `os._exit`, so interpreter finalizers never run with Paddle/OpenMP pools alive.
- `OCRProcess.close` waits 5 s (previously 10 s) before terminating, then kills.
- `load_feeds` initializes `ocr_unchanged_skips=0` (P-15 counter part).

**Tests**
- New `tests/test_ocr_lifecycle.py`: 8 tests.
- `test_live_supervisor_restarts_when_audio_ends` was updated to the new contract: audio ending no longer cancels video/OCR.
- Backend suite: 110 passed.
- The audit artifact's P-08 xfail stub still uses the old `frame_session` signature. It is kept as the historical record; the live check is `tests/test_ocr_lifecycle.py`.

**Still to verify** (operator restart required)
- Over a 2-hour soak, distinct OCR PIDs ≤ 6 + real worker crashes.
- No new `Python-*.ips` reports after `make live` followed by Ctrl-C.

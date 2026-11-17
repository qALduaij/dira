# Session report: Dira audit and F-01 fix

**Date:** 2026-11-17
**Workspace:** `/Users/qusaial-duaij/Desktop/Dira` (branch `feat/dira-platform`, nothing committed)
**Related documents:**
- [Devil's-advocate audit](2026-11-17-devils-advocate-audit.md): full findings, evidence and test ledger.
- [Audit artifacts](2026-11-17-artifacts/): audit tests and measurement scripts.

---

## الملخص

أنجزت هذه الجلسة مرحلتين:

1. **تدقيق مستقل وناقد** لمنصة ديرة: قراءة الشيفرة كاملة، وفحص النظام الحي أثناء عمله، وتشغيل الاختبارات، وكتابة اختبارات تدقيق تثبت العيوب. أهم النتائج:
   - التفريغ الصوتي العربي يتأخر حتى 11 دقيقة.
   - "الموجز الصباحي" يغطي دقيقة واحدة فقط.
   - تنبيهات حرجة متكررة بكثافة غير قابلة للتشغيل.
   - إرسال تلقائي للأدلة إلى خدمة سحابية رغم وصف الواجهة بأنها "محلية".
   - قرص شبه ممتلئ.
2. **إصلاح أهم عيب (F-01):** قياس تأخر التفريغ لكل قناة وعرضه في الواجهة، مع حدّ أقصى (90 ثانية افتراضياً). عند تجاوزه تعود جلسة الكلام في تلك القناة إلى البث الحي دون إيقاف الفيديو أو قراءة الشريط الإخباري.

لم يُعدَّل أي شيء أثناء التدقيق نفسه، ولم يُرسَل أي دليل إلى خدمة خارجية، ولم يُوقَف النظام الحي.

---

## Part 1: The audit

### What I was asked to do

You asked for an adversarial, evidence-driven audit of Dira, covering everything from incoming media to the browser. You wanted claims verified independently rather than accepted from the existing docs, passing tests or previous agents' conclusions. The rules were strict: no production code changes, no stopping the live system, no paid cloud calls, no secrets printed, and no reproducing the known native crash.

### What I did, and why

| Step | What | Why |
|---|---|---|
| 1. Inventory | Checked the real hardware (`sysctl`: Apple M2 Max, 64 GB, 12 cores), running processes, listening ports, Docker containers and the `.env` keys (values redacted) | Performance claims are worthless without knowing the actual machine and what is actually running |
| 2. Documentation | Read `README.md`, `docs/LIVE_ACTIVATION.md`, `docs/VERIFICATION.md`, the feed and MediaMTX configs and the launch scripts | To know exactly which claims needed testing |
| 3. Full code read | All backend modules (about 2,300 lines) and the key frontend files, read directly rather than delegated | The codebase is small, and first-hand reading avoids second-hand errors |
| 4. Live data analysis | Read-only SQL (`mode=ro`) over the live evidence database: 15,000+ observations from the running 2-hour session | The live system had been running about 2 hours; its own data was the best evidence available, with no interruption needed |
| 5. Cross-checks | Compared database delay figures with WhisperLiveKit's own `lag=` log; Qdrant point count with SQLite rows; crash reports with process start times | Two independent sources agreeing makes a finding solid |
| 6. Existing tests | Ran 76 backend and 3 frontend tests with `.venv/bin/python -m pytest` instead of `uv run` | To confirm the claimed pass count without any risk of a dependency sync changing the live environment |
| 7. Audit tests | Wrote 8 `xfail(strict=True)` tests, each stating the *correct* behaviour, which currently fails | Each defect becomes reproducible, and each test flips automatically once fixed. I confirmed each fails on its assertion, not on setup |
| 8. Isolated experiments | Copied the database to a scratch folder for scaling tests; pointed FFmpeg at a silent local "RTSP" server; replayed stored vectors through the real spike detector | To test failure modes safely without touching the live installation |
| 9. Real browser | Opened the live dashboard and measured whether all six videos actually advance; checked Arabic RTL and a 375 px mobile layout; ran a few read-only searches | "Video loaded" is not the same as "video playing"; the operator's view is what matters |
| 10. Documentation check | Used Context7 to confirm uv's sync behaviour and websockets' `recv()` cancellation safety | Recommendations had to rest on current documentation, not memory |
| 11. Report | Wrote `2026-11-17-devils-advocate-audit.md` with an Arabic summary, readiness verdict, requirements matrix, 17 findings, test ledger, performance boundaries, M2 Max assessment and a list of tests not performed | The required deliverable |

### What I deliberately did NOT do

| Not done | Reason |
|---|---|
| Reproduce the OpenMP crash | Forbidden by scope; it is a known native crash on your active machine |
| Call OpenRouter or another LLM | Paid, and would send broadcast evidence externally; mocked instead |
| Stop or restart the live stack | It would interrupt your running installation |
| Measure word error rate or OCR accuracy | No reference transcripts or labelled frames exist; this needs a human Arabic listener |
| Run an isolated single-session Arabic ASR benchmark | It would compete for the GPU with the live ASR server; needs your approval |
| Long soak (24–72 h) | Outside the session's time window; the existing 2 h live run was analysed instead |

### The five most important findings

1. **F-01 (Critical): Arabic ASR cannot keep up.** Al Jazeera's speech evidence reached 674 s (over 11 minutes) of delay. The ASR server's own log reported `lag=673s`. The dashboard showed "Pipeline latency 40 ms" instead, a number that excludes transcription.
2. **F-02 (Critical): briefs cover about one minute.** Every brief, including the "24-hour morning brief", uses only the newest 80 observations, which spans 41–60 seconds.
3. **F-03 and F-04 (High): alerts are unusable.**
   - 205 critical alerts in 2 hours; 75 of them were the same static "عاجل" graphic.
   - 55% of OCR records repeat earlier text.
   - The spike detector silently ignores 89.5% of speech observations.
4. **F-08 (High): automatic cloud egress.** About 14 KB of broadcast text goes to OpenRouter every 5 minutes, while the UI says "Local processing" and "Prepared locally".
5. **F-05 (High): disk exhaustion.** The disk is 98% full with 22 GiB free. The evidence database grows about 1.7 GB per day, mostly duplicated vectors stored as JSON.

**Also confirmed as working:**
- All six videos play: 30 s advanced in 30 s.
- Qdrant and SQLite are consistent.
- No Python crash since the current run started.
- English ASR keeps up (≤ 9 s).
- RTL and mobile layout are correct.
- All existing tests pass.

---

## Part 2: The F-01 fix

### Why F-01 first

It was the highest-value single change for two reasons:

1. It makes the system **honest**. The operator now sees how old each channel's speech evidence is, instead of a reassuring 40 ms figure that measures something else.
2. It **bounds the damage**: speech evidence can no longer silently fall 11 minutes behind.

It also produces the per-channel measurement needed before any decision about new hardware.

### Design decisions

| Decision | Why |
|---|---|
| Use WhisperLiveKit's own `remaining_time_transcription` field as the lag source | It is the exact backlog the server measures (the same number as the `lag=` log line), and it is always included in every payload (checked in WLK 0.2.26's source). Computing lag from transcript timestamps would confuse silence with delay. |
| Count server silence beyond a 15 s grace as lag | A stalled ASR session sends nothing, so with no fallback the reported lag would freeze at a healthy-looking value. |
| Receive with a 5 s timeout (`asyncio.wait_for(socket.recv(), 5)`) | So lag is re-evaluated even when no messages arrive. The websockets 15 docs confirm cancelling `recv()` is safe and loses no data. |
| On exceeding the ceiling, abruptly close the session (no end-of-stream signal) | I checked WLK's server code: an abrupt disconnect cancels the session's processing tasks, so the backlog is **dropped**. A graceful close would make the server finish all queued audio first. |
| Restart **speech only**, not the whole channel | The old supervisor restarted audio and OCR together. Restarting the OCR worker reloads Paddle models and loses on-screen text for no reason. |
| Default ceiling 90 s, configurable, 0 disables | Healthy Arabic delays in the earlier run were mostly 6–40 s, so 90 s avoids needless resets while capping the 674 s worst case. |
| Record resets and skipped seconds per channel | Dropping audio must never be silent. The operator can see exactly how much was not transcribed. |
| Republish channel state on every 3 s metrics tick | Lag changes continuously. This also fixes part of F-06, where a recovered channel kept showing "DEGRADED" until a page reload. |
| Replace the live KPI with "Speech lag · worst channel" | The old "Pipeline latency 40 ms" headline was the most misleading number on the dashboard. The ingest figure is kept as a subtitle. Simulation mode is unchanged. |

### Files changed

| File | Change |
|---|---|
| `backend/dira/config.py` | New setting `asr_max_lag` (`DIRA_ASR_MAX_LAG`, default 90, range 0–3600) |
| `backend/dira/ingest.py` | New `ASRLag` tracker and `ASRLagExceeded` exception; timed receive loop in `audio_session`; new `speech_session` wrapper that restarts speech only; channels initialised with lag, reset and skipped fields |
| `backend/dira/runtime.py` | Metrics tick republishes channels; metrics include `asr_lag_max_seconds` and `asr_max_lag` |
| `frontend/src/types.ts` | New optional channel and metrics fields |
| `frontend/src/App.tsx` | `LagBadge` component on each video tile; live-mode "Speech lag" KPI; placeholders when data is missing |
| `frontend/src/style.css` | Badge styles (green when OK, red above 30 s, grey when unknown) |
| `frontend/dist/` | Rebuilt (served by the live API) |
| `tests/test_asr_lag.py` | 6 new tests |
| `.env.example` | Documents `DIRA_ASR_MAX_LAG` |
| `docs/LIVE_ACTIVATION.md` | Notes the 674 s finding and the new ceiling behaviour |
| `docs/audits/2026-11-17-devils-advocate-audit.md` | F-01 remediation status |

### How it was verified

1. **Test first.** The 6 new tests were written before the code and failed (`ImportError`), then passed after implementation. They cover:
   - the lag calculation, including silence;
   - a real FFmpeg-to-WebSocket session that resets when over the ceiling, continues when under it, and never resets when the ceiling is disabled;
   - a reset restarting speech while OCR keeps running;
   - the metrics tick republishing channel state.
2. **Full suites:** 82 backend tests pass (76 existing + 6 new), plus 3 frontend tests, the TypeScript check and the production build.
3. **End-to-end on an isolated instance:**
   - **Setup:** a second Dira API in live mode on port 8010 with its own data folder and no `.env`, no OCR and no LLM. It used a fake ASR server whose backlog grows 1 s per second, with the ceiling set to 20 s.
   - **Observed:** lag climbed 3 → 8 → 13 → 18 s, reset to about 4 s at about 21 s, and repeated three times. 21, 42 and 63 s of skipped audio were recorded, the channel stayed CONNECTED, and new evidence kept arriving.
   - **Browser:** it showed `ASR 7s ↻3`, then `ASR 13s ↻3` seven seconds later, without a reload.
   - All test processes were stopped afterwards, with no orphaned FFmpeg; the live API on port 8000 was never touched.

### Honest limits of the fix

- **It bounds staleness; it does not add capacity.** Under today's load, Arabic channels will reset regularly and drop audio. The difference is that every drop is now visible.
- **The live system is not running the new backend yet.** You chose to restart it yourself. Until then, a page reload shows `ASR —` placeholders, because the UI files were already rebuilt.
- **Not yet verified:** a 2-hour run on the real ASR servers with the ceiling active.
- **Lint:** 23 pre-existing lint warnings elsewhere in `backend/` were left untouched; the new test file is clean.

---

## Part 3: After you restart

**Restart:** press Ctrl-C in the `make live` terminal, then run:
```bash
cd /Users/qusaial-duaij/Desktop/Dira && make live
```

**Check after 30–60 minutes:**
```bash
grep -a 'rejoining live audio' /Users/qusaial-duaij/Desktop/Dira/logs/api-live.log
```
```bash
curl -s localhost:8000/api/snapshot | python3 -c "import json,sys; [print(c['id'], c['asr_lag_seconds'], c['asr_resets'], c['asr_skipped_seconds']) for c in json.load(sys.stdin)['channels']]"
```

**How to read the results:**

| What you see | Meaning |
|---|---|
| Lag mostly under 90 s, occasional resets on Al Jazeera or Al Hadath | Working as intended |
| Arabic channels resetting every couple of minutes | The ASR server cannot keep up even from a fresh start. Next: cut load (OCR frame-change detection, fewer concurrent Arabic sessions) |
| A tile stuck on `ASR —` while CONNECTED | Bug; report it |

## Recommended next fixes (from the audit, in order)

1. **F-05:** stop storing duplicate JSON vectors in SQLite and add a disk guard. Urgent at 22 GiB free.
2. **F-02:** time-stratified brief selection that states the covered interval.
3. **F-04 and F-03:** OCR and alert deduplication, and spike buckets that tolerate late data.
4. **F-08:** turn off automatic cloud narratives, or show a persistent cloud banner.
5. **F-14:** skip OCR on unchanged frames to free CPU, then re-measure Arabic ASR before deciding on new hardware.

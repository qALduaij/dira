# Dira remediation ledger

Scope: address verified audit findings F-01–F-17, preserving existing evidence and operator credentials. No paid inference tests, crash reproduction, data deletion, or commits.

1. Speech: reject stale results before ingestion; validate all backlog fields; media watchdogs; durable, explicitly estimated gap records; honest speaker metadata.
2. Storage and search: binary vectors with legacy reads and archive recovery; cached counts; disk backpressure; time/channel-stratified brief inputs; lexical stop words and result deduplication.
3. Intelligence: per-claim citations, coverage metadata, explicit cloud scheduling/egress status; arrival-time spike semantics; alert cooldowns and OCR TTL deduplication.
4. Perception/API/UI: lightweight OCR imports and unchanged-frame gating; host validation and locked live external ingestion; resilient playback; accurate counts and labels.
5. Verification: regressions, full suite, frontend build, independent final review, controlled live restart and measured observation window.

Ruling: work in the existing uncommitted feature workspace. A new worktree cannot preserve this uncommitted project without copying it; no commit was requested.
Ruling: preserve historical vector payloads and recovery. New binary storage reduces future growth; no destructive retention or full VACUUM on a nearly full disk.
Ruling: semantic spikes describe arrival volume, not source-time volume. Source timestamps remain intact for evidence and search.
Ruling: cloud inference stays available manually; scheduled cloud calls require explicit configuration. Unit tests use mocked HTTP.

Progress: implementation started. Prior baseline: 82 tests pass. Live backend has not loaded the F-01 changes.

Implementation checkpoint: 95 backend tests pass (13.59 seconds); 3 frontend state tests and production build passed before the final UI additions. Nine reproduced regressions failed first, then passed. A separate cosine-floor regression also failed before its fix.

Implemented: binary vector payloads with legacy decode and persistent archive recovery; O(1) evidence/outbox counts; stratified brief sampling, input/cited IDs and coverage; per-line citation validation; cloud scheduling opt-in and disclosure; arrival-clock spike input; per-rule/channel/text cooldown; OCR 15-minute normalized dedup; lightweight OCR module; unchanged-frame gate with periodic refresh; PCM/video watchdogs; durable estimated gaps; honest speaker provenance; low-disk backpressure; explicit live API ingest enablement plus token; host validation; lexical stopwords, cosine floor and content dedup; alert order/count fixes; HLS bounded retries and overlay recovery; 10 MiB × 4 service log rotation; safe dependency setup instructions.

Ruling: cosine floor 0.30 is adjustable per search and exposed with scores; it is not a calibrated probability. The bounded 10,000-record lexical lane remains documented. Exhaustive multilingual retrieval calibration and archive FTS are separate scale work.
Ruling: gap duration uses reported backlog as an estimate, and restart counters persist. Exact word/audio loss requires a retained audio timeline; recording remains disabled as configured.
Ruling: existing historical confidence values are not rewritten. New speech hides unverified speaker IDs; no real diarization/NER weights are provisioned.
Ruling: no destructive storage migration or retention. Existing JSON vectors coexist with new binary rows. Storage remains append-only with a 2 GiB reserve; free space still needs operator management.

Independent final review: three important findings, all reproduced with four failing regressions: a citation licensing later sentences on the same line; OCR stdin drain outside the response deadline; recovered scheduled/legacy cloud jobs bypassing opt-out. Fix pass: conservative per-sentence citation checks, one deadline around the entire OCR exchange, and persisted manual/scheduled job provenance plus policy enforcement at recovery and execution. Citation syntax still cannot establish semantic truth.

Reviewer limitations accepted: throughput, OCR/ASR accuracy and long-term native stability require measured live/ground-truth validation. No claim of model-quality certification or full two-hour stability follows from unit tests.

Live checkpoint: real Sky Arabia backlog reached 90.1 seconds at 15:08:13 Kuwait; speech rejoined live and a durable estimated-gap record was created while its OCR counters continued. Al Jazeera experienced repeated publisher-read timeouts confirmed independently in MediaMTX logs; the adapter reported degraded/reconnecting and recovered. These are source outages, not a claim of uninterrupted six-channel availability. Source logs are preserved in `2026-11-17-remediation-source-recovery.log`.

Known remaining work: sustained two-hour post-remediation run; recognition/citation-entailment quality evaluation; capacity for sub-second Arabic ASR; operator retention policy; exhaustive archive lexical indexing; calibrated similarity threshold; provisioned diarization/NER. Exception groups currently expose a safe group type rather than all nested causes; correlate source failures with MediaMTX logs. No native Python crash report newer than the pre-existing 12:07:43 report was found during this check.

Final 600.03-second server soak: 61 snapshots, zero REST errors, 1,010 new observations. Sampled backlog peaked at 89.3 seconds; the server independently reset Arabic speech sessions at 90.1 seconds (Sky Arabia and Al Arabiya), persisting loss estimates. Al Jazeera was non-connected in 7/61 snapshots due to publisher-read timeouts and recovered. All six channels were connected in the final snapshot. Ingest p95 ranged 23.12–37.46 ms; this excludes ASR/OCR inference latency. Outbox pending ranged 0–6. SQLite quick_check remained `ok`; zero new cloud briefs were generated after restart. See `2026-11-17-remediation-live-summary.json`.

A live-browser follow-up found that the finite HLS retry budget can remain exhausted after a publisher outage. The server had recovered while the video stayed stopped. A browser-only request-blocking regression is being added; no publisher or MediaMTX mutation is involved.

Final browser recovery fix: the opt-in `live-player.spec.ts` blocked only Sky UK's browser requests for 18 seconds. Before the fix, currentTime remained zero and the test failed after 58.2 seconds. After rebuilding HLS on fatal failures with bounded exponential retry spacing (2–30 seconds, one client/timer), the test passed in 32.7 seconds. No backend or publisher mutation was used. Source outages no longer exhaust a lifetime retry budget permanently.

Completion checkpoint: 102 backend tests green; final isolated browser rerun 4/4 in 5.2 seconds; frontend state tests 4/4; live player recovery regression 1/1; TypeScript/Vite production build and focused Python lint passed. Temporary acceptance backend stopped. At 15:16:29 Kuwait, the deployed backend had run 930 seconds, all six channels were connected, the archive outbox was empty, and the worst reported speech lag was 48.3 seconds. The cloud schedule was off. The provisioned live stack remains running; no commit or push was made.

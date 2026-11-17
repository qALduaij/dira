# Live activation ledger — 2026-11-17

Authorized scope: provision remaining local inference dependencies and weights, activate real feed processing and test it. Existing OpenRouter brief profile remains enabled by the operator.

Plan:
1. Install native semantic/OCR dependencies and isolated WhisperLiveKit runtime.
2. Download official model exports, recording revisions and hashes; validate offline loading.
3. Run Arabic and English ASR and test actual audio; validate Arabic ticker OCR.
4. Start live Dira with independent evidence storage; verify retrieval, alerts, briefs and browser playback.
5. Measure multi-channel capacity, fix observed integration failures, document exact remaining limits.

Pre-flight: actual hardware is M2 Max / 64 GiB. Available disk approximately 34 GiB. Existing Docker media router and Qdrant are running. No microphone, screen recording or accessibility permission is required for direct stream ingestion. Models and environments stay inside the project; no OS security changes are planned.

Ruling: use a compact multilingual SentenceTransformers model compatible with the existing symmetric encoder API, rather than introducing query/passage-prefix handling during deployment. Separate live data prevents mixing demonstration hash vectors with learned vectors.

## Progress

- Native dependency installation started. No perception models were previously provisioned.
- Installed locked semantic, perception and extraction extras; installed isolated WhisperLiveKit 0.2.26 / qwen3-asr-causal 0.1.0. Frozen ASR runtime: `asr-runtime-lock.txt`.
- Downloaded revision-pinned official weights with SHA-256 manifests: `model-manifest.json`, `causal-model-manifest.json`, `english-ocr-manifest.json`. Approximately 3 GB of model assets; no paid model-hosting service required.
- Arabic and English PCM replays through actual WLK WebSockets succeeded on MPS. Around 20 seconds of audio streamed in real time finished in 21–22 seconds, first line in 5.6–6.5 seconds. These are short-sample results, not a six-channel latency guarantee. Transcription errors remain, especially names; no WER certification.
- Multilingual MiniLM embeddings loaded offline and returned Arabic/English cosine 0.842 versus unrelated text 0.018; 384 dimensions. Single-channel Arabic live pilot produced 45 real observations (9 ASR, 36 OCR) with no synthetic events.
- Real images revealed whole-frame OCR voting lost stable headlines when stock values changed. Voting and deduplication now operate per text line. Cumulative WLK lines emit only their new suffix; retention uses a watermark to avoid replaying old session history. Slow OCR consumers now receive the newest decoded frame with bounded buffering.
- Browser test revealed native HLS selection left video paused and mishandled a MediaMTX gap segment. Prefer hls.js/MSE, explicitly start muted playback. All six 1080p videos subsequently advanced in the browser.
- A real OCR `عاجل` observation triggered the existing critical keyword gate. Search returned stored real evidence; an OpenRouter narrative completed as `cloud-llm`, `simulated=false` (see `live-brief-verification.json`).
- Native crash investigation: macOS crash reports confirmed OpenMP failure with multi-threaded CPU Torch alongside the installed numerical runtimes. Single-thread CPU embedding smoke succeeded in 6–8 ms after warmup. Paddle inference in API threads also blocked the event loop and made teardown unreliable. OCR now runs in six separate subprocesses, with JSON protocol output and graceful EOF shutdown. API process never loads Paddle. Native Mac imports default numerical thread pools to one; ASR remains MPS, embeddings use CPU. No macOS security setting was changed.
- The isolated six-channel run reached ingest p95 28 ms with no pending archive writes. This measures ingest processing only, not broadcast or ASR latency. Shutdown of the supervisor/API/OCR children completed in 6.1 seconds; no remaining target processes and no new Python crash report. A numerical-runtime semaphore cleanup warning remains on exit, without a crash.
- Arabic ASR decode pacing is four seconds in `make live` to reduce contention among five windowed sessions; English causal pacing remains two seconds. The underlying launcher defaults to two seconds and validates overrides.
- Fresh review reproduced OCR repetition, ASR-history replay and dropped frame-reader exceptions. Regression tests now cover all three; fixes verified. Live observations without a calibrated confidence score are labeled uncalibrated rather than 100% accurate.
- The final 12-sample live run covered 166 seconds and 318 additional observations: all six sources stayed connected in every sample, no synthetic records, and pending archive writes were zero in the last sample. API snapshot requests took at most 46 ms; ingest p95 ranged 31–34 ms. Both ASR and OCR records were present for every channel.
- Arabic capture-relative ASR delay varied materially: channel medians about 9–44 seconds, maximum sampled delay 67 seconds. English median was 0.6 seconds, maximum 4.5 seconds. These timestamps are adapter-relative and do not include a verified publisher-to-display measurement. This machine does not yet meet a sub-second six-channel Arabic transcription target.
- Aurelio local routing smoke selected OCR for an English ticker query and transcript for an Arabic speaker query; no generative call. Operator configuration enables it.
- 76 Python tests passed with operator `.env`/credentials isolated by the test fixture; three frontend state tests and TypeScript/Vite build passed. Live browser verified six advancing 1920×1080 videos, connected data stream, no simulation control and uncalibrated confidence labels. Screenshot: `dira-live-desktop.png`.

## Run the provisioned installation

```bash
cd /Users/qusaial-duaij/Desktop/Dira
make live
```

This starts the Docker media/vector services, waits for Arabic/English ASR, and starts the API with the prebuilt UI. It uses existing `.env` and `infra/feeds.json`, currently configured for six real primary channels and independent `.data-live` storage. It performs no package/model downloads. Ctrl-C stops the owned API/ASR/OCR processes; the media router and Qdrant remain running. Stop acquisition separately with `docker compose -f docker-compose.mac.yml stop mediamtx`.

Logs: `logs/api-live.log`, `logs/asr-ar.log`, `logs/asr-en.log`. No microphone, screen-recording, accessibility or administrator permission was requested. Do not use macOS “Reopen” for old crash reports; use the project launcher.

## Limits

- This is connected live operation. Publisher feeds use the internet and the operator-enabled OpenRouter profile sends selected evidence text externally. It is not air-gapped.
- OCR is CPU inference: the captured Arabic ticker took about 1.7–2.3 seconds per inference. Video is sampled at 2 fps, but excess frames are intentionally dropped; sub-second OCR inference is not claimed.
- Five Arabic ASR sessions share the GPU. Observe actual delay in `live-soak-verification.json`; low ingest latency does not imply low transcription latency. A later 2 h run reached 674 s of Arabic lag (see `audits/2026-11-17-devils-advocate-audit.md`, F-01).
- Speech lag is now bounded by `DIRA_ASR_MAX_LAG` (default 90 s): each tile shows its WhisperLiveKit-reported lag, and a channel exceeding the ceiling drops its backlog and rejoins live audio. Unprocessed audio may be lost; an estimated coverage-loss duration and persistent reset count appear on the tile. Durable gap records are available at `/api/gaps`; these are not exact audio-loss measurements. This bounds staleness; it does not add capacity.
- Automatic person identification, calibrated speaker diarization, visual detector models and a comprehensive text entity recognizer are not enabled by this activation. ASR speaker IDs are hidden unless the feed explicitly declares diarization enabled; existing historical labels remain unverified. The existing graph only displays entities supplied to observations.
- No long-duration uptime certification, reference-transcript accuracy benchmark or M5 Max benchmark is claimed.

## Audit remediation activation — 17 November, afternoon

The running backend was restarted with the remediation described in `audits/2026-11-17-remediation.md`. The current suite has 102 backend tests, four frontend state tests and four isolated Chrome acceptance tests. The fourth browser test checks cloud egress/manual-scheduling disclosure. No paid synthesis calls were made during remediation validation.

New automatic cloud briefs require `DIRA_CLOUD_AUTO_BRIEFS=true`. Manual requests remain available. Old scheduled or provenance-unknown pending cloud jobs are failed rather than replayed when this opt-in is off.

Logs rotate at 10 MiB with three backups per service. New SQLite vectors use float32 binary payloads; existing JSON vectors are read without a destructive migration. The low-disk reserve defaults to 2 GiB and pauses ingestion visibly; it does not delete evidence or solve disk provisioning.

To collect a read-only two-hour observation run against an already-running local backend:

```bash
.venv/bin/python scripts/verify_live.py --seconds 7200 --output docs/audits/two-hour-live-soak.json
```

This command only reads local REST endpoints. It does not trigger cloud briefs, restart channels, or produce a recognition-accuracy score. Inspect per-channel resets/gaps as well as lag: dropping backlog bounds staleness by sacrificing coverage.

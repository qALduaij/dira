# Dira verification — 17 November 2026

## Observed results

- Python 3.12 on macOS Apple Silicon: **76 tests passed** after live activation. Includes genuine FAISS and embedded Qdrant, durable outbox recovery, endpoint failure fallback, incompatible encoder rejection, independent vector namespaces, persistent job recovery, authentication, cumulative ASR deduplication, OCR line voting, subprocess protocol, frame error recovery and isolation from operator credentials.
- Frontend stream-state tests: **3 passed**. Duplicate updates, bounded lists, alert replacement and stale snapshot rejection.
- TypeScript production build: passed.
- Chrome browser acceptance: **3 tests passed** covering pause/resume, multiview expansion, search, evidence inspection, rule add/toggle/delete, asynchronous brief/export, Arabic RTL, 390-pixel mobile layout without horizontal overflow, desktop preview and reload/reconnection. No browser page errors in the main workflow.
- `docker compose config --quiet`: passed.
- Full API/UI Docker image: built successfully on the local Docker Desktop engine.
- Containerized API on temporary verification port 8002: healthy, Qdrant connected, durable outbox drained to zero.
- Qdrant v1.20.0 service: `/healthz` passed.
- MediaMTX **1.21.4** with CA roots: all six configured primary HLS sources were independently read through local RTSP as **1920×1080 H264 + AAC**. Evidence: `mediahub-verification.json`. The supplied Al Arabiya hyphenated hostname failed DNS; its verified dotted hostname is configured. Version 1.15.4 failed MPEG-TS probing on Al Jazeera/Asharq; upgrading fixed both without disabling TLS.
- Secondary extraction container smoke: idle before demand → runOnDemand HTTP lease → yt-dlp + Streamlink HLS → FFmpeg → MediaMTX audio/video → last-reader cleanup, passed. Temporary containers/network removed. Video is copied; audio is normalized to AAC to supply RTSP global headers.
- Both extraction adapters were tested against local HLS and a controlled regional proxy with distinct source/CDN hostnames, scoped cookies and no credential leakage. Cancellation during refresh, stalled publishers, authentication and shared leases are covered.
- Native Sky News Arabia demux: 32,000 bytes for one second of 16-kHz mono PCM; two 1280×144 ticker RGB frames produced with VideoToolbox. Mid-GOP join/decoder warnings occurred before usable output (`demux-verification.json`); this is not a clean decode latency or accuracy benchmark. Software decoding remains selectable.
- ASR launcher: 21 structural regression tests; Arabic/windowed and English/causal profiles additionally loaded actual local weights and transcribed real broadcast samples. Details and limits: `LIVE_ACTIVATION.md`.
- Current local services: native live API on 8000, Arabic/English ASR on 8001/8003, six isolated OCR workers, Qdrant on 6333, and continuous primary MediaMTX acquisition on 8554/8888. Source recording is disabled; short test fixtures are under ignored `logs/live-samples`. No secondary operator channel is enabled.
- ARM64 Mac, default and extraction Compose configurations validated. The Mac profile uses separate ordinary bridges with loopback-published ports; an internal-only Docker network prevented host-native Qdrant access in this Docker Desktop environment, so no egress-isolation claim is made.
- Python source compilation: passed. Shell launcher syntax and Compose validation are part of the final check.

## Measured local components

The reproducible script is `scripts/benchmark.py`; raw output is `docs/benchmark.json`.

| Component | P50 | P95 | P99 |
|---|---:|---:|---:|
| Three keyword gates, including Arabic normalization and alert construction | 0.0386 ms | 0.0457 ms | 0.0845 ms |
| FAISS hot query, 1,000 synthetic 256-dimensional vectors | 0.3542 ms | 0.4105 ms | 0.4712 ms |

These are single-process synthetic component timings, not transport-to-alert latency or production concurrency measurements. Dashboard pipeline latency measures local TDO ingest, indexing and alert work; it excludes upstream perception.

## Independent review and fixes

A fresh read-only reviewer found six issues. Each was addressed:

1. Live outbox backpressure now retains and retries the current TDO instead of tearing down the source.
2. A completed or failed audio/frame session cancels its sibling, allowing supervised reconnection.
3. Stored encoder compatibility includes dimensions and local model-file identity; different evidence workspaces use separate Qdrant collection namespaces.
4. Explicit modality constraints also apply to lexical retrieval.
5. REST/WS snapshot races were removed: reconnect and resynchronization now obtain an atomic WebSocket snapshot.
6. Job status is persisted and included in reconnect snapshots; interrupted queued/running jobs are recovered after restart.

Regression tests demonstrate the original failures and pass after the fixes. Initial development simulation evidence was preserved in `.data.demo-before-compatibility/` when the compatibility guard was introduced; current demonstration data lives in `.data/`. Both are ignored by Git.

## Limits and remaining deployment validation

- Public primary streams were connectivity/codec-tested. No satellite or paid-feed credentials were supplied; no production ASR/OCR accuracy assessment was performed.
- Local WhisperLiveKit/Qwen3 recognition, Arabic/English PaddleOCR, multilingual SentenceTransformers and Aurelio have since been provisioned and tested against real feeds; see `LIVE_ACTIVATION.md` and `live-final-verification.json`. The final backend suite has 76 passing tests. Six-channel Arabic ASR still has material delay (up to 67 seconds in the sampled run), and reference-transcript accuracy has not been measured. pyannote diarization, TorchScript visual detector and local generative LLM weights remain unprovisioned; the operator-enabled generative brief provider is OpenRouter.
- The ASR contract test uses FFmpeg and a controlled local protocol server, not a speech recognition model.
- Actual host: Apple M2 Max, 64 GiB, arm64. Native MPS ASR and a short six-channel run were measured. No M5 Max/CUDA benchmark, long-duration soak, fault-tolerant cluster, external authentication integration or air-gap certification was performed.
- Semantic-model retrieval requires a supplied local model. Default demo feature hashing is not claimed as true multilingual semantic embeddings. Visual retrieval uses text descriptions/labels, not direct image embeddings.
- TSDuck SCTE-35/EIT/KLV/closed-caption parsing, PCR-grade synchronization, enterprise RBAC and HA remain site-specific integration work, explicitly documented in README.
- A Starlette test-client deprecation warning is emitted for its httpx compatibility path. Tests pass; this is not a runtime error.
- Vite reports an approximately 875 kB uncompressed JavaScript bundle, largely the bundled HLS player. Runtime is local; further route/player lazy loading is a frontend optimization, not a completed claim.

## `master_skills`

All seven files were inspected. Their agent process guidance is useful and largely already active. Setup scripts were not executed; no global skill/configuration replacement took place. See the README assessment for the placeholder instructions, Node version check and Context7 credential/configuration concerns.

## Latest independent integration review

Separate reviews found and resolved extractor cleanup cancellation, validation-error credential disclosure, obsolete Streamlink segment-option names, an invalid v6 detector name, and the English ASR port mismatch. The proxy integration test also exposed an upstream import-order collision between yt-dlp and Streamlink HTTP patches; extraction now completes before Streamlink is loaded in each isolated child. Final profile defaults are `PP-OCRv6_small_det` + `arabic_PP-OCRv5_mobile_rec`, Arabic windowed Qwen3, and English causal Qwen3 on port 8003.

The frontend now uses the required Obsidian colors and 40px glass blur. Desktop/mobile screenshots are `dira-desktop.png` and `dira-mobile.png`; browser tests verify theme tokens, Arabic RTL, simulation controls and reconnect behavior.

## Afternoon audit-remediation verification

- 102 backend tests passed in 13.57 seconds, with operator configuration isolated. New regressions include stale-line rejection, modern ASR backlog fields, durable gaps, disk backpressure, binary/legacy vector recovery, reporting-window sampling, cloud recovery policy, same-line uncited claims, blocked OCR input pipes, host/provenance controls, and cosine floor.
- Four frontend state tests and four isolated Chrome acceptance tests passed (7.8 seconds). The test instance ran on port 8010 with temporary storage and a loopback-only unavailable model endpoint; no paid API calls. Production TypeScript/Vite build succeeded.
- Independent final review found three important defects; all four reproductions failed before fixes and the full suite passed afterward. No repeated review was substituted for regression tests.
- The old live process stopped cleanly; SQLite `quick_check` returned `ok` with 20,317 historical rows and zero pending outbox writes. The new backend loaded the 90-second ceiling and manual-only cloud policy. Initial real browser inspection found six playing 1920×1080 videos and no playback error overlay.
- New single-modality vector payloads measured 1,561 bytes, versus 8,443 bytes average for historical JSON rows (about 81.5% less vector payload storage). This is not a whole-database size reduction; old rows were preserved.
- Read-only search smoke covered 10 Arabic/English queries. `explosions Sanaa` and `explosions in Sanaa` now returned the same five source channels, fixing the reported stopword failure. Timings ranged 259–358 ms; this is not a human-labeled precision benchmark.
- Sustained results and remaining limits are in the remediation ledger and timestamped soak JSON. No two-hour post-remediation stability or recognition-accuracy certification is claimed.

- Additional live-player regression: browser-only HLS requests blocked for 18 seconds, without changing MediaMTX or publisher feeds. Old player failed (currentTime remained 0 after 58.2 seconds); rebuilt-client retry passed (32.7 seconds). Automatic recovery uses one timer/client with 2–30-second exponential retry spacing. Total browser acceptance: four isolated workflow tests plus this one live playback recovery test.

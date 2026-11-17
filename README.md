# Dira · ديرة

A local-first broadcast intelligence command center. Dira turns time-aligned speech, on-screen text and visual descriptions into searchable observations, deterministic alerts and evidence-linked executive briefs.

Built from **Private Multimodal Intelligence Architectures.md** and the six-step implementation mandate. The requested `DIRA_MASTER_SPECIFICATION.md` was absent; the user explicitly authorized the existing research document as the replacement blueprint.

## Start in one command

**Provisioned live installation:** `make live` starts the six real feeds, local Arabic/English ASR, isolated OCR workers, local multilingual search and the configured brief provider. See [live activation and measured limits](docs/LIVE_ACTIVATION.md). The commands below also support an unprovisioned simulation setup; the active `.env` determines the mode.

Prerequisites: macOS Apple Silicon or Linux, **uv**, and **Node.js 22+**. Docker is optional for the default demo. Run from this directory:

```bash
make start
```

Open **http://127.0.0.1:8000**. First startup installs locked dependencies and builds the UI; subsequent runtime needs no internet. Stop with Ctrl-C. Python 3.12 is selected by uv. The native launcher binds to loopback and uses one backend worker.

The demo supplies four fictional bilingual feeds, illustrated animated multiview monitors, transcripts and chyrons, evidence, entity co-occurrence, alert rules and periodic synthetic traffic bursts. Search, alerts, storage and background workers run through the real backend. Every synthetic observation and brief is marked. This is a working local implementation, **not a certified or load-qualified sovereign production deployment**.

## What works

- Obsidian Quantum React/TypeScript command center, dark glass panels, amber/gold accents, responsive desktop/mobile layout, Arabic RTL and English LTR.
- REST and WebSockets, reconnection with atomic snapshots, bounded subscriber queues, pause/resume simulation.
- Validated UTC Temporal Data Objects, source identifiers, confidence, speaker labels, visual tracks and entities.
- Durable SQLite WAL evidence/outbox, persistent Qdrant named vectors, bounded rolling FAISS hot tier; retry after warm-store failures.
- Arabic normalization, Aho-Corasick keyword and time-limited regex gates; FAISS topic matching and statistical topic-volume spikes against prior completed windows. No LLM calls in alert gates.
- Metadata-filtered hybrid retrieval, modality routing and reciprocal rank fusion across speech, OCR and visual-description indexes.
- Morning Brief scheduler (06:00 Asia/Kuwait by default), cross-channel narratives, persistent background jobs, evidence citations and Markdown export.
- OpenAI-compatible **local** inference client with extractive fallback when unavailable. No cloud credentials are needed.
- FFmpeg audio/frame demux, supervised WhisperLiveKit PCM WebSocket client, optional local PaddleOCR lower-third extraction with blur rejection and temporal voting, explicitly enabled diarization-label propagation, local pyannote file diarization wrapper and TorchScript object detection/IoU tracking.

## Native development

```bash
uv sync --frozen --inexact
npm --prefix frontend ci
uv run --no-sync uvicorn dira.api:app --host 127.0.0.1 --port 8000
# In a second terminal; proxies API and WS to the backend:
npm --prefix frontend run dev
```

Copy `.env.example` to `.env` to configure services. Keep secrets out of source control. The frontend uses the backend's origin; the Vite development proxy requires no CORS wildcard. API documentation is at `/docs`.

Default storage is `.data/evidence.db` and `.data/qdrant/`. Evidence, rules, alerts, briefs and pending jobs persist across restart. The hot tier is limited by whichever comes first: 2 hours or 4,000 observations. The System panel shows its actual retained horizon. A 50,000-row warm outbox limit applies backpressure; live adapters retry while the ASR lag ceiling can discard stale speech and rejoin live. A 2 GiB disk reserve pauses ingestion; new vector rows use compact float32 storage with backward-compatible legacy reads. The archive has no automatic evidence deletion; provision disk monitoring and an operator-approved retention policy for long-running installations. MediaMTX recordings rotate after 24 hours.

**Run one backend worker per data directory.** Embedded Qdrant is a single-process development store. Switch to the Qdrant service for operational workloads. Model-space changes require a new data directory and explicit reindexing of historical evidence; Dira refuses incompatible dimensions/model fingerprints.

## Local services and containers

```bash
# Media routing and service-mode vector storage:
make services
# Use service-mode Qdrant with the native backend:
DIRA_QDRANT_URL=http://127.0.0.1:6333 make start

# Full Docker demo (UI is built into the API image):
docker compose up --build -d
# Stop without deleting volumes:
docker compose down
```

Compose binds host ports to loopback. Qdrant uses 6333; MediaMTX exposes RTSP 8554, HLS 8888, SRT/UDP 8890 and metrics 9998. Its control API and WebRTC are disabled by default. The default Compose profile is simulation; optional inference/ASR profiles are separate and require supplied local model files.

On macOS, run inference **natively** for Metal. Docker Linux containers do not expose Apple MPS. FAISS runs on CPU, while the optional SentenceTransformers/TorchScript/pyannote adapters select CUDA, MPS or CPU. Set `DIRA_DEVICE` explicitly when needed. Heavy ASR/OCR/diarization environments are intentionally isolated from the demo API.

## Connect real feeds

1. Provision licensed/authorized feed access, FFmpeg and MediaMTX. Publish to a path such as `rtsp://127.0.0.1:8554/ktv1` or MediaMTX's SRT listener. The system does not acquire satellite or subscription feeds itself.
2. Copy `infra/feeds.example.json` to `infra/feeds.json`; set operator-controlled stream URLs and browser-reachable HLS playback URLs. In Docker, use service hostnames for backend inputs and host-reachable URLs for playback.
3. Supply a **local multilingual SentenceTransformers model directory**, install `uv sync --inexact --extra semantic`, then set `DIRA_EMBEDDING_MODEL=/absolute/path/to/model`. Live mode refuses the demonstration hash encoder. Set `DIRA_ROUTER=aurelio` to use Aurelio's local `HuggingFaceEncoder`/`SemanticRouter`; the default anchor router also makes vector-only decisions.
4. Provision the local ASR models and isolated runtime using [the verified perception profiles](docs/PERCEPTION_PROFILES.md). The native launcher runs Qwen3-ASR on Metal/MPS, with bundled Silero VAD and PCM input. Arabic uses the supported windowed backend; the published causal tower is English-only. Launch the English service separately on port 8003 for Sky UK.
5. Set `DIRA_MODE=live`, `DIRA_ASR_URL=ws://127.0.0.1:8001/asr` and use a separate `DIRA_DATA_DIR` from the hash demo. Start the backend. Disconnected feeds report degraded/reconnecting state with bounded exponential retry.

### Six configured primary channels on Apple Silicon

```bash
make services-mac
```

This uses `docker-compose.mac.yml`: ARM64 MediaMTX **1.21.4** with CA certificates and six continuous HLS pulls, plus persistent Qdrant. Use `DIRA_FEED_CONFIG=infra/primary-feeds.json` for the native backend. All six streams were verified through the media hub at 1080p with audio; see [primary ingestion and hardware setup](docs/PRIMARY_INGESTION.md) and [verification evidence](docs/mediahub-verification.json). The supplied Al Arabiya hostname contained a DNS error; the verified publisher address uses `live.alarabiya.net`.

The default `make services`/Compose demo uses `mediamtx.offline.yml` and does not fetch the public channels. The provisioned live profile uses native Metal for ASR and single-thread CPU embeddings, with isolated CPU OCR workers; Linux containers do not expose Apple's GPU. The observed test machine is M2 Max/64 GiB; M5 Max is the deployment target, not a measured performance result.

## Secondary ingestion for complex sources

An optional Python extraction sidecar uses **yt-dlp + Streamlink** to resolve and periodically renew operator-authorized HLS sources, with domain-selected regional proxies, read-only session-cookie files, bounded retry/stall detection and MediaMTX on-demand hooks. All supplied channel entries are disabled placeholders. DRM bypass and protected-channel access are not implemented or claimed.

See [secondary ingestion setup](docs/SECONDARY_INGESTION.md) for the optional Docker overlay, native startup, session rotation and stable RTSP feed configuration. The default simulation requires none of these services or credentials.

## Optional perception

`uv sync --inexact --extra semantic --extra perception` installs the optional local model runtimes. Supply complete **det/** and **rec/** exports under `DIRA_OCR_MODEL_DIR`, then set `DIRA_ENABLE_OCR=true`. The default CPU OCR profile combines `PP-OCRv6_small_det` with `arabic_PP-OCRv5_mobile_rec`; v6 recognition does not currently include Arabic. FFmpeg selects video explicitly, samples **2 fps**, crops the **lower 20%**, and emits a bounded 1280×144 RGB ticker frame. The OCR adapter rejects low Laplacian variance and requires repeated readings. Native video decoding uses VideoToolbox in auto mode; CPU fallback is configurable. Thresholds and actual ticker accuracy still need calibration. See [perception profiles](docs/PERCEPTION_PROFILES.md).

`DIRA_VISUAL_MODEL` accepts a local **TorchScript** detector whose output is an `N×6` tensor `[x1,y1,x2,y2,score,class_id]` for a normalized RGB `1×3×360×640` input. Configure class labels per feed. Label/IoU tracking assigns temporary object tracks, never biometric identities. Visual search currently embeds those descriptions/labels; direct image/audio embedding checkpoints are not bundled. The optional `Diarizer` in `perception.py` supports local pyannote pipelines for file analysis; continuous diarization comes from WLK.

Timestamp alignment uses the local stream-session clock plus ASR offsets. It is not PCR/PTP-grade synchronization. SCTE-35/EIT/KLV/closed-caption parsing and broadcast transport certification require a site-specific TSDuck/GStreamer adapter; they are not represented as implemented transport decoders.

## Local reasoning

Dira accepts an OpenAI-compatible chat endpoint, including `/v1`:

```dotenv
DIRA_LLM_URL=http://127.0.0.1:8080/v1
DIRA_LLM_MODEL=local
```

This can be a native llama.cpp/MLX service or Linux/CUDA vLLM. Optional CPU container:

```bash
# Supply models/model.gguf first.
docker compose --profile inference up -d inference
```

For the Compose API, use `http://inference:8080/v1`; for native macOS inference accessed by Compose, use `http://host.docker.internal:8080/v1`. No inference endpoint is contacted unless configured. Endpoint hosts are operator-controlled; deployment egress controls establish the actual sovereignty boundary.

Workers receive bounded evidence windows, treat broadcasts as untrusted quotations and have no tool-execution capabilities. Invalid/missing citation IDs or an unavailable endpoint produce a clearly marked extractive fallback. Citation validation checks IDs, **not factual entailment**. Model-generated analysis still requires human review. The no-model fallback selects source observations per channel; it is not LLM narrative reasoning.

## Security and deployment boundary

The supplied launcher and Compose bindings are for a trusted local workstation. Set `DIRA_API_TOKEN` to enable bearer protection on REST and authenticated WebSockets; enter it using Connection settings in the UI. Tokens stay in browser session storage and are sent in the first WebSocket message, not in URL logs. Origin checks, request-size limits, regex timeouts and bounded queues are implemented.

Before any remote deployment: require authentication, use a TLS reverse proxy and an approved identity/RBAC layer, enforce rate limits and network egress policies, protect the media server, restrict model endpoints, define retention/backups, and test throughput/failover on the intended channel count. This repository does not supply enterprise SSO/RBAC, HA clustering, Envoy policy enforcement or legal certification. Do not expose unauthenticated loopback defaults to an untrusted network.

## Test and measure

```bash
make test
uv run --no-sync python scripts/benchmark.py
# Requires running backend at localhost:8000 and Chrome (or Playwright Chromium):
cd frontend && npm run test:e2e
```

The automated suite exercises schema validation, normalization, spike statistics, named-vector retrieval, persistence/idempotency, warm outage recovery, explicit modality filtering, model compatibility, local-model fallback, job recovery, API/auth, WebSocket lifecycle, and FFmpeg→local ASR protocol flow. The ASR protocol test uses a controlled local server; it does not measure recognition accuracy. Browser tests exercise simulation controls, search/evidence, briefs, rules, RTL/mobile overflow and console errors.

See `docs/VERIFICATION.md` for observed results and unverified integrations. Benchmark output is synthetic local component timing, not satellite-to-alert latency, clinical/forensic accuracy, or a production SLA. The research document's vendor figures were not copied into product metrics.

## Repository map

```text
backend/dira/   schemas, configuration, runtime, API, vector/evidence storage,
               deterministic mechanics, model adapters, simulation, briefs
frontend/src/  React command center, WebSocket state, bilingual UI, HLS player
infra/         MediaMTX, feed example, isolated ASR container
scripts/       one-command startup and measured component benchmark
tests/         backend unit/integration and failure-recovery coverage
frontend/tests/ stream state tests and browser acceptance tests
```

## `master_skills` assessment

The seven files form an **agent-development kit**, not a Dira implementation specification. `AGENTS.md` is valuable process guidance but retains unfilled project `TODO`s; it is scoped to that subdirectory and was not blindly installed into the root. `CLAUDE.md` imports it for Claude; `MASTER-INSTRUCTIONS.md` documents the cross-agent setup. Superpowers, Ponytail, REA and Context7 are already available in this session.

`setup.sh`/`install.command` are useful for a new machine, but unnecessary for this build. Inspection found global skill replacement/configuration writes, a Context7 key passed in process arguments, and no backup of Context7 configuration before replacement. Its REA version check excludes the observed Node 24.9.0. The scripts were **not executed**, and global agent configuration was not changed. `.env.example` and `.gitignore` in that folder cover the kit's Context7 key only. The useful testing/review/minimal-code rules were applied within the user's autonomous build mandate.

## Integration references

- [Qdrant Python client](https://github.com/qdrant/qdrant-client): async named-vector upsert/query contracts.
- [Aurelio local execution](https://github.com/aurelio-labs/semantic-router/blob/main/docs/user-guide/guides/local-execution.md): offline routing integration.
- [WhisperLiveKit API](https://github.com/QuentinFuxa/WhisperLiveKit/blob/main/docs/API.md): PCM handshake, committed lines and stream completion.
- [PaddleOCR inference](https://www.paddleocr.ai/v3.6.0/en/version3.x/pipeline_usage/OCR.html): local model paths and OCR result fields.

## Operational safeguards

- `DIRA_ASR_MAX_LAG=90` rejects over-limit speech before ingest and reconnects that speech session. `DIRA_MEDIA_TIMEOUT=20` detects stalled PCM/video input. Reset counters persist, and `/api/gaps` exposes estimated coverage interruptions.
- OCR deduplicates normalized lines for 15 minutes, retains blur rejection and temporal voting, and skips nearly identical frames with periodic refresh. Alert cooldowns distinguish channel, rule and text; a bare breaking badge does not generate a critical alert.
- Briefs sample across time and channels and display sample coverage plus actual cited evidence. Citation checks are syntactic; they cannot prove the model's claims true.
- Cloud reasoning is disclosed in the UI. Scheduling is off unless `DIRA_CLOUD_AUTO_BRIEFS=true`; manual briefs still send evidence to the configured provider.
- External `/api/ingest` in live mode requires both `DIRA_ALLOW_EXTERNAL_INGEST=true` and a configured API token. API-submitted records are marked `external-api`; simulation submissions cannot impersonate live observations. Configure `DIRA_ALLOWED_HOSTS` explicitly for additional server hostnames.
- Search exposes cosine scores, an adjustable `min_similarity` floor (default 0.30), and deduplicated results. Scores are not confidence or proof of a claim. Lexical matching still scans a bounded 10,000-record candidate window.
- Service logs rotate at 10 MiB × four files per service. Evidence is not automatically deleted. See the [remediation ledger](docs/audits/2026-11-17-remediation.md) and [live verification](docs/audits/2026-11-17-remediation-live-soak.json).

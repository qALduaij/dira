# Primary acquisition and Apple Silicon operation

The six publisher HLS sources in `infra/primary-sources.json` are configured in `infra/mediamtx.yml` with **sourceOnDemand: no**. The optional extraction variant retains these continuous primary paths and adds secondary on-demand hooks. The offline demo uses `infra/mediamtx.offline.yml`.

| Path | Channel | Language | Native ASR |
| --- | --- | --- | --- |
| `aljazeera` | Al Jazeera | Arabic | 8001 |
| `alarabiya` | Al Arabiya | Arabic | 8001 |
| `alhadath` | Al Hadath | Arabic | 8001 |
| `sky_arabia` | Sky News Arabia | Arabic | 8001 |
| `asharq` | Asharq News | Arabic | 8001 |
| `sky_uk` | Sky News UK FAST | English | 8003 |

The supplied Asharq URL was verified as a media feed, not as proof of a separate Bloomberg channel identity. It is labeled Asharq. All six configured sources were read through MediaMTX as **1920×1080 H264 video and AAC audio** on 17 November 2026. This is a point-in-time connectivity and codec check, not an uptime guarantee or rights assessment.

The original supplied Al Arabiya host `live-alarabiya.net` failed DNS. The verified correction is `live.alarabiya.net`, preserving the remaining path. Original result: `docs/primary-source-verification.json`; correction evidence: `docs/alarabiya-source-correction.json`; final local RTSP results: `docs/mediahub-verification.json`.

## Start media and intelligence

```bash
make services-mac
```

The standalone `docker-compose.mac.yml` pins `linux/arm64`, keeps Qdrant persistence and loopback ports, and separates its data bridge from the media acquisition bridge. MediaMTX is based on the official **1.21.4** binary inside a Python image with trusted CA roots and the optional hook client. TLS verification remains enabled. The older scratch image lacked CA certificates; version 1.15.4 also rejected two real feeds during MPEG-TS probing. The tested version resolves these failures.

Public-source recording is **off** by default per path. Enable it deliberately after choosing retention/storage capacity. Routing is continuous while this stack runs. `docker compose -f docker-compose.mac.yml stop mediamtx` stops acquisition without removing stored data. `docker compose -f docker-compose.mac.yml up -d mediamtx` resumes it.

Provision a local multilingual embedding model and ASR profiles first; no model downloads happen automatically. See `docs/PERCEPTION_PROFILES.md`. Then configure `.env`:

```dotenv
DIRA_MODE=live
DIRA_DATA_DIR=.data-live
DIRA_QDRANT_URL=http://127.0.0.1:6333
DIRA_FEED_CONFIG=infra/primary-feeds.json
DIRA_EMBEDDING_MODEL=/absolute/path/to/local/multilingual-embedding-model
DIRA_ASR_URL=ws://127.0.0.1:8001/asr
DIRA_VIDEO_HWACCEL=auto
DIRA_FFMPEG_THREADS=1
```

Install `uv sync --frozen --extra semantic` (add `--extra perception` for OCR), then `make start`. The launcher preserves already installed optional extras. For a provisioned, built, disconnected machine, run `.venv/bin/uvicorn dira.api:app --host 127.0.0.1 --port 8000 --workers 1` directly; `make start` includes dependency/build steps and is not an offline installation procedure.

Keep Arabic ASR running on port 8001 and English on 8003. The Sky UK catalog entry overrides the default ASR endpoint. Each feed has a separate WebSocket/session. Concurrency and real-time factor must be measured with the supplied models before operational use. The shared runtime's encoder lock prevents simultaneous unbounded model inference.

`infra/primary-feeds.docker.json` contains container-reachable media URLs and browser-reachable HLS URLs. Native Metal inference is recommended. Container inference is CPU/CUDA only; the Mac profile does not claim MPS passthrough.

## Efficient demux and Sky News Arabia audio

Audio extraction selects `-map 0:a:0 -vn -ac 1 -ar 16000 -f s16le`. No language-tag selection is used. Sky News Arabia's source reports its shared audio as `eng`; the configured channel and TDO language remain `ar`. Probe evidence confirms a single audio rendition. MediaMTX exposes it as its first audio track.

The source HLS probe reported program **4** for Sky News Arabia's 1080p variant. If an operator intentionally reads that original HLS directly, this catalog mapping is supported:

```json
{"audio_program_id": 4, "audio_stream_index": 0}
```

It produces `-map 0:p:4:a:0`. A program number is **not an audio PID**, and programs can change. Local RTSP no longer carries MPEG-TS program tables, so putting `-map 0:p:4` on the RTSP reader is invalid. Dira rejects that configuration rather than silently losing audio. For the mandated local-router architecture, keep `audio_stream_index: 0` and omit `audio_program_id`.

OCR selects `-map 0:v:0 -an -vf 'fps=2,crop=in_w:in_h*0.20:0:in_h*0.80,scale=1280:144'`. The cropped RGB frame is passed directly to Laplacian rejection and OCR; it is never cropped twice. Decoder and filter threads are bounded. `DIRA_VIDEO_HWACCEL=auto` chooses VideoToolbox on native macOS and software elsewhere; choose `none` if a codec/device cannot use hardware decoding. PaddleOCR itself remains CPU inference. Optional full-scene tracking uses a separate 1 fps/640×360 reader only when its model is enabled, so a ticker crop cannot become the scene detector's input.

## Deterministic work and model boundaries

Aho-Corasick matches all normalized keyword patterns in one text pass, preserving overlapping rules and Arabic normalization. Regex gates retain their timeout. FAISS assigns observations to bounded semantic topics, then statistical counts compare the current window to completed baseline windows. FAISS hot retrieval, persistent Qdrant named vectors, metadata filtering and RRF remain local. Aurelio's local encoder/router is optional with `DIRA_ROUTER=aurelio`.

Generative calls remain in the asynchronous narrative and Morning Brief workers. The “90% mechanics / 10% reasoning” requirement is an architectural division, not a fabricated measured CPU/token percentage. Without a configured local LLM, briefs use the labeled extractive fallback.

## Connected acquisition versus air-gapped analysis

Internet HLS acquisition requires internet connectivity. A genuinely air-gapped analysis host cannot fetch those URLs simultaneously. Deploy acquisition on a separate authorized gateway and transfer approved media over the site's controlled mechanism; run analysis, vectors and pre-provisioned model endpoints locally. The supplied Mac networking separates service bridges and binds exposed ports to loopback; it does not enforce outbound isolation or a host-wide firewall. An internal-only Docker network suppressed Qdrant's host-published port on the tested Docker Desktop runtime, so the native development profile uses a normal bridge. Air-gap certification, media transfer policy and model integrity/accuracy validation are deployment work, not claimed by this repository.

The test machine is **Apple M2 Max, 64 GiB, arm64**. The configuration targets M5 Max through native Metal/MPS, VideoToolbox and bounded CPU workers. No M5-specific latency or throughput measurement is claimed.

## Repeat verification

```bash
# Live source manifests and codec inspection, no recording:
uv run --extra extraction python scripts/verify_primary_sources.py
# Temporary isolated MediaMTX container; all six local RTSP paths:
uv run --extra extraction python scripts/verify_mediahub.py
# Synthetic secondary extraction, with no real channel requests:
uv run --extra extraction python scripts/test_extraction_stack.py
```

The last test expects locally built `dira-extractor:local` and `dira-mediamtx-extraction:local` images; build them with their corresponding Dockerfiles first. It removes its temporary containers/network. Source verification scripts overwrite their JSON reports with the latest observations.

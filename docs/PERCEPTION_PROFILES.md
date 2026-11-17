# Local perception profiles

Verified against the published WhisperLiveKit **0.2.26**, qwen3-asr-causal **0.1.0**,
PaddleOCR **3.7.0**, and PaddlePaddle **3.3.1** distributions on 2026-11-17.
These profiles have now been provisioned and exercised on real streams on the
M2 Max. See [live activation, crash remediation and measured limits](LIVE_ACTIVATION.md).
M5 Max throughput and reference-transcript accuracy remain unmeasured.

| Workload | Runtime | Local models | Hardware |
| --- | --- | --- | --- |
| Arabic live ASR (default) | WLK `qwen3-streaming`, `windowed` | Qwen3-ASR-0.6B or 1.7B | Native PyTorch MPS / Metal; explicit CPU fallback |
| English causal ASR | WLK `qwen3-streaming`, `causal` | Qwen3-ASR-0.6B + matching 192-frame causal tower | Native MPS / Metal; CPU or CUDA if selected |
| Arabic chyron OCR | PaddleOCR detector + recognizer | PP-OCRv6 detector + `arabic_PP-OCRv5_mobile_rec` | CPU in the current Python integration |

The published causal tower is English-only. Its published fine-tune belongs to
the 0.6B model; applying it to 1.7B is invalid. Dira's launcher refuses Arabic
causal mode and verifies the 0.6B audio architecture. Arabic uses the windowed
backend until an Arabic causal tower is supplied and evaluated in a separate
profile. [WLK backend documentation](https://github.com/QuentinFuxa/WhisperLiveKit/blob/main/docs/backends.md),
[Qwen3-ASR-0.6B configuration](https://huggingface.co/Qwen/Qwen3-ASR-0.6B/blob/main/config.json).

PP-OCRv6 exists, but its official recognizer language list does **not** include
Arabic. PaddleOCR's Arabic selection uses the v5 Arabic recognizer. Combining a
v6 detector with that explicit local recognizer preserves v6 detection without
claiming a nonexistent v6 Arabic recognizer. Retain each model's original
`inference.yml` and its matching name. Actual Arabic ticker accuracy requires a
local broadcast benchmark. [Official model selection](https://github.com/PaddlePaddle/PaddleOCR/blob/main/paddleocr/_pipelines/ocr.py),
[OCR model/language documentation](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html).

## Native Apple Silicon ASR

Use a native arm64 Python 3.12 environment, separate from the Dira API. The
launcher never installs dependencies or downloads model weights. Provision the
environment while connected, or install from a transferred wheelhouse:

```bash
python3.12 -m venv .venv-asr
.venv-asr/bin/python -m pip install 'whisperlivekit[qwen3-streaming]==0.2.26' 'qwen3-asr-causal==0.1.0'
```

Keep the complete local Hugging Face snapshot, including tokenizer, processor,
configuration, and every weight shard. Resolve snapshot symlinks when copying
onto another machine. Example layout:

```text
models/
  qwen3-asr-0.6b/
    config.json
    preprocessor_config.json
    tokenizer_config.json
    tokenizer.json                 # or vocab.json + merges.txt
    model.safetensors              # or index JSON and every named shard
    ...                            # preserve the remaining snapshot files
  qwen3-causal/tower.safetensors    # local published 0.6B/192-frame tower
  ocr/
    det/                           # complete PP-OCRv6 inference export
      inference.yml
      inference.json
      inference.pdiparams
    rec/                           # complete arabic_PP-OCRv5_mobile_rec export
      inference.yml
      inference.json
      inference.pdiparams
```

Launch Arabic ASR from the repository root:

```bash
export DIRA_ASR_MODEL_DIR="$PWD/models/qwen3-asr-0.6b"
export DIRA_ASR_DEVICE=mps
export DIRA_ASR_LANGUAGE=ar
export DIRA_ASR_AUDIO_BACKEND=windowed
.venv-asr/bin/python scripts/start_asr.py --check
.venv-asr/bin/python scripts/start_asr.py
```

In a second terminal, keep the Arabic service running and launch the English causal profile on port 8003 (the Sky UK feed uses this port):

```bash
export DIRA_ASR_PORT=8003
export DIRA_ASR_LANGUAGE=en
export DIRA_ASR_AUDIO_BACKEND=causal
export DIRA_ASR_TOWER_CHECKPOINT="$PWD/models/qwen3-causal/tower.safetensors"
.venv-asr/bin/python scripts/start_asr.py --check
.venv-asr/bin/python scripts/start_asr.py
```

`--check` validates paths, nonempty files, shard references, package versions,
bundled Silero VAD, and device availability without loading ASR weights. It does
not validate weight contents, model accuracy, or inference throughput. An
incomplete local snapshot fails before WLK starts. The launcher forces
`HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, and
`HF_HUB_DISABLE_TELEMETRY=1`; it passes `--warmup-file ''` so the default remote
warmup audio is not fetched. It uses the actual WLK option `--model_dir` with an
underscore, and never passes a Hub identifier as a local model path.

Silero VAD/VAC remains enabled through WLK's defaults. WLK packages its Silero
ONNX/JIT assets, so a separate `torch.hub.load` or VAD model fetch is unnecessary.
The JIT VAD runs on CPU; Qwen inference runs on MPS. The launcher retains the
upstream two-second chunk and 200-step segment settings. Causal mode uses the
published 192-frame block and 15-second left context. These control bounded
streaming work; they are not a measured latency guarantee.
[Pinned CLI source](https://github.com/QuentinFuxa/WhisperLiveKit/blob/v0.2.26/whisperlivekit/parse_args.py),
[Silero loading source](https://github.com/QuentinFuxa/WhisperLiveKit/blob/v0.2.26/whisperlivekit/silero_vad_iterator.py).

By default the server listens on `127.0.0.1:8001`. Dira uses
`DIRA_ASR_URL=ws://127.0.0.1:8001/asr` and sends 16-kHz mono signed 16-bit
little-endian PCM. `--pcm-input` is set. The existing committed-line websocket
contract remains unchanged. `DIRA_ASR_HOST` and `DIRA_ASR_PORT` override the
listener; use a trusted private interface when connecting from containers.

MPS availability is checked explicitly; a missing GPU does not silently become
CPU inference. Set `DIRA_ASR_DEVICE=cpu` deliberately for fallback. The upstream
`auto` dtype selects float16 on MPS and float32 on CPU. Do not enable blanket
PyTorch CPU fallbacks or unlimited MPS allocation as a performance shortcut.
Measure real-time factor, commit latency, memory, and Arabic error rate before
increasing concurrent feeds.

WLK also publishes `qwen3-vllm-metal`, an **experimental** MLX decoder route.
It is not this launcher's default or a verified M5 Max optimization. That route
has its own `whisperlivekit[qwen3-vllm-metal]` dependency extra and
`--qwen3-vllm-metal-*` flags; benchmark it separately before substituting it.
Native MPS is the directly supported conservative route here.
[Qwen backend support](https://github.com/QuentinFuxa/WhisperLiveKit/blob/main/docs/backends.md).

## OCR on native macOS

Provision `paddleocr==3.7.0` and `paddlepaddle==3.3.1` into the Dira perception
environment with the rest of its dependencies. Supply `DIRA_OCR_MODEL_DIR` with
the complete `det/` and `rec/` exports above, then enable `DIRA_ENABLE_OCR=true`.
Use `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` before importing PaddleOCR to
skip PaddleX's network availability probe. This variable only skips the probe;
it is **not** a general download firewall. Both local model directories must be
validated, and document orientation, unwarping, and text-line orientation must
stay disabled to avoid implicit auxiliary models.

The matching PaddleOCR constructor arguments are
`text_detection_model_dir`, `text_recognition_model_dir`,
`text_detection_model_name`, `text_recognition_model_name`, and `device="cpu"`.
Model names must match their own `inference.yml` metadata; for example,
`PP-OCRv6_small_det` and `arabic_PP-OCRv5_mobile_rec`. Do not call this pair
`PP-OCRv6 Arabic`. Native PaddleOCR CPU inference is the honest fallback for the
current integration; no MPS device is asserted for its Paddle engine. A future
Core ML/ONNX accelerator would need explicit export, execution-provider, and
Arabic accuracy validation.
[PaddleOCR local-model API](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/OCR.en.md),
[PaddleX model source checks](https://github.com/PaddlePaddle/PaddleX/blob/develop/paddlex/utils/official_models.py).

## Containers and air-gapped deployment

`infra/Dockerfile.asr` is an explicit CPU fallback, not Apple GPU passthrough.
For native Metal, run ASR on the host and configure the containerized API to use
`ws://host.docker.internal:8001/asr`, with a host binding reachable from Docker.
For the container's own ASR process, mount models read-only, remove any old WLK
command override, and set:

```text
DIRA_ASR_MODEL_DIR=/models/qwen3-asr-0.6b
DIRA_ASR_DEVICE=cpu
DIRA_ASR_LANGUAGE=ar
DIRA_ASR_AUDIO_BACKEND=windowed
DIRA_ASR_HOST=0.0.0.0
```

Build/download dependencies on a connected staging machine of the same OS,
architecture, and Python version; transfer the complete wheelhouse, model
bundles, and container images where applicable. Record model revisions,
licenses, checksums, and `pip freeze` with the deployment. The top-level ASR
packages are pinned; transitive packages must be frozen in the deployment
wheelhouse for a fully reproducible install. Offline install example:

```bash
.venv-asr/bin/python -m pip install --no-index --find-links /approved/wheelhouse 'whisperlivekit[qwen3-streaming]==0.2.26' 'qwen3-asr-causal==0.1.0'
```

The Dockerfile's package installation is a build-time online operation unless
adapted to a transferred wheelhouse/base-image cache; build the image before
disconnecting. Runtime model paths and offline flags do not make a network
build air-gapped. Verify a deployment with external egress blocked, a local
speech replay, and a local Arabic chyron replay. Dependency/source inspection
and launcher validation alone cannot certify an end-to-end air-gap test.

Package records used for this profile:
[WhisperLiveKit 0.2.26](https://pypi.org/project/whisperlivekit/0.2.26/),
[qwen3-asr-causal 0.1.0](https://pypi.org/project/qwen3-asr-causal/0.1.0/),
[PaddleOCR 3.7.0](https://pypi.org/project/paddleocr/3.7.0/),
[PaddlePaddle 3.3.1](https://pypi.org/project/paddlepaddle/3.3.1/).

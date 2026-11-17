#!/usr/bin/env python3
"""Start pinned WhisperLiveKit with local Qwen3 weights; never fetch models."""

import argparse
import importlib.metadata
import json
import os
import platform
import shlex
import sys
from pathlib import Path


def local_file(path):
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"Required nonempty local file is missing: {path}")
    return path


def build_command(env):
    root_value = env.get("DIRA_ASR_MODEL_DIR", "")
    if not root_value:
        raise ValueError("Set DIRA_ASR_MODEL_DIR to a complete local Qwen3-ASR model directory")
    root = Path(root_value).expanduser().resolve()
    for name in ("config.json", "tokenizer_config.json", "preprocessor_config.json"):
        local_file(root / name)
    if not (root / "tokenizer.json").is_file():
        local_file(root / "vocab.json")
        local_file(root / "merges.txt")
    else:
        local_file(root / "tokenizer.json")
    index = root / "model.safetensors.index.json"
    if index.is_file():
        shards = set(json.loads(index.read_text())["weight_map"].values())
        if not shards:
            raise ValueError("Local weight index contains no shards")
        for shard in shards:
            candidate = (root / shard).resolve()
            if not candidate.is_relative_to(root):
                raise ValueError("Weight index references a file outside the model directory")
            local_file(candidate)
    else:
        local_file(root / "model.safetensors")
    config = json.loads((root / "config.json").read_text())
    if config.get("model_type") != "qwen3_asr":
        raise ValueError("DIRA_ASR_MODEL_DIR must contain a Qwen3-ASR model")
    language = env.get("DIRA_ASR_LANGUAGE", "ar")
    if not language or language == "auto":
        raise ValueError("Qwen3 streaming requires an explicit DIRA_ASR_LANGUAGE")
    backend = env.get("DIRA_ASR_AUDIO_BACKEND", "windowed")
    if backend not in {"windowed", "causal"}:
        raise ValueError("DIRA_ASR_AUDIO_BACKEND must be windowed or causal")
    device = env.get("DIRA_ASR_DEVICE", "mps")
    if device not in {"mps", "cpu", "cuda"}:
        raise ValueError("DIRA_ASR_DEVICE must be mps, cpu or cuda")
    port = int(env.get("DIRA_ASR_PORT", "8001"))
    if not 1 <= port <= 65535:
        raise ValueError("DIRA_ASR_PORT must be between 1 and 65535")
    chunk = float(env.get("DIRA_ASR_CHUNK_SEC", "2.0"))
    if not 0.5 <= chunk <= 10:
        raise ValueError("ASR chunk duration must be between 0.5 and 10 seconds")
    command = [
        sys.executable, "-m", "whisperlivekit.basic_server",
        "--host", env.get("DIRA_ASR_HOST", "127.0.0.1"), "--port", str(port),
        "--backend", "qwen3-streaming", "--model_dir", str(root),
        "--language", language, "--pcm-input", "--warmup-file", "",
        "--qwen3-streaming-device", device,
        "--qwen3-streaming-dtype", "auto",
        "--qwen3-streaming-audio-backend", backend,
        "--qwen3-streaming-chunk-sec", str(chunk),
        "--qwen3-streaming-segment-max-steps", "200",
        "--log-level", "INFO",
    ]
    if backend == "causal":
        if language not in {"en", "English"}:
            raise ValueError("The published causal tower is English-only; use windowed for Arabic")
        audio = config.get("thinker_config", {}).get("audio_config", {})
        if audio.get("d_model") != 896 or audio.get("encoder_layers") != 18:
            raise ValueError("This causal profile requires Qwen3-ASR-0.6B, matching the published tower")
        tower_value = env.get("DIRA_ASR_TOWER_CHECKPOINT", "")
        if not tower_value:
            raise ValueError("Causal mode requires a local DIRA_ASR_TOWER_CHECKPOINT file")
        tower = local_file(Path(tower_value).expanduser().resolve())
        if tower.suffix not in {".pt", ".safetensors"}:
            raise ValueError("Causal tower must be a local .pt or .safetensors file")
        command += [
            "--qwen3-streaming-tower-checkpoint", str(tower),
            "--qwen3-streaming-left-context-sec", "15",
            "--qwen3-streaming-block-frames", "192",
        ]
    return command, device


def check_runtime(device):
    for package, expected in (("whisperlivekit", "0.2.26"), ("qwen3-asr-causal", "0.1.0")):
        actual = importlib.metadata.version(package)
        if actual != expected:
            raise ValueError(f"Expected {package}=={expected}, found {actual}; use the documented ASR environment")
    distribution = importlib.metadata.distribution("whisperlivekit")
    local_file(Path(distribution.locate_file("whisperlivekit/silero_vad_models/silero_vad.jit")))
    import torch

    if device == "mps" and (
        platform.system() != "Darwin" or platform.machine() != "arm64" or not torch.backends.mps.is_available()
    ):
        raise ValueError("MPS requires native arm64 macOS with available PyTorch MPS; set DIRA_ASR_DEVICE=cpu for fallback")
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("DIRA_ASR_DEVICE=cuda requested but PyTorch CUDA is unavailable")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate local files/runtime and print command without loading weights")
    args = parser.parse_args()
    # Set before importing any inference libraries. Missing local assets fail closed.
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    try:
        command, device = build_command(os.environ)
        check_runtime(device)
    except (ValueError, OSError, KeyError, ImportError, importlib.metadata.PackageNotFoundError) as exc:
        parser.exit(2, f"ASR preflight failed: {exc}\n")
    if args.check:
        print(shlex.join(command))
    else:
        os.execv(sys.executable, command)


if __name__ == "__main__":
    main()

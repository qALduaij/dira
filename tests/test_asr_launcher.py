"""Launcher structure checks use placeholder files, never inference weights."""

import json
import runpy
import sys
from pathlib import Path

import pytest

build_command = runpy.run_path(str(Path(__file__).parents[1] / "scripts/start_asr.py"))["build_command"]


@pytest.fixture
def snapshot(tmp_path):
    root = tmp_path / "qwen model"
    root.mkdir()
    for name in ("tokenizer_config.json", "preprocessor_config.json", "tokenizer.json", "model.safetensors"):
        (root / name).write_text("placeholder")
    (root / "config.json").write_text(
        json.dumps(
            {
                "model_type": "qwen3_asr",
                "thinker_config": {"audio_config": {"d_model": 896, "encoder_layers": 18}},
            }
        )
    )
    return root


def flag(command, name):
    return command[command.index(name) + 1]


def test_arabic_windowed_uses_local_mps_pcm_and_keeps_vad(snapshot):
    command, device = build_command({"DIRA_ASR_MODEL_DIR": str(snapshot)})
    assert command[:3] == [sys.executable, "-m", "whisperlivekit.basic_server"]
    assert device == "mps"
    assert flag(command, "--model_dir") == str(snapshot.resolve())
    assert flag(command, "--backend") == "qwen3-streaming"
    assert flag(command, "--language") == "ar"
    assert flag(command, "--qwen3-streaming-audio-backend") == "windowed"
    assert flag(command, "--qwen3-streaming-device") == "mps"
    assert flag(command, "--warmup-file") == ""
    assert flag(command, "--host") == "127.0.0.1"
    assert "--pcm-input" in command
    assert not {"--no-vad", "--no-vac", "--qwen3-streaming-tower-checkpoint"}.intersection(command)


def test_english_causal_uses_matching_local_tower(snapshot):
    tower = snapshot.parent / "tower.safetensors"
    tower.write_text("placeholder")
    command, device = build_command(
        {
            "DIRA_ASR_MODEL_DIR": str(snapshot),
            "DIRA_ASR_LANGUAGE": "en",
            "DIRA_ASR_AUDIO_BACKEND": "causal",
            "DIRA_ASR_TOWER_CHECKPOINT": str(tower),
            "DIRA_ASR_DEVICE": "cpu",
            "DIRA_ASR_PORT": "8123",
        }
    )
    assert device == "cpu"
    assert flag(command, "--language") == "en"
    assert flag(command, "--qwen3-streaming-audio-backend") == "causal"
    assert flag(command, "--qwen3-streaming-tower-checkpoint") == str(tower.resolve())
    assert flag(command, "--qwen3-streaming-block-frames") == "192"
    assert flag(command, "--qwen3-streaming-left-context-sec") == "15"
    assert flag(command, "--port") == "8123"


def test_causal_rejects_arabic_and_missing_tower(snapshot):
    env = {"DIRA_ASR_MODEL_DIR": str(snapshot), "DIRA_ASR_AUDIO_BACKEND": "causal"}
    with pytest.raises(ValueError, match="English-only"):
        build_command(env)
    with pytest.raises(ValueError, match="DIRA_ASR_TOWER_CHECKPOINT"):
        build_command(env | {"DIRA_ASR_LANGUAGE": "en"})


@pytest.mark.parametrize("model_dir", ["", "Qwen/Qwen3-ASR-0.6B", "/nonexistent/dira-asr-model"])
def test_missing_snapshot_or_hub_id_fails(model_dir):
    with pytest.raises(ValueError):
        build_command({"DIRA_ASR_MODEL_DIR": model_dir})


@pytest.mark.parametrize("name", ["config.json", "tokenizer_config.json", "preprocessor_config.json", "model.safetensors"])
@pytest.mark.parametrize("empty", [False, True])
def test_incomplete_snapshot_fails(snapshot, name, empty):
    if empty:
        (snapshot / name).write_text("")
    else:
        (snapshot / name).unlink()
    with pytest.raises(ValueError, match="Required nonempty local file"):
        build_command({"DIRA_ASR_MODEL_DIR": str(snapshot)})


def test_missing_tokenizer_requires_complete_vocabulary_pair(snapshot):
    (snapshot / "tokenizer.json").unlink()
    env = {"DIRA_ASR_MODEL_DIR": str(snapshot)}
    with pytest.raises(ValueError, match="vocab.json"):
        build_command(env)
    (snapshot / "vocab.json").write_text("{}")
    with pytest.raises(ValueError, match="merges.txt"):
        build_command(env)
    (snapshot / "merges.txt").write_text("placeholder")
    build_command(env)


def test_sharded_snapshot_requires_every_shard(snapshot):
    (snapshot / "model.safetensors").unlink()
    (snapshot / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": {"first": "part1.safetensors", "last": "part2.safetensors"}})
    )
    (snapshot / "part1.safetensors").write_text("placeholder")
    env = {"DIRA_ASR_MODEL_DIR": str(snapshot)}
    with pytest.raises(ValueError, match="part2.safetensors"):
        build_command(env)
    (snapshot / "part2.safetensors").write_text("placeholder")
    build_command(env)


@pytest.mark.parametrize("escape", ["relative", "absolute", "symlink"])
def test_shard_cannot_escape_model_directory(snapshot, escape):
    outside = snapshot.parent / "outside.safetensors"
    outside.write_text("placeholder")
    if escape == "relative":
        shard = "../outside.safetensors"
    elif escape == "absolute":
        shard = str(outside.resolve())
    else:
        (snapshot / "linked.safetensors").symlink_to(outside)
        shard = "linked.safetensors"
    (snapshot / "model.safetensors.index.json").write_text(json.dumps({"weight_map": {"weight": shard}}))
    with pytest.raises(ValueError, match="outside the model directory"):
        build_command({"DIRA_ASR_MODEL_DIR": str(snapshot)})


def test_empty_weight_index_fails(snapshot):
    (snapshot / "model.safetensors.index.json").write_text('{"weight_map": {}}')
    with pytest.raises(ValueError, match="no shards"):
        build_command({"DIRA_ASR_MODEL_DIR": str(snapshot)})


def test_chunk_pacing_is_configurable_and_bounded(snapshot):
    env = {"DIRA_ASR_MODEL_DIR": str(snapshot), "DIRA_ASR_CHUNK_SEC": "4"}
    command, _ = build_command(env)
    assert flag(command, "--qwen3-streaming-chunk-sec") == "4.0"
    for invalid in ("0", "nan", "20"):
        with pytest.raises(ValueError, match="chunk"):
            build_command({**env, "DIRA_ASR_CHUNK_SEC": invalid})

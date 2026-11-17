"""Post-remediation adversarial tests (second audit, 2026-11-17).

Each xfail(strict=True) test states the CORRECT behaviour and fails today. Isolated: tmp_path stores, loopback
fixtures, mocked HTTP, no operator .env, no live services. Run:

    .venv/bin/python -m pytest -q -p no:cacheprovider -o asyncio_mode=auto \
        --rootdir=docs/audits/2026-11-17-post-remediation-artifacts \
        docs/audits/2026-11-17-post-remediation-artifacts/test_post_remediation_findings.py
"""

import asyncio
import json
import os
import shutil
import subprocess
import time
from types import SimpleNamespace

import httpx
import pytest
import websockets

from dira.briefs import generate_brief
from dira.config import Settings
from dira.ingest import audio_session, load_feeds
from dira.models import TDO, utcnow
from dira.runtime import Runtime
from dira.simulation import make_event
from dira.store import EvidenceStore, VectorStore


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key in list(os.environ):
        if key.startswith("DIRA_"):
            monkeypatch.delenv(key)


# --- P-01: one undecodable archive row blocks the whole warm-store outbox --------------------------------
@pytest.mark.xfail(strict=True, reason="P-01: flush() is all-or-nothing; a poison row is retried forever")
async def test_poison_row_does_not_block_outbox(tmp_path):
    db = EvidenceStore(tmp_path / "e.db")
    store = VectorStore(db, 4, qdrant_path=str(tmp_path / "q"), namespace="audit")
    await store.start()
    now = utcnow()
    for i in range(3):
        event = TDO(channel_id="c", start=now, end=now, transcript=f"line {i}")
        await store.add(event, {"transcript": [1.0, 0.0, 0.0, float(i)]})
    oldest = db.pending(1)[0][0]
    with db.lock, db.db:  # simulate one corrupted/legacy-incompatible payload (oldest => first in every batch)
        db.db.execute("UPDATE evidence SET vectors=? WHERE id=?", (b"XXXX", oldest))
    for _ in range(3):
        await store.flush()
    await store.close()
    assert db.counts()["pending"] == 1, "healthy rows must be archived; only the poison row may remain"


# --- P-07: "stratified" brief sample collapses to a few minutes when data is dense and recent -------------
@pytest.mark.xfail(strict=True, reason="P-07: fixed 24h buckets + newest-first within bucket cluster the sample")
def test_brief_sample_spreads_over_available_evidence(tmp_path):
    from datetime import timedelta

    db = EvidenceStore(tmp_path / "e.db")
    now = utcnow()
    for i in range(4 * 3600 // 2):  # 4 h of live-like density: one observation every 2 s, rotating 6 channels
        at = now - timedelta(seconds=2 * i)
        db.insert(TDO(channel_id=f"ch{i % 6}", start=at, end=at, transcript=f"line {i}"), {})
    events, coverage = db.brief_sample(now - timedelta(hours=24), now, 80)
    minutes = {int(e.start.timestamp() // 60) for e in events}
    assert len(minutes) >= 20, f"80 samples cover only {len(minutes)} distinct minutes of 240 available"


# --- P-08: a speech-side failure also kills and respawns the channel's OCR worker -------------------------
@pytest.mark.xfail(strict=True, reason="P-08: supervisor restarts frame/OCR session on any speech failure")
async def test_speech_failure_does_not_respawn_ocr(monkeypatch):
    import dira.ingest as ingest
    from dira.runtime import EventBus

    frame_starts, audio_calls = [], []

    async def audio(runtime, feed):
        audio_calls.append(1)
        await asyncio.sleep(0.05)
        raise TimeoutError("PCM stalled")  # e.g. a publisher hiccup on the audio path only

    async def frames(runtime, feed):
        frame_starts.append(1)  # in production: spawns a ~1.2 GB Paddle OCR worker (model load)
        await asyncio.Future()

    monkeypatch.setattr(ingest, "audio_session", audio)
    monkeypatch.setattr(ingest, "frame_session", frames)
    feed = {"id": "c"}
    runtime = SimpleNamespace(settings=Settings(enable_ocr=True), channels=[feed], bus=EventBus())
    task = asyncio.create_task(ingest.supervise_feed(runtime, feed))
    await asyncio.sleep(3.5)  # backoff 1 s + 2 s => three speech attempts
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert len(audio_calls) >= 3
    assert len(frame_starts) == 1, f"OCR session started {len(frame_starts)}x for {len(audio_calls)} speech failures"


# --- P-02: per-sentence citation check rejects ordinary abbreviations ------------------------------------
def _mock_llm(monkeypatch, content):
    real = httpx.AsyncClient

    def respond(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(**kw, transport=httpx.MockTransport(respond)))


@pytest.mark.xfail(strict=True, reason="P-02: 'U.S. officials' is split into an uncited sentence 'U.S.'")
async def test_abbreviation_with_citation_is_accepted(monkeypatch):
    event = make_event(1)
    _mock_llm(monkeypatch, f"- U.S. officials met Kuwaiti ministers [{event.id}].")
    settings = Settings(_env_file=None, llm_url="http://127.0.0.1:9/v1", llm_provider="local")
    brief = await generate_brief([event], "narrative", settings)
    assert brief.mode == "local-llm", brief.error


# --- P-03: egress policy trusts a self-declared provider label, not the endpoint host ---------------------
@pytest.mark.xfail(strict=True, reason="P-03: a remote URL labelled provider=local bypasses the cloud opt-in")
def test_remote_endpoint_is_treated_as_cloud(tmp_path):
    runtime = Runtime(
        Settings(data_dir=tmp_path, llm_url="https://openrouter.ai/api/v1", llm_provider="local")
    )
    assert not runtime.job_allowed({"trigger": "scheduled"}), "scheduled egress to a remote host needs opt-in"


# --- P-04: channel snapshots expose operator stream URLs (and any credentials inside them) ---------------
@pytest.mark.xfail(strict=True, reason="P-04: snapshot/WS 'channels' publish raw feed config incl. input_url")
async def test_snapshot_does_not_expose_stream_credentials(tmp_path):
    feeds = tmp_path / "feeds.json"
    feeds.write_text(json.dumps([{"id": "ktv", "name": "KTV", "input_url": "rtsp://operator:s3cret@10.0.0.5/live"}]))
    runtime = Runtime(Settings(data_dir=tmp_path, simulation_interval=100))
    await runtime.start(background=False)
    try:
        runtime.channels = load_feeds(feeds)
        assert "s3cret" not in json.dumps(runtime.snapshot(), default=str)
    finally:
        await runtime.stop()


# --- P-05: ASR timestamps are anchored to FFmpeg spawn time, not to the first audio sample ----------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not installed")
@pytest.mark.xfail(strict=True, reason="P-05: base clock starts before the source delivers audio")
async def test_asr_timestamp_tracks_first_audio_not_process_spawn(tmp_path):
    wav = tmp_path / "a.wav"
    await asyncio.to_thread(
        subprocess.run,
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=1", "-ar", "16000", str(wav)],
        check=True,
    )
    body = wav.read_bytes()

    async def slow_http(reader, writer):  # a source that takes 3 s to start delivering
        await reader.readuntil(b"\r\n\r\n")
        await asyncio.sleep(3)
        writer.write(b"HTTP/1.0 200 OK\r\nContent-Type: audio/wav\r\n\r\n" + body)
        await writer.drain()
        writer.close()

    first_audio = {}

    async def asr(ws):
        await ws.send(json.dumps({"type": "config", "useAudioWorklet": True}))
        async for data in ws:
            if data and "t" not in first_audio:
                first_audio["t"] = time.time()
                line = {"start": "0:00:00", "end": "0:00:01", "speaker": 1, "text": "اختبار التوقيت"}
                await ws.send(json.dumps({"lines": [line], "remaining_time_transcription": 0}))
            if not data:
                await ws.send(json.dumps({"type": "ready_to_stop"}))
                break

    events = []
    http = await asyncio.start_server(slow_http, "127.0.0.1", 0)
    async with http, websockets.serve(asr, "127.0.0.1", 0) as ws_server:
        url = f"http://127.0.0.1:{http.sockets[0].getsockname()[1]}/a.wav"
        port = ws_server.sockets[0].getsockname()[1]

        class Rt:
            settings = SimpleNamespace(asr_url=f"ws://127.0.0.1:{port}/asr", asr_max_lag=90, media_timeout=20)

            async def ingest(self, event):
                events.append(event)

        await asyncio.wait_for(audio_session(Rt(), {"id": "t", "input_url": url}), 20)
    assert events and abs(events[0].start.timestamp() - first_audio["t"]) < 1.0, (
        events[0].start.timestamp() - first_audio["t"] if events else None
    )


# --- P-06: a malformed (non-object) ASR message tears down the whole channel ------------------------------
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not installed")
@pytest.mark.xfail(strict=True, reason="P-06: payload.get on a JSON list raises AttributeError")
async def test_malformed_asr_message_is_ignored(tmp_path):
    wav = tmp_path / "a.wav"
    await asyncio.to_thread(
        subprocess.run,
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=0.5", "-ar", "16000", str(wav)],
        check=True,
    )

    async def asr(ws):
        await ws.send(json.dumps({"type": "config", "useAudioWorklet": True}))
        await ws.send("[]")
        async for data in ws:
            if not data:
                await ws.send(json.dumps({"type": "ready_to_stop"}))
                break

    async with websockets.serve(asr, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        rt = SimpleNamespace(settings=SimpleNamespace(asr_url=f"ws://127.0.0.1:{port}/asr", asr_max_lag=90))
        await asyncio.wait_for(audio_session(rt, {"id": "t", "input_url": str(wav)}), 10)

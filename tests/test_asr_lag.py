"""F-01: per-channel ASR lag is measured, shown, and bounded by a jump-to-live reset."""

import asyncio
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest
import websockets
from dira import ingest
from dira.config import Settings
from dira.ingest import ASRLag, ASRLagExceeded, audio_session
from dira.runtime import EventBus, Runtime


def drain(queue):
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def test_lag_follows_server_report_and_counts_prolonged_silence():
    lag = ASRLag(now=100.0, grace=10)
    assert lag.value(100.0) == 0
    lag.update({"remaining_time_transcription": 12.5}, 105.0)
    assert lag.value(105.0) == 12.5
    assert lag.value(115.0) == 12.5  # inside the grace period the server may have nothing new to say
    assert lag.value(125.0) == 22.5  # beyond it, silence from the server is lag
    lag.update({"lines": []}, 126.0)  # heartbeats without valid backlog must not conceal a stalled decoder
    assert lag.value(126.0) == 23.5


@pytest.mark.asyncio
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not installed")
@pytest.mark.parametrize(
    "reported, ceiling, resets",
    [(500.0, 90, True), (5.0, 90, False), (500.0, 0, False)],
    ids=["over-ceiling", "under-ceiling", "ceiling-disabled"],
)
async def test_audio_session_reports_lag_and_jumps_to_live(tmp_path, reported, ceiling, resets):
    wav = tmp_path / "audio.wav"
    await asyncio.to_thread(
        subprocess.run,
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=0.5", "-ar", "16000", str(wav)],
        check=True,
    )

    observations = []

    async def collect(event):
        observations.append(event)

    async def asr(ws):
        await ws.send(json.dumps({"type": "config", "useAudioWorklet": True}))
        reported_once = False
        async for data in ws:
            if not reported_once:
                await ws.send(json.dumps({"lines": [{"start": 0, "end": 0.1, "text": "committed speech"}], "remaining_time_transcription": reported}))
                reported_once = True
            if not data:
                await ws.send(json.dumps({"type": "ready_to_stop"}))
                break

    async with websockets.serve(asr, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        runtime = SimpleNamespace(
            ingest=collect, settings=SimpleNamespace(asr_url=f"ws://127.0.0.1:{port}/asr", asr_max_lag=ceiling)
        )
        feed = {"id": "test", "input_url": str(wav)}
        session = audio_session(runtime, feed)
        if resets:
            with pytest.raises(ASRLagExceeded) as caught:
                await asyncio.wait_for(session, 5)
            assert caught.value.lag == pytest.approx(reported, abs=1)
        else:
            await asyncio.wait_for(session, 5)
    assert feed["asr_lag_seconds"] == pytest.approx(reported, abs=1)
    assert len(observations) == (0 if resets else 1)


@pytest.mark.asyncio
async def test_lag_reset_restarts_speech_only_and_is_recorded(monkeypatch):
    calls, cancelled = [], []

    async def audio(runtime, feed):
        calls.append(1)
        if len(calls) == 1:
            raise ASRLagExceeded(120.0)
        await asyncio.Future()

    async def frames(runtime, feed, *_):
        try:
            await asyncio.Future()
        finally:
            cancelled.append(True)

    monkeypatch.setattr(ingest, "audio_session", audio)
    monkeypatch.setattr(ingest, "frame_session", frames)
    bus = EventBus()
    queue = bus.subscribe()
    feed = {"id": "aljazeera", "status": "connected"}
    runtime = SimpleNamespace(settings=Settings(enable_ocr=True), channels=[feed], bus=bus)
    task = asyncio.create_task(ingest.supervise_feed(runtime, feed))
    try:
        await asyncio.sleep(0.1)
        assert len(calls) == 2, "speech must restart immediately at the live edge"
        assert not cancelled, "OCR must keep running through a speech reset"
        assert feed["asr_resets"] == 1
        assert feed["asr_skipped_seconds"] == 120.0
        assert any(m["type"] == "channels" for m in drain(queue))
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_metrics_tick_republishes_channel_state(tmp_path):
    runtime = Runtime(Settings(data_dir=tmp_path, simulation_interval=100))
    await runtime.start(background=False)
    queue = runtime.bus.subscribe()
    task = asyncio.create_task(runtime.metrics_loop())
    try:
        await asyncio.sleep(0.05)
        assert "channels" in {m["type"] for m in drain(queue)}
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await runtime.stop()

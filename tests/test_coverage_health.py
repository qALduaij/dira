"""Coverage-health truthfulness (audit 2026-11-18, N-01/N-02/N-07): honest reset causes, host sleep, degraded ASR."""

import asyncio
import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest
import websockets
from dira import ingest
from dira import runtime as runtime_module
from dira.config import Settings
from dira.ingest import ASRHealth, ASRLag, ASRLagExceeded, asr_recovered, audio_session
from dira.models import Alert
from dira.runtime import EventBus, Runtime


# Reset cause classification -----------------------------------------------------------------------------------
def test_silent_server_is_classified_silent():
    # WhisperLiveKit pushes only on change, so a healthy session with nothing new is silent, not backlogged.
    lag = ASRLag(now=0.0)
    lag.update({"remaining_time_transcription": 0, "remaining_time_transcription_processing": 0}, 0.0)
    assert lag.value(106.0) > 90
    assert lag.cause(90) == "silent"


def test_steadily_growing_report_is_backlog():
    lag = ASRLag(now=0.0)
    for t in range(1, 101):
        lag.update({"remaining_time_transcription": t * 0.95}, float(t))
    assert lag.value(100.0) > 90
    assert lag.cause(90) == "backlog"


def test_report_jumping_faster_than_monotonic_time_is_wall_clock_jump():
    # WLK uses time(); after macOS sleep it reports the sleep duration as backlog (live: 1,061.6 s).
    lag = ASRLag(now=0.0)
    lag.update({"remaining_time_transcription": 1.0}, 1.0)
    lag.update({"remaining_time_transcription": 1061.6}, 2.0)
    assert lag.cause(90) == "wall_clock_jump"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not installed")
async def test_audio_session_bounds_estimate_by_session_age(tmp_path):
    wav = tmp_path / "audio.wav"
    await asyncio.to_thread(
        subprocess.run,
        ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=2", "-ar", "16000", str(wav)],
        check=True,
    )

    async def asr(ws):
        await ws.send(json.dumps({"type": "config", "useAudioWorklet": True}))
        reported = False
        async for _ in ws:  # keep draining audio like WLK, so the client's close frame is read promptly
            if not reported:
                await ws.send(json.dumps({"lines": [], "remaining_time_transcription": 1061.6}))
                reported = True

    async with websockets.serve(asr, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        runtime = SimpleNamespace(
            ingest=None, settings=SimpleNamespace(asr_url=f"ws://127.0.0.1:{port}/asr", asr_max_lag=90)
        )
        with pytest.raises(ASRLagExceeded) as caught:
            await asyncio.wait_for(audio_session(runtime, {"id": "t", "input_url": str(wav)}), 10)
    assert caught.value.cause == "wall_clock_jump"
    assert caught.value.lag == pytest.approx(1061.6, abs=1)
    assert caught.value.estimate < 10, "loss cannot exceed the time this session existed"


# Supervisor bookkeeping ---------------------------------------------------------------------------------------
def supervised(monkeypatch, audio):
    gaps, alerts = [], []

    async def frames(runtime, feed, *_):
        await asyncio.Future()

    async def record_gap(feed, reason, estimate, **_):
        gaps.append((reason, estimate))

    async def health_alert(feed, detail):
        alerts.append(detail)

    monkeypatch.setattr(ingest, "audio_session", audio)
    monkeypatch.setattr(ingest, "frame_session", frames)
    monkeypatch.setattr(ingest, "backoff", lambda delay: 0.01)
    feed = {"id": "aljazeera", "status": "connected", "asr_resets": 0, "asr_skipped_seconds": 0.0}
    runtime = SimpleNamespace(
        settings=Settings(), channels=[feed], bus=EventBus(), record_gap=record_gap, health_alert=health_alert
    )
    return feed, runtime, gaps, alerts


async def run_until(runtime, feed, condition):
    task = asyncio.create_task(ingest.supervise_feed(runtime, feed))
    try:
        for _ in range(200):
            if condition():
                break
            await asyncio.sleep(0.01)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_reset_records_cause_and_bounded_estimate(monkeypatch):
    calls = []

    async def audio(runtime, feed):
        calls.append(1)
        if len(calls) == 1:
            raise ASRLagExceeded(1061.6, "wall_clock_jump", 3.0)
        await asyncio.Future()

    feed, runtime, gaps, _ = supervised(monkeypatch, audio)
    await run_until(runtime, feed, lambda: len(calls) >= 2)
    assert ("asr_wall_clock_jump", 3.0) in gaps
    assert feed["asr_skipped_seconds"] == 3.0
    assert feed["asr_last_reset_cause"] == "wall_clock_jump"


async def test_clean_asr_session_end_records_coverage_gap(monkeypatch):
    calls = []

    async def audio(runtime, feed):
        calls.append(1)
        if len(calls) > 1:
            await asyncio.Future()  # first session ends normally (publisher EOF -> ready_to_stop)

    feed, runtime, gaps, _ = supervised(monkeypatch, audio)
    await run_until(runtime, feed, lambda: len(calls) >= 2)
    assert len(calls) >= 2
    assert ("asr_session_end", None) in gaps


async def test_repeated_resets_mark_asr_degraded_and_alert_once(monkeypatch):
    calls = []

    async def audio(runtime, feed):
        calls.append(1)
        if len(calls) <= 4:
            raise ASRLagExceeded(91.0, "backlog", 91.0)
        await asyncio.Future()

    feed, runtime, gaps, alerts = supervised(monkeypatch, audio)
    await run_until(runtime, feed, lambda: len(calls) >= 5)
    assert feed["asr_degraded"] is True
    assert feed["asr_status"] == "degraded"
    assert len(alerts) == 1, "one alert per degradation episode, not one per reset"
    assert [r for r, _ in gaps].count("asr_backlog") == 4


def test_degradation_window_cooldown_and_recovery():
    feed = {}
    health = ASRHealth(feed)
    assert health.reset(0.0) is False
    assert health.reset(10.0) is False
    assert health.reset(20.0) is True and feed["asr_degraded"] is True
    assert health.reset(30.0) is False  # cooldown
    assert asr_recovered(feed, 30.0 + 599) is False
    assert asr_recovered(feed, 30.0 + 600) is True and feed["asr_degraded"] is False
    # Resets spread beyond the 10-minute window do not degrade.
    feed2 = {}
    spread = ASRHealth(feed2)
    assert not any(spread.reset(t) for t in (0.0, 400.0, 800.0)) and not feed2.get("asr_degraded")


# Host sleep ---------------------------------------------------------------------------------------------------
async def test_host_sleep_records_one_gap_per_live_channel(tmp_path, monkeypatch):
    clock = {"wall": 1000.0, "mono": 50.0}
    monkeypatch.setattr(runtime_module, "wall_time", lambda: clock["wall"])
    monkeypatch.setattr(runtime_module, "monotonic", lambda: clock["mono"])
    rt = Runtime(Settings(data_dir=tmp_path, simulation_interval=100))
    await rt.start(background=False)
    try:
        rt.channels = [{"id": "a", "status": "connected"}, {"id": "b", "status": "simulated"}]
        clock["wall"] += 3
        clock["mono"] += 3
        assert await rt.check_host_sleep() == 0
        clock["wall"] += 903  # 900 s asleep: wall clock advanced, monotonic did not
        clock["mono"] += 3
        assert await rt.check_host_sleep() == pytest.approx(900)
        gaps = rt.db.objects("gap")
        assert [(g["channel_id"], g["reason"], g["bounds_estimated"]) for g in gaps] == [("a", "host_sleep", False)]
        assert gaps[0]["estimated_lost_seconds"] == pytest.approx(900)
    finally:
        await rt.stop()


async def test_health_alert_is_persisted_without_evidence_reference(tmp_path):
    rt = Runtime(Settings(data_dir=tmp_path, simulation_interval=100))
    await rt.start(background=False)
    try:
        queue = rt.bus.subscribe()
        await rt.health_alert({"id": "alarabiya"}, "3 speech resets in 10 min")
        stored = rt.db.objects("alert")
        assert stored[0]["kind"] == "health" and stored[0]["tdo_id"] is None
        assert Alert.model_validate(stored[0]).severity == "warning"
        assert queue.get_nowait()["type"] == "alert"
    finally:
        await rt.stop()

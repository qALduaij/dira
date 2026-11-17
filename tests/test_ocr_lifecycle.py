"""OCR worker lifecycle: independent speech/frame supervision, one long-lived worker per channel, safe exit.

Regression for docs/audits/2026-11-17-post-remediation-audit.md P-08/P-09 (48 OCR worker PIDs in 2 h for six
channels; native segfaults at worker interpreter shutdown). Isolated: fake workers, no Paddle, no live services.
"""

import asyncio
import json
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import dira.ingest as ingest
from dira.config import Settings
from dira.ocr_process import OCRProcess
from dira.runtime import EventBus

FRAME = b"\0" * (1280 * 144 * 3)
BACKEND = str(Path(__file__).resolve().parents[1] / "backend")


class FakeOCR:
    def __init__(self, starts, fail_first=False):
        starts.append(self)
        self.process = SimpleNamespace(returncode=None, pid=1000 + len(starts))
        self.stats, self.closed, self.fail_first = {"frames": 0}, False, fail_first

    async def extract(self, raw):
        if self.fail_first:
            self.fail_first = False
            self.process.returncode = -11
            raise RuntimeError("OCR worker exited")
        self.stats = {"frames": self.stats["frames"] + 1}
        return "headline"

    async def close(self):
        self.closed = True
        self.process.returncode = 0


def stub_runtime(feed):
    return SimpleNamespace(settings=Settings(enable_ocr=True), channels=[feed], bus=EventBus())


async def run_for(coro, seconds, feed):
    """Run a supervisor, return the feed state as it was while running, then stop it."""
    task = asyncio.create_task(coro)
    await asyncio.sleep(seconds)
    running = dict(feed)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    return running


@pytest.mark.asyncio
async def test_speech_failure_does_not_restart_frames(monkeypatch):
    frame_starts, audio_calls = [], []

    async def audio(runtime, feed):
        audio_calls.append(1)
        await asyncio.sleep(0.05)
        raise TimeoutError("PCM stalled")

    async def frames(runtime, feed, *_):
        frame_starts.append(1)
        await asyncio.Future()

    monkeypatch.setattr(ingest, "audio_session", audio)
    monkeypatch.setattr(ingest, "frame_session", frames)
    monkeypatch.setattr(ingest, "backoff", lambda delay: 0.01)
    feed = {"id": "c"}
    running = await run_for(ingest.supervise_feed(stub_runtime(feed), feed), 0.5, feed)
    assert len(audio_calls) >= 3
    assert len(frame_starts) == 1, f"frame session restarted {len(frame_starts)}x for speech failures"
    assert running["last_error_type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_frame_failure_does_not_restart_speech(monkeypatch):
    frame_starts, audio_calls = [], []

    async def audio(runtime, feed):
        audio_calls.append(1)
        await asyncio.Future()

    async def frames(runtime, feed, *_):
        frame_starts.append(1)
        await asyncio.sleep(0.05)
        raise TimeoutError("video stalled")

    monkeypatch.setattr(ingest, "audio_session", audio)
    monkeypatch.setattr(ingest, "frame_session", frames)
    monkeypatch.setattr(ingest, "backoff", lambda delay: 0.01)
    feed = {"id": "c", "status": "connected"}
    running = await run_for(ingest.supervise_feed(stub_runtime(feed), feed), 0.5, feed)
    assert len(frame_starts) >= 3
    assert len(audio_calls) == 1
    assert running["status"] == "connected", "a video-only failure must not mark speech degraded"
    assert running["ocr_status"] == "degraded"
    assert running["last_frame_error_type"] == "TimeoutError"
    assert feed["status"] == "stopped"


@pytest.mark.asyncio
async def test_ocr_worker_survives_frame_session_restarts(monkeypatch):
    starts, extracted = [], []

    async def start(*args):
        return FakeOCR(starts)

    async def audio(runtime, feed):
        await asyncio.Future()

    async def frames(runtime, feed, ocr):
        extracted.append(await ocr.extract(FRAME))
        raise TimeoutError("video stalled")  # e.g. a publisher hiccup on the video path

    monkeypatch.setattr(OCRProcess, "start", staticmethod(start))
    monkeypatch.setattr(ingest, "audio_session", audio)
    monkeypatch.setattr(ingest, "frame_session", frames)
    monkeypatch.setattr(ingest, "backoff", lambda delay: 0.01)
    feed = {"id": "c"}
    running = await run_for(ingest.supervise_feed(stub_runtime(feed), feed), 0.5, feed)
    assert len(extracted) >= 3
    assert len(starts) == 1, f"OCR model loaded {len(starts)}x across frame-session restarts"
    assert starts[0].closed, "the worker must be closed when the channel supervisor stops"
    assert running["ocr_worker_restarts"] == 0
    assert running["ocr_worker_pid"] == starts[0].process.pid
    assert feed["ocr_worker_pid"] is None


@pytest.mark.asyncio
async def test_ocr_worker_crash_restarts_once_after_backoff(monkeypatch):
    starts = []

    async def factory():
        return FakeOCR(starts, fail_first=not starts)

    monkeypatch.setattr(ingest, "backoff", lambda delay: 0.2)
    feed = {"id": "c"}
    worker = ingest.OCRWorker(feed, factory)
    with pytest.raises(RuntimeError):
        await worker.extract(FRAME)
    began = time.monotonic()
    assert await worker.extract(FRAME) == "headline"
    assert time.monotonic() - began >= 0.15, "restart must wait for the backoff"
    assert await worker.extract(FRAME) == "headline"
    assert len(starts) == 2
    assert feed["ocr_worker_restarts"] == 1
    assert feed["ocr_worker_pid"] == starts[1].process.pid
    assert worker.stats == {"frames": 2}
    await worker.close()
    assert starts[1].closed


@pytest.mark.asyncio
async def test_ocr_model_loads_are_serialised(monkeypatch):
    active, peak = [], []

    async def factory():
        active.append(1)
        peak.append(len(active))
        await asyncio.sleep(0.05)
        active.pop()
        return FakeOCR([])

    workers = [ingest.OCRWorker({"id": f"c{i}"}, factory) for i in range(4)]
    await asyncio.gather(*(w.extract(FRAME) for w in workers))
    assert max(peak) == 1, "at most one OCR model load may run at a time"


WORKER_STUB = """
import atexit, os, sys, types
stub = types.ModuleType("dira.ocr")
class ChyronOCR:
    stats = {}
    def __init__(self, *args, **kwargs):
        pass
    def extract(self, frame):
        return "headline"
stub.ChyronOCR = ChyronOCR
sys.modules["dira.ocr"] = stub
atexit.register(lambda: os.write(2, b"FINALIZERS-RAN"))  # stands in for native thread-pool teardown
sys.argv = ["dira.ocr_worker", "--model-dir", "m", "--detector", "d", "--recognizer", "r"]
import runpy
runpy.run_module("dira.ocr_worker", run_name="__main__")
"""


@pytest.mark.asyncio
async def test_worker_exits_cleanly_without_running_finalizers(tmp_path):
    script = tmp_path / "worker.py"
    script.write_text(textwrap.dedent(WORKER_STUB))
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={"PYTHONPATH": BACKEND},
    )
    assert json.loads(await asyncio.wait_for(process.stdout.readline(), 20))["ready"]
    worker = OCRProcess(process)
    assert await worker.extract(FRAME) == "headline"
    began = time.monotonic()
    await worker.close()
    assert time.monotonic() - began < 5
    assert process.returncode == 0
    assert b"FINALIZERS-RAN" not in await process.stderr.read()


@pytest.mark.asyncio
async def test_close_terminates_a_worker_that_ignores_eof():
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(60)", stdin=asyncio.subprocess.PIPE
    )
    worker = OCRProcess(process)
    worker.close_timeout = 0.2
    began = time.monotonic()
    await worker.close()
    assert time.monotonic() - began < 4
    assert process.returncode is not None


def test_feeds_initialise_ocr_counters(tmp_path):
    path = tmp_path / "feeds.json"
    path.write_text(json.dumps([{"id": "a", "name": "A", "input_url": "rtsp://127.0.0.1/a"}]))
    feed = ingest.load_feeds(path)[0]
    assert feed["ocr_unchanged_skips"] == 0
    assert feed["ocr_worker_restarts"] == 0
    assert feed["ocr_worker_pid"] is None

import asyncio
from collections import deque

import numpy as np
import pytest

from dira.perception import ChyronOCR, parse_asr_lines


def test_cumulative_asr_emits_only_new_committed_text():
    seen = {}
    first = {"start": "0:00:00", "end": "0:00:03", "speaker": 1, "text": "خبر من الكويت"}
    assert parse_asr_lines({"lines": [first]}, seen)[0]["text"] == first["text"]
    updated = {**first, "end": "0:00:06", "text": first["text"] + " عن أسعار النفط"}
    delta = parse_asr_lines({"lines": [updated]}, seen)
    assert delta[0]["text"] == "عن أسعار النفط"
    assert delta[0]["start"] == first["end"]
    assert parse_asr_lines({"lines": [updated]}, seen) == []


def test_stable_headline_survives_changing_stock_prices():
    class Engine:
        calls = 0

        def predict(self, frame):
            self.calls += 1
            return [{"rec_texts": [f"{self.calls}.25", "صندوق النقد يحذر"], "rec_scores": [0.99, 0.95]}]

    ocr = object.__new__(ChyronOCR)
    ocr.engine, ocr.threshold, ocr.history = Engine(), 0, deque(maxlen=3)
    frame = np.zeros((12, 12, 3), dtype=np.uint8)
    assert ocr.extract(frame) == ""
    assert ocr.extract(frame) == "صندوق النقد يحذر"


def test_ocr_clock_changes_do_not_repeat_headline():
    class Engine:
        times = iter(["12:00", "12:00", "12:01", "12:01"])

        def predict(self, frame):
            return [{"rec_texts": ["عاجل إغلاق الموانئ", next(self.times)], "rec_scores": [0.95, 0.99]}]

    ocr = object.__new__(ChyronOCR)
    ocr.engine, ocr.threshold, ocr.history = Engine(), 0, deque(maxlen=3)
    outputs = [ocr.extract(np.zeros((12, 12, 3))) for _ in range(4)]
    assert sum("عاجل" in text for text in outputs) == 1


@pytest.mark.asyncio
async def test_frame_read_failure_reaches_supervisor():
    from dira.ingest import latest_frames

    reader = asyncio.StreamReader()
    reader.set_exception(ConnectionResetError("source disconnected"))
    frames = latest_frames(reader, 3)
    with pytest.raises(ConnectionResetError):
        await asyncio.wait_for(anext(frames), 0.1)


def test_unmeasured_confidence_is_not_one_hundred_percent():
    from dira.models import TDO, utcnow

    assert TDO(channel_id="live", start=utcnow(), end=utcnow()).confidence is None


def test_asr_eviction_does_not_replay_full_session_history():
    seen = {}
    payload = {"lines": [{"start": i, "end": i + 1, "speaker": 1, "text": str(i)} for i in range(10001)]}
    assert len(parse_asr_lines(payload, seen)) == 10001
    assert parse_asr_lines(payload, seen) == []


def test_native_mac_thread_defaults_apply_before_numeric_imports(monkeypatch):
    import importlib
    import os
    import sys
    import dira

    monkeypatch.setattr(sys, "platform", "darwin")
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        monkeypatch.delenv(key, raising=False)
    importlib.reload(dira)
    assert os.environ["OMP_NUM_THREADS"] == "1"


def test_tests_do_not_use_operator_live_configuration():
    from dira.config import Settings

    settings = Settings()
    assert settings.mode == "simulation"
    assert settings.llm_url == ""
    assert settings.embedding_model == ""


@pytest.mark.asyncio
async def test_slow_frame_consumer_gets_latest_frame_and_eof():
    from dira.ingest import latest_frames

    reader = asyncio.StreamReader()
    reader.feed_data(b"aaa")
    frames = latest_frames(reader, 3)
    assert (await anext(frames))[0] == b"aaa"
    reader.feed_data(b"bbbcccddd")
    reader.feed_eof()
    await asyncio.sleep(0.01)
    assert (await anext(frames))[0] == b"ddd"
    with pytest.raises(asyncio.IncompleteReadError):
        await anext(frames)


@pytest.mark.asyncio
async def test_ocr_subprocess_protocol(monkeypatch):
    from dira.ocr_process import OCRProcess

    class Writer:
        data = b""

        def write(self, data):
            self.data += data

        async def drain(self):
            pass

        def close(self):
            pass

    class Process:
        returncode = None
        stdin = Writer()
        stdout = asyncio.StreamReader()

        async def wait(self):
            self.returncode = 0

    process = Process()
    process.stdout.feed_data(b'{"ready":true}\n{"text":"headline"}\n')

    async def spawn(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    ocr = await OCRProcess.start("models/ocr", "det", "rec", 1)
    assert await ocr.extract(b"pixels") == "headline"
    assert process.stdin.data == b"pixels"
    await ocr.close()
    assert process.returncode == 0

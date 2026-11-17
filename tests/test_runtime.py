import asyncio
import numpy as np
import pytest
from dira.config import Settings
from dira.runtime import Runtime, EventBus
from dira.models import SearchRequest
from dira.perception import sharpness, Tracker, parse_asr_lines
from dira.simulation import make_event


def test_blur_gate_and_tracker():
    assert sharpness(np.zeros((16, 16))) == 0
    checker = (np.indices((16, 16)).sum(axis=0) % 2) * 255
    assert sharpness(checker) > 100
    t = Tracker()
    first = t.update([{"name": "ship", "bbox": [0, 0, 10, 10]}], 1)
    second = t.update([{"name": "ship", "bbox": [1, 1, 11, 11]}], 2)
    assert first[0].track_id == second[0].track_id
    assert t.update([], 50) == []
    assert not t.tracks


def test_asr_committed_lines_dedup_and_silence():
    payload = {
        "lines": [
            {"start": 0, "end": 1, "text": "hello", "speaker": 1},
            {"start": 1, "end": 2, "text": "", "speaker": -2},
        ],
        "buffer_transcription": "partial",
    }
    seen = {}
    assert len(parse_asr_lines(payload, seen)) == 1
    assert parse_asr_lines(payload, seen) == []


@pytest.mark.asyncio
async def test_slow_subscriber_resync():
    bus = EventBus(queue_size=2)
    q = bus.subscribe()
    for i in range(5):
        bus.publish("tdo", {"i": i})
    assert q.qsize() <= 2
    events = [q.get_nowait() for _ in range(q.qsize())]
    assert any(e["type"] == "resync" for e in events)


@pytest.mark.asyncio
async def test_pipeline_search_brief_and_restart(tmp_path):
    settings = Settings(data_dir=tmp_path, simulation_interval=100)
    runtime = Runtime(settings)
    await runtime.start(background=False)
    e = make_event(3)
    assert await runtime.ingest(e)
    assert not await runtime.ingest(e)
    result = await runtime.search(SearchRequest(query=e.transcript[:20]))
    assert any(x["event"]["id"] == str(e.id) for x in result["results"])
    job = runtime.enqueue_brief("morning")
    await runtime.process_job(job)
    brief = runtime.db.objects("brief")[0]
    assert str(e.id) in brief["evidence_ids"]
    assert brief["mode"] == "extractive"
    await runtime.stop()
    again = Runtime(settings)
    await again.start(background=False)
    assert again.db.get(str(e.id)) is not None
    assert again.db.objects("brief")
    await again.stop()

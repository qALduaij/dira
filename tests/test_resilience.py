import asyncio
from datetime import timedelta
import numpy as np
import pytest
from dira.config import Settings
from dira.runtime import Runtime
from dira.models import TDO, SearchRequest, utcnow
from dira.simulation import make_event
from dira.store import EvidenceStore, VectorStore
from dira.briefs import generate_brief


@pytest.mark.asyncio
async def test_explicit_modality_excludes_other_text(tmp_path):
    r = Runtime(Settings(data_dir=tmp_path))
    await r.start(background=False)
    e = TDO(channel_id="test", start=utcnow(), end=utcnow(), transcript="uniquespokenword", ocr="")
    await r.ingest(e)
    result = await r.search(SearchRequest(query="uniquespokenword", modality="ocr", channel_id="test"))
    assert result["results"] == []
    await r.stop()


@pytest.mark.asyncio
async def test_warm_failure_retains_outbox_then_retries(tmp_path, monkeypatch):
    db = EvidenceStore(tmp_path / "db")
    store = VectorStore(db, dimension=2)
    await store.start()
    original = store.client.upsert

    async def unavailable(*a, **k):
        raise ConnectionError("simulated outage")

    monkeypatch.setattr(store.client, "upsert", unavailable)
    e = make_event(1)
    await store.add(e, {"transcript": [1.0, 0.0]})
    await store.flush()
    assert len(db.pending()) == 1
    assert not store.ready
    monkeypatch.setattr(store.client, "upsert", original)
    await store.flush()
    assert db.pending() == []
    assert store.ready
    await store.close()
    db.close()


@pytest.mark.asyncio
async def test_local_llm_unavailable_preserves_evidence():
    e = make_event(1)
    brief = await generate_brief([e], "morning", Settings(llm_url="http://127.0.0.1:1/v1"))
    assert brief.mode == "extractive"
    assert brief.error
    assert str(e.id) in brief.content


@pytest.mark.asyncio
async def test_live_supervisor_restarts_when_audio_ends(monkeypatch):
    import dira.ingest as ingest

    calls, cancelled = [], []

    async def audio(runtime, feed):
        calls.append(1)

    async def frames(runtime, feed, *_):
        try:
            await asyncio.Future()
        finally:
            cancelled.append(True)

    monkeypatch.setattr(ingest, "audio_session", audio)
    monkeypatch.setattr(ingest, "frame_session", frames)
    monkeypatch.setattr(ingest, "backoff", lambda delay: 0.01)

    class Bus:
        def publish(self, *args):
            pass

    class RuntimeStub:
        settings = Settings(enable_ocr=True)
        channels = []
        bus = Bus()

    task = asyncio.create_task(ingest.supervise_feed(RuntimeStub(), {"id": "test"}))
    try:
        await asyncio.sleep(0.1)
        # Speech restarts on its own; video/OCR (and its loaded model) keep running (audit P-08).
        assert len(calls) >= 2
        assert not cancelled
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert cancelled == [True]


@pytest.mark.asyncio
async def test_embedding_dimension_change_rejected(tmp_path):
    r = Runtime(Settings(data_dir=tmp_path, embedding_dimension=64))
    await r.start(background=False)
    await r.stop()
    changed = Runtime(Settings(data_dir=tmp_path, embedding_dimension=128))
    try:
        with pytest.raises(ValueError, match="Embedding model changed"):
            await changed.start(background=False)
    finally:
        changed.db.close()


@pytest.mark.asyncio
async def test_pending_brief_job_recovers_after_restart(tmp_path):
    r = Runtime(Settings(data_dir=tmp_path))
    await r.start(background=False)
    job = r.enqueue_brief("morning")
    await r.stop()
    again = Runtime(Settings(data_dir=tmp_path))
    await again.start(background=False)
    assert job["id"] in again.snapshot()["jobs"]
    assert again.jobs.qsize() == 1
    await again.stop()


@pytest.mark.asyncio
async def test_live_delivery_retries_same_observation(monkeypatch):
    from dira.ingest import deliver

    event = make_event(1)
    calls = []

    class R:
        async def ingest(self, e):
            calls.append(e.id)
            if len(calls) < 2:
                raise OverflowError("backpressure")

    await deliver(R(), event)
    assert calls == [event.id, event.id]


@pytest.mark.asyncio
async def test_independent_workspaces_do_not_share_warm_collections(tmp_path):
    a = Runtime(Settings(data_dir=tmp_path / "a"))
    b = Runtime(Settings(data_dir=tmp_path / "b"))
    await a.start(background=False)
    await b.start(background=False)
    assert a.vectors.collection != b.vectors.collection
    await a.stop()
    await b.stop()


@pytest.mark.asyncio
async def test_new_warm_target_requeues_existing_archive(tmp_path):
    db = EvidenceStore(tmp_path / "db")
    old = VectorStore(db, dimension=2, qdrant_path=str(tmp_path / "old"))
    await old.start()
    e = make_event(1, utcnow() - timedelta(hours=3))
    await old.add(e, {"transcript": [1.0, 0.0]})
    await old.flush()
    assert db.pending() == []
    await old.close()
    new = VectorStore(db, dimension=2, qdrant_path=str(tmp_path / "new"))
    await new.start()
    await new.flush()
    hits = await new.search([1.0, 0.0], "transcript", SearchRequest(query="archive"))
    assert [str(hit.id) for hit in hits] == [str(e.id)]
    await new.close()
    db.close()

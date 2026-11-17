from datetime import datetime, timedelta, timezone
import numpy as np
import pytest
from pydantic import ValidationError
from dira.models import TDO, Rule, SearchRequest
from dira.mechanics import GateEngine, SpikeDetector, rrf, normalize
from dira.store import EvidenceStore, HotIndex, VectorStore
from dira.embeddings import HashEncoder


def event(**kwargs):
    return TDO(
        channel_id="ktv1",
        start=datetime.now(timezone.utc),
        end=datetime.now(timezone.utc),
        transcript="Kuwait energy market",
        **kwargs,
    )


def test_tdo_rejects_naive_time_and_reversed_interval():
    with pytest.raises(ValidationError):
        TDO(channel_id="ktv1", start=datetime.now(), end=datetime.now())
    with pytest.raises(ValidationError):
        TDO(
            channel_id="ktv1",
            start=datetime.now(timezone.utc),
            end=datetime.now(timezone.utc) - timedelta(seconds=2),
        )


def test_gate_normalizes_arabic_and_bounds_regex():
    engine = GateEngine([Rule(name="Energy", pattern="النفط", kind="keyword")])
    e = event(ocr="ارتفاع أسعار النَّفْط")
    assert engine.evaluate(e)[0].rule_name == "Energy"
    assert normalize("إعْلان") == "اعلان"
    with pytest.raises(ValidationError):
        Rule(name="bad", pattern="(", kind="regex")


def test_rrf_deduplicates_per_list():
    result = rrf([["a", "a", "b"], ["b", "c"]])
    assert result[0][0] == "b"
    assert dict(result)["a"] == pytest.approx(1 / 61)


def test_spike_compares_current_window_to_prior_windows():
    d = SpikeDetector(window_seconds=10, baseline_windows=4, min_count=4, threshold=2)
    v = np.array([1.0, 0.0], dtype=np.float32)
    for stamp in [0, 10, 20, 30]:
        assert d.observe(v, stamp) is None
    results = [d.observe(v, 40 + i / 10) for i in range(7)]
    assert any(x is not None and x["z_score"] >= 2 for x in results)
    assert d.observe(v, 5) is None  # late data cannot rewind baseline


def test_persistence_is_idempotent_and_outbox_survives_restart(tmp_path):
    path = tmp_path / "evidence.db"
    db = EvidenceStore(path)
    e = event()
    vectors = {"transcript": [1.0, 0.0]}
    assert db.insert(e, vectors)
    assert not db.insert(e, vectors)
    db.close()
    db = EvidenceStore(path)
    assert db.get(str(e.id)).transcript == e.transcript
    assert len(db.pending(100)) == 1
    db.ack([str(e.id)])
    assert db.pending(100) == []
    db.close()


def test_hot_index_evicts_and_filters_before_top_k():
    hot = HotIndex(2, capacity=3)
    for i in range(6):
        e = event()
        e.channel_id = "other" if i % 2 else "ktv1"
        hot.add(e, {"transcript": [1.0, 0.0]})
    assert len(hot.records) == 3
    hits = hot.search([1.0, 0.0], "transcript", SearchRequest(query="x", channel_id="ktv1"))
    assert len(hits) == 1
    assert all(hot.records[x].channel_id == "ktv1" for x in hits)


@pytest.mark.asyncio
async def test_qdrant_named_vectors_and_retry(tmp_path):
    db = EvidenceStore(tmp_path / "db")
    store = VectorStore(db, dimension=64, qdrant_path=str(tmp_path / "qdrant"), capacity=2)
    await store.start()
    encoder = HashEncoder(64)
    ids = []
    for i in range(4):
        e = event()
        ids.append(str(e.id))
        await store.add(e, {"transcript": encoder.encode(e.transcript).tolist()})
    await store.flush()
    assert not db.pending(100)
    hits = await store.search(encoder.encode("energy").tolist(), "transcript", SearchRequest(query="energy"))
    assert set(ids) == {str(x.id) for x in hits}
    await store.close()
    db.close()

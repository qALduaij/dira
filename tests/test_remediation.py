import json
from datetime import timedelta
from collections import deque

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from dira.api import create_app
from dira.briefs import generate_brief
from dira.config import Settings
from dira.ingest import ASRLag
from dira.mechanics import GateEngine
from dira.models import Rule, SearchRequest, TDO, utcnow
from dira.perception import ChyronOCR, parse_asr_lines
from dira.simulation import make_event
from dira.store import EvidenceStore


def test_processing_backlog_cannot_be_hidden_by_legacy_zero():
    lag = ASRLag(0)
    lag.update(
        {
            "remaining_time_transcription": 0,
            "remaining_time_transcription_processing": 120,
            "remaining_time_transcription_policy": 10,
        },
        1,
    )
    assert lag.value(1) >= 130
    lag.update({"remaining_time_transcription": float("nan")}, 2)
    assert lag.value(2) >= 130


def test_vectors_are_compact_but_recoverable(tmp_path):
    from dira.store import decode_vectors

    db = EvidenceStore(tmp_path / "e.db")
    vector = {"ocr": np.random.default_rng(1).random(384).tolist()}
    e = make_event(1)
    db.insert(e, vector)
    raw = db.pending()[0][2]
    assert isinstance(raw, bytes) and len(raw) < 1800
    assert np.allclose(decode_vectors(raw)["ocr"], vector["ocr"])
    assert decode_vectors(json.dumps(vector)) == vector
    db.ack([str(e.id)])
    assert db.counts() == {"evidence": 1, "pending": 0}
    db.requeue_all()
    assert db.counts()["pending"] == 1
    db.close()


def test_brief_sampling_spans_time_and_channels(tmp_path):
    db = EvidenceStore(tmp_path / "e.db")
    now = utcnow()
    for hour in range(24):
        for channel in ("a", "b", "c"):
            for i in range(4):
                at = now - timedelta(hours=hour, seconds=i)
                db.insert(TDO(channel_id=channel, start=at, end=at, transcript=f"{channel} {hour} {i}"), {})
    events, coverage = db.brief_sample(now - timedelta(hours=24), now, 80)
    assert len(events) <= 80
    assert {e.channel_id for e in events} == {"a", "b", "c"}
    assert max(e.start for e in events) - min(e.start for e in events) > timedelta(hours=22)
    assert coverage["total_observations"] == 288
    assert coverage["sampled_observations"] == len(events)
    db.close()


@pytest.mark.asyncio
async def test_uncited_claim_rejected(monkeypatch):
    event = make_event(1)
    client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": f"- Observed [{event.id}]\n- Fabricated uncited claim."}}]
            },
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(**kw, transport=transport))
    brief = await generate_brief([event], "morning", Settings(llm_url="http://localhost:9"))
    assert brief.mode == "extractive"
    assert "citation" in brief.error.lower()


def test_ocr_rotating_headline_deduplicated():
    script = iter([["Headline"]] * 3 + [[]] * 3 + [["Headline"]] * 3)

    class Engine:
        def predict(self, frame):
            texts = next(script)
            return [{"rec_texts": texts, "rec_scores": [1] * len(texts)}]

    ocr = ChyronOCR.__new__(ChyronOCR)
    ocr.engine, ocr.threshold, ocr.history = Engine(), -1, deque(maxlen=3)
    frame = np.zeros((4, 4, 3))
    assert sum(bool(ocr.extract(frame)) for _ in range(9)) == 1


def test_alert_cooldown_and_bare_breaking_marker():
    gate = GateEngine([Rule(name="Breaking", pattern="عاجل", severity="critical")])
    now = utcnow()
    e = TDO(channel_id="a", start=now, end=now, ocr="عاجل")
    assert not gate.evaluate(e)
    e.ocr = "عاجل ارتفاع أسعار النفط"
    assert len(gate.evaluate(e)) == 1
    assert not gate.evaluate(e)
    e.ocr = "عاجل افتتاح ميناء جديد"
    assert len(gate.evaluate(e)) == 1


def test_lexical_stopwords_and_object_update_order(tmp_path):
    db = EvidenceStore(tmp_path / "e.db")
    e = make_event(1).model_copy(
        update={"transcript": "In the last ten years.", "ocr": "", "translation": ""}
    )
    db.insert(e, {})
    assert not db.lexical(SearchRequest(query="explosions in Sanaa"))
    db.save("alert", {"id": "old", "acknowledged": False})
    db.save("alert", {"id": "new", "acknowledged": False})
    db.save("alert", {"id": "old", "acknowledged": True})
    assert db.objects("alert")[0]["id"] == "new"
    db.close()


def test_host_and_external_evidence_provenance(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path, simulation_interval=100))) as client:
        assert client.get("/api/snapshot", headers={"Host": "attacker.example"}).status_code == 400
        e = make_event(1).model_copy(update={"simulated": False, "source": "whisperlivekit"})
        response = client.post("/api/ingest", json=e.model_dump(mode="json"))
        assert response.status_code == 201
        saved = client.get("/api/evidence/" + response.json()["id"]).json()
        assert saved["simulated"] and saved["source"] == "external-api"


def test_punctuation_is_not_speech():
    assert not parse_asr_lines({"lines": [{"start": 0, "end": 1, "text": "...،!"}]}, {})


@pytest.mark.asyncio
async def test_disk_guard_gap_persistence_and_arrival_clock(tmp_path):
    from dira.runtime import Runtime

    r = Runtime(Settings(data_dir=tmp_path))
    await r.start(background=False)
    try:
        observed = []
        r.spikes.observe = lambda vector, stamp: observed.append(stamp)
        await r.ingest(make_event(1, utcnow()))
        await r.ingest(make_event(2, utcnow() - timedelta(minutes=10)))
        assert observed[1] >= observed[0]
        await r.record_gap({"id": "a", "asr_resets": 2, "asr_skipped_seconds": 120}, "asr_lag_limit", 120)
        assert r.db.objects("gap")[0]["estimated_lost_seconds"] == 120
        r.disk_free_gb = 0
        with pytest.raises(OverflowError, match="disk reserve"):
            await r.ingest(make_event(3))
        assert r.metrics()["disk_guard_active"]
    finally:
        await r.stop()
    db = EvidenceStore(tmp_path / "evidence.db")
    assert db.object("feed_health", "a")["asr_resets"] == 2
    assert db.objects("gap")[0]["bounds_estimated"]
    db.close()


@pytest.mark.asyncio
async def test_video_watchdog_and_backpressure_lag_check():
    import asyncio
    from dira.ingest import latest_frames, deliver, ASRLagExceeded
    from types import SimpleNamespace

    frames = latest_frames(asyncio.StreamReader(), 3, timeout=0.01)
    with pytest.raises(TimeoutError):
        await anext(frames)
    await frames.aclose()
    calls = []

    async def full(event):
        calls.append(event)
        raise OverflowError()

    def check():
        if calls:
            raise ASRLagExceeded(100)

    with pytest.raises(ASRLagExceeded):
        await deliver(SimpleNamespace(ingest=full), make_event(1), check)
    assert len(calls) == 1


def test_ocr_import_does_not_load_native_search_libraries():
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            'import dira.ocr,sys; assert not ({"faiss", "torch", "sklearn"} & sys.modules.keys())',
        ],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr


def test_search_relevance_floor(tmp_path):
    from dira.store import HotIndex

    hot = HotIndex(2)
    hot.add(make_event(1), {"ocr": [1, 0]})
    assert not hot.search([0, 1], "ocr", SearchRequest(query="unrelated"))


@pytest.mark.asyncio
@pytest.mark.parametrize("opt_in", [False, True])
async def test_cloud_scheduler_requires_opt_in(tmp_path, monkeypatch, opt_in):
    import asyncio
    import dira.runtime as module

    runtime = module.Runtime(
        Settings(
            data_dir=tmp_path,
            llm_url="http://127.0.0.1:9",
            llm_provider="cloud",
            cloud_auto_briefs=opt_in,
            brief_hour=0,
        )
    )
    ticks = 0

    async def tick(seconds):
        nonlocal ticks
        ticks += 1
        if ticks > 1:
            raise asyncio.CancelledError()

    monkeypatch.setattr(module.asyncio, "sleep", tick)
    with pytest.raises(asyncio.CancelledError):
        await runtime.scheduler()
    assert runtime.jobs.qsize() == (1 if opt_in else 0)
    runtime.db.close()


def test_live_api_ingest_requires_both_opt_in_and_auth(tmp_path):
    for token, opt_in in [("", False), ("", True), ("secret", False)]:
        settings = Settings(
            data_dir=tmp_path,
            mode="live",
            embedding_model="/not-loaded",
            api_token=token,
            allow_external_ingest=opt_in,
        )
        client = TestClient(
            create_app(settings)
        )  # No lifespan/model initialization needed to test access gate.
        headers = {"Authorization": "Bearer secret"} if token else {}
        response = client.post("/api/ingest", json=make_event(1).model_dump(mode="json"), headers=headers)
        assert response.status_code == 403
        client.close()


@pytest.mark.asyncio
async def test_citation_on_first_sentence_does_not_license_following_claims(monkeypatch):
    event = make_event(1)
    client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": f"- Observed [{event.id}]. Fabricated claim. More fabricated claims."
                        }
                    }
                ]
            },
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(**kw, transport=transport))
    brief = await generate_brief([event], "morning", Settings(llm_url="http://localhost:9"))
    assert brief.mode == "extractive"


@pytest.mark.asyncio
async def test_ocr_deadline_covers_blocked_input_pipe():
    import asyncio
    from types import SimpleNamespace
    from dira.ocr_process import OCRProcess

    class BlockedWriter:
        def write(self, raw):
            pass

        async def drain(self):
            await asyncio.Future()

    process = SimpleNamespace(stdin=BlockedWriter(), stdout=asyncio.StreamReader())
    worker = OCRProcess(process)
    worker.exchange_timeout = 0.01
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(worker.extract(b"frame"), 0.1)
    # A caller deadline also raises TimeoutError; verify the worker's own deadline fired.
    assert worker.stats.get("timeouts") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("trigger", ["scheduled", None])
async def test_recovered_cloud_jobs_cannot_bypass_policy(tmp_path, monkeypatch, trigger):
    from dira.runtime import Runtime

    db = EvidenceStore(tmp_path / "evidence.db")
    job = {"id": "old-job", "kind": "morning", "status": "running"}
    if trigger:
        job["trigger"] = trigger
    db.save("job", job)
    db.close()
    runtime = Runtime(
        Settings(
            data_dir=tmp_path, llm_provider="cloud", llm_url="http://127.0.0.1:9", cloud_auto_briefs=False
        )
    )
    await runtime.start(background=False)
    try:
        assert runtime.jobs.empty()
        assert runtime.job_status["old-job"]["status"] == "failed"
    finally:
        await runtime.stop()

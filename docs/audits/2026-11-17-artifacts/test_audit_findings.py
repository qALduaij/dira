"""Devil's-advocate audit tests, 2026-11-17.

Each xfail(strict=True) test states the CORRECT behaviour and currently fails, documenting a confirmed defect.
When a fix lands, the test XPASSes, strict mode turns that into a failure, and the marker should be removed.
Run in isolation (not collected by `make test`):

    .venv/bin/python -m pytest -q -p no:cacheprovider docs/audits/2026-11-17-artifacts/test_audit_findings.py

No network, no live services, no operator .env: every store lives in pytest's tmp_path.
"""

import asyncio
import json
from collections import deque
from datetime import timedelta
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient

from dira import ingest as ingest_module
from dira.api import create_app
from dira.briefs import generate_brief
from dira.config import Settings
from dira.mechanics import SpikeDetector
from dira.models import TDO, SearchRequest, utcnow
from dira.perception import ChyronOCR
from dira.runtime import EventBus, Runtime
from dira.simulation import make_event
from dira.store import EvidenceStore


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    import os

    for key in list(os.environ):
        if key.startswith("DIRA_"):
            monkeypatch.delenv(key)


TOPIC = np.array([1.0, 0.0], dtype=np.float32)
OTHER = np.array([0.0, 1.0], dtype=np.float32)


def _baseline(d, base):
    for w in range(4):
        d.observe(TOPIC, base + w * 30)


def test_control_in_order_burst_spikes():
    """Control: the detector works when every observation arrives in timestamp order."""
    d, base = SpikeDetector(), 30_000_000
    _baseline(d, base)
    assert any(d.observe(TOPIC, base + 120 + i) for i in range(6))


@pytest.mark.xfail(strict=True, reason="F-03: SpikeDetector discards observations older than the newest one seen")
def test_delayed_asr_burst_still_counts():
    """Live order: a near-real-time OCR line on another topic arrives first; ASR for the burst arrives late."""
    d, base = SpikeDetector(), 30_000_000
    _baseline(d, base)
    d.observe(OTHER, base + 149)  # OCR, current wall clock
    assert any(d.observe(TOPIC, base + 120 + i) for i in range(6))  # ASR, minutes of lag compressed


@pytest.mark.xfail(strict=True, reason="F-02: a 24 h morning brief only receives the newest 80 observations")
async def test_morning_brief_spans_reporting_window(tmp_path):
    r = Runtime(Settings(data_dir=tmp_path, simulation_interval=100))
    await r.start(background=False)
    try:
        now = utcnow()
        for i in range(240):  # one observation every 6 minutes for 24 h
            await r.ingest(make_event(i, now - timedelta(minutes=6 * i)))
        job = {"id": "audit", "kind": "morning", "status": "queued"}
        await r.process_job(job)
        brief = next(b for b in r.db.objects("brief") if b["id"] == job["brief_id"])
        starts = [r.db.get(k).start for k in brief["evidence_ids"]]
        assert (max(starts) - min(starts)) >= timedelta(hours=12)
    finally:
        await r.stop()


@pytest.mark.xfail(strict=True, reason="F-07: one valid citation lets every other uncited claim through")
async def test_uncited_claims_are_rejected(monkeypatch):
    event = make_event(1)
    fabricated = (
        f"- Observed coverage of the topic [{event.id}]\n"
        "- The Kuwaiti cabinet resigned this morning.\n"  # no evidence anywhere
        "- Oil exports from Kuwait were halted.\n"
    )
    real_client = httpx.AsyncClient

    def respond(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": fabricated}}]})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real_client(**kw, transport=httpx.MockTransport(respond))
    )
    settings = Settings(_env_file=None, llm_url="http://127.0.0.1:9/v1", llm_provider="local")
    brief = await generate_brief([event], "narrative", settings)
    assert brief.mode == "extractive", "a brief with uncited factual bullets must not be presented as LLM analysis"


class _FakeEngine:
    def __init__(self, script):
        self.script = iter(script)

    def predict(self, roi):
        texts = next(self.script)
        return [{"rec_texts": texts, "rec_scores": [0.99] * len(texts)}]


@pytest.mark.xfail(strict=True, reason="F-04: a ticker that disappears for 3 frames is emitted again as new evidence")
def test_rotating_headline_is_not_new_evidence():
    script = [["عاجل"]] * 3 + [[]] * 3 + [["عاجل"]] * 3 + [[]] * 3 + [["عاجل"]] * 3
    ocr = ChyronOCR.__new__(ChyronOCR)
    ocr.engine, ocr.threshold, ocr.history = _FakeEngine(script), -1, deque(maxlen=3)
    frame = np.random.default_rng(0).integers(0, 255, (144, 1280, 3), dtype=np.uint8)
    emitted = [ocr.extract(frame) for _ in script]
    assert sum(1 for t in emitted if t) == 1, emitted


@pytest.mark.xfail(strict=True, reason="F-10: lexical lane scores stop-word overlap and outweighs vector lanes")
def test_stopword_only_overlap_is_not_a_lexical_hit(tmp_path):
    store = EvidenceStore(tmp_path / "e.db")
    noise = TDO(channel_id="sky_uk", start=utcnow(), end=utcnow(), language="en", transcript="In the last ten years.")
    store.insert(noise, {})
    hits = store.lexical(SearchRequest(query="explosions in Sanaa"))
    assert noise.id not in {h.id for h in hits}


@pytest.mark.xfail(strict=True, reason="F-11: unauthenticated clients can store records marked as live evidence")
def test_client_cannot_forge_live_evidence(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, simulation_interval=100))
    with TestClient(app) as c:
        now = utcnow().isoformat()
        forged = {
            "channel_id": "ktv1", "start": now, "end": now, "transcript": "عاجل: حل مجلس الأمة",
            "simulated": False, "source": "whisperlivekit",
        }
        response = c.post("/api/ingest", json=forged)
        if response.status_code == 201:
            stored = c.get(f"/api/evidence/{response.json()['id']}").json()
            assert stored["simulated"] or stored["source"] != "whisperlivekit"


@pytest.mark.xfail(strict=True, reason="F-11: no Host validation; DNS-rebinding reads succeed without a token")
def test_foreign_host_header_is_rejected(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, simulation_interval=100))
    with TestClient(app) as c:
        assert c.get("/api/snapshot", headers={"Host": "rebind.attacker.example:8000"}).status_code in (400, 403)


@pytest.mark.xfail(strict=True, reason="F-06: the recovered 'connected' state is never published to browsers")
async def test_reconnected_channel_state_is_published(monkeypatch):
    feed = {"id": "aljazeera", "status": "connecting"}
    runtime = SimpleNamespace(
        settings=SimpleNamespace(enable_ocr=False, visual_model=""), bus=EventBus(), channels=[feed]
    )
    published, original = [], runtime.bus.publish

    def record(kind, data):  # the bus passes a live reference; copy the state at publish time
        if kind == "channels":
            published.append(json.loads(json.dumps(data))[0]["status"])
        original(kind, data)

    runtime.bus.publish = record
    calls = {"n": 0}

    async def fake_audio(rt, f):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient upstream failure")
        f["status"] = "connected"
        await asyncio.Event().wait()

    monkeypatch.setattr(ingest_module, "audio_session", fake_audio)
    task = asyncio.create_task(ingest_module.supervise_feed(runtime, feed))
    await asyncio.sleep(1.5)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    # Browsers saw 'degraded'; the later recovery to 'connected' never reaches them.
    assert published and published[-1] == "connected", published

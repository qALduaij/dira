"""2026-11-18 audit: focused reproductions. Production code is unchanged.

Strict xfail = the test asserts the CORRECT behaviour and currently fails; it flips to XPASS (a failure under
strict mode) once fixed. Tests without xfail pin behaviour the report relies on (N-02/N-07 updated after the 2026-11-18 fix).

Run (isolated: tmp_path storage, no network beyond loopback, operator .env never read):
  .venv/bin/python -m pytest -q -p no:cacheprovider -o asyncio_mode=auto \
    --rootdir=docs/audits/2026-11-18-artifacts docs/audits/2026-11-18-artifacts/test_2026_11_18_findings.py
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pytest
from dira import ingest
from dira.config import Settings
from dira.ingest import ASRLag
from dira.mechanics import GateEngine, SpikeDetector
from dira.models import TDO, Rule, SearchRequest
from dira.runtime import EventBus
from dira.store import EvidenceStore


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key in list(os.environ):
        if key.startswith("DIRA_"):
            monkeypatch.delenv(key)


def unit(seed, dim=64):
    v = np.random.default_rng(seed).normal(size=dim).astype(np.float32)
    return v / np.linalg.norm(v)


# N-03 ---------------------------------------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="N-03: FIFO eviction drops an ACTIVE topic after 128 newer topics")
def test_active_spike_topic_survives_unrelated_topic_churn():
    """Live replay: a new topic every 0.9 s, so 128 topics last ~1.9 min; the 12-window baseline is unreachable."""
    detector = SpikeDetector()
    story = unit(0)
    t = 0.0
    for window in range(6):  # a steady story: 1 observation per 30 s window for 3 minutes
        detector.observe(story, t)
        for i in range(30):  # ...amid unrelated one-off texts, as on live channels (~1 new topic per second)
            detector.observe(unit(1000 + window * 100 + i), t + 0.5 + i * 0.9)
        t += 30
    survivors = [x for x in detector.topics if float(x["centroid"] @ story) > 0.99]
    assert survivors and len(survivors[0]["history"]) >= 5, "the active story lost its baseline"


# N-05 ---------------------------------------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="N-05: lexical lane has no Arabic clitic handling (و/ب/ل/ال prefixes)")
def test_lexical_matches_arabic_prefixed_forms(tmp_path):
    store = EvidenceStore(tmp_path / "e.db")
    now = datetime.now(UTC)
    event = TDO(channel_id="alarabiya", start=now, end=now, transcript="وصل الوزير بالكويت صباح اليوم")
    store.insert(event, {"transcript": [0.0] * 4})
    hits = store.lexical(SearchRequest(query="الكويت"))
    assert [str(e.id) for e in hits] == [str(event.id)]


def test_lexical_window_is_row_bounded_not_time_bounded(tmp_path):
    """Characterization: an exact-match row older than the newest 10,000 rows is invisible to the lexical lane.
    At the measured live rate (~5,250 rows/h) that is ~1.8-1.9 h of history (see report §4)."""
    store = EvidenceStore(tmp_path / "e.db")
    base = datetime.now(UTC) - timedelta(hours=3)
    target = TDO(channel_id="kwt", start=base, end=base, transcript="رئيس مجلس الأمة")
    store.insert(target, {"transcript": [0.0] * 4})
    with store.lock, store.db:
        store.db.executemany(
            "INSERT INTO evidence VALUES (?,?,?,?,?,?,0)",
            [
                (f"r{i}", base.timestamp() + 1 + i, base.timestamp() + 1 + i, "kwt",
                 TDO(channel_id="kwt", start=base, end=base, transcript=f"filler {i}").model_dump_json(), "[]")
                for i in range(10_000)
            ],
        )
    assert store.lexical(SearchRequest(query="مجلس الأمة")) == []


# N-06 ---------------------------------------------------------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="N-06: keyword gates match substrings, not words")
def test_english_keyword_requires_word_boundary():
    gates = GateEngine([Rule(name="Energy (EN)", pattern="oil", severity="critical")])
    now = datetime.now(UTC)
    alerts = gates.evaluate(TDO(channel_id="sky_uk", start=now, end=now, transcript="political turmoil in the region"))
    assert alerts == []


@pytest.mark.xfail(strict=True, reason="P-10 (still open): one-character OCR variants of a station promo bypass cooldown")
def test_promo_variants_share_one_cooldown():
    gates = GateEngine([Rule(name="Breaking coverage", pattern="عاجل", severity="critical")])
    now = datetime.now(UTC)
    variants = [
        "تابعوا أحدث الأخبار لحظة ورودها على حسابنا للأخبار العاجلة",
        "تابعوا أحدث الأخبار لحظة ورودها على حسابنا للأخبارالعاجلة",
        "تابعوا أحدث الأخبار لحظة ورودها على حسابنا للأخبار العاجلة 1",
    ]
    fired = [gates.evaluate(TDO(channel_id="asharq", start=now, end=now, ocr=v)) for v in variants]
    assert sum(len(a) for a in fired) <= 1


# N-07 ---------------------------------------------------------------------------------------------------------
# N-07 fixed on 2026-11-18 (tests/test_coverage_health.py); kept as a passing regression.
async def test_clean_asr_session_end_records_coverage_gap(monkeypatch):
    calls, gaps = [], []

    async def audio(runtime, feed):
        calls.append(1)
        if len(calls) > 1:
            await asyncio.Future()  # second session stays up
        # first session ends normally, e.g. publisher EOF -> b"" -> WLK ready_to_stop

    async def frames(runtime, feed, *_):
        await asyncio.Future()

    async def record_gap(feed, reason, estimate):
        gaps.append(reason)

    monkeypatch.setattr(ingest, "audio_session", audio)
    monkeypatch.setattr(ingest, "frame_session", frames)
    monkeypatch.setattr(ingest, "backoff", lambda delay: 0.01)
    feed = {"id": "aljazeera", "status": "connected"}
    runtime = SimpleNamespace(settings=Settings(), channels=[feed], bus=EventBus(), record_gap=record_gap)
    task = asyncio.create_task(ingest.supervise_feed(runtime, feed))
    try:
        for _ in range(100):
            if len(calls) >= 2:
                break
            await asyncio.sleep(0.01)
        assert len(calls) >= 2, "speech did not restart"
        assert gaps, "the interval between sessions is a coverage interruption but nothing was recorded"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


# N-02 ---------------------------------------------------------------------------------------------------------
def test_server_silence_is_classified_silent():
    """WhisperLiveKit pushes only when its response changes (results_formatter `should_push`). Before the
    2026-11-18 fix this reset was booked as `asr_lag_limit` with a 90 s loss; it now carries cause `silent`
    (gap reason `asr_silent`) and a loss bounded by session age."""
    lag = ASRLag(now=0.0)  # default 15 s grace
    lag.update({"remaining_time_transcription": 0, "remaining_time_transcription_processing": 0}, 0.0)
    assert lag.value(104.0) < 90
    assert lag.value(106.0) > 90  # reset fires although the server never reported any backlog
    assert lag.cause(90) == "silent"


def test_wall_clock_jump_is_classified():
    """WLK computes remaining_time_transcription from time() (wall clock), which advances during macOS sleep.
    Before the 2026-11-18 fix the inflated value was booked verbatim as loss (live max 1,061.6 s); it is now
    cause `wall_clock_jump`, and audio_session bounds the estimate by the session's monotonic age."""
    lag = ASRLag(now=0.0)
    lag.update({"remaining_time_transcription": 1061.6}, 1.0)
    assert lag.value(1.0) == pytest.approx(1061.6)
    assert lag.cause(90) == "wall_clock_jump"

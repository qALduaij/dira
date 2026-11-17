import json
import shutil
import subprocess

import numpy as np
import pytest
from dira.ingest import audio_map, load_feeds, video_filter
from dira.mechanics import GateEngine, SpikeDetector
from dira.models import TDO, Rule, utcnow
from dira.perception import ChyronOCR


def test_explicit_audio_maps_do_not_depend_on_language_tags(tmp_path):
    assert audio_map({"audio_stream_index": 0}) == "0:a:0"
    assert audio_map({"audio_stream_index": 1, "audio_program_id": 42}) == "0:p:42:a:1"
    path = tmp_path / "feeds.json"
    path.write_text(
        json.dumps(
            [{"id": "sky", "name": "Sky", "input_url": "rtsp://127.0.0.1/sky", "audio_program_id": 42}]
        )
    )
    with pytest.raises(ValueError, match="program"):
        load_feeds(path)
    with pytest.raises(ValueError):
        audio_map({"audio_stream_index": -1})


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg required")
def test_ocr_track_has_two_bottom_crops_per_second():
    # White lower fifth, black elsewhere: including the full frame would dilute the mean.
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=black:s=320x180:r=10:d=1,drawbox=x=0:y=144:w=320:h=36:color=white:t=fill",
        "-vf",
        video_filter("ocr"),
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    result = subprocess.run(command, capture_output=True, check=True, timeout=10)
    frames = np.frombuffer(result.stdout, dtype=np.uint8).reshape(-1, 144, 1280, 3)
    assert len(frames) == 2
    assert frames.mean() > 250


def test_ocr_consumes_entire_precropped_ticker():
    seen = []

    class Engine:
        def predict(self, roi):
            seen.append(roi.shape)
            return [{"rec_texts": ["خبر عاجل"], "rec_scores": [0.99]}]

    from collections import deque

    ocr = object.__new__(ChyronOCR)
    ocr.engine, ocr.threshold, ocr.history = Engine(), 0, deque(maxlen=3)
    frame = np.zeros((144, 1280, 3), dtype=np.uint8)
    assert ocr.extract(frame) == ""
    assert ocr.extract(frame) == "خبر عاجل"
    assert seen == [(144, 1280, 3), (144, 1280, 3)]


def test_incomplete_ocr_exports_fail_before_model_initialization(tmp_path):
    (tmp_path / "det").mkdir()
    (tmp_path / "rec").mkdir()
    with pytest.raises(ValueError, match="local OCR export"):
        ChyronOCR(tmp_path)


def test_keyword_automaton_preserves_duplicates_overlaps_and_channel_filters():
    rules = [
        Rule(name="Arabic", pattern="إعلان", kind="keyword"),
        Rule(name="Same normalized", pattern="اعلان", kind="keyword"),
        Rule(name="Overlap", pattern="اعلان هام", kind="keyword"),
        Rule(name="Other channel", pattern="اعلان", kind="keyword", channel_id="other"),
    ]
    engine = GateEngine(rules)
    event = TDO(channel_id="sky", start=utcnow(), end=utcnow(), transcript="إعلان هام إعلان هام")
    assert [a.rule_name for a in engine.evaluate(event)] == ["Arabic", "Same normalized", "Overlap"]
    assert engine.keywords.kind == 2  # compiled Aho-Corasick automaton, not a repeated per-rule scan
    assert GateEngine([]).evaluate(event) == []


def test_faiss_topic_eviction_keeps_centroid_indices_aligned():
    detector = SpikeDetector(max_topics=2)
    for n, vector in enumerate(np.eye(3, dtype=np.float32)):
        detector.observe(vector, n)
    detector.observe(np.array([0, 1, 0], dtype=np.float32), 3)
    assert len(detector.topics) == detector.index.ntotal == 2
    assert detector.topics[0]["count"] == 2

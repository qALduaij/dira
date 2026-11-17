"""OCR-only worker dependencies; no embeddings, FAISS or Torch imports here."""

import os
from pathlib import Path
from collections import Counter, deque
from time import monotonic
import numpy as np
from .text import normalize


def sharpness(frame):
    gray = np.asarray(frame, dtype=np.float32)
    if gray.ndim == 3:
        gray = gray.mean(axis=2)
    if min(gray.shape) < 3:
        return 0.0
    lap = gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:] - 4 * gray[1:-1, 1:-1]
    return float(lap.var())


class ChyronOCR:
    def __init__(
        self,
        model_dir,
        threshold=80,
        detection_model="PP-OCRv6_small_det",
        recognition_model="arabic_PP-OCRv5_mobile_rec",
        cpu_threads=2,
    ):
        root = Path(model_dir)
        if not (root / "det").is_dir() or not (root / "rec").is_dir():
            raise ValueError("OCR requires local det/ and rec/ model directories")
        for component in ("det", "rec"):
            for name in ("inference.yml", "inference.json", "inference.pdiparams"):
                path = root / component / name
                if not path.is_file() or path.stat().st_size == 0:
                    raise ValueError("incomplete local OCR export; supply config, graph and weights")
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        from paddleocr import PaddleOCR

        self.engine = PaddleOCR(
            text_detection_model_dir=str(root / "det"),
            text_recognition_model_dir=str(root / "rec"),
            text_detection_model_name=detection_model,
            text_recognition_model_name=recognition_model,
            device="cpu",
            cpu_threads=cpu_threads,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        self.threshold = threshold
        self.history = deque(maxlen=3)

    def extract(self, frame):
        roi = frame  # Already cropped to the bottom 20% by FFmpeg.
        self.stats = getattr(self, "stats", {"frames": 0, "blur_drops": 0, "emitted_lines": 0})
        self.stats["frames"] += 1
        if sharpness(roi) < self.threshold:
            self.stats["blur_drops"] += 1
            return ""
        texts = []
        for result in self.engine.predict(roi):
            texts.extend(t for t, s in zip(result["rec_texts"], result["rec_scores"]) if s >= 0.65)
        self.history.append(set(texts))
        votes = Counter(t for frame_texts in self.history for t in frame_texts)
        now = monotonic()
        emitted = getattr(self, "emitted_lines", {})
        emitted = {key: at for key, at in emitted.items() if now - at < 900}
        new_lines = list(dict.fromkeys(t for t in texts if votes[t] >= 2 and normalize(t) not in emitted))
        for text in new_lines:
            emitted[normalize(text)] = now
        self.emitted_lines = dict(list(emitted.items())[-4096:])
        self.stats["emitted_lines"] += len(new_lines)
        return " ".join(new_lines)

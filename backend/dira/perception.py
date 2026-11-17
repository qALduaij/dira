"""Optional perception engines load only when configured with local models."""

from pathlib import Path


from .ocr import ChyronOCR as ChyronOCR, sharpness as sharpness
from .models import Entity


def parse_asr_lines(payload, seen):
    """Only stable/committed lines; never the ephemeral transcription buffer."""

    def stamp(value):
        result = 0.0
        for part in str(value).split(":"):
            result = result * 60 + float(part)
        return result

    history = seen.setdefault("lines", {})
    floor = seen.get("floor", -1)
    result = []
    for line in payload.get("lines", []):
        if not any(c.isalnum() for c in line.get("text", "")) or line.get("speaker") == -2:
            continue
        key = (line.get("start"), line.get("speaker"))
        if stamp(line.get("start", 0)) <= floor:
            continue
        previous = history.get(key)
        history[key] = dict(line)
        if previous:
            if not line["text"].startswith(previous["text"]):
                # A revision to previously emitted words is not a new observation.
                continue
            text = line["text"][len(previous["text"]) :].strip()
            if any(c.isalnum() for c in text):
                result.append({**line, "text": text, "start": previous["end"]})
        else:
            result.append(line)
    # Session history is bounded even for days-long live feeds.
    if len(history) > 10000:
        discarded = sorted(history, key=lambda key: stamp(key[0]))[:-1000]
        seen["floor"] = max(stamp(key[0]) for key in discarded)
        for key in discarded:
            del history[key]
    return result


def iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = (
        max(0, a[2] - a[0]) * max(0, a[3] - a[1]) + max(0, b[2] - b[0]) * max(0, b[3] - b[1]) - intersection
    )
    return intersection / max(union, 1e-9)


class Tracker:
    """Label + IoU tracking. IDs are tracks, never biometric identities."""

    def __init__(self, max_age=10):
        self.tracks, self.counter, self.max_age = {}, 0, max_age

    def update(self, detections, timestamp):
        self.tracks = {k: v for k, v in self.tracks.items() if timestamp - v["time"] <= self.max_age}
        result, matched = [], set()
        for detection in detections:
            candidates = [
                (iou(v["bbox"], detection["bbox"]), k)
                for k, v in self.tracks.items()
                if v["name"] == detection["name"] and k not in matched
            ]
            score, key = max(candidates, default=(0, None))
            if score < 0.3:
                self.counter += 1
                key = str(self.counter)
            matched.add(key)
            self.tracks[key] = {**detection, "time": timestamp}
            result.append(
                Entity(
                    name=detection["name"],
                    kind="object",
                    bbox=detection["bbox"],
                    confidence=detection.get("confidence", 1),
                    track_id=key,
                )
            )
        return result


class VisualDetector:
    """Local TorchScript detector with Nx6 output: x1,y1,x2,y2,score,label."""

    def __init__(self, model_path, labels, device="auto"):
        import torch
        from .embeddings import select_device

        self.torch, self.device, self.labels = torch, select_device(device), labels
        self.model = torch.jit.load(model_path, map_location=self.device).eval()
        self.tracker = Tracker()

    def detect(self, frame, timestamp):
        t = self.torch.from_numpy(frame.copy()).permute(2, 0, 1).unsqueeze(0).float().to(self.device) / 255
        with self.torch.inference_mode():
            output = self.model(t).detach().cpu().numpy().reshape(-1, 6)
        detections = [
            {"name": self.labels[int(row[5])], "bbox": row[:4].tolist(), "confidence": float(row[4])}
            for row in output
            if row[4] >= 0.6 and int(row[5]) < len(self.labels)
        ]
        return self.tracker.update(detections, timestamp)


class Diarizer:
    def __init__(self, model_path, device="auto"):
        if not Path(model_path).exists():
            raise ValueError("diarization requires local pyannote pipeline weights")
        import torch
        from .embeddings import select_device
        from pyannote.audio import Pipeline

        self.pipeline = Pipeline.from_pretrained(model_path).to(torch.device(select_device(device)))

    def segments(self, audio_path):
        output = self.pipeline(audio_path)
        annotation = getattr(output, "speaker_diarization", output)
        return [
            {"start": turn.start, "end": turn.end, "speaker": speaker}
            for turn, _, speaker in annotation.itertracks(yield_label=True)
        ]

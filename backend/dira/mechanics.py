from time import monotonic
from collections import defaultdict, deque

import ahocorasick
import faiss
import numpy as np
import regex

from .models import TDO, Alert, Rule


from .text import normalize


def rrf(rankings: list[list[str]], k=60, weights=None):
    scores = defaultdict(float)
    for i, ranking in enumerate(rankings):
        for rank, key in enumerate(dict.fromkeys(ranking), 1):
            scores[key] += (weights[i] if weights else 1) / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


class GateEngine:
    def __init__(self, rules: list[Rule]):
        self.rules = [
            (r, regex.compile(r.pattern, regex.I) if r.kind == "regex" else normalize(r.pattern))
            for r in rules
            if r.enabled
        ]
        self.timeouts = 0
        self.recent = {}
        self.suppressed = 0
        self.keywords = ahocorasick.Automaton()
        groups = defaultdict(list)
        for index, (rule, pattern) in enumerate(self.rules):
            if rule.kind == "keyword" and pattern:
                groups[pattern].append(index)
        for pattern, indices in groups.items():
            self.keywords.add_word(pattern, indices)
        if groups:
            self.keywords.make_automaton()

    def evaluate(self, event: TDO):
        raw = event.text()
        text = normalize(raw)
        alerts = []
        matched_keywords = (
            {index for _, indices in self.keywords.iter(text) for index in indices}
            if len(self.keywords)
            else set()
        )
        for index, (rule, pattern) in enumerate(self.rules):
            if rule.channel_id and rule.channel_id != event.channel_id:
                continue
            try:
                matched = (
                    pattern.search(raw, timeout=0.002) if rule.kind == "regex" else index in matched_keywords
                )
            except TimeoutError:
                self.timeouts += 1
                continue
            if matched:
                # Bare on-screen badges convey no event. A breaking rule needs substantive text.
                if (
                    rule.kind == "keyword"
                    and pattern in ("عاجل", "breaking", "breaking news")
                    and text.strip() == pattern
                ):
                    continue
                key = (str(rule.id), event.channel_id, " ".join(text.split()))
                now = monotonic()
                self.recent = {k: at for k, at in self.recent.items() if now - at < 900}
                if key in self.recent:
                    self.suppressed += 1
                    continue
                self.recent[key] = now
                if len(self.recent) > 10000:
                    self.recent.pop(next(iter(self.recent)))
                alerts.append(
                    Alert(
                        tdo_id=event.id,
                        channel_id=event.channel_id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        detail=raw[:350],
                        kind=rule.kind,
                        simulated=event.simulated,
                    )
                )
        return alerts


class SpikeDetector:
    """Compare topic counts to completed windows, excluding the current window."""

    def __init__(self, window_seconds=30, baseline_windows=12, min_count=4, threshold=3, max_topics=128):
        self.window_seconds, self.baseline_windows = window_seconds, baseline_windows
        self.min_count, self.threshold, self.max_topics = min_count, threshold, max_topics
        self.topics = []
        self.latest = -float("inf")
        self.index = None

    def observe(self, vector, timestamp):
        if timestamp < self.latest:
            return None
        self.latest = timestamp
        v = np.asarray(vector, dtype=np.float32)
        norm = np.linalg.norm(v)
        if norm == 0:
            return None
        v = v / norm
        bucket = int(timestamp // self.window_seconds)
        if self.index is None:
            self.index = faiss.IndexFlatIP(len(v))
        scores, neighbors = self.index.search(v.reshape(1, -1), 1)
        idx = int(neighbors[0, 0])
        if idx < 0 or float(scores[0, 0]) < 0.72:
            if len(self.topics) >= self.max_topics:
                self.topics.pop(0)
                self.index.reset()
                if self.topics:
                    self.index.add(np.stack([topic["centroid"] for topic in self.topics]))
            self.topics.append(
                {
                    "centroid": v,
                    "bucket": bucket,
                    "count": 0,
                    "history": deque(maxlen=self.baseline_windows),
                    "alerted": False,
                }
            )
            idx = len(self.topics) - 1
            self.index.add(v.reshape(1, -1))
        topic = self.topics[idx]
        gap = bucket - topic["bucket"]
        if gap > 0:
            topic["history"].append(topic["count"])
            topic["history"].extend([0] * min(gap - 1, self.baseline_windows))
            topic.update(bucket=bucket, count=0, alerted=False)
        topic["count"] += 1
        history = topic["history"]
        if len(history) < 3 or topic["count"] < self.min_count or topic["alerted"]:
            return None
        mean, std = float(np.mean(history)), max(float(np.std(history)), 1.0)
        z = (topic["count"] - mean) / std
        if z >= self.threshold:
            topic["alerted"] = True
            return {"z_score": round(z, 2), "count": topic["count"], "baseline": round(mean, 2)}
        return None

"""Measured component timings, not end-to-end broadcast latency claims."""

import json
import platform
from time import perf_counter_ns
import numpy as np
from dira.mechanics import GateEngine
from dira.models import Rule, SearchRequest
from dira.simulation import make_event
from dira.embeddings import HashEncoder
from dira.store import HotIndex


def measure(fn, iterations):
    for _ in range(20):
        fn()
    samples = []
    for _ in range(iterations):
        start = perf_counter_ns()
        fn()
        samples.append((perf_counter_ns() - start) / 1e6)
    return {f"p{p}_ms": round(float(np.percentile(samples, p)), 4) for p in [50, 95, 99]}


def main():
    gate = GateEngine(
        [
            Rule(name="Breaking", pattern="عاجل"),
            Rule(name="Energy", pattern="النفط"),
            Rule(name="Maritime", pattern="الموانئ"),
        ]
    )
    e = make_event(3)
    encoder = HashEncoder(256)
    hot = HotIndex(256, capacity=1000)
    for i in range(1000):
        event = make_event(i)
        hot.add(event, {"transcript": encoder.encode(event.text()).tolist()})
    query = encoder.encode("energy")
    result = {
        "platform": platform.platform(),
        "configuration": {"vectors": 1000, "dimension": 256, "keyword_rules": 3},
        "keyword_gate": measure(lambda: gate.evaluate(e), 5000),
        "hot_faiss": measure(lambda: hot.search(query, "transcript", SearchRequest(query="energy")), 500),
        "note": "Local synthetic component benchmark. Does not include ASR/OCR, satellite transport, model inference or production concurrency.",
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

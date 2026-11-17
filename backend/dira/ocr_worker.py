"""Fixed-size RGB frames in, one JSON result out. Spawned only by the local API."""

import argparse
import json
import os
import sys
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--detector", required=True)
    parser.add_argument("--recognizer", required=True)
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    # Native libraries may write to fd 1; keep their diagnostics off the protocol pipe.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    from .ocr import ChyronOCR
    import numpy as np

    model = ChyronOCR(
        args.model_dir,
        detection_model=args.detector,
        recognition_model=args.recognizer,
        cpu_threads=args.threads,
    )
    print(json.dumps({"ready": True}), file=protocol, flush=True)
    frame_bytes = 1280 * 144 * 3
    while True:
        raw = sys.stdin.buffer.read(frame_bytes)
        if not raw:
            break
        if len(raw) != frame_bytes:
            raise ValueError("incomplete RGB frame")
        frame = np.frombuffer(raw, np.uint8).reshape(144, 1280, 3)
        text = model.extract(frame)
        print(json.dumps({"text": text, "stats": model.stats}, ensure_ascii=False), file=protocol, flush=True)


def run():
    """Exit without interpreter finalization: Paddle/OpenMP thread-pool teardown segfaults at shutdown."""
    code = 0
    try:
        main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    except BaseException:
        traceback.print_exc()
        code = 1
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)


if __name__ == "__main__":
    run()

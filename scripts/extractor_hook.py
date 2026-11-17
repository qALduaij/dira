"""MediaMTX runOnDemand client; holds a lease until MediaMTX sends SIGINT."""

import os
import re
import signal
import sys
from urllib.request import ProxyHandler, Request, build_opener


def main():
    channel = os.environ.get("MTX_PATH", "")
    token = os.environ.get("DIRA_EXTRACTOR_TOKEN", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", channel) or not token:
        return 1
    base = os.environ.get("DIRA_EXTRACTOR_URL", "http://127.0.0.1:8002").rstrip("/")
    request = Request(f"{base}/leases/{channel}", headers={"Authorization": f"Bearer {token}"})
    # Local control traffic must not inherit the regional media proxy.
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=15) as response:
            while response.readline():
                pass
    except (KeyboardInterrupt, SystemExit):
        return 0
    except Exception:  # noqa: BLE001 -- keep control-plane credentials out of errors
        print("Dira extractor lease unavailable", file=sys.stderr)
    return 1


if __name__ == "__main__":

    def terminate(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, terminate)
    raise SystemExit(main())

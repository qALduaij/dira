"""Opt-in six-channel live HLS → MediaMTX → RTSP verification in a temporary container."""

import concurrent.futures
import json
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    name = "dira-primary-verify-" + uuid.uuid4().hex[:8]
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "-p",
            "127.0.0.1::8554",
            "-v",
            f"{ROOT / 'infra/mediamtx.yml'}:/mediamtx.yml:ro",
            "dira-mediamtx:local",
        ],
        check=True,
        capture_output=True,
    )
    try:
        address = subprocess.check_output(["docker", "port", name, "8554/tcp"], text=True).strip()

        def probe(channel):
            deadline = time.monotonic() + 40
            result = {"id": channel["id"], "checked_at": datetime.now(UTC).isoformat()}
            while time.monotonic() < deadline:
                try:
                    process = subprocess.run(
                        [
                            "ffprobe",
                            "-v",
                            "error",
                            "-rtsp_transport",
                            "tcp",
                            "-show_entries",
                            "stream=index,codec_type,codec_name,width,height,sample_rate,channels",
                            "-of",
                            "json",
                            f"rtsp://{address}/{channel['id']}",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=15,
                        check=False,
                    )
                    result["exit_code"] = process.returncode
                    if process.returncode == 0:
                        result["streams"] = json.loads(process.stdout)["streams"]
                        return result
                except subprocess.TimeoutExpired:
                    result["error"] = "RTSP probe timed out"
                time.sleep(2)
            result["error"] = "No readable RTSP media before timeout; inspect upstream source compatibility"
            return result

        sources = json.loads((ROOT / "infra/primary-sources.json").read_text())
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            report = list(pool.map(probe, sources))
        (ROOT / "docs/mediahub-verification.json").write_text(json.dumps(report, indent=2) + "\n")
        for row in report:
            print(
                row["id"],
                [(s["codec_type"], s.get("width"), s.get("height")) for s in row.get("streams", [])],
                row.get("error", "OK"),
                flush=True,
            )
        logs = subprocess.check_output(["docker", "logs", name], stderr=subprocess.STDOUT, text=True)
        Path("/tmp/dira-primary-mediamtx.log").write_text(logs)
        if any("error" in row for row in report):
            raise SystemExit(1)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=True)


if __name__ == "__main__":
    main()

"""Opt-in network verification of the six user-supplied public sources; no recording."""

import concurrent.futures
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def verify(source):
    result = {
        "id": source["id"],
        "source_url": source["source_url"],
        "checked_at": datetime.now(UTC).isoformat(),
    }
    try:
        request = Request(source["source_url"], headers={"User-Agent": "Dira/0.1 source-verification"})
        with urlopen(request, timeout=12) as response:
            playlist = response.read(1024 * 1024).decode()
            result["http_status"] = response.status
            result["playlist_valid"] = playlist.lstrip().startswith("#EXTM3U")
            result["variants"] = [
                line for line in playlist.splitlines() if line.startswith("#EXT-X-STREAM-INF")
            ]
            result["audio_renditions"] = [
                line
                for line in playlist.splitlines()
                if line.startswith("#EXT-X-MEDIA") and "TYPE=AUDIO" in line
            ]
    except (OSError, UnicodeError) as error:
        result["manifest_error"] = type(error).__name__
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-rw_timeout",
                "12000000",
                "-analyzeduration",
                "3000000",
                "-probesize",
                "3000000",
                "-show_programs",
                "-show_streams",
                "-of",
                "json",
                source["source_url"],
            ],
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
        result["probe_exit_code"] = probe.returncode
        if probe.returncode == 0:
            data = json.loads(probe.stdout)
            result["streams"] = [
                {
                    k: stream[k]
                    for k in (
                        "index",
                        "id",
                        "codec_type",
                        "codec_name",
                        "width",
                        "height",
                        "sample_rate",
                        "channels",
                        "tags",
                    )
                    if k in stream
                }
                for stream in data.get("streams", [])
            ]
            result["programs"] = [
                {
                    "program_id": p.get("program_id"),
                    "stream_indices": [s["index"] for s in p.get("streams", [])],
                }
                for p in data.get("programs", [])
            ]
        else:
            result["probe_error"] = "ffprobe could not open playable media"
    except subprocess.TimeoutExpired:
        result["probe_error"] = "probe timed out after 25 seconds"
    return result


if __name__ == "__main__":
    sources = json.loads((ROOT / "infra/primary-sources.json").read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        report = list(pool.map(verify, sources))
    output = ROOT / "docs/primary-source-verification.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for row in report:
        print(
            row["id"],
            row.get("http_status", row.get("manifest_error")),
            row.get("probe_error", "playable audio/video metadata read"),
        )

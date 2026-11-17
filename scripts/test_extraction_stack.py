"""Opt-in synthetic smoke test; creates and removes an isolated Docker stack."""

import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.STDOUT).strip()


def wait_for(predicate, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise TimeoutError("synthetic extraction stack did not reach expected state")


def main():
    network = "dira-extraction-smoke-" + uuid.uuid4().hex[:8]
    containers, producer, reader = [], None, None
    opener = build_opener(ProxyHandler({}))
    docker("network", "create", network)
    try:
        with tempfile.TemporaryDirectory(prefix="dira-extraction-smoke-") as directory:
            fixture = Path(directory)
            fixture.chmod(0o755)
            config = {
                "channels": [
                    {
                        "id": "ktv1",
                        "enabled": True,
                        "extractor": "yt-dlp",
                        "source_url": "http://source:8090/master.m3u8",
                        "refresh_seconds": 60,
                    }
                ]
            }
            (fixture / "channels.json").write_text(json.dumps(config))
            (fixture / "master.m3u8").write_text(
                "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=300000,RESOLUTION=320x180,"
                'CODECS="avc1.64000c,mp4a.40.2"\nindex.m3u8\n'
            )
            media_config = (ROOT / "infra/mediamtx.extraction.yml").read_text()
            # Exercise only the synthetic secondary path, never the real primary sources.
            media_config = (
                media_config.split("paths:\n", 1)[0]
                + "paths:\n"
                + media_config[media_config.index("  '~^(") :]
            )
            (fixture / "mediamtx.yml").write_text(
                media_config.replace("record: yes", "record: no").replace(
                    "runOnDemandCloseAfter: 10s", "runOnDemandCloseAfter: 2s"
                )
            )
            producer = subprocess.Popen(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-re",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc=size=320x180:rate=10",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:sample_rate=48000",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-preset",
                    "ultrafast",
                    "-tune",
                    "zerolatency",
                    "-g",
                    "10",
                    "-c:a",
                    "aac",
                    "-f",
                    "hls",
                    "-hls_time",
                    "1",
                    "-hls_list_size",
                    "6",
                    "-hls_flags",
                    "delete_segments",
                    str(fixture / "index.m3u8"),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            wait_for(lambda: (fixture / "index.m3u8").exists())

            def run(name, image, args):
                full = network + "-" + name
                docker(
                    "run", "-d", "--name", full, "--network", network, "--network-alias", name, *args, image
                )
                containers.append(full)
                return full

            source = network + "-source"
            docker(
                "run",
                "-d",
                "--name",
                source,
                "--network",
                network,
                "--network-alias",
                "source",
                "-v",
                f"{fixture}:/fixtures:ro",
                "--entrypoint",
                "python3",
                "dira-mediamtx-extraction:local",
                "-m",
                "http.server",
                "8090",
                "--directory",
                "/fixtures",
            )
            containers.append(source)
            worker = run(
                "extractor",
                "dira-extractor:local",
                [
                    "--init",
                    "-p",
                    "127.0.0.1::8002",
                    "-v",
                    f"{fixture}:/fixtures:ro",
                    "-e",
                    "DIRA_EXTRACTOR_TOKEN=synthetic-test",
                    "-e",
                    "DIRA_EXTRACTOR_CONFIG=/fixtures/channels.json",
                    "-e",
                    "DIRA_EXTRACTOR_PUBLISH_BASE=rtsp://mediamtx:8554",
                ],
            )
            media = run(
                "mediamtx",
                "dira-mediamtx-extraction:local",
                [
                    "-p",
                    "127.0.0.1::8554",
                    "-v",
                    f"{fixture}/mediamtx.yml:/mediamtx.yml:ro",
                    "-e",
                    "DIRA_EXTRACTOR_TOKEN=synthetic-test",
                    "-e",
                    "DIRA_EXTRACTOR_URL=http://extractor:8002",
                ],
            )
            api = "http://" + docker("port", worker, "8002/tcp")
            rtsp = "rtsp://" + docker("port", media, "8554/tcp") + "/ktv1"

            def state():
                request = Request(api + "/channels", headers={"Authorization": "Bearer synthetic-test"})
                with opener.open(request, timeout=2) as response:
                    return json.load(response)["active"]

            wait_for(lambda: opener.open(api + "/health", timeout=2).close() or True)
            assert state() == {}, "extraction started without demand"
            reader = subprocess.Popen(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-rtsp_transport",
                    "tcp",
                    "-i",
                    rtsp,
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0",
                    "-t",
                    "2",
                    "-f",
                    "null",
                    "-",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            wait_for(lambda: state().get("ktv1", {}).get("state") == "publishing")
            _, errors = reader.communicate(timeout=30)
            assert reader.returncode == 0, errors.decode()
            wait_for(lambda: state() == {}, timeout=20)
            # No long-lived extraction or FFmpeg children should survive the last reader.
            processes = docker(
                "exec",
                worker,
                "/app/.venv/bin/python",
                "-c",
                "from pathlib import Path; import json; "
                "print(json.dumps([p.read_bytes().decode(errors='replace').split(chr(0)) "
                "for p in Path('/proc').glob('[0-9]*/cmdline') if p.exists()]))",
            )
            for args in json.loads(processes):
                assert "dira.extraction.source" not in args
                assert not args or not args[0].endswith("ffmpeg")
            print("PASS: idle → RTSP demand → real HLS extraction → audio/video → last-reader cleanup")
    finally:
        for process in (reader, producer):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for name in reversed(containers):
            docker("rm", "-f", name)
        docker("network", "rm", network)


if __name__ == "__main__":
    main()

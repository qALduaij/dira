"""Controlled HLS only: optional extraction dependencies and FFmpeg required."""

import json
import os
import shutil
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

pytest.importorskip("streamlink")
pytest.importorskip("yt_dlp")


@pytest.fixture
def hls_source(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg required")
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=160x90:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-g",
            "10",
            "-c:a",
            "aac",
            "-f",
            "hls",
            "-hls_time",
            "1",
            "-hls_list_size",
            "0",
            str(tmp_path / "index.m3u8"),
        ],
        check=True,
        timeout=20,
    )
    (tmp_path / "master.m3u8").write_text(
        '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=200000,RESOLUTION=160x90,CODECS="avc1.64000a,mp4a.40.2"\n'
        "index.m3u8\n"
    )

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/master.m3u8"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("extractor", ["yt-dlp", "streamlink"])
def test_extracts_real_audio_video_without_leaking_url(hls_source, tmp_path, extractor):
    config = tmp_path / "extractors.json"
    config.write_text(
        json.dumps(
            {"channels": [{"id": "test", "enabled": True, "source_url": hls_source, "extractor": extractor}]}
        )
    )
    result = subprocess.run(
        [sys.executable, "-m", "dira.extraction.source", "test"],
        env=dict(os.environ, DIRA_EXTRACTOR_CONFIG=str(config)),
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert len(result.stdout) > 1000
    media = tmp_path / "received.ts"
    media.write_bytes(result.stdout)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(media)],
        capture_output=True,
        check=True,
        timeout=10,
    )
    assert {s["codec_type"] for s in json.loads(probe.stdout)["streams"]} == {"audio", "video"}
    assert hls_source.encode() not in result.stdout + result.stderr


@pytest.mark.parametrize("extractor", ["yt-dlp", "streamlink"])
def test_regional_proxy_covers_cdn_and_preserves_cookie_domains(hls_source, tmp_path, extractor):
    # The source and CDN are deliberately unresolvable; every request must use this proxy.
    master = tmp_path / "master.m3u8"
    master.write_text(master.read_text().replace("index.m3u8", "http://cdn.test/index.m3u8"))
    playlist = tmp_path / "index.m3u8"
    playlist.write_text(
        "\n".join(
            "http://cdn.test/" + line if line.endswith(".ts") else line
            for line in playlist.read_text().splitlines()
        )
        + "\n"
    )
    observed = []

    class ProxyHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            url = urlsplit(self.path)
            observed.append((url.hostname, url.path, self.headers.get("Cookie", "")))
            self.path = url.path
            super().do_GET()

        def log_message(self, *_):
            pass

    proxy = ThreadingHTTPServer(("127.0.0.1", 0), partial(ProxyHandler, directory=str(tmp_path)))
    thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    thread.start()
    cookies = tmp_path / "cookies.txt"
    original = (
        "# Netscape HTTP Cookie File\n"
        "origin.test\tFALSE\t/\tFALSE\t2147483647\tsession\torigin-secret\n"
        "cdn.test\tFALSE\t/\tFALSE\t2147483647\tsession\tcdn-secret\n"
    )
    cookies.write_text(original)
    config = tmp_path / "extractors.json"
    config.write_text(
        json.dumps(
            {
                "domain_proxies": {"origin.test": "TEST_REGIONAL_PROXY"},
                "channels": [
                    {
                        "id": "test",
                        "enabled": True,
                        "extractor": extractor,
                        "source_url": "http://origin.test/master.m3u8",
                        "cookie_file": str(cookies),
                    }
                ],
            }
        )
    )
    try:
        result = subprocess.run(
            [sys.executable, "-m", "dira.extraction.source", "test"],
            env=dict(
                os.environ,
                DIRA_EXTRACTOR_CONFIG=str(config),
                TEST_REGIONAL_PROXY=f"http://127.0.0.1:{proxy.server_port}",
            ),
            capture_output=True,
            timeout=30,
            check=False,
        )
    finally:
        proxy.shutdown()
        proxy.server_close()
        thread.join()
    assert result.returncode == 0, result.stderr.decode()
    assert len(result.stdout) > 1000
    assert any(host == "cdn.test" and path.endswith(".ts") for host, path, _ in observed)
    assert any(host == "origin.test" for host, _, _ in observed)
    for host, _, cookie in observed:
        assert cookie == ("session=origin-secret" if host == "origin.test" else "session=cdn-secret")
    assert cookies.read_text() == original
    assert b"secret" not in result.stdout + result.stderr

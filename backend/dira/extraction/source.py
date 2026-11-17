"""Isolated extractor/HLS reader. stdout is media only; secrets never enter argv."""

import logging
import os
import sys
from contextlib import redirect_stdout
from http.cookiejar import MozillaCookieJar

from .config import Catalog, ExtractorSettings, http_url, proxy_for


class QuietLogger:
    def debug(self, *_):
        pass

    warning = error = debug


def select_ytdlp_stream(info):
    if (
        not info
        or info.get("has_drm")
        or info.get("requested_formats")
        or info.get("protocol") not in ("m3u8", "m3u8_native")
        or info.get("vcodec") == "none"
        or info.get("acodec") == "none"
    ):
        raise ValueError("a clear, combined audio/video HLS stream is required")
    return http_url(info.get("url", ""))


def resolve(channel, routes):
    url = channel.source()
    proxy = proxy_for(url, routes)
    cookies = MozillaCookieJar()
    if channel.cookie_file:
        # Read-only Netscape cookie file; never scrape a browser or overwrite the original.
        cookies.load(str(channel.cookie_file), ignore_discard=True, ignore_expires=False)

    if channel.extractor == "yt-dlp":
        from yt_dlp import YoutubeDL

        options = {
            "format": "best[protocol^=m3u8][vcodec!=none][acodec!=none]",
            "noplaylist": True,
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "logger": QuietLogger(),
            "cachedir": False,
            "socket_timeout": 15,
            "retries": 1,
            "extractor_retries": 1,
            "proxy": proxy or "",
            "geo_bypass": False,
            "allow_unplayable_formats": False,
        }
        with YoutubeDL(options) as ydl:
            for cookie in cookies:
                ydl.cookiejar.set_cookie(cookie)
            info = ydl.extract_info(url, download=False)
            media_url = select_ytdlp_stream(info)
            for cookie in ydl.cookiejar:
                cookies.set_cookie(cookie)
            # Preserve playback context without flattening domain-scoped cookies into headers.
            headers = {
                k: v
                for k, v in (info.get("http_headers") or {}).items()
                if k.lower() in ("user-agent", "referer", "origin", "accept")
            }

    # Each child resolves one source. Load Streamlink AFTER yt-dlp extraction: both patch
    # urllib3 URL normalization, and the reverse order breaks hostname/proxy requests.
    from streamlink import Streamlink
    from streamlink.stream.hls import HLSStream

    session = Streamlink()
    # Routing must apply to extraction AND the media CDN; do not inherit ambient proxies.
    session.http.trust_env = False
    if proxy:
        session.set_option("http-proxy", proxy)
    session.set_option("http-timeout", 15)
    session.set_option("stream-timeout", 20)
    session.set_option("stream-segment-timeout", 15)
    session.set_option("stream-segment-attempts", 2)
    session.set_option("ringbuffer-size", 4 * 1024 * 1024)
    session.http.cookies.update(cookies)
    if channel.extractor == "yt-dlp":
        return HLSStream(session, media_url, headers=headers)

    streams = session.streams(url)
    stream = streams.get(channel.quality)
    if not isinstance(stream, HLSStream):
        raise TypeError("selected Streamlink stream must be HLS (no DASH or external muxer)")
    http_url(stream.url)
    return stream


def main():
    logging.disable(logging.CRITICAL)
    # Third-party background threads may bypass loggers when raising exceptions.
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), sys.stderr.fileno())
    try:
        settings = ExtractorSettings()
        catalog = Catalog.load(settings.config)
        channel = catalog.channel(sys.argv[1])
        # Libraries must not corrupt the binary media pipe with informational output.
        with redirect_stdout(sys.stderr):
            stream = resolve(channel, catalog.domain_proxies)
        with stream.open() as reader:
            while chunk := reader.read(64 * 1024):
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
    except Exception:  # noqa: BLE001 -- never expose upstream credentials in errors
        # Upstream exceptions often embed signed URLs or credentials.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

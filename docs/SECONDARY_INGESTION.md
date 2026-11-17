# Secondary media ingestion

This optional worker resolves **operator-authorized, clear HLS** streams using yt-dlp or Streamlink, downloads the media through the same configured regional route, and pipes it into FFmpeg for RTSP publishing. The existing simulation and direct feed adapters do not depend on it.

```text
Dira audio/frame reader → MediaMTX channel → runOnDemand hook
                                              ↓ authenticated HTTP lease
                                        Extractor supervisor
                                              ↓ isolated child per attempt
                          yt-dlp or Streamlink → HLS media reader → FFmpeg
                                                                    ↓
                                                       MediaMTX stable RTSP path
```

The channel examples are **disabled placeholders**, not verified working integrations with Kuwait TV, Bloomberg, CNN, CNBC Arabia or BBC. A provider's availability, session requirements and regional conditions must be established separately. DRM-protected sources, DASH-only sources, separate audio/video renditions requiring an external muxer, CAPTCHA and YouTube bot challenges are not handled by this scaffold. No DRM key, CDM, browser-cookie scraping or geo-bypass code is supplied.

## Docker setup

From the repository root:

```bash
cp infra/extractors.example.json infra/extractors.json
mkdir -p secrets
# If .env does not exist, create it from .env.example first.
```

Set a private random `DIRA_EXTRACTOR_TOKEN` in `.env`. Use the same value for MediaMTX and the worker; the Compose overlay wires this automatically. Do not use the public example values from tests. Configure one authorized channel before enabling it. Then:

```bash
docker compose -f compose.yaml -f compose.extraction.yaml up --build -d extractor mediamtx
```

This explicitly replaces the base MediaMTX container with a Python-capable image and the on-demand configuration; any existing viewers may reconnect. It retains the existing ports and recording volume. The extractor listens on **127.0.0.1:8002** at the host, and **extractor:8002** internally. No extraction starts until a configured path is requested. The normal `docker compose up` remains the original simulation stack.

## Configure a channel

`infra/extractors.json` contains a `channels` list and a `domain_proxies` mapping. Channel IDs must match the enabled MediaMTX paths: `ktv1`, `bloomberg`, `cnn`, `cnbc_arabia`, `bbc`, `cbs`, `nbc`. Add other IDs to the path regex in `infra/mediamtx.extraction.yml` when needed.

Example entry, after obtaining an authorized source:

```json
{
  "id": "ktv1",
  "enabled": true,
  "extractor": "streamlink",
  "source_url_file": "/run/secrets/dira/ktv-source-url.txt",
  "cookie_file": "/run/secrets/dira/ktv-cookies.txt",
  "quality": "best",
  "refresh_seconds": 300
}
```

- Choose `source_url` for a stable public webpage/HLS URL **or** `source_url_file` for an operator-managed URL file, never both. The file contains one HTTP(S) URL, including any authorized signed query parameters. Do not use a homepage unless the chosen extractor supports its live player.
- `cookie_file` is optional: an operator-provided **Netscape cookie file** with correct domain/path/expiry fields. Cookie scopes are preserved through extraction and CDN playback. The worker does not save changes back to the file. Arbitrary Authorization headers and PO-token/plugin-specific arguments are not exposed by this scaffold.
- `extractor` is explicitly `yt-dlp` or `streamlink`. There is no automatic fallback that changes access strategy. yt-dlp selects its best combined audio/video HLS rendition; `quality` applies to Streamlink only.
- `refresh_seconds` is a conservative maximum attempt age, **not a detected token expiry**. Set it below the provider's known URL lifetime. Each renewal performs fresh extraction. An already expired session cannot be renewed without the operator updating its credentials. Reusing a static signed URL cannot mint a new token.
- Mounted cookie/URL files are reread on each attempt; update them atomically to rotate sessions. Changes to channel IDs, enablement or refresh settings require restarting the extractor. Environment/proxy changes require recreating it.

The Docker worker runs as user `dira` (UID 1000); provision file permissions so that this user can read the necessary files without making them world-readable. Native execution uses your user. Relative file paths are resolved from the service's working directory; absolute paths are clearer. `.env`, `secrets/`, `infra/extractors.json` and `infra/feeds.json` are excluded from Git and Docker build contexts. They are mounted at runtime, not copied into images.

## Regional routing

The supplied mapping is:

```json
{
  "51.com.kw": "DIRA_PROXY_KW",
  "bbc.co.uk": "DIRA_PROXY_UK",
  "bbc.com": "DIRA_PROXY_UK"
}
```

Set the named variables in `.env`, for example an operator-managed `http://gateway:3128` or `socks5h://gateway:1080`. A rule matches the source hostname and its subdomains; the longest matching suffix wins. The selected route then applies to **the entire source session**, including redirects, manifests and CDN segments. This keeps metadata extraction and media downloads on the same egress IP. `socks5h` delegates DNS resolution to the proxy.

A matching rule with an empty/invalid variable **fails closed**; it never silently tries direct access. Unmatched source domains connect directly and ignore ambient HTTP proxy variables. Remove a rule when direct access is deliberately intended. Add other regional environment variables to the Compose overlay if you introduce new mappings.

This is a routing abstraction, not a VPN manager: provision VPN connections and regional proxy gateways externally. On Docker Desktop, a host-side proxy usually needs `host.docker.internal` instead of `127.0.0.1`; the gateway must be reachable from the container. No OS routing tables or VPN accounts are changed.

## On-demand behavior and Dira feeds

MediaMTX runs `scripts/extractor_hook.py` when a reader requests a configured channel. The hook sends the internal shared token in an Authorization header and holds an HTTP streaming lease. The worker shares one publisher among concurrent leases. Closing the last lease stops and reaps both source and FFmpeg processes. MediaMTX closes its hook 10 seconds after demand ends; HLS clients may keep the MediaMTX muxer active for its own idle interval first.

Extraction, transport failures and media stalls retry with bounded exponential delay. A progress watchdog detects missing video frames. Each configured refresh tears down and recreates the publishing session; this **can cause a playback gap and reader reconnection**. It does not promise seamless rollover. Dira's existing live reader supervision reconnects automatically. The relay copies RTSP-compatible video (H264 recommended) and encodes audio as AAC at 128 kbit/s. Audio normalization supplies the global headers required by RTSP; no video transcoding is performed. Both audio and video are required.

Use a stable local input in `infra/feeds.json`, for example:

```json
{
  "id": "ktv1",
  "name": "Kuwait TV",
  "name_ar": "تلفزيون الكويت",
  "input_url": "rtsp://127.0.0.1:8554/ktv1",
  "playback_url": "http://127.0.0.1:8888/ktv1/index.m3u8",
  "language": "ar"
}
```

The feed file itself is a JSON **array** of such entries. When Dira runs in Docker, use `rtsp://mediamtx:8554/ktv1` for its input, keeping the playback URL reachable by the user's browser. Existing live ASR/model prerequisites still apply. A continuously running Dira reader is demand, so its channel stays active.

## Native service

```bash
uv sync --frozen --extra extraction
uv run --env-file .env --extra extraction uvicorn dira.extraction.service:create_app \
  --factory --host 127.0.0.1 --port 8002 --workers 1 \
  --no-access-log --timeout-graceful-shutdown 10
```

FFmpeg must be on PATH. `--env-file` exports regional proxy variables to child processes as well as loading service settings. Set `DIRA_EXTRACTOR_CONFIG` to the native catalog path and `DIRA_EXTRACTOR_PUBLISH_BASE=rtsp://127.0.0.1:8554`. Native MediaMTX must inherit `DIRA_EXTRACTOR_TOKEN`/`DIRA_EXTRACTOR_URL` and use an absolute hook/interpreter path instead of `/opt/dira/extractor_hook.py`.

Run exactly **one** uvicorn worker. Multiple worker processes would each manage their own publishers. `/health` is public liveness; authenticated `GET /channels` returns only IDs, enabled flags and active states (`extracting`, `publishing`, `renewing`, `retrying`). It never returns source URLs or cookies. `/leases/{id}` is the internal long-lived hook endpoint, not a URL-resolution API. Errors are deliberately sanitized; external-library stderr is suppressed because it can contain session credentials. A healthy service does not mean a channel is playable.

## Verification

```bash
uv run --extra extraction pytest tests/test_extraction.py tests/test_extraction_media.py -q
```

The media tests generate local H264/AAC HLS with FFmpeg and exercise both real libraries, including a controlled proxy with separate source/CDN hostnames and domain-scoped cookies. Other tests cover required proxy failure, DRM markers, API auth, reference counts, refresh/stall restart, cleanup races and a real HTTP hook disconnect. Without the extraction extra, media tests are explicitly skipped.

The library versions are locked in `uv.lock`; refresh and retest them when a provider changes. No installed version guarantees that a particular YouTube channel will be available without additional authorized access mechanisms.

Reference contracts: [MediaMTX 1.21.4 configuration](https://github.com/bluenviron/mediamtx/blob/v1.21.4/mediamtx.yml), [yt-dlp embedding](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp), [Streamlink stream API](https://streamlink.github.io/api/stream.html), [Streamlink proxy configuration](https://streamlink.github.io/cli/proxy.html).

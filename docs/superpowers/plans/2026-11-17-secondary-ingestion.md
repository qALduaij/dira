# Secondary ingestion implementation plan

**Goal:** Scaffold operator-configured yt-dlp/Streamlink extraction, per-source regional routing, and MediaMTX on-demand publishing without DRM bypass.

**Architecture:** An optional, single-worker FastAPI sidecar holds a reference-counted publisher per configured channel. A MediaMTX hook holds an authenticated streaming HTTP lease; disconnecting its last lease stops the publisher. A bounded subprocess extracts and reads HLS through Streamlink, piping media into FFmpeg over a local pipe. Restarting the extraction on failure or a configured refresh interval renews source URLs while clients keep a stable RTSP path (reconnection may be required).

**Scope:** The user's three-part request is the specification. Existing demo and direct feeds remain operational. No subscriptions, credentials, VPN changes, protected-channel tests or DRM bypass. Operator configurations are disabled examples. No commits are required in this existing uncommitted workspace.

## Review focus

- Last-reader disconnect and service shutdown must reap extraction and FFmpeg processes.
- Multiple readers must share one publisher; renewal must not leak children.
- A required but missing regional proxy must fail closed, including for CDN segment traffic.
- Credentials and signed URLs must not appear in command arguments, service responses or logs.
- Both extraction libraries must be exercised against controlled local HLS, not assumed compatible.

## Tasks

- [x] Add validated configuration and isolated extraction adapters; test routing, disabled channels, DRM rejection and local HLS.
- [x] Add lease API, process supervision, refresh/backoff and hook; test authentication, shared leases and process cleanup.
- [x] Add optional Docker overlay, dormant MediaMTX hooks, secret placeholders and operator guide; validate builds/config and a synthetic on-demand round trip.
- [x] Run regression suite and fresh code review, resolve material findings, record verification.

## Pre-flight

The only new interface to existing ingest is a stable `rtsp://mediamtx:8554/<channel>` URL. Hook and worker share a token and channel ID, never a source URL. The stock MediaMTX image contains no Python, so hooks are comments in the base configuration and enabled through a separate override using a Python-capable image. A VPN is externally provisioned; domain rules select an HTTP/SOCKS proxy endpoint for the entire source session.

Verification: see docs/VERIFICATION.md for actual checks and model/hardware limitations.

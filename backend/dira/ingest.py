"""Supervised local feed adapters; URLs come only from operator configuration."""

import asyncio
import json
import logging
import math
import platform
import random
import weakref
from collections import deque
from contextlib import suppress
from datetime import timedelta
from time import monotonic
from urllib.parse import urlparse

import numpy as np
import websockets

from .models import TDO, utcnow
from .perception import VisualDetector, parse_asr_lines
from .ocr_process import OCRProcess

log = logging.getLogger(__name__)


def audio_map(feed):
    index = feed.get("audio_stream_index", 0)
    program = feed.get("audio_program_id")
    if type(index) is not int or index < 0 or index > 65535:
        raise ValueError("invalid audio stream index")
    if program is not None and (type(program) is not int or program < 0 or program > 65535):
        raise ValueError("invalid audio program ID")
    return f"0:p:{program}:a:{index}" if program is not None else f"0:a:{index}"


def video_filter(kind):
    if kind == "ocr":
        return "fps=2,crop=in_w:in_h*0.20:0:in_h*0.80,scale=1280:144"
    return "fps=1,scale=640:360"


def load_feeds(path):
    if not path.exists():
        raise ValueError(f"Live mode requires feed configuration: {path}")
    feeds = json.loads(path.read_text())
    ids = set()
    for feed in feeds:
        if feed["id"] in ids:
            raise ValueError("duplicate feed ID")
        ids.add(feed["id"])
        audio_map(feed)
        if feed.get("audio_program_id") is not None and feed["input_url"].startswith("rtsp:"):
            raise ValueError("RTSP has no MPEG-TS program tables; select audio_stream_index instead")
        if urlparse(feed["input_url"]).scheme not in ("rtsp", "srt", "udp", "http", "https", "rtmp"):
            raise ValueError("feed must use an allowed streaming protocol")
        TDO(channel_id=feed["id"], start=utcnow(), end=utcnow())
        feed.update(
            status="connecting",
            name_ar=feed.get("name_ar", feed["name"]),
            short=feed.get("short", feed["id"]),
            color=feed.get("color", "#c6ac70"),
            region=feed.get("region", "Local"),
            category="Live",
            playback_url=feed.get("playback_url", ""),
            asr_lag_seconds=None,
            asr_resets=0,
            asr_skipped_seconds=0.0,
            asr_degraded=False,
            asr_last_reset_cause=None,
            ocr_unchanged_skips=0,
            ocr_worker_restarts=0,
            ocr_worker_pid=None,
            ocr_worker_started_at=None,
        )
    return feeds


class ASRLagExceeded(Exception):
    """`cause` is backlog, silent or wall_clock_jump; `estimate` is the coverage loss, bounded by session age."""

    def __init__(self, lag, cause="backlog", estimate=None):
        super().__init__(f"ASR lag {lag:.0f}s exceeded the configured ceiling ({cause})")
        self.lag, self.cause = lag, cause
        self.estimate = lag if estimate is None else estimate


class ASRLag:
    """Backlog reported by WhisperLiveKit, plus server silence beyond a grace period (a stalled session).

    WLK computes its backlog from the wall clock, so after host sleep a report can grow faster than real
    time; that is a clock jump, not transcription backlog."""

    def __init__(self, now, grace=15.0, jump_tolerance=5.0):
        self.reported, self.at, self.grace, self.started = 0.0, now, grace, now
        self.jump_tolerance, self.jumped = jump_tolerance, False

    def cause(self, ceiling):
        if self.jumped:
            return "wall_clock_jump"
        return "backlog" if self.reported >= ceiling else "silent"

    def update(self, payload, now):
        values = {}
        for key in (
            "remaining_time_transcription",
            "remaining_time_transcription_processing",
            "remaining_time_transcription_policy",
        ):
            try:
                value = float(payload[key])
                if math.isfinite(value) and value >= 0:
                    values[key] = value
            except (KeyError, TypeError, ValueError):
                pass
        if values:
            reported = max(
                values.get("remaining_time_transcription", 0),
                values.get("remaining_time_transcription_processing", 0)
                + values.get("remaining_time_transcription_policy", 0),
            )
            if reported - self.reported > (now - self.at) + self.jump_tolerance:
                self.jumped = True
            self.reported, self.at = reported, now

    def value(self, now):
        return self.reported + max(0.0, now - self.at - self.grace)


ASR_DEGRADED_WINDOW, ASR_DEGRADED_RESETS = 600.0, 3
ASR_RECOVERY, ASR_ALERT_COOLDOWN = 600.0, 1800.0


class ASRHealth:
    """Repeated speech resets mean ASR is not delivering; mark it degraded instead of looking connected."""

    def __init__(self, feed):
        self.feed, self.resets, self.alerted_at = feed, deque(), None

    def reset(self, now):
        """Record one reset; True when an operator alert is due (once per cooldown)."""
        self.resets.append(now)
        self.feed["_asr_last_reset"] = now
        while now - self.resets[0] > ASR_DEGRADED_WINDOW:
            self.resets.popleft()
        if len(self.resets) < ASR_DEGRADED_RESETS:
            return False
        self.feed["asr_degraded"] = True
        if self.alerted_at is not None and now - self.alerted_at < ASR_ALERT_COOLDOWN:
            return False
        self.alerted_at = now
        return True


def asr_recovered(feed, now):
    """Clear degradation after a quiet period with no resets."""
    if feed.get("asr_degraded") and now - feed.get("_asr_last_reset", now) >= ASR_RECOVERY:
        feed["asr_degraded"] = False
        return True
    return False


def seconds(value):
    if isinstance(value, (int, float)):
        return float(value)
    result = 0.0
    for part in str(value).split(":"):
        result = result * 60 + float(part)
    return result


async def stop_process(process):
    if process.returncode is None:
        with suppress(ProcessLookupError):
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 3)
        except TimeoutError:
            with suppress(ProcessLookupError):
                process.kill()
            await process.wait()


async def audio_session(runtime, feed):
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-nostdin",
        "-loglevel",
        "error",
        "-threads",
        str(getattr(runtime.settings, "ffmpeg_threads", 1)),
        *(["-rtsp_transport", "tcp"] if feed["input_url"].startswith("rtsp:") else []),
        "-i",
        feed["input_url"],
        "-map",
        audio_map(feed),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "s16le",
        "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    base, seen = utcnow(), {}
    try:
        async with websockets.connect(
            feed.get("asr_url", runtime.settings.asr_url), max_size=2**22, open_timeout=10
        ) as socket:
            config = json.loads(await asyncio.wait_for(socket.recv(), 10))
            if config.get("type") != "config" or not config.get("useAudioWorklet"):
                raise ValueError("WhisperLiveKit must run with --pcm-input")
            feed["status"] = "connecting"
            feed["asr_status"] = "degraded" if feed.get("asr_degraded") else "connected"
            ceiling = getattr(runtime.settings, "asr_max_lag", 0)
            lag = ASRLag(monotonic())
            feed["asr_lag_seconds"] = 0.0

            async def send_audio():
                while data := await asyncio.wait_for(
                    process.stdout.read(3200), getattr(runtime.settings, "media_timeout", 20)
                ):
                    feed["last_pcm_at"] = utcnow().isoformat()
                    feed["status"] = "connected"
                    await asyncio.wait_for(socket.send(data), 10)
                await socket.send(b"")

            def check_lag():
                now = monotonic()
                if asr_recovered(feed, now):
                    feed["asr_status"] = "connected"
                current = lag.value(now)
                feed["asr_lag_seconds"] = round(current, 1)
                if ceiling and current > ceiling:
                    raise ASRLagExceeded(current, lag.cause(ceiling), min(current, now - lag.started))

            sender = asyncio.create_task(send_audio())
            try:
                while True:
                    try:
                        # Cancelling recv() is safe; the timeout lets a silent server count as lag.
                        raw = await asyncio.wait_for(socket.recv(), 5)
                    except TimeoutError:
                        raw = None
                    except websockets.ConnectionClosedOK:
                        break
                    if sender.done() and not sender.cancelled():
                        sender.result()  # Propagate PCM stalls and transport failures.
                    payload = json.loads(raw) if raw is not None else {}
                    if payload.get("type") == "error":
                        raise RuntimeError("ASR reported an error")
                    if payload.get("type") == "ready_to_stop":
                        break
                    if raw is not None:
                        lag.update(payload, monotonic())
                    check_lag()  # Reject stale evidence BEFORE parse/delivery, including buffered lines.
                    for line in parse_asr_lines(payload, seen):
                        start = base + timedelta(seconds=seconds(line.get("start", 0)))
                        end = base + timedelta(seconds=seconds(line.get("end", 0)))
                        e = TDO(
                            channel_id=feed["id"],
                            start=start,
                            end=end,
                            transcript=line["text"],
                            translation=line.get("translation", ""),
                            speaker=f"{feed['id']}:{line['speaker']}"
                            if feed.get("diarization_enabled") and line.get("speaker") is not None
                            else None,
                            language=feed.get("language", "ar"),
                            source="whisperlivekit",
                        )
                        await deliver(runtime, e, check_lag)
                        feed["last_transcript_at"] = utcnow().isoformat()
                    check_lag()
            finally:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
    finally:
        await stop_process(process)


async def latest_frames(stream, frame_bytes, timeout=20):
    """Drain decoded video continuously; a slow model receives the newest frame."""
    queue = asyncio.Queue(maxsize=1)

    async def read():
        try:
            while True:
                raw = await asyncio.wait_for(stream.readexactly(frame_bytes), timeout)
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait((raw, utcnow()))
        except (asyncio.IncompleteReadError, OSError, TimeoutError) as exc:
            await queue.put(exc)

    reader = asyncio.create_task(read())
    try:
        while True:
            item = await queue.get()
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)


def backoff(delay):
    """Jittered retry delay so channels hit by one shared outage do not restart in lockstep."""
    return delay * random.uniform(1.0, 1.3)


_model_loads = weakref.WeakKeyDictionary()


def model_load_lock():
    """At most one ~1.2 GB OCR model load at a time, per event loop."""
    return _model_loads.setdefault(asyncio.get_running_loop(), asyncio.Lock())


class OCRWorker:
    """One long-lived OCR process per channel. It survives frame-session restarts and is replaced only when
    the worker itself fails, after an exponential, jittered backoff."""

    def __init__(self, feed, factory, max_delay=60.0):
        self.feed, self.factory, self.max_delay = feed, factory, max_delay
        self.process, self.failures, self.retry_at, self.starts = None, 0, 0.0, 0
        self.stats = {}
        feed.setdefault("ocr_worker_restarts", 0)
        feed.setdefault("ocr_worker_pid", None)

    async def _ensure(self):
        if self.process is not None and self.process.process.returncode is None:
            return self.process
        if self.process is not None:  # Died between exchanges.
            await self._discard()
        if (wait := self.retry_at - monotonic()) > 0:
            await asyncio.sleep(wait)
        async with model_load_lock():
            try:
                self.process = await self.factory()
            except Exception:
                self._failed()
                raise
        if self.starts:
            self.feed["ocr_worker_restarts"] = self.feed.get("ocr_worker_restarts", 0) + 1
        self.starts += 1
        self.feed["ocr_worker_pid"] = getattr(self.process.process, "pid", None)
        self.feed["ocr_worker_started_at"] = utcnow().isoformat()
        return self.process

    def _failed(self):
        self.failures += 1
        self.retry_at = monotonic() + backoff(min(2 ** (self.failures - 1), self.max_delay))

    async def _discard(self):
        process, self.process = self.process, None
        self.feed["ocr_worker_pid"] = None
        with suppress(Exception):
            await process.close()

    async def extract(self, raw):
        process = await self._ensure()
        try:
            text = await process.extract(raw)
        except BaseException as exc:
            # A timeout or cancellation mid-exchange leaves an unread response in the pipe; replace the worker.
            if not isinstance(exc, asyncio.CancelledError):
                self._failed()
            await self._discard()
            raise
        self.failures = 0
        self.stats = process.stats
        return text

    async def close(self):
        if self.process is not None:
            await self._discard()


async def observe_frames(runtime, feed, kind, ocr=None):
    s = runtime.settings
    ocr = ocr if kind == "ocr" else None
    detector = (
        await asyncio.to_thread(VisualDetector, s.visual_model, feed.get("labels", []), s.device)
        if kind == "visual"
        else None
    )
    accel = s.video_hwaccel
    hardware = accel == "videotoolbox" or (accel == "auto" and platform.system() == "Darwin")
    width, height = (1280, 144) if kind == "ocr" else (640, 360)
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-nostdin",
        "-loglevel",
        "error",
        "-threads",
        str(s.ffmpeg_threads),
        "-filter_threads",
        "1",
        *(["-hwaccel", "videotoolbox"] if hardware else []),
        *(["-rtsp_transport", "tcp"] if feed["input_url"].startswith("rtsp:") else []),
        "-i",
        feed["input_url"],
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        video_filter(kind),
        "-pix_fmt",
        "rgb24",
        "-f",
        "rawvideo",
        "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    frames = latest_frames(process.stdout, width * height * 3, getattr(s, "media_timeout", 20))
    previous_frame, last_inference, inferences = None, 0.0, 0
    try:
        async for raw, now in frames:
            frame = np.frombuffer(raw, np.uint8).reshape(height, width, 3)
            feed[f"last_{kind}_frame_at"] = now.isoformat()
            feed[f"{kind}_status"] = "connected"
            # Only skip nearly identical ticker frames; refresh periodically and never skip initial voting.
            thumb = frame[::8, ::8].astype(np.int16)
            same = previous_frame is not None and np.mean(np.abs(thumb - previous_frame)) < 0.5
            if ocr and same and inferences >= 2 and monotonic() - last_inference < 5:
                feed["ocr_unchanged_skips"] = feed.get("ocr_unchanged_skips", 0) + 1
                continue
            previous_frame, last_inference = thumb, monotonic()
            inferences += 1
            text = await ocr.extract(raw) if ocr else ""
            if ocr:
                feed["ocr_stats"] = getattr(ocr, "stats", {})
            entities = await asyncio.to_thread(detector.detect, frame, now.timestamp()) if detector else []
            if text or entities:
                feed[f"last_{kind}_observation_at"] = utcnow().isoformat()
                await deliver(
                    runtime,
                    TDO(
                        channel_id=feed["id"],
                        start=now,
                        end=now,
                        ocr=text,
                        visual=", ".join(e.name for e in entities),
                        entities=entities,
                        language=feed.get("language", "ar"),
                        source="local-perception",
                    ),
                )
    finally:
        feed[f"{kind}_status"] = "stopped"
        await frames.aclose()
        await stop_process(process)


async def frame_session(runtime, feed, ocr=None):
    # The optional full-scene detector must never receive the ticker-only OCR crop.
    async with asyncio.TaskGroup() as group:
        if runtime.settings.enable_ocr:
            group.create_task(observe_frames(runtime, feed, "ocr", ocr))
        if runtime.settings.visual_model:
            group.create_task(observe_frames(runtime, feed, "visual"))


async def speech_session(runtime, feed, health=None):
    """Bound speech staleness: drop the ASR backlog and rejoin live audio; video/OCR keep running."""
    while True:
        try:
            return await audio_session(runtime, feed)
        except ASRLagExceeded as exc:
            feed["asr_resets"] = feed.get("asr_resets", 0) + 1
            feed["asr_skipped_seconds"] = round(feed.get("asr_skipped_seconds", 0.0) + exc.estimate, 1)
            feed["asr_last_reset_cause"] = exc.cause
            feed["asr_lag_seconds"] = None
            alert = health.reset(monotonic()) if health else False
            feed["asr_status"] = "degraded" if feed.get("asr_degraded") else "reconnecting"
            feed["status"] = "reconnecting"
            if hasattr(runtime, "record_gap"):
                await runtime.record_gap(feed, f"asr_{exc.cause}", exc.estimate)
            if alert and hasattr(runtime, "health_alert"):
                await runtime.health_alert(
                    feed,
                    f"Speech recognition degraded: {len(health.resets)} resets in "
                    f"{ASR_DEGRADED_WINDOW / 60:.0f} min (last cause: {exc.cause}). Transcripts are incomplete.",
                )
            log.warning(
                "Feed %s ASR reset (%s, lag %.0fs, est. loss %.0fs); rejoining live audio",
                feed["id"], exc.cause, exc.lag, exc.estimate,
            )
            runtime.bus.publish("channels", runtime.channels)


async def supervise(runtime, feed, run, failed):
    """Restart one session kind with its own jittered exponential backoff; reset after a healthy run."""
    delay = 1
    while True:
        began = monotonic()
        try:
            await run()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # Log types, never credential-bearing adapter exception strings.
            try:
                await failed(exc)
            except Exception:
                log.exception("Feed %s failure bookkeeping failed", feed["id"])
        if monotonic() - began > 60:
            delay = 1
        runtime.bus.publish("channels", runtime.channels)
        await asyncio.sleep(backoff(delay))
        delay = min(delay * 2, 30)


async def supervise_feed(runtime, feed):
    """Speech and frames fail independently: a PCM stall must not reload the channel's OCR model."""
    s = runtime.settings
    ocr = (
        OCRWorker(
            feed,
            lambda: OCRProcess.start(
                feed.get("ocr_model_dir", s.ocr_model_dir),
                s.ocr_detection_model,
                feed.get("ocr_recognition_model", s.ocr_recognition_model),
                s.ocr_cpu_threads,
            ),
        )
        if s.enable_ocr
        else None
    )

    health = ASRHealth(feed)

    async def speech():
        await speech_session(runtime, feed, health)
        # A clean end (publisher EOF -> ready_to_stop) is still an interruption until the next session.
        feed["status"] = "reconnecting"
        if hasattr(runtime, "record_gap"):
            await runtime.record_gap(feed, "asr_session_end", None)

    async def speech_failed(exc):
        feed["status"] = "degraded"
        feed["asr_status"] = "disconnected"
        feed["last_error_type"] = type(exc).__name__
        if hasattr(runtime, "record_gap"):
            await runtime.record_gap(feed, type(exc).__name__, None)
        log.warning("Feed %s speech disconnected (%s); retrying", feed["id"], type(exc).__name__)

    async def frames():
        await frame_session(runtime, feed, ocr)

    async def frames_failed(exc):
        if s.enable_ocr:
            feed["ocr_status"] = "degraded"
        if s.visual_model:
            feed["visual_status"] = "degraded"
        feed["last_frame_error_type"] = type(exc).__name__
        if hasattr(runtime, "record_gap"):
            await runtime.record_gap(feed, f"frames:{type(exc).__name__}", None)
        log.warning("Feed %s video disconnected (%s); retrying", feed["id"], type(exc).__name__)

    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(supervise(runtime, feed, speech, speech_failed))
            if s.enable_ocr or s.visual_model:
                group.create_task(supervise(runtime, feed, frames, frames_failed))
    finally:
        feed["status"] = "stopped"
        if ocr:
            await ocr.close()


async def deliver(runtime, event, check=None):
    """Preserve the current observation while the durable outbox applies backpressure."""
    while True:
        if check:
            check()
        try:
            await runtime.ingest(event)
            return
        except OverflowError:
            await asyncio.sleep(1)

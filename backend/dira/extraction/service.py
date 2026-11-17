"""One uvicorn worker: shared on-demand publishers, bounded retries and cancellation."""

import asyncio
import hmac
import json
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse

from ..ingest import stop_process
from .config import Catalog, ExtractorSettings

log = logging.getLogger(__name__)


class Manager:
    def __init__(self, settings, catalog):
        self.settings, self.catalog = settings, catalog
        self.entries = {}
        self.lock = asyncio.Lock()

    def status(self):
        return {
            key: {k: value[k] for k in ("readers", "state", "attempts")}
            for key, value in self.entries.items()
        }

    async def acquire(self, channel):
        async with self.lock:
            if channel.id not in self.entries:
                self.entries[channel.id] = {
                    "readers": 0,
                    "state": "starting",
                    "attempts": 0,
                    "task": asyncio.create_task(self.supervise(channel)),
                }
            self.entries[channel.id]["readers"] += 1

    async def release(self, channel_id):
        async with self.lock:
            entry = self.entries.get(channel_id)
            if not entry:
                return
            entry["readers"] -= 1
            if entry["readers"] == 0:
                entry["task"].cancel()
                await asyncio.gather(entry["task"], return_exceptions=True)
                del self.entries[channel_id]

    async def close(self):
        async with self.lock:
            tasks = [e["task"] for e in self.entries.values()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.entries.clear()

    async def supervise(self, channel):
        delay = self.settings.retry_seconds
        while True:
            entry = self.entries[channel.id]
            entry["state"] = "extracting"
            entry["attempts"] += 1
            try:
                await self.publish_once(channel)
                delay = self.settings.retry_seconds
                entry["state"] = "renewing"
            except asyncio.CancelledError:
                raise
            except (OSError, RuntimeError, ValueError, TimeoutError):
                entry["state"] = "retrying"
                log.warning("Extractor channel %s unavailable; retrying", channel.id)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.settings.max_retry_seconds)

    async def publish_once(self, channel):
        read_fd, write_fd = os.pipe()
        processes, tasks = [], []
        try:
            env = dict(os.environ, DIRA_EXTRACTOR_CONFIG=str(self.settings.config.resolve()))
            source = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "dira.extraction.source",
                channel.id,
                stdout=write_fd,
                stderr=asyncio.subprocess.DEVNULL,
                env=env,
            )
            processes.append(source)
            ffmpeg = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-progress",
                "pipe:1",
                "-stats_period",
                "1",
                "-i",
                "pipe:0",
                "-map",
                "0:v:0",
                "-map",
                "0:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-f",
                "rtsp",
                "-rtsp_transport",
                "tcp",
                f"{self.settings.publish_base.rstrip('/')}/{channel.id}",
                stdin=read_fd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            processes.append(ffmpeg)
            os.close(read_fd)
            os.close(write_fd)
            read_fd = write_fd = None
            tasks = [asyncio.create_task(p.wait()) for p in processes]
            tasks.append(asyncio.create_task(self.watch_progress(ffmpeg, channel.id)))
            done, _ = await asyncio.wait(
                tasks, timeout=channel.refresh_seconds, return_when=asyncio.FIRST_COMPLETED
            )
            if done:
                for task in done:
                    task.result()
                raise RuntimeError("media pipeline ended")
            # A proactive refresh deliberately rebuilds the signed URL/session.
        finally:
            for fd in (read_fd, write_fd):
                if fd is not None:
                    os.close(fd)

            async def cleanup():
                for process in processes:
                    await stop_process(process)
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

            # A lease can close during a normal refresh's cleanup, not just during playback.
            reaping = asyncio.create_task(cleanup())
            try:
                await asyncio.shield(reaping)
            except asyncio.CancelledError:
                await reaping
                raise

    async def watch_progress(self, ffmpeg, channel_id):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.settings.startup_timeout
        last_frame = 0
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("media stalled")
            line = await asyncio.wait_for(ffmpeg.stdout.readline(), remaining)
            if not line:
                raise RuntimeError("publisher ended")
            if line.startswith(b"frame="):
                frame = int(line.split(b"=", 1)[1])
                if frame > last_frame:
                    last_frame = frame
                    deadline = loop.time() + self.settings.stall_timeout
                    self.entries[channel_id]["state"] = "publishing"


def create_app(settings=None):
    settings = settings or ExtractorSettings()

    @asynccontextmanager
    async def lifespan(app):
        if not settings.token.strip():
            raise ValueError("DIRA_EXTRACTOR_TOKEN is required")
        manager = Manager(settings, Catalog.load(settings.config))
        app.state.manager = manager
        try:
            yield
        finally:
            await manager.close()

    app = FastAPI(title="Dira secondary extractor", lifespan=lifespan, docs_url=None, redoc_url=None)

    async def authorize(authorization: str = Header(default="")):
        if not hmac.compare_digest(authorization.encode(), f"Bearer {settings.token}".encode()):
            raise HTTPException(401, "invalid extractor credentials")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/channels", dependencies=[Depends(authorize)])
    async def channels():
        manager = app.state.manager
        return {
            "channels": [
                {"id": c.id, "enabled": c.enabled, "extractor": c.extractor} for c in manager.catalog.channels
            ],
            "active": manager.status(),
        }

    @app.get("/leases/{channel_id}", dependencies=[Depends(authorize)])
    async def lease(channel_id: str):
        manager = app.state.manager
        try:
            channel = manager.catalog.channel(channel_id)
        except KeyError:
            raise HTTPException(404, "unknown channel") from None
        except ValueError:
            raise HTTPException(409, "channel disabled") from None

        async def events():
            await manager.acquire(channel)
            try:
                while True:
                    yield json.dumps(manager.status()[channel_id]) + "\n"
                    await asyncio.sleep(2)
            finally:
                # Starlette's cancellation scope must not interrupt process cleanup.
                import anyio

                with anyio.CancelScope(shield=True):
                    await manager.release(channel_id)

        return StreamingResponse(
            events(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return app

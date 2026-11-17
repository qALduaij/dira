import asyncio
import anyio
from contextlib import asynccontextmanager, suppress
import hmac
from pathlib import Path
from typing import Literal
from uuid import UUID
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
from .config import Settings
from .models import TDO, Rule, SearchRequest
from .runtime import Runtime

ROOT = Path(__file__).resolve().parents[2]


class SimulationControl(BaseModel):
    paused: bool


class BriefRequest(BaseModel):
    kind: Literal["morning", "narrative"] = "morning"


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > 1_048_576:
                raise HTTPException(413, "Request body exceeds 1 MiB")
            return message

        await self.app(scope, limited_receive, send)


def create_app(settings=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        runtime = Runtime(settings)
        app.state.runtime = runtime
        await runtime.start()
        try:
            yield
        finally:
            await runtime.stop()

    app = FastAPI(title="Dira | ديرة", version="0.1.0", lifespan=lifespan)
    app.add_middleware(BodyLimit)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts.split(","))
    allowed = set(settings.allowed_origins.split(","))
    semaphore = asyncio.Semaphore(8)

    @app.middleware("http")
    async def access(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if origin and origin not in allowed:
                return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
            if settings.api_token and not hmac.compare_digest(
                request.headers.get("authorization", ""), "Bearer " + settings.api_token
            ):
                return JSONResponse({"detail": "Bearer token required"}, status_code=401)
            length = request.headers.get("content-length", "0")
            if not length.isdigit() or int(length) > 1_048_576:
                return JSONResponse({"detail": "Request body exceeds 1 MiB"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    def rt():
        return app.state.runtime

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": settings.mode}

    @app.get("/api/snapshot")
    async def snapshot():
        return rt().snapshot()

    @app.get("/api/metrics")
    async def metrics():
        return rt().metrics()

    @app.get("/api/graph")
    async def graph():
        return rt().graph()

    @app.get("/api/evidence/{key}")
    async def evidence(key: UUID):
        event = await asyncio.to_thread(rt().db.get, str(key))
        if not event:
            raise HTTPException(404, "Observation not found")
        return event

    @app.post("/api/ingest", status_code=201)
    async def ingest(event: TDO):
        if settings.mode == "live" and (not settings.allow_external_ingest or not settings.api_token):
            raise HTTPException(
                403, "External live ingestion requires explicit enablement and API authentication"
            )
        event = event.model_copy(
            update={"source": "external-api", "simulated": settings.mode == "simulation"}
        )
        try:
            async with semaphore:
                added = await rt().ingest(event)
            return {"id": str(event.id), "inserted": added}
        except OverflowError as exc:
            raise HTTPException(503, str(exc), headers={"Retry-After": "5"}) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/search")
    async def search(query: SearchRequest):
        async with semaphore:
            return await rt().search(query)

    @app.get("/api/rules")
    async def rules():
        return rt().db.objects("rule")

    @app.post("/api/rules", status_code=201)
    async def save_rule(rule: Rule):
        if len(rt().db.objects("rule")) >= 100 and not any(
            x["id"] == str(rule.id) for x in rt().db.objects("rule")
        ):
            raise HTTPException(409, "Maximum 100 rules")
        rt().db.save("rule", rule)
        rt().reload_rules()
        rt().bus.publish("rules", rt().db.objects("rule"))
        return rule

    @app.delete("/api/rules/{key}", status_code=204)
    async def delete_rule(key: UUID):
        rt().db.delete("rule", str(key))
        rt().reload_rules()
        rt().bus.publish("rules", rt().db.objects("rule"))

    @app.post("/api/alerts/{key}/ack")
    async def acknowledge(key: UUID):
        alert = rt().db.object("alert", str(key))
        if not alert:
            raise HTTPException(404, "Alert not found")
        alert["acknowledged"] = True
        rt().db.save("alert", alert)
        rt().bus.publish("alert", alert)
        return alert

    @app.post("/api/briefs", status_code=202)
    async def brief(body: BriefRequest):
        try:
            return rt().enqueue_brief(body.kind)
        except OverflowError as exc:
            raise HTTPException(429, str(exc)) from exc

    @app.get("/api/gaps")
    async def gaps():
        return rt().db.objects("gap", 200)

    @app.get("/api/jobs/{key}")
    async def job(key: UUID):
        if str(key) not in rt().job_status:
            raise HTTPException(404, "Job not found")
        return rt().job_status[str(key)]

    @app.post("/api/simulation")
    async def simulation(control: SimulationControl):
        if settings.mode != "simulation":
            raise HTTPException(409, "Simulation controls unavailable in live mode")
        rt().paused = control.paused
        rt().bus.publish("metrics", rt().metrics())
        return {"paused": rt().paused}

    @app.websocket("/api/ws")
    async def socket(ws: WebSocket):
        origin = ws.headers.get("origin")
        if origin and origin not in allowed:
            await ws.close(code=1008)
            return
        await ws.accept()
        queue = None
        sender = None
        try:
            auth = await asyncio.wait_for(ws.receive_json(), 5)
            if settings.api_token and not hmac.compare_digest(str(auth.get("token", "")), settings.api_token):
                await ws.close(code=1008)
                return
            queue = rt().bus.subscribe()
            await ws.send_json({"type": "snapshot", "sequence": rt().bus.sequence, "data": rt().snapshot()})

            async def send():
                while True:
                    try:
                        message = await asyncio.wait_for(queue.get(), 20)
                    except asyncio.TimeoutError:
                        message = {"type": "heartbeat", "data": {}}
                    await asyncio.wait_for(ws.send_json(message), 10)

            sender = asyncio.create_task(send())

            async def receive():
                while True:
                    await ws.receive_text()

            receiver = asyncio.create_task(receive())
            try:
                await asyncio.wait([sender, receiver], return_when=asyncio.FIRST_COMPLETED)
            finally:
                receiver.cancel()
                with anyio.CancelScope(shield=True):
                    await asyncio.gather(receiver, return_exceptions=True)
        except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, asyncio.CancelledError):
            pass
        finally:
            if queue is not None:
                rt().bus.queues.discard(queue)
            with anyio.CancelScope(shield=True):
                if sender:
                    sender.cancel()
                    await asyncio.gather(sender, return_exceptions=True)
                with suppress(Exception):
                    await ws.close()

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "DELETE", "PUT", "PATCH"])
    async def missing_api(path: str):
        raise HTTPException(404, "Unknown API route")

    dist = ROOT / "frontend" / "dist"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    if (ROOT / "media").exists():
        app.mount("/media", StaticFiles(directory=ROOT / "media"), name="media")

    @app.get("/{path:path}")
    async def frontend(path: str):
        if not (dist / "index.html").exists():
            return JSONResponse(
                {"detail": "Build frontend with npm --prefix frontend run build"}, status_code=503
            )
        return FileResponse(dist / "index.html")

    return app


app = create_app()

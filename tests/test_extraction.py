import asyncio
import json
import os
import signal
import socket
import sys
from pathlib import Path

import httpx
import pytest
import uvicorn
from dira.extraction.config import Catalog, Channel, ExtractorSettings, proxy_for
from dira.extraction.service import Manager, create_app
from dira.extraction.source import select_ytdlp_stream
from fastapi.testclient import TestClient


def test_proxy_domain_boundary_and_missing_route(monkeypatch):
    routes = {"bbc.co.uk": "UK_PROXY", "news.bbc.co.uk": "NEWS_PROXY"}
    monkeypatch.setenv("UK_PROXY", "http://127.0.0.1:9010")
    monkeypatch.setenv("NEWS_PROXY", "socks5h://127.0.0.1:9011")
    assert proxy_for("https://www.bbc.co.uk/live", routes) == "http://127.0.0.1:9010"
    assert proxy_for("https://news.bbc.co.uk/live", routes) == "socks5h://127.0.0.1:9011"
    assert proxy_for("https://evilbbc.co.uk/live", routes) is None
    monkeypatch.delenv("UK_PROXY")
    with pytest.raises(ValueError, match="proxy"):
        proxy_for("https://bbc.co.uk/live", routes)


def test_invalid_channels_and_drm_are_rejected():
    with pytest.raises(ValueError):
        Channel(id="../escape", source_url="https://example.test/live")
    with pytest.raises(ValueError):
        Channel(id="bbc", enabled=True, source_url="file:///etc/passwd")
    info = {
        "url": "https://cdn.test/stream.m3u8",
        "protocol": "m3u8_native",
        "vcodec": "h264",
        "acodec": "aac",
    }
    assert select_ytdlp_stream(info) == info["url"]
    for extra in ({"has_drm": True}, {"acodec": "none"}, {"protocol": "http"}, {"url": "file:///etc/passwd"}):
        with pytest.raises(ValueError):
            select_ytdlp_stream(info | extra)


def test_disabled_and_duplicate_catalog(tmp_path):
    path = tmp_path / "channels.json"
    path.write_text(json.dumps({"channels": [{"id": "bbc", "enabled": False}]}))
    catalog = Catalog.load(path)
    with pytest.raises(ValueError, match="disabled"):
        catalog.channel("bbc")
    path.write_text(json.dumps({"channels": [{"id": "bbc"}, {"id": "bbc"}]}))
    with pytest.raises(ValueError, match="duplicate"):
        Catalog.load(path)


async def test_shared_leases_cancel_publisher_on_last_release():
    manager = Manager(ExtractorSettings(token="test"), Catalog(channels=[]))
    entered, stopped = asyncio.Event(), asyncio.Event()

    async def publisher(channel):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            stopped.set()

    manager.supervise = publisher
    channel = Channel(id="bbc", enabled=True, source_url="https://example.test/live")
    await manager.acquire(channel)
    await entered.wait()
    await manager.acquire(channel)
    assert manager.status()["bbc"]["readers"] == 2
    await manager.release("bbc")
    assert not stopped.is_set()
    await manager.release("bbc")
    assert stopped.is_set()
    assert manager.status() == {}


def test_api_auth_disabled_and_unknown_channels(tmp_path):
    path = tmp_path / "channels.json"
    path.write_text('{"channels":[{"id":"bbc","enabled":false}]}')
    settings = ExtractorSettings(token="test-secret", config=path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/channels").status_code == 401
        headers = {"Authorization": "Bearer test-secret"}
        assert client.get("/leases/bbc", headers=headers).status_code == 409
        assert client.get("/leases/missing", headers=headers).status_code == 404
        assert "test-secret" not in client.get("/channels", headers=headers).text


async def until(predicate, timeout=6):
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.02)


@pytest.mark.parametrize("stalled", [False, True])
async def test_renewal_or_stall_restarts_and_reaps_children(monkeypatch, stalled):
    real_spawn = asyncio.create_subprocess_exec
    children = []

    async def spawn(*args, **kwargs):
        if "dira.extraction.source" in args:
            program = "import os,time\nwhile True: os.write(1,b'x'*1024); time.sleep(.02)"
        elif stalled:
            program = "import time; print('frame=1',flush=True); time.sleep(30)"
        else:
            program = "import os\ni=0\nwhile os.read(0,1024):\n i+=1\n print('frame='+str(i),flush=True)"
        child = await real_spawn(sys.executable, "-c", program, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    manager = Manager(
        ExtractorSettings(token="test", stall_timeout=1, retry_seconds=0.1), Catalog(channels=[])
    )
    channel = Channel(id="test", enabled=True, source_url="https://example.test/live")
    if not stalled:
        channel = channel.model_copy(update={"refresh_seconds": 0.3})
    try:
        await manager.acquire(channel)
        await until(lambda: manager.status()["test"]["attempts"] >= 2 and len(children) >= 4)
    finally:
        await manager.close()
    assert len(children) >= 4
    assert all(child.returncode is not None for child in children)
    assert manager.status() == {}


async def test_hook_disconnect_releases_real_http_lease(tmp_path, monkeypatch):
    async def idle(self, channel):
        await asyncio.Future()

    monkeypatch.setattr(Manager, "supervise", idle)
    path = tmp_path / "channels.json"
    path.write_text('{"channels":[{"id":"bbc","enabled":true,"source_url":"https://example.test/live"}]}')
    app = create_app(ExtractorSettings(token="test-token", config=path))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", lifespan="on", timeout_graceful_shutdown=2)
    )
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    hook = None
    try:
        await until(lambda: server.started)
        hook = await asyncio.create_subprocess_exec(
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "scripts/extractor_hook.py"),
            env=dict(
                os.environ,
                MTX_PATH="bbc",
                DIRA_EXTRACTOR_TOKEN="test-token",
                DIRA_EXTRACTOR_URL=f"http://127.0.0.1:{port}",
            ),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await until(lambda: "bbc" in app.state.manager.status())
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(
                f"http://127.0.0.1:{port}/channels", headers={"Authorization": "Bearer test-token"}
            )
        assert response.json()["active"]["bbc"]["readers"] == 1
        hook.send_signal(signal.SIGINT)
        stdout, stderr = await asyncio.wait_for(hook.communicate(), 5)
        assert hook.returncode == 0
        assert b"test-token" not in stdout + stderr
        await until(lambda: not app.state.manager.status())
    finally:
        if hook and hook.returncode is None:
            hook.kill()
            await hook.wait()
        server.should_exit = True
        await serving
        sock.close()


def test_invalid_configuration_never_renders_secrets():
    for validate in (
        lambda: Catalog.model_validate({"channels": [{"id": "bbc", "source_url": "https://x/?s=SECRET "}]}),
        lambda: ExtractorSettings(token="SECRET", publish_base="invalid"),
    ):
        with pytest.raises(ValueError) as error:
            validate()
        assert "SECRET" not in str(error.value)


async def test_disconnect_during_refresh_cleanup_finishes_reaping(monkeypatch):
    from dira.extraction import service

    entered, cleaned = asyncio.Event(), []

    class Child:
        async def wait(self):
            await asyncio.Future()

    async def spawn(*args, **kwargs):
        return Child()

    async def progress(*args):
        raise RuntimeError("stream ended")

    async def stop(child):
        entered.set()
        await asyncio.sleep(0.05)
        cleaned.append(child)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    monkeypatch.setattr(service, "stop_process", stop)
    manager = Manager(ExtractorSettings(token="test"), Catalog(channels=[]))
    monkeypatch.setattr(manager, "watch_progress", progress)
    channel = Channel(id="test", enabled=True, source_url="https://example.test/live")
    await manager.acquire(channel)
    await asyncio.wait_for(entered.wait(), 2)
    await manager.release("test")
    assert len(cleaned) == 2
    assert manager.status() == {}

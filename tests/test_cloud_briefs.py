import json

import httpx
import pytest
from dira.briefs import generate_brief
from dira.config import Settings
from dira.simulation import make_event


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 401])
async def test_cloud_brief_label_and_expired_key_fallback(monkeypatch, status):
    event = make_event(1)
    client_class = httpx.AsyncClient

    def respond(request):
        assert request.headers["Authorization"] == "Bearer test-only"
        assert json.loads(request.content)["reasoning"] == {"enabled": False}
        return httpx.Response(
            status,
            json={"choices": [{"message": {"content": f"SIMULATION: observation [{event.id}]"}}]},
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(**kwargs, transport=httpx.MockTransport(respond)),
    )
    settings = Settings(
        _env_file=None,
        llm_url="https://openrouter.ai/api/v1",
        llm_provider="cloud",
        llm_api_key="test-only",
    )
    brief = await generate_brief([event], "morning", settings)
    assert brief.mode == ("cloud-llm" if status == 200 else "extractive")
    assert brief.simulated
    assert str(event.id) in brief.content
    assert bool(brief.error) == (status != 200)

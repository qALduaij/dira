from fastapi.testclient import TestClient
from dira.api import create_app
from dira.config import Settings


def test_api_snapshot_search_websocket_and_rules(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, simulation_interval=100))
    with TestClient(app) as c:
        assert c.get("/health").json()["status"] == "ok"
        state = c.get("/api/snapshot").json()
        assert len(state["channels"]) == 4
        assert state["events"][0]["simulated"]
        assert c.post("/api/search", json={"query": "النفط"}).json()["results"]
        assert c.post("/api/search", json={"query": " "}).status_code == 422
        assert c.post("/api/rules", json={"name": "bad", "kind": "regex", "pattern": "("}).status_code == 422
        with c.websocket_connect("/api/ws") as ws:
            ws.send_json({"token": ""})
            assert ws.receive_json()["type"] == "snapshot"
            c.post("/api/simulation", json={"paused": True})
            assert ws.receive_json()["type"] == "metrics"
        job = c.post("/api/briefs", json={"kind": "morning"})
        assert job.status_code == 202


def test_auth_and_unknown_api_path(tmp_path):
    with TestClient(
        create_app(Settings(data_dir=tmp_path, api_token="secret", simulation_interval=100))
    ) as c:
        assert c.get("/api/snapshot").status_code == 401
        assert c.get("/api/snapshot", headers={"Authorization": "Bearer secret"}).status_code == 200
        assert c.get("/api/nope", headers={"Authorization": "Bearer secret"}).status_code == 404
        assert (
            c.post(
                "/api/simulation",
                json={"paused": True},
                headers={"Authorization": "Bearer secret", "Origin": "https://evil.example"},
            ).status_code
            == 403
        )

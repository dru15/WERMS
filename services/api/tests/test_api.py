from uuid import uuid4

import httpx
import pytest
from werms_api.config import Settings
from werms_api.main import create_app
from werms_api.network import build_demo_network
from werms_api.operations import Operations

OPERATOR_KEY = "test-only-operator-key-with-enough-characters"


@pytest.fixture
async def client(tmp_path):
    path = tmp_path / "pilot.sqlite3"
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            operational_db_path=str(path),
            operator_api_key=OPERATOR_KEY,
        ),
        Operations(path, network=build_demo_network()),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_health_and_network_contract(client):
    assert (await client.get("/health/live")).json() == {"status": "ok"}
    state = (await client.get("/api/v1/system/status")).json()
    assert state["model_mode"] == "disabled"
    assert state["operational_store"] == "sqlite-pilot"
    graph = (await client.get("/api/v1/network")).json()
    assert len(graph["nodes"]) == 48
    assert len(graph["roads"]) == 82
    assert state["road_version"] == graph["version"]


async def test_preview_confirmation_closure_and_checkin_contract(client):
    inputs = {"origin_node_id": "n24", "party_size": 4}
    preview = await client.post("/api/v1/routes/preview", json=inputs)
    assert preview.status_code == 200
    assert all(s["reserved_demand"] == 0 for s in (await client.get("/api/v1/shelters")).json())
    inputs["request_id"] = str(uuid4())
    booked = await client.post("/api/v1/routes", json=inputs)
    assert booked.status_code == 201
    plan = booked.json()
    assert plan["shelter"]["reserved_demand"] == 4
    assert (await client.post("/api/v1/routes", json=inputs)).json()["route_id"] == plan["route_id"]
    road = plan["edge_ids"][0]
    protected = f"/api/v1/roads/{road}/closure"
    closure = {"closed": True, "reason": "Confirmed test incident"}
    assert (await client.put(protected, json=closure)).status_code == 401
    headers = {"X-Operator-Key": OPERATOR_KEY}
    assert (await client.put(protected, json=closure, headers=headers)).status_code == 200
    invalid = (await client.get(f"/api/v1/routes/{plan['route_id']}/status")).json()
    assert invalid["status"] == "invalid"
    assert invalid["shelter"]["reserved_demand"] == 0
    new = (
        await client.post(
            "/api/v1/routes",
            json={
                **inputs,
                "request_id": str(uuid4()),
                "replace_route_id": plan["route_id"],
            },
        )
    ).json()
    assert road not in new["edge_ids"]
    endpoint = f"/api/v1/routes/{new['route_id']}/arrive"
    assert (await client.post(endpoint)).status_code == 401
    arrival = (await client.post(endpoint, headers=headers)).json()
    assert arrival["status"] == "arrived"
    assert (await client.post(endpoint, headers=headers)).json()["shelter"] == arrival["shelter"]
    assert (await client.get("/api/v1/operator/audit")).status_code == 401
    audit = (await client.get("/api/v1/operator/audit", headers=headers)).json()
    assert any(event["action"] == "reservation.arrived" for event in audit)


async def test_operator_access_and_invalid_inputs(client):
    assert (await client.post("/api/v1/operator/access", json={"key": "秘密"})).status_code == 401
    assert (await client.post("/api/v1/operator/access", json={"key": "wrong"})).status_code == 401
    assert (
        await client.post("/api/v1/operator/access", json={"key": OPERATOR_KEY})
    ).status_code == 200
    assert (await client.post("/api/v1/routes/preview", json={"party_size": 2})).status_code == 422
    assert (
        await client.post(
            "/api/v1/routes/preview",
            json={
                "origin_node_id": "n24",
                "party_size": 21,
            },
        )
    ).status_code == 422
    assert (
        await client.post(
            "/api/v1/routes/preview",
            json={
                "origin": {"latitude": 0, "longitude": 0},
            },
        )
    ).json()["detail"]["code"] == "UNSUPPORTED_ORIGIN"

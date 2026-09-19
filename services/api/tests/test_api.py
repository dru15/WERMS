import httpx
import pytest

from werms_api.main import app, store


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
        yield api_client


async def test_health_and_status_contract(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health/live")).json() == {"status": "ok"}
    response = await client.get("/api/v1/system/status")
    assert response.status_code == 200
    assert response.json()["model_mode"] == "disabled"


async def test_route_contract_contains_safety_versions(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/routes",
        json={"origin": {"latitude": 34.0522, "longitude": -118.2437}, "party_size": 1},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["hazard_version"] == store.hazard.version
    assert payload["road_version"] == store.road_version
    assert payload["model_mode"] == "disabled"
    assert "HARD_HAZARDS_EXCLUDED" in payload["reason_codes"]
    assert "SOFT_RISK_PENALTY_APPLIED" not in payload["reason_codes"]

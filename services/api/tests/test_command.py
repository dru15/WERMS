from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from werms_api.command import CommandDesk
from werms_api.config import Settings
from werms_api.identity import Identity
from werms_api.main import create_app
from werms_api.network import build_demo_network
from werms_api.operations import OperationError, Operations
from werms_api.schemas import DispatchRequest, IncidentRequest, ResourceRequest

KEY = "test-only-bootstrap-key-long-enough"
PASSWORD = "test-only-password-long-enough"


@pytest.fixture
async def desk(tmp_path):
    path = tmp_path / "command.sqlite3"
    ops = Operations(path, network=build_demo_network())
    app = create_app(
        Settings(
            _env_file=None, app_env="test", operational_db_path=str(path), operator_api_key=KEY
        ),
        ops,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, ops


async def staff(client, username, role, shelter_id=None):
    result = await client.post(
        "/api/v1/operator/accounts",
        headers={"X-Operator-Key": KEY},
        json={"username": username, "password": PASSWORD, "role": role, "shelter_id": shelter_id},
    )
    assert result.status_code == 201, result.text
    session = (
        await client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    ).json()
    return {"Authorization": f"Bearer {session['token']}"}


async def test_role_scope_shelter_conflicts_and_session_revocation(desk):
    client, ops = desk
    sites = (await client.get("/api/v1/shelters")).json()
    scoped = await staff(client, "site-staff", "shelter", sites[0]["shelter_id"])
    dispatch = await staff(client, "dispatch", "dispatcher")
    assert (await client.get("/api/v1/operator/accounts", headers=dispatch)).status_code == 403
    assert (await client.get("/api/v1/operator/audit", headers=scoped)).status_code == 403
    assert (
        await client.post(
            "/api/v1/resources", headers=scoped, json={"name": "Engine 1", "kind": "engine"}
        )
    ).status_code == 403
    update = {
        "occupancy": 0,
        "status": "open",
        "reason": "Exercise correction",
        "expected_updated_at": sites[1]["updated_at"],
    }
    assert (
        await client.put(f"/api/v1/shelters/{sites[1]['shelter_id']}", headers=scoped, json=update)
    ).status_code == 403
    inputs = {
        "origin_node_id": "n24",
        "party_size": 2,
        "shelter_id": sites[0]["shelter_id"],
        "request_id": str(uuid4()),
    }
    booking = (await client.post("/api/v1/routes", json=inputs)).json()
    update.update(expected_updated_at=sites[0]["updated_at"], occupancy=sites[0]["capacity"])
    endpoint = f"/api/v1/shelters/{sites[0]['shelter_id']}"
    assert (await client.put(endpoint, headers=scoped, json=update)).status_code == 409
    update.update(occupancy=0, status="closed")
    assert (await client.put(endpoint, headers=scoped, json=update)).status_code == 200
    invalid = (await client.get(f"/api/v1/routes/{booking['route_id']}")).json()
    assert invalid["status"] == "invalid" and invalid["cause"] == "SHELTER_CLOSED"
    assert invalid["shelter"]["reserved_demand"] == 0
    assert (await client.put(endpoint, headers=scoped, json=update)).status_code == 409
    token = scoped["Authorization"][7:]
    assert (
        Identity(Operations(ops.path, network=build_demo_network())).authenticate(token)["role"]
        == "shelter"
    )
    assert (await client.post("/api/v1/auth/logout", headers=scoped)).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=scoped)).status_code == 401
    assert (
        await client.post(
            "/api/v1/operator/accounts/dispatch/disable", headers={"X-Operator-Key": KEY}
        )
    ).status_code == 200
    assert (await client.get("/api/v1/command", headers=dispatch)).status_code == 401
    with ops.transaction() as db:
        assert PASSWORD not in " ".join(str(tuple(r)) for r in db.execute("SELECT * FROM accounts"))


async def test_incident_dispatch_acknowledgement_release_and_audit(desk):
    client, _ = desk
    headers = await staff(client, "dispatcher", "dispatcher")
    report = {
        "title": "Exercise road obstruction",
        "description": "Training scenario obstruction",
        "source": "Project exercise report",
        "observed_at": datetime.now(UTC).isoformat(),
        "priority": "high",
        "road_id": None,
    }
    incident = (await client.post("/api/v1/incidents", headers=headers, json=report)).json()
    resource = (
        await client.post(
            "/api/v1/resources", headers=headers, json={"name": "Exercise engine", "kind": "engine"}
        )
    ).json()
    body = {
        "request_id": str(uuid4()),
        "resource_id": resource["id"],
        "incident_id": incident["id"],
        "note": "Training dispatch instructions",
    }
    assignment = (await client.post("/api/v1/assignments", headers=headers, json=body)).json()
    replay = (await client.post("/api/v1/assignments", headers=headers, json=body)).json()
    assert replay["id"] == assignment["id"]
    assert (
        await client.post(
            "/api/v1/assignments", headers=headers, json={**body, "request_id": str(uuid4())}
        )
    ).status_code == 409
    target = f"/api/v1/incidents/{incident['id']}"
    change = {
        "version": 1,
        "status": "acknowledged",
        "priority": "critical",
        "note": "Escalated report",
    }
    assert (await client.put(target, headers=headers, json=change)).status_code == 200
    assert (await client.put(target, headers=headers, json=change)).status_code == 409
    change.update(version=2, status="resolved")
    assert (await client.put(target, headers=headers, json=change)).status_code == 409
    assignment_url = f"/api/v1/assignments/{assignment['id']}"
    assert (
        await client.put(
            assignment_url,
            headers=headers,
            json={"status": "resolved", "note": "Too early to complete"},
        )
    ).status_code == 409
    for status in ("acknowledged", "resolved", "resolved"):
        assert (
            await client.put(
                assignment_url,
                headers=headers,
                json={"status": status, "note": "Operator exercise update"},
            )
        ).status_code == 200
    assert (await client.put(target, headers=headers, json=change)).status_code == 200
    state = (await client.get("/api/v1/command", headers=headers)).json()
    assert state["resources"][0]["status"] == "available"
    assert state["incidents"][0]["status"] == "resolved"
    # Reporting never silently turns an unverified observation into a hard road closure.
    assert (await client.get("/api/v1/hazards")).json()["blocked_edge_ids"]
    events = (await client.get("/api/v1/operator/audit", headers={"X-Operator-Key": KEY})).json()
    assert any(e["action"] == "resource.dispatched" and e["actor"] == "dispatcher" for e in events)


async def test_login_throttle_persists_failures(desk):
    client, _ = desk
    for _ in range(5):
        assert (
            await client.post(
                "/api/v1/auth/login", json={"username": "unknown", "password": "wrong"}
            )
        ).status_code == 401
    assert (
        await client.post("/api/v1/auth/login", json={"username": "unknown", "password": "wrong"})
    ).status_code == 429


def test_parallel_dispatch_never_double_allocates_and_survives_restart(tmp_path):
    path = tmp_path / "dispatch.sqlite3"
    network = build_demo_network()
    command = CommandDesk(Operations(path, network=network))
    incident = command.report(
        IncidentRequest(
            title="Test incident",
            description="Exercise incident",
            source="Exercise source",
            observed_at=datetime.now(UTC),
            priority="high",
        ),
        "test",
    )
    resource = command.register(ResourceRequest(name="One shared engine", kind="engine"), "test")

    def attempt(_):
        local = CommandDesk(Operations(path, network=network))
        try:
            local.dispatch(
                DispatchRequest(
                    request_id=uuid4(),
                    resource_id=resource["id"],
                    incident_id=incident["id"],
                    note="Exercise dispatch",
                ),
                "test",
            )
            return True
        except OperationError as error:
            assert error.code == "RESOURCE_UNAVAILABLE"
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(attempt, range(8))) == 1
    restarted = CommandDesk(Operations(path, network=network)).snapshot()
    assert len(restarted["assignments"]) == 1
    assert restarted["resources"][0]["status"] == "deployed"

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from werms_api.network import build_demo_network
from werms_api.operations import OperationError, Operations
from werms_api.scenarios import compare_scenario
from werms_api.schemas import ConfirmRouteRequest, ScenarioRequest


def test_scenario_is_repeatable_and_never_writes_bookings_closures_or_audit(tmp_path):
    ops = Operations(tmp_path / "lab.sqlite3", network=build_demo_network())
    now = datetime.now(UTC)
    booking = ops.confirm(ConfirmRouteRequest(origin_node_id="n24", request_id=uuid4()), now=now)
    before = ops.snapshot(now=now).model_dump_json()
    audit = ops.audit()
    request = ScenarioRequest(origin_node_id="n24", blocked_edge_ids=[booking.edge_ids[0]])
    first, second = compare_scenario(ops, request, now=now), compare_scenario(ops, request, now=now)
    assert first["outcome"] == "rerouted"
    assert first["simulated"] == second["simulated"]
    assert all(request.blocked_edge_ids[0] not in p["edge_ids"] for p in first["simulated"])
    assert ops.snapshot(now=now).model_dump_json() == before
    assert ops.audit() == audit
    assert ops.get_route(booking.route_id, now=now).status == "valid"


def test_scenario_handles_no_route_unknown_inputs_and_site_unavailability(tmp_path):
    ops = Operations(tmp_path / "lab.sqlite3", network=build_demo_network())
    request = ScenarioRequest(
        origin_node_id="n24", unavailable_shelter_ids=[s["id"] for s in ops.network["shelters"]]
    )
    result = compare_scenario(ops, request)
    assert result["outcome"] == "no_route" and result["delta_minutes"] is None
    assert result["reachable_before"] > 0 and result["reachable_after"] == 0
    with pytest.raises(OperationError, match="unknown road"):
        compare_scenario(
            ops, ScenarioRequest(origin_node_id="n24", blocked_edge_ids=["not-a-road"])
        )


def test_lab_excludes_expired_demand_without_changing_saved_reservation(tmp_path):
    ops = Operations(tmp_path / "lab.sqlite3", network=build_demo_network())
    then = datetime.now(UTC) - timedelta(hours=1)
    booking = ops.confirm(
        ConfirmRouteRequest(origin_node_id="n24", request_id=uuid4(), party_size=3), now=then
    )
    result = compare_scenario(ops, ScenarioRequest(origin_node_id="n24"))
    assert all(p["shelter"]["reserved_demand"] == 0 for p in result["baseline"])
    with ops.transaction() as db:
        assert (
            db.execute("SELECT status FROM routes WHERE id=?", (booking.route_id,)).fetchone()[0]
            == "valid"
        )

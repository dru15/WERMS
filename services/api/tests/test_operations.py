from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from werms_api.network import build_demo_network
from werms_api.operations import OperationError, Operations
from werms_api.schemas import ConfirmRouteRequest, RouteRequest


@pytest.fixture
def operations(tmp_path):
    return Operations(tmp_path / "pilot.sqlite3", network=build_demo_network())


def confirmation(**overrides):
    return ConfirmRouteRequest(
        origin_node_id="n24",
        party_size=4,
        request_id=uuid4(),
        **overrides,
    )


def test_previews_do_not_consume_capacity_and_paths_match_network(operations):
    request = RouteRequest(origin_node_id="n24", party_size=20)
    initial = operations.snapshot()
    roads = {r["id"]: r for r in operations.network["roads"]}
    for _ in range(20):
        plans = operations.preview(request)
        assert len(plans) == 3
        for plan in plans:
            assert not set(plan.edge_ids) & set(initial.hazard.blocked_edge_ids)
            for i, edge_id in enumerate(plan.edge_ids):
                road = roads[edge_id]
                assert {plan.path[i].node_id, plan.path[i + 1].node_id} == {
                    road["from"],
                    road["to"],
                }
    assert operations.snapshot() == initial


def test_confirm_is_idempotent_and_rejects_reused_inputs(operations):
    request = confirmation()
    first = operations.confirm(request)
    second = operations.confirm(request)
    assert first.route_id == second.route_id
    assert second.shelter.reserved_demand == 4
    with pytest.raises(OperationError, match="different inputs"):
        operations.confirm(request.model_copy(update={"party_size": 5}))
    assert sum(s.reserved_demand for s in operations.snapshot().shelters) == 4


def test_bookings_and_closures_survive_restart(operations):
    booking = operations.confirm(confirmation())
    unrelated = next(
        r["id"]
        for r in operations.network["roads"]
        if r["id"] not in booking.edge_ids
        and r["id"] not in operations.snapshot().hazard.blocked_edge_ids
    )
    operations.set_closure(unrelated, True, "Test closure")
    restarted = Operations(operations.path, network=operations.network)
    assert restarted.get_route(booking.route_id).status == "valid"
    assert restarted.get_route(booking.route_id).shelter.reserved_demand == 4
    assert unrelated in restarted.snapshot().hazard.blocked_edge_ids


def test_close_invalidates_only_intersecting_plans_and_releases_booking(operations):
    booking = operations.confirm(confirmation())
    road = booking.edge_ids[0]
    operations.set_closure(road, True, "Threat intersects road")
    invalid = operations.get_route(booking.route_id)
    assert invalid.status == "invalid"
    assert invalid.cause == "HARD_HAZARD_INTERSECTION"
    assert invalid.shelter.reserved_demand == 0
    assert road not in operations.preview(RouteRequest(origin_node_id="n24"))[0].edge_ids
    operations.set_closure(road, False, "Threat cleared")
    assert operations.get_route(booking.route_id).status == "invalid"


def test_expiry_releases_capacity_once_and_replays_stay_expired(operations):
    now = datetime.now(UTC)
    request = confirmation()
    booking = operations.confirm(request, now=now)
    future = now + timedelta(seconds=301)
    assert operations.get_route(booking.route_id, now=future).status == "expired"
    assert operations.get_route(booking.route_id, now=future).shelter.reserved_demand == 0
    assert operations.confirm(request, now=future).status == "expired"
    expiry_events = [e for e in operations.audit() if e["action"] == "reservation.expired"]
    assert len(expiry_events) == 1


def test_arrival_and_cancellation_are_idempotent(operations):
    booking = operations.confirm(confirmation())
    before = booking.shelter.occupancy
    arrival = operations.arrive(booking.route_id)
    assert arrival.status == "arrived"
    assert arrival.shelter.occupancy == before + 4
    assert arrival.shelter.reserved_demand == 0
    assert operations.arrive(booking.route_id).shelter.occupancy == before + 4
    with pytest.raises(OperationError, match="already checked in"):
        operations.cancel(booking.route_id)
    other = operations.confirm(confirmation())
    assert operations.cancel(other.route_id).status == "cancelled"
    assert operations.cancel(other.route_id).shelter.reserved_demand == 0


def test_replacement_is_atomic_and_does_not_leak_capacity(operations):
    booking = operations.confirm(confirmation())
    replacement = operations.confirm(confirmation(replace_route_id=booking.route_id))
    assert operations.get_route(booking.route_id).status == "cancelled"
    assert sum(s.reserved_demand for s in operations.snapshot().shelters) == 4
    with pytest.raises(OperationError):
        operations.confirm(
            confirmation(
                origin=None, replace_route_id=replacement.route_id, shelter_id="does-not-exist"
            )
        )
    assert operations.get_route(replacement.route_id).status == "valid"
    assert sum(s.reserved_demand for s in operations.snapshot().shelters) == 4


def test_concurrent_requests_across_store_instances_never_exceed_policy(operations):
    other = Operations(operations.path, network=operations.network)

    def reserve(i):
        store = operations if i % 2 else other
        try:
            return store.confirm(
                ConfirmRouteRequest(
                    origin_node_id="n24",
                    shelter_id="north",
                    party_size=20,
                    request_id=uuid4(),
                )
            )
        except OperationError as error:
            assert error.code == "NO_SAFE_ROUTE"
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(20)))
    assert len([r for r in results if r]) == 3
    shelter = next(s for s in operations.snapshot().shelters if s.shelter_id == "north")
    assert shelter.occupancy + shelter.reserved_demand == 132
    assert shelter.utilization <= 0.9


def test_invalid_origins_and_all_exits_closed_are_controlled(operations):
    with pytest.raises(OperationError) as error:
        operations.preview(RouteRequest(origin={"latitude": 0, "longitude": 0}))
    assert error.value.code == "UNSUPPORTED_ORIGIN"
    for road in operations.network["roads"]:
        if "n24" in (road["from"], road["to"]):
            operations.set_closure(road["id"], True, "All exits closed")
    with pytest.raises(OperationError) as error:
        operations.preview(RouteRequest(origin_node_id="n24"))
    assert error.value.code == "NO_SAFE_ROUTE"
    assert sum(s.reserved_demand for s in operations.snapshot().shelters) == 0


def test_full_party_is_considered_before_selecting_shelter(operations):
    with operations.transaction() as db:
        db.execute("UPDATE shelters SET occupancy=143 WHERE id='north'")
    plans = operations.preview(RouteRequest(origin_node_id="n24", party_size=2))
    assert "north" not in {p.shelter.shelter_id for p in plans}
    assert operations.confirm(confirmation()).shelter.shelter_id != "north"

from datetime import UTC, datetime

import pytest

from werms_api.domain.models import HazardState, NoSafeRouteError
from werms_api.domain.routing import calculate_safe_route
from werms_api.store import DemoStore


def test_route_never_uses_hard_blocked_edge() -> None:
    store = DemoStore()
    store.hazard = HazardState(
        version="test-002",
        source_timestamp=datetime.now(UTC),
        blocked_edge_ids=frozenset({"e12"}),
    )

    route = calculate_safe_route(
        origin_node_id="n0",
        nodes=store.nodes,
        edges=store.edges,
        shelters=store.shelters.values(),
        hazard=store.hazard,
        redirect_threshold=0.90,
    )

    assert "e12" not in route.edge_ids
    assert "HARD_HAZARDS_EXCLUDED" in route.reason_codes


def test_no_safe_route_is_a_controlled_domain_outcome() -> None:
    store = DemoStore()
    store.hazard = HazardState(
        version="test-003",
        source_timestamp=datetime.now(UTC),
        blocked_edge_ids=frozenset({"e01", "e03"}),
    )

    with pytest.raises(NoSafeRouteError):
        calculate_safe_route(
            origin_node_id="n0",
            nodes=store.nodes,
            edges=store.edges,
            shelters=store.shelters.values(),
            hazard=store.hazard,
            redirect_threshold=0.90,
        )


def test_shelter_over_threshold_is_not_selected() -> None:
    store = DemoStore()
    store.shelters["s-north"].occupancy = 110

    route = calculate_safe_route(
        origin_node_id="n0",
        nodes=store.nodes,
        edges=store.edges,
        shelters=store.shelters.values(),
        hazard=store.hazard,
        redirect_threshold=0.90,
    )

    assert route.shelter_id == "s-east"


import random
from datetime import UTC, datetime

import pytest
from werms_api.domain.models import (
    CostWeights,
    HazardState,
    NoSafeRouteError,
    Point,
    RoadEdge,
    RoadNode,
    Shelter,
)
from werms_api.domain.routing import _astar, _edge_cost, calculate_safe_route
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


def test_geographic_distance_does_not_override_minimum_travel_time():
    now = datetime.now(UTC)
    nodes = {
        "start": RoadNode("start", Point(0, 0)),
        "detour": RoadNode("detour", Point(50, 50)),
        "finish": RoadNode("finish", Point(0, 0.01)),
        "isolated": RoadNode("isolated", Point(0, 0.02)),
    }
    # An arbitrary graph can have tiny travel costs across a large physical
    # distance; an unscaled geographic heuristic incorrectly picks direct.
    edges = [
        RoadEdge("direct", "start", "finish", 1, 8),
        RoadEdge("via", "start", "detour", 100, 1),
        RoadEdge("last", "detour", "finish", 100, 1),
    ]
    route = calculate_safe_route(
        origin_node_id="start",
        nodes=nodes,
        edges=iter(edges),
        shelters=[
            Shelter("isolated", "Unreachable", "isolated", nodes["isolated"].point, 100, 0),
            Shelter("s", "Shelter", "finish", nodes["finish"].point, 100, 0),
        ],
        hazard=HazardState("test", now, frozenset()),
        redirect_threshold=0.9,
        now=now,
    )
    assert route.edge_ids == ("via", "last")
    assert route.estimated_minutes == 2


def test_freshness_penalty_does_not_depend_on_osm_shape_point_density():
    weights = CostWeights()
    long_edge = RoadEdge("long", "a", "b", 1, 2, live_risk=0.3, predictive_risk=0.7)
    short_edge = RoadEdge("short", "a", "b", 0.1, 0.2, live_risk=0.3, predictive_risk=0.7)
    kwargs = {"hard_blocked": False, "data_age_minutes": 30, "weights": weights}
    assert _edge_cost(long_edge, **kwargs) == pytest.approx(10 * _edge_cost(short_edge, **kwargs))


def test_astar_matches_exhaustive_optimum_on_geographically_misleading_graphs():
    rng = random.Random(41)
    now = datetime.now(UTC)
    for _ in range(50):
        nodes = {
            str(i): RoadNode(str(i), Point(rng.uniform(-70, 70), rng.uniform(-170, 170)))
            for i in range(7)
        }
        edges = [
            RoadEdge(
                f"{a}-{b}", str(a), str(b), 1, rng.uniform(0, 10), predictive_risk=rng.random()
            )
            for a in range(7)
            for b in range(a + 1, 7)
            if rng.random() < 0.6
        ]
        blocked = frozenset(e.edge_id for e in edges if rng.random() < 0.2)
        hazard = HazardState("random", now, blocked)
        weights = CostWeights()

        def exhaustive(node, edges=edges, blocked=blocked, weights=weights):
            if node == "6":
                return 0.0
            return min(
                (
                    _edge_cost(
                        e, hard_blocked=e.edge_id in blocked, data_age_minutes=0, weights=weights
                    )
                    + exhaustive(e.target)
                    for e in edges
                    if e.source == node
                ),
                default=float("inf"),
            )

        expected = exhaustive("0")
        result = _astar(
            origin_node_id="0",
            destination_node_id="6",
            nodes=nodes,
            edges=edges,
            hazard=hazard,
            now=now,
            weights=weights,
        )
        if expected == float("inf"):
            assert result is None
        else:
            assert result is not None
            assert result[2] == pytest.approx(expected)
            assert not blocked.intersection(e.edge_id for e in result[1])

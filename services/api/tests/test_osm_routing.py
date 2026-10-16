from datetime import UTC, datetime

import pytest

from werms_api.domain.models import (
    HazardState,
    NoSafeRouteError,
    Point,
    RoadEdge,
    RoadNode,
    Shelter,
)
from werms_api.domain.routing import calculate_safe_route
from werms_api.network import routing_graph


def test_osm_one_way_edges_are_not_silently_made_bidirectional():
    graph = {
        "nodes": [
            {"id": "a", "latitude": 34, "longitude": -118},
            {"id": "b", "latitude": 34.001, "longitude": -118},
        ],
        "roads": [
            {
                "id": "forward",
                "from": "a",
                "to": "b",
                "minutes": 1,
                "km": 1,
                "traffic": 1,
                "direction": "forward",
                "osm_way_id": "123",
            },
            {
                "id": "reverse",
                "from": "a",
                "to": "b",
                "minutes": 1,
                "km": 1,
                "traffic": 1,
                "direction": "reverse",
                "osm_way_id": "456",
            },
        ],
    }
    _, edges = routing_graph(graph, traffic=True)
    assert [(e.edge_id, e.source, e.target, e.way_id) for e in edges] == [
        ("forward", "a", "b", "123"),
        ("reverse", "b", "a", "456"),
    ]


@pytest.mark.parametrize("restriction", ["no_left_turn", "only_right_turn"])
def test_turn_restrictions_require_incoming_edge_state(restriction):
    nodes = {key: RoadNode(key, Point(34, -118)) for key in ["a", "via", "b", "c"]}
    edges = [
        RoadEdge("approach", "a", "via", 1, 1, way_id="10"),
        RoadEdge("illegal", "via", "b", 1, 1, way_id="20"),
        RoadEdge("detour", "via", "c", 1, 2, way_id="30"),
        RoadEdge("finish", "c", "b", 1, 2, way_id="40"),
    ]
    rule = {
        "via": "via",
        "from_way": "10",
        "to_way": "20" if restriction.startswith("no_") else "30",
        "restriction": restriction,
    }
    now = datetime.now(UTC)
    route = calculate_safe_route(
        origin_node_id="a",
        nodes=nodes,
        edges=edges,
        shelters=[Shelter("s", "Site", "b", nodes["b"].point, 100, 0)],
        hazard=HazardState("test", now, frozenset()),
        redirect_threshold=0.9,
        turn_restrictions=(rule,),
        now=now,
    )
    assert route.edge_ids == ("approach", "detour", "finish")


def test_turn_constraints_and_closures_combine_to_return_no_route():
    nodes = {key: RoadNode(key, Point(34, -118)) for key in ["a", "via", "b"]}
    now = datetime.now(UTC)
    with pytest.raises(NoSafeRouteError):
        calculate_safe_route(
            origin_node_id="a",
            nodes=nodes,
            edges=[
                RoadEdge("first", "a", "via", 1, 1, way_id="10"),
                RoadEdge("last", "via", "b", 1, 1, way_id="20"),
            ],
            shelters=[Shelter("s", "Site", "b", nodes["b"].point, 100, 0)],
            hazard=HazardState("test", now, frozenset({"last"})),
            redirect_threshold=0.9,
            now=now,
        )

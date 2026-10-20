from uuid import uuid4

import pytest
from werms_api.network import build_demo_network
from werms_api.operations import OperationError, Operations
from werms_api.schemas import ConfirmRouteRequest
from werms_api.spatial import validated_polygon


def test_polygon_validation_rejects_nonfinite_open_and_oversized_geometries():
    for coordinates in ([[[0, 0], [1, 0], [0, 1]]], [[[0, 0], [float("nan"), 1], [0, 1], [0, 0]]]):
        with pytest.raises(ValueError):
            validated_polygon({"type": "Polygon", "coordinates": coordinates})


def test_published_fire_constraints_invalidate_bookings_and_survive_spatial_outage(tmp_path):
    ops = Operations(tmp_path / "fire.sqlite3", network=build_demo_network())
    route = ops.confirm(ConfirmRouteRequest(origin_node_id="n24", request_id=uuid4(), party_size=4))
    edge = route.edge_ids[len(route.edge_ids) // 2]

    class SpatialFixture:
        def intersections(self, polygon):
            return [edge]

    ops.spatial = SpatialFixture()
    identifier = str(uuid4())
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 1], [0, 0]]]}
    state = ops.publish_fire_exclusion(identifier, polygon, "Demonstration perimeter", "test")
    assert edge in state.hazard.blocked_edge_ids
    assert ops.get_route(route.route_id).cause == "FIRE_EXCLUSION_INTERSECTION"
    assert sum(s.reserved_demand for s in state.shelters) == 0
    ops.spatial = None
    assert edge in ops.snapshot().hazard.blocked_edge_ids
    assert (
        edge
        in ops.publish_fire_exclusion(
            identifier, polygon, "Demonstration perimeter", "test"
        ).hazard.blocked_edge_ids
    )
    assert len(ops.fire_exclusions()) == 1
    with pytest.raises(OperationError, match="another payload"):
        ops.publish_fire_exclusion(identifier, polygon, "Changed reason", "test")
    with pytest.raises(OperationError, match="Deactivate"):
        ops.set_closure(edge, False, "Cannot override fire")
    ops.set_fire_exclusion(identifier, False, "test")
    assert edge not in ops.snapshot().hazard.blocked_edge_ids
    assert ops.get_route(route.route_id).status == "invalid"

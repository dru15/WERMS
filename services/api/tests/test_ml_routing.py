
import pytest
from werms_api.operations import OperationError, Operations
from werms_api.risk_routing import replay_ml_route
from werms_api.schemas import RouteRequest


def test_model_routing_penalty_is_soft_but_closures_capacity_and_country_are_hard(tmp_path):
    network = {
        "version": "ml-routing-fixture",
        "name": "Test graph",
        "country": "US",
        "data_mode": "fictional-pilot",
        "nodes": [
            {"id": name, "latitude": 34 + index * 0.001, "longitude": -118, "x": index, "y": 0}
            for index, name in enumerate(["a", "b", "c"])
        ],
        "roads": [
            {"id": "direct", "from": "a", "to": "c", "km": 1, "minutes": 2, "traffic": 1},
            {"id": "via", "from": "a", "to": "b", "km": 1, "minutes": 2, "traffic": 1},
            {"id": "last", "from": "b", "to": "c", "km": 1, "minutes": 2, "traffic": 1},
        ],
        "shelters": [
            {"id": "s", "node": "c", "name": "Fixture destination", "capacity": 100, "occupancy": 0}
        ],
        "origins": [{"node": "a", "name": "Test origin"}],
        "initial_closures": [],
    }

    class ResearchFixture:
        def case(self, _):
            return {"latitude": 34, "longitude": -118, "reference_date": "2024-06-01"}

        def report(self):
            return {"champion": "fixture"}

        def infer(self, _):
            return {"predictions": {"fixture": 1.0}, "model_version": "fixture-only"}

    class SpatialFixture:
        def project_risk(self, _):
            return {"direct": 1.0}

    ops = Operations(tmp_path / "ml.sqlite3", network=network, spatial=SpatialFixture())
    request = RouteRequest(origin_node_id="a", party_size=4)
    result = replay_ml_route(ops, ResearchFixture(), "fixture", request)
    assert result["baseline"]["edge_ids"] == ["direct"]
    assert result["edge_ids"] == ["via", "last"]
    assert result["creates_booking"] is False
    assert sum(s.reserved_demand for s in ops.snapshot().shelters) == 0
    ops.set_closure("via", True, "Test hard exclusion")
    assert replay_ml_route(ops, ResearchFixture(), "fixture", request)["edge_ids"] == ["direct"]
    ops.set_closure("direct", True, "Test hard exclusion")
    with pytest.raises(OperationError, match="No capacity"):
        replay_ml_route(ops, ResearchFixture(), "fixture", request)
    ops.network["country"] = "IN"
    with pytest.raises(OperationError, match="US-only"):
        replay_ml_route(ops, ResearchFixture(), "fixture", request)

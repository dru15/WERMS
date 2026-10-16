from pathlib import Path

from werms_api.network import build_network
from werms_api.operations import Operations
from werms_api.schemas import RouteRequest


def test_packaged_extract_has_real_coordinates_provenance_and_directionality():
    network = build_network()
    assert network["data_mode"] == "osm-pilot"
    assert len(network["nodes"]) > 500
    assert len(network["roads"]) > 500
    assert len(network["source"]["sha256"]) == 64
    assert network["source"]["license"] == "ODbL-1.0"
    assert network["source"]["data_timestamp"]
    assert any(r["direction"] != "both" for r in network["roads"])
    assert network["turn_restrictions"]
    south, west, north, east = network["bounds"]
    for point in network["nodes"]:
        assert point["id"].startswith("osm-")
        assert south <= point["latitude"] <= north
        assert west <= point["longitude"] <= east
    assert all(
        site["osm_url"].startswith("https://www.openstreetmap.org/") for site in network["shelters"]
    )


def test_all_real_pilot_origins_route_on_directed_edges_and_reroute_after_closure(tmp_path: Path):
    store = Operations(tmp_path / "real.sqlite3")
    roads = {r["id"]: r for r in store.network["roads"]}
    for origin in store.network["origins"]:
        request = RouteRequest(origin_node_id=origin["node"], party_size=4)
        plans = store.preview(request)
        assert len(plans) == 3
        for plan in plans:
            assert plan.road_version == store.network["version"]
            for i, edge_id in enumerate(plan.edge_ids):
                road = roads[edge_id]
                pair = (plan.path[i].node_id, plan.path[i + 1].node_id)
                if road["direction"] == "forward":
                    assert pair == (road["from"], road["to"])
                elif road["direction"] == "reverse":
                    assert pair == (road["to"], road["from"])
                else:
                    assert set(pair) == {road["from"], road["to"]}
        edge_id = plans[0].edge_ids[len(plans[0].edge_ids) // 2]
        store.set_closure(edge_id, True, "Real-graph rerouting test")
        alternatives = store.preview(request)
        assert all(edge_id not in p.edge_ids for p in alternatives)
        store.set_closure(edge_id, False, "Clear test closure")

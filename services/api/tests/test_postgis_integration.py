"""Runs against a real private PostGIS cluster when WERMS_TEST_SPATIAL_URL is set."""

import os
from uuid import uuid4

import pytest
from werms_api.spatial import SpatialIndex


@pytest.mark.skipif(not os.environ.get("WERMS_TEST_SPATIAL_URL"), reason="Requires real PostGIS")
def test_real_postgis_intersections_include_boundary_contact_and_reject_invalid_polygon():
    version = f"test-{uuid4()}"
    network = {
        "version": version,
        "nodes": [
            {"id": "a", "latitude": 30, "longitude": 78},
            {"id": "b", "latitude": 30, "longitude": 78.01},
            {"id": "c", "latitude": 30.02, "longitude": 78.02},
            {"id": "d", "latitude": 30.02, "longitude": 78.03},
        ],
        "roads": [
            {"id": "touch", "from": "a", "to": "b"},
            {"id": "disjoint", "from": "c", "to": "d"},
        ],
    }
    spatial = SpatialIndex(os.environ["WERMS_TEST_SPATIAL_URL"], network)
    try:
        polygon = {
            "type": "Polygon",
            "coordinates": [
                [[78.005, 29.99], [78.015, 29.99], [78.015, 30], [78.005, 30], [78.005, 29.99]]
            ],
        }
        assert spatial.intersections(polygon) == ["touch"]
        assert spatial.status()["indexed_segments"] == 2
        bowtie = {
            "type": "Polygon",
            "coordinates": [[[78, 30], [78.01, 30.01], [78, 30.01], [78.01, 30], [78, 30]]],
        }
        with pytest.raises(ValueError, match="topologically invalid"):
            spatial.intersections(bowtie)
    finally:
        with spatial.connect() as db:
            db.execute("DELETE FROM werms_roads WHERE road_version=%s", (version,))
            db.execute("DELETE FROM werms_road_versions WHERE version=%s", (version,))

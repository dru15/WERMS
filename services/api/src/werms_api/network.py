"""Backend-owned, versioned road networks for routing and map rendering."""

import json
import math
from importlib.resources import files

from werms_api.domain.models import Point, RoadEdge, RoadNode


def build_demo_network() -> dict:
    nodes = []
    for i in range(48):
        row, col = divmod(i, 8)
        x = 80 + col * 108 + math.sin(row * 1.3 + col) * 13
        y = 85 + row * 88 + math.sin(col * 0.9) * 17
        nodes.append(
            {
                "id": f"n{i}",
                "x": x,
                "y": y,
                "latitude": 34.08 - y / 10000,
                "longitude": -118.28 + x / 10000,
            }
        )
    names = [
        "Ridge Avenue",
        "Canyon Road",
        "Oak Street",
        "Main Street",
        "Valley Boulevard",
        "Creek Road",
    ]
    vertical = [
        "Mill Lane",
        "Pine Street",
        "Cedar Drive",
        "Park Road",
        "River Lane",
        "Elm Street",
        "Hill Road",
        "East Avenue",
    ]
    roads = []
    for i in range(48):
        row, col = divmod(i, 8)
        for j in ([i + 1] if col < 7 else []) + ([i + 8] if row < 5 else []):
            roads.append(
                {
                    "id": f"r{i}-{j}",
                    "from": f"n{i}",
                    "to": f"n{j}",
                    "name": names[row] if j == i + 1 else vertical[col],
                    "minutes": round(1.1 + ((i + j) % 5) * 0.24, 2),
                    "km": round(0.45 + ((i + j) % 4) * 0.07, 2),
                    "traffic": 1.6 if (i + j) % 7 == 0 else 1.0,
                }
            )
    return {
        "version": "pine-ridge-002",
        "name": "Pine Ridge district",
        "data_mode": "fictional-pilot",
        "nodes": nodes,
        "roads": roads,
        "origins": [
            {"node": "n24", "name": "Old Mill Road"},
            {"node": "n18", "name": "Pine Ridge Market"},
            {"node": "n41", "name": "Creekside residential"},
        ],
        "shelters": [
            {
                "id": "north",
                "node": "n3",
                "name": "North Ridge School",
                "capacity": 160,
                "occupancy": 72,
            },
            {
                "id": "east",
                "node": "n31",
                "name": "East Valley Centre",
                "capacity": 120,
                "occupancy": 81,
            },
            {
                "id": "south",
                "node": "n44",
                "name": "Creekside Sports Hall",
                "capacity": 200,
                "occupancy": 113,
            },
        ],
        "initial_closures": ["r6-7", "r7-15", "r14-15", "r15-23"],
    }


def routing_graph(network: dict, *, traffic: bool) -> tuple[dict, tuple]:
    nodes = {
        n["id"]: RoadNode(n["id"], Point(n["latitude"], n["longitude"])) for n in network["nodes"]
    }
    edges = []
    for road in network["roads"]:
        minutes = road["minutes"] * (road["traffic"] if traffic else 1)
        direction = road.get("direction", "both")
        connections = []
        if direction in {"both", "forward"}:
            connections.append((road["from"], road["to"]))
        if direction in {"both", "reverse"}:
            connections.append((road["to"], road["from"]))
        for source, target in connections:
            edges.append(
                RoadEdge(
                    road["id"], source, target, road["km"], minutes, way_id=road.get("osm_way_id")
                )
            )
    return nodes, tuple(edges)


def build_network() -> dict:
    path = files("werms_api").joinpath("data/palisades-network.json")
    network = json.loads(path.read_text(encoding="utf-8"))
    if network.get("data_mode") != "osm-pilot" or not network.get("roads"):
        raise ValueError(
            "A valid OSM pilot extract is required; no fictional fallback is substituted."
        )
    return network

"""Acquire one bounded OSM extract; compile the pilot graph reproducibly."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/api/src"))

BOUNDS = (34.039, -118.533, 34.051, -118.514)
ENDPOINT = "https://overpass-api.de/api/interpreter"
ROAD_CLASSES = {
    "motorway": 80,
    "motorway_link": 35,
    "trunk": 65,
    "trunk_link": 30,
    "primary": 50,
    "primary_link": 30,
    "secondary": 40,
    "secondary_link": 25,
    "tertiary": 35,
    "tertiary_link": 25,
    "unclassified": 30,
    "residential": 30,
    "living_street": 15,
    "service": 15,
}


def query() -> str:
    bbox = ",".join(map(str, BOUNDS))
    classes = "|".join(ROAD_CLASSES)
    return f"""[out:json][timeout:60];(
      way["highway"~"^({classes})$"]({bbox});
      relation["type"="restriction"]({bbox});
      nwr["amenity"~"^(school|library|community_centre)$"]({bbox});
      nwr["leisure"="park"]({bbox});
    );out body center;>;out skel qt;"""


def distance_km(a: dict, b: dict) -> float:
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat = lat2 - lat1
    dlon = math.radians(b["lon"] - a["lon"])
    chord = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(chord)))


def speed(tags: dict) -> tuple[float, str]:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(mph)?", tags.get("maxspeed", ""))
    if match:
        value = float(match[1]) * (1.609344 if match[2] else 1)
        if 5 <= value <= 140:
            return value, "osm-maxspeed"
    return ROAD_CLASSES[tags["highway"]], "road-class-assumption"


def compile_network(raw: dict, digest: str, selected_sites: list[str]) -> dict:
    elements = {}
    for entry in raw["elements"]:
        elements.setdefault((entry["type"], entry["id"]), {}).update(entry)
    points = {e["id"]: e for e in elements.values() if e["type"] == "node"}
    roads = []
    excluded_ways = set()
    restrictions = []
    for relation in elements.values():
        if (
            relation["type"] != "relation"
            or relation.get("tags", {}).get("type") != "restriction"
        ):
            continue
        tags = relation["tags"]
        if {"motorcar", "motor_vehicle", "vehicle"} & set(
            tags.get("except", "").split(";")
        ):
            continue
        members = relation.get("members", [])
        from_ways = [
            m["ref"] for m in members if m["role"] == "from" and m["type"] == "way"
        ]
        to_ways = [
            m["ref"] for m in members if m["role"] == "to" and m["type"] == "way"
        ]
        via_nodes = [
            m["ref"] for m in members if m["role"] == "via" and m["type"] == "node"
        ]
        restriction = tags.get(
            "restriction:motorcar",
            tags.get("restriction:motor_vehicle", tags.get("restriction", "")),
        )
        if len(from_ways) != 1 or len(to_ways) != 1 or len(via_nodes) != 1:
            # Multi-way/conditional maneuvers need a richer state machine. Exclude
            # their incoming ways instead of silently allowing an illegal turn.
            excluded_ways.update(from_ways)
            continue
        if restriction.startswith(("no_", "only_")):
            restrictions.append(
                {
                    "via": f"osm-{via_nodes[0]}",
                    "from_way": str(from_ways[0]),
                    "to_way": str(to_ways[0]),
                    "restriction": restriction,
                }
            )
        else:
            excluded_ways.update(from_ways)

    used = set()
    for way in elements.values():
        tags = way.get("tags", {})
        if (
            way["type"] != "way"
            or tags.get("highway") not in ROAD_CLASSES
            or way["id"] in excluded_ways
        ):
            continue
        access = next(
            (
                tags[k]
                for k in ["motorcar", "motor_vehicle", "vehicle", "access"]
                if k in tags
            ),
            "yes",
        )
        if access in {
            "no",
            "private",
            "agricultural",
            "forestry",
            "customers",
            "destination",
        }:
            continue
        if any(key.endswith(":conditional") for key in tags):
            continue
        if (
            tags.get("area") == "yes"
            or tags.get("construction")
            or tags.get("highway") == "construction"
        ):
            continue
        maximum, speed_source = speed(tags)
        estimated_speed = min(40.0, maximum * 0.7)
        one_way = tags.get(
            "oneway",
            "yes"
            if tags.get("junction") == "roundabout" or tags["highway"] == "motorway"
            else "no",
        )
        if one_way not in {"no", "0", "false", "yes", "1", "true", "-1"}:
            continue
        direction = (
            "reverse"
            if one_way == "-1"
            else "forward"
            if one_way in {"yes", "1", "true"}
            else "both"
        )
        for i, (a_id, b_id) in enumerate(zip(way["nodes"], way["nodes"][1:])):
            if a_id not in points or b_id not in points:
                continue
            a, b = points[a_id], points[b_id]
            if not all(
                BOUNDS[0] <= p["lat"] <= BOUNDS[2]
                and BOUNDS[1] <= p["lon"] <= BOUNDS[3]
                for p in [a, b]
            ):
                continue
            km = distance_km(a, b)
            if km < 0.0001:
                continue
            roads.append(
                {
                    "id": f"osm-way-{way['id']}-{i}",
                    "from": f"osm-{a_id}",
                    "to": f"osm-{b_id}",
                    "name": tags.get(
                        "name",
                        tags.get("ref", tags["highway"].replace("_", " ").title()),
                    ),
                    "minutes": round(km / estimated_speed * 60, 6),
                    "km": round(km, 6),
                    "traffic": 1,
                    "direction": direction,
                    "osm_way_id": str(way["id"]),
                    "highway": tags["highway"],
                    "speed_source": speed_source,
                    "maxspeed_kph": maximum,
                }
            )
            used.update([a_id, b_id])
    nodes = [
        {
            "id": f"osm-{i}",
            "latitude": points[i]["lat"],
            "longitude": points[i]["lon"],
            "x": (points[i]["lon"] - BOUNDS[1]) / (BOUNDS[3] - BOUNDS[1]) * 940,
            "y": (BOUNDS[2] - points[i]["lat"]) / (BOUNDS[2] - BOUNDS[0]) * 620,
        }
        for i in sorted(used)
    ]

    def nearest(point):
        return min(
            nodes,
            key=lambda n: distance_km(
                point, {"lat": n["latitude"], "lon": n["longitude"]}
            ),
        )

    pois = []
    for e in elements.values():
        tags = e.get("tags", {})
        if "name" in tags and (
            tags.get("amenity") in {"school", "library", "community_centre"}
            or tags.get("leisure") == "park"
        ):
            point = e.get("center", e)
            if "lat" not in point and e["type"] == "way":
                vertices = [points[n] for n in e.get("nodes", []) if n in points]
                if vertices:
                    point = {
                        "lat": sum(p["lat"] for p in vertices) / len(vertices),
                        "lon": sum(p["lon"] for p in vertices) / len(vertices),
                    }
            if "lat" in point and "lon" in point:
                pois.append((tags["name"], point, e))
    if not selected_sites:
        print("Available mapped places:")
        for name, point, e in sorted(pois, key=lambda p: p[0]):
            print(f"  {name} | {e['type']}/{e['id']} | {point['lat']}, {point['lon']}")
        return {}
    shelters = []
    for name in selected_sites:
        poi = next((p for p in pois if p[0] == name), None)
        if poi is None:
            raise ValueError(f"Mapped place not found: {name}")
        _, point, element = poi
        node = nearest(point)
        snap = (
            distance_km(point, {"lat": node["latitude"], "lon": node["longitude"]})
            * 1000
        )
        if snap > 250:
            raise ValueError(f"Mapped place has no nearby road access: {name}")
        shelters.append(
            {
                "id": f"demo-{element['type']}-{element['id']}",
                "node": node["id"],
                "name": name,
                "capacity": 100,
                "occupancy": 0,
                "latitude": point["lat"],
                "longitude": point["lon"],
                "access_distance_m": round(snap),
                "site_mode": "demonstration-assembly-site",
                "osm_url": f"https://www.openstreetmap.org/{element['type']}/{element['id']}",
            }
        )
    origins = []
    for label, lat, lon in [
        ("Palisades Village area", 34.0477, -118.5255),
        ("Sunset Boulevard area", 34.0446, -118.515),
        ("Temescal Canyon Road area", 34.0427, -118.5311),
    ]:
        origins.append({"name": label, "node": nearest({"lat": lat, "lon": lon})["id"]})
    graph_digest = hashlib.sha256(
        json.dumps(
            {
                "nodes": nodes,
                "roads": roads,
                "shelters": shelters,
                "origins": origins,
                "turn_restrictions": restrictions,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "version": f"osm-palisades-{graph_digest[:12]}",
        "name": "Pacific Palisades, Los Angeles",
        "data_mode": "osm-pilot",
        "bounds": list(BOUNDS),
        "nodes": nodes,
        "roads": roads,
        "shelters": shelters,
        "origins": origins,
        "initial_closures": [],
        "turn_restrictions": restrictions,
        "source": {
            "name": "OpenStreetMap contributors",
            "url": "https://www.openstreetmap.org/copyright",
            "license": "ODbL-1.0",
            "endpoint": ENDPOINT,
            "data_timestamp": raw.get("osm3s", {}).get("timestamp_osm_base"),
            "sha256": digest,
            "query": query(),
            "imported_at": datetime.now(UTC).isoformat(),
            "excluded_complex_restriction_ways": len(excluded_ways),
        },
        "travel_time_mode": "estimated-from-road-speeds",
        "hazard_mode": "operator-demonstration",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument(
        "--osm-api", action="store_true", help="Use one bounded official OSM API GET."
    )
    parser.add_argument("--site", action="append", default=[])
    args = parser.parse_args()
    raw_path = ROOT / "data/raw/palisades-osm.json"
    if args.fetch:
        request = Request(
            args.endpoint,
            data=urlencode({"data": query()}).encode(),
            headers={
                "User-Agent": "WERMS/0.3 (+https://github.com/dru15/WERMS)",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        if args.osm_api:
            south, west, north, east = BOUNDS
            args.endpoint = f"https://api.openstreetmap.org/api/0.6/map.json?bbox={west},{south},{east},{north}"
            request = Request(
                args.endpoint,
                headers={
                    "User-Agent": "WERMS/0.3 (+https://github.com/dru15/WERMS)",
                    "Accept": "application/json",
                },
            )
        request.add_header("Accept-Encoding", "gzip")
        print(f"Fetching bounded OSM extract: {args.endpoint}", flush=True)
        try:
            with urlopen(request, timeout=30) as response:
                print(
                    f"HTTP {response.status}; encoding={response.headers.get('Content-Encoding', 'identity')}",
                    flush=True,
                )
                chunks, total = [], 0
                deadline = time.monotonic() + 120
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > 20_000_000 or time.monotonic() > deadline:
                        raise ValueError(
                            "Bounded download exceeded its size or duration limit."
                        )
                    if len(chunks) % 16 == 0:
                        print(f"Received {total // 1024} KiB", flush=True)
                payload = b"".join(chunks)
                if response.headers.get("Content-Encoding") == "gzip":
                    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as compressed:
                        payload = compressed.read(20_000_001)
        except HTTPError as error:
            raise RuntimeError(
                f"OSM download failed ({error.code}): {error.read(2000).decode(errors='replace')}"
            ) from error
        if len(payload) > 20_000_000:
            raise ValueError("Extract exceeds the bounded import size.")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(payload)
        raw_path.with_suffix(".meta.json").write_text(
            json.dumps(
                {
                    "endpoint": args.endpoint,
                    "downloaded_at": datetime.now(UTC).isoformat(),
                }
            ),
            encoding="utf-8",
        )
    payload = raw_path.read_bytes()
    raw = json.loads(payload)
    if raw.get("remark"):
        raise ValueError(raw["remark"])
    graph = compile_network(raw, hashlib.sha256(payload).hexdigest(), args.site)
    if graph:
        graph["source"].update(
            json.loads(raw_path.with_suffix(".meta.json").read_text())
        )
        if not graph["source"]["data_timestamp"]:
            graph["source"]["data_timestamp"] = graph["source"]["downloaded_at"]
            graph["source"]["timestamp_mode"] = "download-time"
        if "api.openstreetmap.org/api/0.6/map" in graph["source"]["endpoint"]:
            graph["source"].pop("query", None)
            graph["source"]["request_format"] = "OSM API 0.6 JSON bounding-box request"
        destination = ROOT / "services/api/src/werms_api/data/palisades-network.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(graph, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        print(
            f"Imported {len(graph['nodes'])} nodes, {len(graph['roads'])} roads, "
            f"{len(graph['turn_restrictions'])} turn restrictions; {destination}"
        )


if __name__ == "__main__":
    main()

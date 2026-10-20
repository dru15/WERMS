"""Add bounded local OSM context without changing any routing geometry/version."""

import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    for profile in ("dehradun", "palisades"):
        path = ROOT / f"services/api/src/werms_api/data/{profile}-network.json"
        network = json.loads(path.read_text(encoding="utf-8"))
        payload = (ROOT / f"data/raw/{profile}-osm.json").read_bytes()
        if hashlib.sha256(payload).hexdigest() != network["source"]["sha256"]:
            raise ValueError("Context must use exactly the graph's archived OSM source.")
        raw = json.loads(payload)
        points = {e["id"]: [e["lon"], e["lat"]] for e in raw["elements"] if e["type"] == "node"}
        features = []
        for element in raw["elements"]:
            if element["type"] != "way":
                continue
            tags = element.get("tags", {})
            water = tags.get("natural") == "water" or tags.get("waterway") == "riverbank"
            building = "building" in tags
            green = (
                tags.get("landuse") in {"forest", "grass", "meadow", "recreation_ground"}
                or tags.get("natural") in {"wood", "scrub", "grassland"}
                or tags.get("leisure") in {"park", "garden", "nature_reserve"}
            )
            line = tags.get("waterway") in {"river", "stream", "canal"}
            ids = element.get("nodes", [])
            if not (water or building or green or line) or any(node not in points for node in ids):
                continue
            coordinates = [points[node] for node in ids]
            if len(coordinates) < 2 or not all(
                math.isfinite(value) for p in coordinates for value in p
            ):
                continue
            polygon = len(coordinates) >= 4 and coordinates[0] == coordinates[-1]
            if not polygon and not line:
                continue
            kind = "water" if water or line else "building" if building else "green"
            features.append(
                {
                    "type": "Feature",
                    "properties": {"kind": kind, "osm_way_id": str(element["id"])},
                    "geometry": {
                        "type": "Polygon" if polygon else "LineString",
                        "coordinates": [coordinates] if polygon else coordinates,
                    },
                }
            )
        network["context"] = {"type": "FeatureCollection", "features": features}
        path.write_text(json.dumps(network, separators=(",", ":")) + "\n", encoding="utf-8")
        print(
            f"{profile}: {len(features)} real OSM context features; "
            f"routing version unchanged: {network['version']}"
        )


if __name__ == "__main__":
    main()

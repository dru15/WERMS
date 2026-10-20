"""PostGIS geometry evaluation; published exclusions are frozen into the booking store.

The spatial database evaluates full geometry. SQLite serializes publication,
closure invalidation, capacity and confirmation, avoiding a distributed commit.
Existing published hard constraints survive a later spatial database outage.
"""

from __future__ import annotations

import hashlib
import json
import math


class SpatialUnavailable(RuntimeError):
    pass


def validated_polygon(value: dict) -> dict:
    if value.get("type") != "Polygon":
        raise ValueError("A GeoJSON Polygon geometry is required.")
    rings = value.get("coordinates")
    if not isinstance(rings, list) or not 1 <= len(rings) <= 16:
        raise ValueError("Polygon must contain 1 to 16 rings.")
    vertices = 0
    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
            raise ValueError("Polygon rings must be closed and contain at least four coordinates.")
        vertices += len(ring)
        for point in ring:
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("Coordinates must be longitude, latitude pairs.")
            if any(
                isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
                for x in point
            ):
                raise ValueError("Coordinates must be finite numbers.")
            if not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
                raise ValueError("Coordinates are outside geographic bounds.")
    if vertices > 4096:
        raise ValueError("Polygon exceeds the 4096-vertex limit.")
    return {"type": "Polygon", "coordinates": rings}


class SpatialIndex:
    def __init__(self, url: str, network: dict):
        import psycopg

        self.psycopg = psycopg
        self.url = url
        self.network = network
        self.version = network["version"]
        self.prepare()

    def connect(self):
        return self.psycopg.connect(
            self.url, connect_timeout=5, options="-c statement_timeout=10000"
        )

    def prepare(self):
        points = {n["id"]: [n["longitude"], n["latitude"]] for n in self.network["nodes"]}
        rows = [
            (
                self.version,
                r["id"],
                json.dumps(
                    {"type": "LineString", "coordinates": [points[r["from"]], points[r["to"]]]}
                ),
            )
            for r in self.network["roads"]
        ]
        digest = hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS werms_road_versions (
                version text PRIMARY KEY, fingerprint text NOT NULL, segments integer NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS werms_roads (
                road_version text NOT NULL REFERENCES werms_road_versions(version),
                edge_id text NOT NULL, geom geometry(LineString,4326) NOT NULL,
                PRIMARY KEY(road_version,edge_id))""")
            db.execute(
                "CREATE INDEX IF NOT EXISTS werms_roads_geom ON werms_roads USING gist(geom)"
            )
            existing = db.execute(
                "SELECT fingerprint,segments FROM werms_road_versions WHERE version=%s",
                (self.version,),
            ).fetchone()
            if existing and existing != (digest, len(rows)):
                raise ValueError("PostGIS road-version fingerprint mismatch.")
            if not existing:
                db.execute(
                    "INSERT INTO werms_road_versions VALUES (%s,%s,%s)",
                    (self.version, digest, len(rows)),
                )
                with db.cursor() as cursor:
                    cursor.executemany(
                        "INSERT INTO werms_roads VALUES "
                        "(%s,%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326))",
                        rows,
                    )
            db.execute("ANALYZE werms_roads")

    def intersections(self, polygon: dict) -> list[str]:
        geometry = json.dumps(validated_polygon(polygon), allow_nan=False)
        try:
            with self.connect() as db:
                valid = db.execute(
                    "SELECT ST_IsValid(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326))", (geometry,)
                ).fetchone()[0]
                if not valid:
                    raise ValueError("Polygon is topologically invalid; it was not repaired.")
                rows = db.execute(
                    "SELECT edge_id FROM werms_roads WHERE road_version=%s AND "
                    "ST_Intersects(geom,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)) "
                    "ORDER BY edge_id",
                    (self.version, geometry),
                ).fetchall()
                return [row[0] for row in rows]
        except self.psycopg.Error as error:
            raise SpatialUnavailable(
                "PostGIS is unavailable; new exclusions cannot be evaluated."
            ) from error

    def status(self):
        try:
            with self.connect() as db:
                version = db.execute("SELECT PostGIS_Lib_Version()").fetchone()[0]
                count = db.execute(
                    "SELECT count(*) FROM werms_roads WHERE road_version=%s", (self.version,)
                ).fetchone()[0]
            return {
                "status": "connected",
                "engine": "PostGIS",
                "version": version,
                "road_version": self.version,
                "indexed_segments": count,
            }
        except self.psycopg.Error:
            return {"status": "unavailable", "engine": "PostGIS"}

    def project_risk(self, points: list[dict]) -> dict[str, float]:
        if not 1 <= len(points) <= 5000:
            raise ValueError("Risk projection requires 1 to 5000 scored locations.")
        for point in points:
            if not all(
                isinstance(point.get(k), (float, int)) and math.isfinite(point[k])
                for k in ("latitude", "longitude", "probability")
            ):
                raise ValueError("Invalid risk point.")
            if not (
                24 <= point["latitude"] <= 50
                and -125 <= point["longitude"] <= -66
                and 0 <= point["probability"] <= 1
            ):
                raise ValueError("Risk point is outside the supported CONUS model domain.")
        try:
            with self.connect() as db:
                rows = db.execute(
                    """SELECT r.edge_id,max(p.probability)
                    FROM werms_roads r JOIN json_to_recordset(%s::json)
                    AS p(latitude double precision,longitude double precision,
                         probability double precision)
                    ON ST_Intersects(r.geom,ST_Buffer(
                        ST_SetSRID(ST_Point(p.longitude,p.latitude),4326)::geography,3000)::geometry)
                    WHERE r.road_version=%s GROUP BY r.edge_id""",
                    (json.dumps(points, allow_nan=False), self.version),
                ).fetchall()
            return {edge: float(probability) for edge, probability in rows}
        except self.psycopg.Error as error:
            raise SpatialUnavailable("PostGIS risk projection is unavailable.") from error

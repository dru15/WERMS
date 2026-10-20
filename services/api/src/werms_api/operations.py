"""Transactional pilot operations; comparisons never allocate shelter capacity."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from werms_api.domain.models import HazardState, NoSafeRouteError, Point, Shelter, ShelterStatus
from werms_api.domain.routing import calculate_safe_route
from werms_api.network import build_network, routing_graph
from werms_api.schemas import (
    ConfirmRouteRequest,
    Coordinate,
    HazardResponse,
    RoutePoint,
    RoutePreview,
    RouteRequest,
    RouteResponse,
    ShelterResponse,
    ShelterUpdate,
    SnapshotResponse,
)


class OperationError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class Operations:
    def __init__(
        self,
        path: str | Path,
        *,
        threshold: float = 0.9,
        validity_seconds: int = 300,
        network: dict | None = None,
        spatial=None,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.threshold = threshold
        self.validity_seconds = validity_seconds
        self.network = network if network is not None else build_network()
        self.spatial = spatial
        self.nodes, self.edges = routing_graph(self.network, traffic=True)
        with self.transaction() as db:
            schema_version = db.execute("PRAGMA user_version").fetchone()[0]
            if schema_version not in (0, 1, 2):
                raise RuntimeError("Stored schema version is unsupported; migrate explicitly.")
            db.execute("""CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS shelters (
                id TEXT PRIMARY KEY, occupancy INTEGER NOT NULL CHECK (occupancy >= 0),
                status TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS closures (
                edge_id TEXT PRIMARY KEY, reason TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS fire_exclusions (
                id TEXT PRIMARY KEY, geometry TEXT NOT NULL, edge_ids TEXT NOT NULL,
                reason TEXT NOT NULL, active INTEGER NOT NULL, created_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS routes (
                id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                fingerprint TEXT NOT NULL, shelter_id TEXT NOT NULL REFERENCES shelters(id),
                party_size INTEGER NOT NULL CHECK (party_size BETWEEN 1 AND 20),
                status TEXT NOT NULL CHECK (
                    status IN ('valid','invalid','expired','cancelled','arrived')),
                cause TEXT, valid_until TEXT NOT NULL, payload TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS audit (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL, action TEXT NOT NULL,
                entity_id TEXT NOT NULL, timestamp TEXT NOT NULL, details TEXT NOT NULL)""")
            existing = db.execute("SELECT value FROM meta WHERE key='road_version'").fetchone()
            if existing and existing[0] != self.network["version"]:
                raise RuntimeError("Stored road version requires an explicit migration.")
            if not existing:
                now = datetime.now(UTC).isoformat()
                db.executemany(
                    "INSERT INTO meta VALUES (?, ?)",
                    [
                        ("road_version", self.network["version"]),
                        ("revision", "1"),
                        ("hazard_version", "1"),
                        ("hazard_timestamp", now),
                    ],
                )
                db.executemany(
                    "INSERT INTO shelters VALUES (?, ?, 'open', ?)",
                    [(s["id"], s["occupancy"], now) for s in self.network["shelters"]],
                )
                db.executemany(
                    "INSERT INTO closures VALUES (?, 'Initial pilot closure', ?)",
                    [(e, now) for e in self.network["initial_closures"]],
                )
            # Older releases must refuse this store rather than ignore published fire exclusions.
            db.execute("PRAGMA user_version=2")

    @contextmanager
    def transaction(self):
        # Each operation owns its connection; BEGIN IMMEDIATE serializes capacity
        # decisions even across independent API instances on the same local file.
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _bump(self, db):
        db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")

    def _audit(
        self,
        db,
        action: str,
        entity_id: str,
        now: datetime,
        *,
        actor: str = "system",
        details: dict | None = None,
    ):
        db.execute(
            "INSERT INTO audit(actor,action,entity_id,timestamp,details) VALUES (?,?,?,?,?)",
            (actor, action, entity_id, now.isoformat(), json.dumps(details or {})),
        )

    def _expire(self, db, now: datetime):
        rows = db.execute(
            "SELECT id FROM routes WHERE status='valid' AND valid_until<=?", (now.isoformat(),)
        ).fetchall()
        if rows:
            db.execute(
                "UPDATE routes SET status='expired', cause='VALIDITY_EXPIRED' "
                "WHERE status='valid' AND valid_until<=?",
                (now.isoformat(),),
            )
            self._bump(db)
            for row in rows:
                self._audit(db, "reservation.expired", row["id"], now)

    def _hazard(self, db) -> HazardState:
        meta = dict(db.execute("SELECT key,value FROM meta").fetchall())
        return HazardState(
            version=f"hazard-{meta['hazard_version']}",
            source_timestamp=datetime.fromisoformat(meta["hazard_timestamp"]),
            blocked_edge_ids=frozenset(r[0] for r in db.execute("SELECT edge_id FROM closures"))
            | frozenset(
                edge
                for row in db.execute("SELECT edge_ids FROM fire_exclusions WHERE active=1")
                for edge in json.loads(row[0])
            ),
        )

    def _shelters(self, db, *, at: datetime | None = None) -> list[Shelter]:
        seeds = {s["id"]: s for s in self.network["shelters"]}
        demand = dict(
            db.execute(
                "SELECT shelter_id,SUM(party_size) FROM routes "
                "WHERE status='valid' AND (? IS NULL OR valid_until>?) GROUP BY shelter_id",
                (at.isoformat() if at else None, at.isoformat() if at else None),
            ).fetchall()
        )
        result = []
        for row in db.execute("SELECT * FROM shelters ORDER BY id"):
            s = seeds[row["id"]]
            result.append(
                Shelter(
                    s["id"],
                    s["name"],
                    s["node"],
                    Point(s["latitude"], s["longitude"])
                    if "latitude" in s
                    else self.nodes[s["node"]].point,
                    s["capacity"],
                    row["occupancy"],
                    demand.get(s["id"], 0),
                    ShelterStatus(row["status"]),
                    datetime.fromisoformat(row["updated_at"]),
                )
            )
        return result

    @staticmethod
    def _serialize_shelter(s: Shelter) -> ShelterResponse:
        return ShelterResponse(
            shelter_id=s.shelter_id,
            node_id=s.node_id,
            name=s.name,
            location=Coordinate(latitude=s.point.latitude, longitude=s.point.longitude),
            capacity=s.capacity,
            occupancy=s.occupancy,
            reserved_demand=s.reserved_demand,
            utilization=s.utilization,
            status=s.status,
            updated_at=s.updated_at,
        )

    def _snapshot(self, db) -> SnapshotResponse:
        hazard = self._hazard(db)
        return SnapshotResponse(
            hazard=HazardResponse(
                version=hazard.version,
                source_timestamp=hazard.source_timestamp,
                blocked_edge_ids=sorted(hazard.blocked_edge_ids),
            ),
            shelters=[self._serialize_shelter(s) for s in self._shelters(db)],
            revision=int(db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0]),
        )

    def snapshot(self, *, now: datetime | None = None) -> SnapshotResponse:
        with self.transaction() as db:
            self._expire(db, now or datetime.now(UTC))
            return self._snapshot(db)

    def _origin(self, request: RouteRequest) -> str:
        if request.origin_node_id is not None:
            if request.origin_node_id not in self.nodes:
                raise OperationError(
                    "UNSUPPORTED_ORIGIN", "Choose a point in the pilot network.", 422
                )
            return request.origin_node_id
        point = request.origin
        assert point is not None
        latitudes = [n.point.latitude for n in self.nodes.values()]
        longitudes = [n.point.longitude for n in self.nodes.values()]
        bounds = self.network.get(
            "bounds",
            [
                min(latitudes) - 0.005,
                min(longitudes) - 0.005,
                max(latitudes) + 0.005,
                max(longitudes) + 0.005,
            ],
        )
        if not (
            bounds[0] <= point.latitude <= bounds[2] and bounds[1] <= point.longitude <= bounds[3]
        ):
            raise OperationError(
                "UNSUPPORTED_ORIGIN", "Location is outside the supported pilot area.", 422
            )
        nearest = min(
            self.nodes,
            key=lambda key: (
                (self.nodes[key].point.latitude - point.latitude) ** 2
                + (self.nodes[key].point.longitude - point.longitude) ** 2
            ),
        )
        target = self.nodes[nearest].point
        distance_m = ((target.latitude - point.latitude) * 111320) ** 2 + (
            (target.longitude - point.longitude) * 111320 * math.cos(math.radians(point.latitude))
        ) ** 2
        if self.network["data_mode"] == "osm-pilot" and distance_m > 200**2:
            raise OperationError(
                "UNSUPPORTED_ORIGIN", "Choose a point within 200 m of a mapped road.", 422
            )
        return nearest

    def _previews(
        self,
        db,
        request: RouteRequest,
        now: datetime,
        *,
        hazard: HazardState | None = None,
        shelters: list[Shelter] | None = None,
    ) -> list[RoutePreview]:
        origin = self._origin(request)
        hazard = hazard if hazard is not None else self._hazard(db)
        nodes, edges = routing_graph(self.network, traffic=request.traffic)
        shelters = shelters if shelters is not None else self._shelters(db)
        if request.shelter_id and request.shelter_id not in {s.shelter_id for s in shelters}:
            raise OperationError("UNKNOWN_SHELTER", "Shelter was not found.", 404)
        candidates = []
        for shelter in shelters:
            if request.shelter_id and shelter.shelter_id != request.shelter_id:
                continue
            try:
                plan = calculate_safe_route(
                    origin_node_id=origin,
                    nodes=nodes,
                    edges=edges,
                    shelters=[shelter],
                    hazard=hazard,
                    redirect_threshold=self.threshold,
                    party_size=request.party_size,
                    now=now,
                    turn_restrictions=tuple(self.network.get("turn_restrictions", [])),
                )
            except NoSafeRouteError:
                continue
            reasons = list(plan.reason_codes)
            if (now - hazard.source_timestamp).total_seconds() > 1800:
                reasons.append("PILOT_STATE_OLDER_THAN_30_MINUTES")
            candidates.append(
                (
                    plan.total_cost,
                    RoutePreview(
                        shelter=self._serialize_shelter(shelter),
                        path=[
                            RoutePoint(
                                node_id=n,
                                latitude=nodes[n].point.latitude,
                                longitude=nodes[n].point.longitude,
                            )
                            for n in plan.node_ids
                        ],
                        edge_ids=list(plan.edge_ids),
                        distance_km=round(plan.distance_km, 2),
                        estimated_minutes=round(plan.estimated_minutes, 1),
                        risk_score=round(plan.risk_score, 3),
                        hazard_version=hazard.version,
                        road_version=self.network["version"],
                        hazard_source_timestamp=hazard.source_timestamp,
                        created_at=now,
                        valid_until=now + timedelta(seconds=self.validity_seconds),
                        reason_codes=reasons,
                    ),
                )
            )
        if not candidates:
            raise OperationError(
                "NO_SAFE_ROUTE", "No open route leads to a shelter that fits your party."
            )
        return [preview for _, preview in sorted(candidates, key=lambda item: item[0])]

    def preview(self, request: RouteRequest, *, now: datetime | None = None) -> list[RoutePreview]:
        now = now or datetime.now(UTC)
        with self.transaction() as db:
            self._expire(db, now)
            return self._previews(db, request, now)

    def _route(self, db, route_id: str) -> RouteResponse:
        row = db.execute("SELECT * FROM routes WHERE id=?", (route_id,)).fetchone()
        if row is None:
            raise OperationError("ROUTE_NOT_FOUND", "Booking was not found.", 404)
        payload = json.loads(row["payload"])
        shelter = next(s for s in self._shelters(db) if s.shelter_id == row["shelter_id"])
        payload.update(
            route_id=row["id"],
            status=row["status"],
            cause=row["cause"],
            party_size=row["party_size"],
            shelter=self._serialize_shelter(shelter),
        )
        return RouteResponse.model_validate(payload)

    def confirm(
        self, request: ConfirmRouteRequest, *, now: datetime | None = None
    ) -> RouteResponse:
        now = now or datetime.now(UTC)
        fingerprint = hashlib.sha256(
            request.model_dump_json(exclude={"request_id"}).encode()
        ).hexdigest()
        with self.transaction() as db:
            self._expire(db, now)
            previous = db.execute(
                "SELECT * FROM routes WHERE request_id=?", (str(request.request_id),)
            ).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise OperationError(
                        "IDEMPOTENCY_CONFLICT", "This request ID has different inputs."
                    )
                return self._route(db, previous["id"])
            if request.replace_route_id:
                old = self._route(db, str(request.replace_route_id))
                if old.status == "arrived":
                    raise OperationError(
                        "ALREADY_ARRIVED", "An arrived booking cannot be replaced."
                    )
                db.execute(
                    "UPDATE routes SET status='cancelled',cause='REPLACED' "
                    "WHERE id=? AND status IN ('valid','invalid','expired')",
                    (old.route_id,),
                )
            plan = self._previews(db, request, now)[0]
            route_id = str(uuid4())
            db.execute(
                "INSERT INTO routes VALUES (?,?,?,?,?,'valid',NULL,?,?)",
                (
                    route_id,
                    str(request.request_id),
                    fingerprint,
                    plan.shelter.shelter_id,
                    request.party_size,
                    plan.valid_until.isoformat(),
                    plan.model_dump_json(),
                ),
            )
            self._bump(db)
            self._audit(
                db,
                "reservation.confirmed",
                route_id,
                now,
                actor="booking-holder",
                details={
                    "party_size": request.party_size,
                    "replaces": str(request.replace_route_id) if request.replace_route_id else None,
                },
            )
            return self._route(db, route_id)

    def get_route(self, route_id: str, *, now: datetime | None = None) -> RouteResponse:
        with self.transaction() as db:
            self._expire(db, now or datetime.now(UTC))
            return self._route(db, route_id)

    def cancel(self, route_id: str) -> RouteResponse:
        now = datetime.now(UTC)
        with self.transaction() as db:
            self._expire(db, now)
            route = self._route(db, route_id)
            if route.status == "arrived":
                raise OperationError("ALREADY_ARRIVED", "An arrived party is already checked in.")
            if route.status == "valid":
                db.execute(
                    "UPDATE routes SET status='cancelled',cause='CANCELLED_BY_HOLDER' WHERE id=?",
                    (route_id,),
                )
                self._bump(db)
                self._audit(db, "reservation.cancelled", route_id, now, actor="booking-holder")
            return self._route(db, route_id)

    def arrive(
        self, route_id: str, *, actor: str = "operator", shelter_id: str | None = None
    ) -> RouteResponse:
        now = datetime.now(UTC)
        with self.transaction() as db:
            self._expire(db, now)
            route = self._route(db, route_id)
            if shelter_id and route.shelter.shelter_id != shelter_id:
                raise OperationError("SHELTER_SCOPE", "This booking belongs to another site.", 403)
            if route.status == "arrived":
                return route
            if route.status != "valid":
                raise OperationError(
                    "BOOKING_NOT_ACTIVE", "Only an active booking can be checked in."
                )
            db.execute(
                "UPDATE shelters SET occupancy=occupancy+?,updated_at=? WHERE id=?",
                (route.party_size, now.isoformat(), route.shelter.shelter_id),
            )
            db.execute("UPDATE routes SET status='arrived',cause=NULL WHERE id=?", (route_id,))
            self._bump(db)
            self._audit(db, "reservation.arrived", route_id, now, actor=actor)
            return self._route(db, route_id)

    def set_closure(
        self, edge_id: str, closed: bool, reason: str, *, actor: str = "operator"
    ) -> SnapshotResponse:
        if edge_id not in {r["id"] for r in self.network["roads"]}:
            raise OperationError("UNKNOWN_ROAD", "Road was not found.", 404)
        now = datetime.now(UTC)
        with self.transaction() as db:
            self._expire(db, now)
            exists = db.execute("SELECT 1 FROM closures WHERE edge_id=?", (edge_id,)).fetchone()
            if not closed and any(
                edge_id in json.loads(row[0])
                for row in db.execute("SELECT edge_ids FROM fire_exclusions WHERE active=1")
            ):
                raise OperationError(
                    "FIRE_EXCLUSION_ACTIVE",
                    "Deactivate the fire exclusion before reopening this segment.",
                )
            if bool(exists) == closed:
                return self._snapshot(db)
            if closed:
                db.execute(
                    "INSERT INTO closures VALUES (?,?,?)", (edge_id, reason, now.isoformat())
                )
                for row in db.execute(
                    "SELECT id,payload FROM routes WHERE status='valid'"
                ).fetchall():
                    if edge_id in json.loads(row["payload"])["edge_ids"]:
                        db.execute(
                            "UPDATE routes SET status='invalid',cause='HARD_HAZARD_INTERSECTION' "
                            "WHERE id=?",
                            (row["id"],),
                        )
                        self._audit(
                            db, "route.invalidated", row["id"], now, details={"road": edge_id}
                        )
            else:
                db.execute("DELETE FROM closures WHERE edge_id=?", (edge_id,))
            db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='hazard_version'")
            db.execute("UPDATE meta SET value=? WHERE key='hazard_timestamp'", (now.isoformat(),))
            self._bump(db)
            self._audit(
                db,
                "road.closed" if closed else "road.reopened",
                edge_id,
                now,
                actor=actor,
                details={"reason": reason},
            )
            return self._snapshot(db)

    def update_shelter(
        self, shelter_id: str, request: ShelterUpdate, actor: str
    ) -> SnapshotResponse:
        now = datetime.now(UTC)
        with self.transaction() as db:
            self._expire(db, now)
            shelter = next((s for s in self._shelters(db) if s.shelter_id == shelter_id), None)
            if shelter is None:
                raise OperationError("UNKNOWN_SHELTER", "Assembly site was not found.", 404)
            if shelter.updated_at != request.expected_updated_at:
                raise OperationError(
                    "STALE_UPDATE", "Site changed since you opened it. Refresh before saving."
                )
            demand = shelter.reserved_demand if request.status != "closed" else 0
            if request.occupancy + demand > shelter.capacity:
                raise OperationError(
                    "CAPACITY_CONFLICT", "Occupancy and active reservations exceed capacity."
                )
            db.execute(
                "UPDATE shelters SET occupancy=?,status=?,updated_at=? WHERE id=?",
                (
                    request.occupancy,
                    request.status,
                    now.isoformat(),
                    shelter_id,
                ),
            )
            if request.status == "closed":
                bookings = db.execute(
                    "SELECT id FROM routes WHERE shelter_id=? AND status='valid'", (shelter_id,)
                ).fetchall()
                db.execute(
                    "UPDATE routes SET status='invalid',cause='SHELTER_CLOSED' "
                    "WHERE shelter_id=? AND status='valid'",
                    (shelter_id,),
                )
                for row in bookings:
                    self._audit(
                        db,
                        "route.invalidated",
                        row["id"],
                        now,
                        actor=actor,
                        details={"shelter": shelter_id},
                    )
            self._bump(db)
            self._audit(
                db,
                "shelter.updated",
                shelter_id,
                now,
                actor=actor,
                details=request.model_dump(mode="json"),
            )
            return self._snapshot(db)

    def fire_exclusions(self) -> list[dict]:
        with self.transaction() as db:
            return [
                {
                    "id": r["id"],
                    "geometry": json.loads(r["geometry"]),
                    "edge_ids": json.loads(r["edge_ids"]),
                    "reason": r["reason"],
                    "active": bool(r["active"]),
                    "created_at": r["created_at"],
                }
                for r in db.execute("SELECT * FROM fire_exclusions ORDER BY created_at DESC")
            ]

    def publish_fire_exclusion(self, identifier: str, geometry: dict, reason: str, actor: str):
        from werms_api.spatial import validated_polygon

        canonical = json.dumps(validated_polygon(geometry), sort_keys=True, separators=(",", ":"))
        now = datetime.now(UTC)

        # Recover an already committed publication even while PostGIS is offline.
        with self.transaction() as db:
            self._expire(db, now)
            existing = db.execute(
                "SELECT geometry,reason FROM fire_exclusions WHERE id=?", (identifier,)
            ).fetchone()
            if existing:
                if tuple(existing) != (canonical, reason):
                    raise OperationError(
                        "IDEMPOTENCY_CONFLICT", "Exclusion ID already has another payload."
                    )
                return self._snapshot(db)
        if self.spatial is None:
            raise OperationError(
                "SPATIAL_UNAVAILABLE", "Configure PostGIS to evaluate fire geometry.", 503
            )
        edge_ids = self.spatial.intersections(geometry)
        with self.transaction() as db:
            self._expire(db, now)
            existing = db.execute(
                "SELECT geometry,reason FROM fire_exclusions WHERE id=?", (identifier,)
            ).fetchone()
            if existing:
                if tuple(existing) != (canonical, reason):
                    raise OperationError(
                        "IDEMPOTENCY_CONFLICT", "Exclusion ID already has another payload."
                    )
                return self._snapshot(db)
            db.execute(
                "INSERT INTO fire_exclusions VALUES (?,?,?,?,1,?)",
                (identifier, canonical, json.dumps(edge_ids), reason, now.isoformat()),
            )
            self._exclusion_changed(db, identifier, edge_ids, now, actor)
            return self._snapshot(db)

    def set_fire_exclusion(self, identifier: str, active: bool, actor: str):
        now = datetime.now(UTC)
        with self.transaction() as db:
            self._expire(db, now)
            row = db.execute("SELECT * FROM fire_exclusions WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise OperationError("NOT_FOUND", "Fire exclusion was not found.", 404)
            if bool(row["active"]) != active:
                db.execute(
                    "UPDATE fire_exclusions SET active=? WHERE id=?", (int(active), identifier)
                )
                self._exclusion_changed(
                    db, identifier, json.loads(row["edge_ids"]) if active else [], now, actor
                )
            return self._snapshot(db)

    def _exclusion_changed(self, db, identifier, edge_ids, now, actor):
        blocked = set(edge_ids)
        for row in db.execute("SELECT id,payload FROM routes WHERE status='valid'").fetchall():
            if blocked.intersection(json.loads(row["payload"])["edge_ids"]):
                db.execute(
                    "UPDATE routes SET status='invalid',cause='FIRE_EXCLUSION_INTERSECTION' "
                    "WHERE id=?",
                    (row["id"],),
                )
                self._audit(
                    db,
                    "route.invalidated",
                    row["id"],
                    now,
                    actor=actor,
                    details={"fire_exclusion": identifier},
                )
        db.execute("UPDATE meta SET value=CAST(value AS INTEGER)+1 WHERE key='hazard_version'")
        db.execute("UPDATE meta SET value=? WHERE key='hazard_timestamp'", (now.isoformat(),))
        self._bump(db)
        self._audit(
            db,
            "fire_exclusion.changed",
            identifier,
            now,
            actor=actor,
            details={"blocked_segments": len(blocked), "engine": "PostGIS"},
        )

    def audit(self) -> list[dict]:
        with self.transaction() as db:
            return [
                dict(row)
                for row in db.execute("SELECT * FROM audit ORDER BY sequence DESC LIMIT 100")
            ]

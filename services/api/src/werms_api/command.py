"""Transactional incident and resource lifecycle for the pilot command desk."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from werms_api.operations import OperationError, Operations
from werms_api.schemas import (
    AssignmentUpdate,
    DispatchRequest,
    IncidentRequest,
    IncidentUpdate,
    ResourceRequest,
)


class CommandDesk:
    def __init__(self, operations: Operations):
        self.operations = operations
        with operations.transaction() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS incidents (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                source TEXT NOT NULL, observed_at TEXT NOT NULL, priority TEXT NOT NULL,
                road_id TEXT, status TEXT NOT NULL, version INTEGER NOT NULL,
                updated_at TEXT NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS resources (
                id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, kind TEXT NOT NULL,
                offline INTEGER NOT NULL DEFAULT 0)""")
            db.execute("""CREATE TABLE IF NOT EXISTS assignments (
                id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                resource_id TEXT NOT NULL REFERENCES resources(id),
                incident_id TEXT NOT NULL REFERENCES incidents(id),
                status TEXT NOT NULL, note TEXT NOT NULL, updated_at TEXT NOT NULL,
                fingerprint TEXT NOT NULL)""")
            db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS resource_active_assignment
                ON assignments(resource_id) WHERE status IN ('dispatched','acknowledged')""")

    def snapshot(self) -> dict:
        with self.operations.transaction() as db:
            return {
                "incidents": [
                    dict(r) for r in db.execute("SELECT * FROM incidents ORDER BY updated_at DESC")
                ],
                "resources": [
                    dict(r)
                    for r in db.execute(
                        "SELECT r.*, CASE WHEN offline=1 THEN 'offline' "
                        "WHEN EXISTS(SELECT 1 FROM assignments a WHERE a.resource_id=r.id "
                        "AND a.status IN ('dispatched','acknowledged')) THEN 'deployed' "
                        "ELSE 'available' END AS status FROM resources r ORDER BY name"
                    )
                ],
                "assignments": [
                    dict(r)
                    for r in db.execute(
                        "SELECT id,request_id,resource_id,incident_id,status,note,updated_at "
                        "FROM assignments ORDER BY updated_at DESC"
                    )
                ],
            }

    def report(self, request: IncidentRequest, actor: str) -> dict:
        now = datetime.now(UTC)
        if request.observed_at > now + timedelta(minutes=5):
            raise OperationError(
                "FUTURE_OBSERVATION", "Observation time cannot be in the future.", 422
            )
        if request.road_id and request.road_id not in {
            r["id"] for r in self.operations.network["roads"]
        }:
            raise OperationError("UNKNOWN_ROAD", "Road was not found.", 422)
        incident_id = str(uuid4())
        with self.operations.transaction() as db:
            db.execute(
                "INSERT INTO incidents VALUES (?,?,?,?,?,?,?,'reported',1,?)",
                (
                    incident_id,
                    request.title.strip(),
                    request.description,
                    request.source,
                    request.observed_at.isoformat(),
                    request.priority,
                    request.road_id,
                    now.isoformat(),
                ),
            )
            self.operations._bump(db)
            self.operations._audit(
                db,
                "incident.reported",
                incident_id,
                now,
                actor=actor,
                details=request.model_dump(mode="json"),
            )
            return dict(db.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone())

    def update_incident(self, incident_id: str, request: IncidentUpdate, actor: str) -> dict:
        now = datetime.now(UTC)
        with self.operations.transaction() as db:
            row = db.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
            if not row:
                raise OperationError("UNKNOWN_INCIDENT", "Incident was not found.", 404)
            if row["version"] != request.version:
                raise OperationError(
                    "STALE_UPDATE", "Another operator changed this incident. Refresh first."
                )
            allowed = {
                "reported": {"acknowledged"},
                "acknowledged": {"resolved"},
                "resolved": set(),
            }
            if request.status != row["status"] and request.status not in allowed[row["status"]]:
                raise OperationError(
                    "INVALID_TRANSITION",
                    "Acknowledge before resolving; resolved incidents stay closed.",
                )
            if row["status"] == "resolved":
                raise OperationError("INCIDENT_RESOLVED", "Resolved incidents cannot be changed.")
            if (
                request.status == "resolved"
                and db.execute(
                    "SELECT 1 FROM assignments WHERE incident_id=? "
                    "AND status IN ('dispatched','acknowledged')",
                    (incident_id,),
                ).fetchone()
            ):
                raise OperationError(
                    "ACTIVE_ASSIGNMENTS", "Complete or cancel active assignments first."
                )
            db.execute(
                "UPDATE incidents SET status=?,priority=?,version=version+1,updated_at=? "
                "WHERE id=?",
                (
                    request.status,
                    request.priority,
                    now.isoformat(),
                    incident_id,
                ),
            )
            self.operations._bump(db)
            self.operations._audit(
                db, "incident.updated", incident_id, now, actor=actor, details=request.model_dump()
            )
            return dict(db.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone())

    def register(self, request: ResourceRequest, actor: str) -> dict:
        resource_id = str(uuid4())
        name = request.name.strip()
        if len(name) < 3:
            raise OperationError(
                "INVALID_NAME", "Enter a resource name of at least three characters.", 422
            )
        with self.operations.transaction() as db:
            if db.execute("SELECT 1 FROM resources WHERE name=?", (name,)).fetchone():
                raise OperationError("RESOURCE_EXISTS", "That resource name already exists.")
            db.execute(
                "INSERT INTO resources(id,name,kind) VALUES (?,?,?)",
                (resource_id, name, request.kind),
            )
            self.operations._audit(
                db,
                "resource.registered",
                resource_id,
                datetime.now(UTC),
                actor=actor,
                details={"name": name, "kind": request.kind},
            )
            self.operations._bump(db)
            return {"id": resource_id, "name": name, "kind": request.kind, "status": "available"}

    def availability(self, resource_id: str, offline: bool, actor: str):
        with self.operations.transaction() as db:
            if not db.execute("SELECT 1 FROM resources WHERE id=?", (resource_id,)).fetchone():
                raise OperationError("UNKNOWN_RESOURCE", "Resource was not found.", 404)
            if db.execute(
                "SELECT 1 FROM assignments WHERE resource_id=? "
                "AND status IN ('dispatched','acknowledged')",
                (resource_id,),
            ).fetchone():
                raise OperationError(
                    "RESOURCE_DEPLOYED",
                    "Complete the active assignment before changing availability.",
                )
            db.execute("UPDATE resources SET offline=? WHERE id=?", (int(offline), resource_id))
            self.operations._bump(db)
            self.operations._audit(
                db,
                "resource.availability",
                resource_id,
                datetime.now(UTC),
                actor=actor,
                details={"offline": offline},
            )

    def dispatch(self, request: DispatchRequest, actor: str) -> dict:
        fingerprint = request.model_dump_json(exclude={"request_id"})
        now = datetime.now(UTC)
        with self.operations.transaction() as db:
            previous = db.execute(
                "SELECT * FROM assignments WHERE request_id=?", (str(request.request_id),)
            ).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise OperationError(
                        "IDEMPOTENCY_CONFLICT", "This dispatch request has different inputs."
                    )
                return {k: v for k, v in dict(previous).items() if k != "fingerprint"}
            resource = db.execute(
                "SELECT * FROM resources WHERE id=?", (str(request.resource_id),)
            ).fetchone()
            incident = db.execute(
                "SELECT * FROM incidents WHERE id=?", (str(request.incident_id),)
            ).fetchone()
            if not resource or not incident:
                raise OperationError(
                    "DISPATCH_TARGET_MISSING", "Choose a registered resource and incident.", 404
                )
            if incident["status"] == "resolved":
                raise OperationError("INCIDENT_RESOLVED", "Cannot dispatch to a resolved incident.")
            if (
                resource["offline"]
                or db.execute(
                    "SELECT 1 FROM assignments WHERE resource_id=? "
                    "AND status IN ('dispatched','acknowledged')",
                    (str(request.resource_id),),
                ).fetchone()
            ):
                raise OperationError(
                    "RESOURCE_UNAVAILABLE", "Resource is already deployed or offline."
                )
            assignment_id = str(uuid4())
            db.execute(
                "INSERT INTO assignments VALUES (?,?,?,?,'dispatched',?,?,?)",
                (
                    assignment_id,
                    str(request.request_id),
                    str(request.resource_id),
                    str(request.incident_id),
                    request.note,
                    now.isoformat(),
                    fingerprint,
                ),
            )
            self.operations._bump(db)
            self.operations._audit(
                db,
                "resource.dispatched",
                assignment_id,
                now,
                actor=actor,
                details=json.loads(fingerprint),
            )
            return {
                "id": assignment_id,
                "resource_id": str(request.resource_id),
                "incident_id": str(request.incident_id),
                "status": "dispatched",
            }

    def update_assignment(self, assignment_id: str, request: AssignmentUpdate, actor: str):
        now = datetime.now(UTC)
        with self.operations.transaction() as db:
            row = db.execute("SELECT * FROM assignments WHERE id=?", (assignment_id,)).fetchone()
            if not row:
                raise OperationError("UNKNOWN_ASSIGNMENT", "Assignment was not found.", 404)
            if row["status"] == request.status:
                return
            transitions = {
                "dispatched": {"acknowledged", "cancelled"},
                "acknowledged": {"resolved", "cancelled"},
            }
            if request.status not in transitions.get(row["status"], set()):
                raise OperationError(
                    "INVALID_TRANSITION",
                    "Acknowledge dispatch before completion; closed assignments stay closed.",
                )
            db.execute(
                "UPDATE assignments SET status=?,note=?,updated_at=? WHERE id=?",
                (
                    request.status,
                    request.note,
                    now.isoformat(),
                    assignment_id,
                ),
            )
            self.operations._bump(db)
            self.operations._audit(
                db,
                f"assignment.{request.status}",
                assignment_id,
                now,
                actor=actor,
                details={"note": request.note},
            )

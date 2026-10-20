"""What-if analysis against one coherent snapshot, without operational writes."""

from dataclasses import replace
from datetime import UTC, datetime
from time import perf_counter

from werms_api.domain.models import ShelterStatus
from werms_api.operations import OperationError, Operations
from werms_api.schemas import ScenarioRequest


def compare_scenario(
    operations: Operations, request: ScenarioRequest, *, now: datetime | None = None
) -> dict:
    started = perf_counter()
    now = now or datetime.now(UTC)
    polygon_edges = []
    if request.fire_polygon is not None:
        if operations.spatial is None:
            raise OperationError(
                "SPATIAL_UNAVAILABLE", "PostGIS is required for polygon scenarios.", 503
            )
        polygon_edges = operations.spatial.intersections(request.fire_polygon)
    unknown = set(request.blocked_edge_ids) - {r["id"] for r in operations.network["roads"]}
    if unknown:
        raise OperationError("UNKNOWN_ROAD", "Scenario contains an unknown road segment.", 422)
    if set(request.unavailable_shelter_ids) - {s["id"] for s in operations.network["shelters"]}:
        raise OperationError("UNKNOWN_SHELTER", "Scenario contains an unknown assembly site.", 422)
    with operations.transaction() as db:
        hazard = operations._hazard(db)
        shelters = operations._shelters(db, at=now)
        revision = int(db.execute("SELECT value FROM meta WHERE key='revision'").fetchone()[0])
        scenario_hazard = replace(
            hazard,
            blocked_edge_ids=hazard.blocked_edge_ids
            | set(request.blocked_edge_ids)
            | set(polygon_edges),
        )
        scenario_shelters = [
            replace(s, status=ShelterStatus.CLOSED)
            if s.shelter_id in request.unavailable_shelter_ids
            else s
            for s in shelters
        ]

        def plans(current_hazard, current_shelters):
            try:
                return operations._previews(
                    db, request, now, hazard=current_hazard, shelters=current_shelters
                )
            except OperationError as error:
                if error.code != "NO_SAFE_ROUTE":
                    raise
                return []

        baseline = plans(hazard, shelters)
        simulated = plans(scenario_hazard, scenario_shelters)
    a, b = baseline[0] if baseline else None, simulated[0] if simulated else None
    return {
        "mode": "what-if-only",
        "admission_threshold": operations.threshold,
        "planner": "Hazard-aware A* with turn restrictions",
        "changes_operational_state": False,
        "fire_intersections": polygon_edges,
        "spatial_engine": "PostGIS" if request.fire_polygon is not None else None,
        "road_version": operations.network["version"],
        "snapshot_revision": revision,
        "created_at": now.isoformat(),
        "inputs": request.model_dump(mode="json"),
        "baseline": [p.model_dump(mode="json") for p in baseline],
        "simulated": [p.model_dump(mode="json") for p in simulated],
        "outcome": "no_baseline_route"
        if not a
        else "no_route"
        if not b
        else "rerouted"
        if (a.edge_ids, a.shelter.shelter_id) != (b.edge_ids, b.shelter.shelter_id)
        else "unchanged",
        "delta_minutes": round(b.estimated_minutes - a.estimated_minutes, 1) if a and b else None,
        "delta_km": round(b.distance_km - a.distance_km, 2) if a and b else None,
        "destination_changed": bool(a and b and a.shelter.shelter_id != b.shelter.shelter_id),
        "reachable_before": len(baseline),
        "reachable_after": len(simulated),
        "compute_ms": round((perf_counter() - started) * 1000, 2),
    }

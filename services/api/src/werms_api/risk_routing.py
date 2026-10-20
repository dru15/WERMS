"""Historical research replay: join genuine model scores to roads through PostGIS.

This endpoint deliberately refuses cross-region transfer. It cannot create a
booking or turn a US case into an India fire forecast.
"""

from dataclasses import replace
from datetime import UTC, datetime

from werms_api.domain.models import HazardState, NoSafeRouteError
from werms_api.domain.routing import calculate_safe_route
from werms_api.network import routing_graph
from werms_api.operations import OperationError


def replay_ml_route(operations, research, case_id, request):
    case = research.case(case_id)
    if case is None:
        raise OperationError("NOT_FOUND", "Held-out case was not found.", 404)
    if operations.network.get("country") != "US":
        raise OperationError(
            "MODEL_OUT_OF_DISTRIBUTION",
            "FireCastRL is US-only; its scores cannot be applied to India roads.",
            422,
        )
    if operations.spatial is None:
        raise OperationError(
            "SPATIAL_UNAVAILABLE", "PostGIS is required to project ML scores.", 503
        )
    try:
        inference = research.infer(case_id)
    except (RuntimeError, ValueError, ImportError, OSError) as error:
        raise OperationError(
            "MODEL_UNAVAILABLE", "Research model inference is unavailable. Retry shortly.", 503
        ) from error
    report = research.report()
    probability = inference["predictions"][report["champion"]]
    scores = operations.spatial.project_risk(
        [
            {
                "latitude": case["latitude"],
                "longitude": case["longitude"],
                "probability": probability,
            }
        ]
    )
    if not scores:
        raise OperationError(
            "MODEL_SPATIAL_COVERAGE_MISSING",
            "This case has no GRIDMET-scale overlap with the road pilot.",
            422,
        )
    now = datetime.now(UTC)
    with operations.transaction() as db:
        hazard = operations._hazard(db)
        origin = operations._origin(request)
        nodes, edges = routing_graph(operations.network, traffic=request.traffic)
        baseline_edges = edges
        edges = tuple(
            replace(edge, predictive_risk=scores.get(edge.edge_id, 0.0)) for edge in edges
        )
        shelters = operations._shelters(db, at=now)
        if request.shelter_id:
            shelters = [s for s in shelters if s.shelter_id == request.shelter_id]
        try:
            route = calculate_safe_route(
                origin_node_id=origin,
                nodes=nodes,
                edges=edges,
                shelters=shelters,
                hazard=HazardState(
                    hazard.version,
                    hazard.source_timestamp,
                    hazard.blocked_edge_ids,
                    inference["model_version"],
                ),
                redirect_threshold=operations.threshold,
                party_size=request.party_size,
                now=now,
                turn_restrictions=tuple(operations.network.get("turn_restrictions", [])),
            )
            baseline = calculate_safe_route(
                origin_node_id=origin,
                nodes=nodes,
                edges=baseline_edges,
                shelters=shelters,
                hazard=hazard,
                redirect_threshold=operations.threshold,
                party_size=request.party_size,
                now=now,
                turn_restrictions=tuple(operations.network.get("turn_restrictions", [])),
            )
        except NoSafeRouteError as error:
            raise OperationError("NO_SAFE_ROUTE", str(error)) from error
    covered = [edge for edge in route.edge_ids if edge in scores]
    return {
        "mode": "historical-research-replay",
        "creates_booking": False,
        "model_version": inference["model_version"],
        "reference_date": case["reference_date"],
        "model": report["champion"],
        "cohort_probability": probability,
        "risk_scores": scores,
        "origin_node_id": origin,
        "node_ids": list(route.node_ids),
        "baseline": {
            "node_ids": list(baseline.node_ids),
            "edge_ids": list(baseline.edge_ids),
            "shelter_id": baseline.shelter_id,
            "distance_km": baseline.distance_km,
            "estimated_minutes": baseline.estimated_minutes,
            "total_cost": baseline.total_cost,
        },
        "spatial_engine": "PostGIS ST_Intersects",
        "projected_segments": len(scores),
        "covered_route_segments": len(covered),
        "unscored_route_segments": len(route.edge_ids) - len(covered),
        "road_version": operations.network["version"],
        "edge_ids": list(route.edge_ids),
        "shelter_id": route.shelter_id,
        "distance_km": route.distance_km,
        "estimated_minutes": route.estimated_minutes,
        "total_cost": route.total_cost,
        "hazard_version": hazard.version,
        "snapshot_timestamp": now.isoformat(),
        "scope": "Historical model score on current demonstration road and capacity snapshot",
        "reason_codes": [*route.reason_codes, "HISTORICAL_ML_REPLAY", "UNSCORED_ROADS_ARE_UNKNOWN"],
        "interpretation": (
            "3 km experimental support neighbourhood (not a measured grid footprint); "
            "soft exposure penalty, "
            "not a route-safety probability"
        ),
    }

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware

from werms_api.config import get_settings
from werms_api.domain.models import NoSafeRouteError
from werms_api.domain.routing import calculate_safe_route
from werms_api.realtime import ConnectionManager
from werms_api.schemas import (
    Coordinate,
    HazardResponse,
    RoutePoint,
    RouteRequest,
    RouteResponse,
    RouteStatusResponse,
    ScenarioAdvanceResponse,
    ShelterResponse,
    SystemStatusResponse,
)
from werms_api.store import DemoStore, SavedRoute

settings = get_settings()
store = DemoStore()
realtime = ConnectionManager()

app = FastAPI(
    title="WERMS Operational API",
    version="0.1.0",
    description=(
        "Safety-oriented wildfire evacuation routing. ML risk is soft evidence and cannot "
        "override hard hazards or closures."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def serialize_shelter(shelter) -> ShelterResponse:
    return ShelterResponse(
        shelter_id=shelter.shelter_id,
        name=shelter.name,
        location=Coordinate(
            latitude=shelter.point.latitude,
            longitude=shelter.point.longitude,
        ),
        capacity=shelter.capacity,
        occupancy=shelter.occupancy,
        reserved_demand=shelter.reserved_demand,
        utilization=shelter.utilization,
        status=shelter.status,
        updated_at=shelter.updated_at,
    )


@app.get("/health/live", tags=["health"])
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def ready() -> dict[str, str]:
    return {"status": "ready", "store": "in-memory-demo"}


@app.get("/api/v1/system/status", response_model=SystemStatusResponse, tags=["system"])
async def system_status() -> SystemStatusResponse:
    return SystemStatusResponse(
        environment=settings.app_env,
        model_mode=settings.model_mode,
        hazard_version=store.hazard.version,
        road_version=store.road_version,
        websocket_clients=realtime.client_count,
    )


@app.get("/api/v1/hazards", response_model=HazardResponse, tags=["hazards"])
async def hazards() -> HazardResponse:
    return HazardResponse(
        version=store.hazard.version,
        source_timestamp=store.hazard.source_timestamp,
        blocked_edge_ids=sorted(store.hazard.blocked_edge_ids),
        model_version=store.hazard.model_version,
        model_mode=settings.model_mode,
    )


@app.get("/api/v1/shelters", response_model=list[ShelterResponse], tags=["shelters"])
async def shelters() -> list[ShelterResponse]:
    return [serialize_shelter(shelter) for shelter in store.shelters.values()]


@app.post(
    "/api/v1/routes",
    response_model=RouteResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["routes"],
)
async def create_route(request: RouteRequest) -> RouteResponse:
    origin_node_id = store.nearest_node_id(request.origin.latitude, request.origin.longitude)
    try:
        plan = calculate_safe_route(
            origin_node_id=origin_node_id,
            nodes=store.nodes,
            edges=store.edges,
            shelters=store.shelters.values(),
            hazard=store.hazard,
            redirect_threshold=settings.shelter_redirect_threshold,
        )
    except NoSafeRouteError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "NO_SAFE_ROUTE", "message": str(error)},
        ) from error

    try:
        shelter = await store.reserve_shelter(
            plan.shelter_id,
            request.party_size,
            settings.shelter_redirect_threshold,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "SHELTER_CAPACITY_CHANGED", "message": str(error)},
        ) from error

    route_id = str(uuid4())
    created_at = datetime.now(UTC)
    await store.save_route(
        SavedRoute(
            route_id=route_id,
            edge_ids=plan.edge_ids,
            hazard_version=store.hazard.version,
        )
    )
    return RouteResponse(
        route_id=route_id,
        shelter=serialize_shelter(shelter),
        path=[
            RoutePoint(
                node_id=node_id,
                latitude=store.nodes[node_id].point.latitude,
                longitude=store.nodes[node_id].point.longitude,
            )
            for node_id in plan.node_ids
        ],
        edge_ids=list(plan.edge_ids),
        distance_km=round(plan.distance_km, 2),
        estimated_minutes=round(plan.estimated_minutes, 1),
        risk_score=round(plan.risk_score, 3),
        hazard_version=store.hazard.version,
        road_version=store.road_version,
        model_version=store.hazard.model_version,
        model_mode=settings.model_mode,
        hazard_source_timestamp=store.hazard.source_timestamp,
        created_at=created_at,
        valid_until=created_at + timedelta(seconds=settings.route_validity_seconds),
        reason_codes=list(plan.reason_codes),
    )


@app.get(
    "/api/v1/routes/{route_id}/status",
    response_model=RouteStatusResponse,
    tags=["routes"],
)
async def route_status(route_id: str) -> RouteStatusResponse:
    route = store.routes.get(route_id)
    if route is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")
    return RouteStatusResponse(
        route_id=route_id,
        status="valid" if route.valid else "invalid",
        cause=route.invalidation_cause,
        hazard_version=store.hazard.version,
    )


@app.post(
    "/api/v1/demo/scenario/advance",
    response_model=ScenarioAdvanceResponse,
    tags=["demo"],
)
async def advance_demo_scenario() -> ScenarioAdvanceResponse:
    if settings.app_env == "production":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    edge_id, invalidated = await store.advance_hazard()
    event = ScenarioAdvanceResponse(
        hazard_version=store.hazard.version,
        newly_blocked_edge_id=edge_id,
        invalidated_route_ids=invalidated,
    )
    await realtime.broadcast(event.model_dump(mode="json"))
    return event


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    await realtime.connect(websocket)
    await websocket.send_json(
        {"event": "connected", "hazard_version": store.hazard.version}
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        realtime.disconnect(websocket)


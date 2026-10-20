from __future__ import annotations

import json
import secrets
import threading
from importlib.resources import files
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from werms_api.command import CommandDesk
from werms_api.config import Settings, get_settings
from werms_api.identity import Identity
from werms_api.ml_research import ResearchModels
from werms_api.operations import OperationError, Operations
from werms_api.realtime import ConnectionManager
from werms_api.risk_routing import replay_ml_route
from werms_api.scenarios import compare_scenario
from werms_api.schemas import (
    AccountRequest,
    AssignmentUpdate,
    ClosureRequest,
    ConfirmRouteRequest,
    DispatchRequest,
    FireExclusionRequest,
    FireExclusionStatus,
    HazardResponse,
    IncidentRequest,
    IncidentUpdate,
    LoginRequest,
    OperatorAccessRequest,
    ResourceRequest,
    RoutePreview,
    RouteRequest,
    RouteResponse,
    ScenarioRequest,
    ShelterResponse,
    ShelterUpdate,
    SnapshotResponse,
    SystemStatusResponse,
)
from werms_api.spatial import SpatialIndex, SpatialUnavailable
from werms_api.weather import WeatherContext


def operator_key(settings: Settings) -> str:
    configured = settings.operator_api_key
    if configured and configured.get_secret_value():
        key = configured.get_secret_value()
        if len(key) < 24:
            raise ValueError("OPERATOR_API_KEY must contain at least 24 characters.")
        return key
    if settings.app_env == "production":
        raise ValueError("Production requires an explicit OPERATOR_API_KEY and HTTPS.")
    path = Path(settings.operational_db_path).parent / "operator.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as file:
            file.write(secrets.token_urlsafe(32))
        path.chmod(0o600)
    except FileExistsError:
        pass
    key = path.read_text(encoding="utf-8").strip()
    if len(key) < 24:
        raise ValueError("The local operator key is invalid; supply OPERATOR_API_KEY explicitly.")
    return key


def create_app(settings: Settings | None = None, operations: Operations | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.model_mode != "disabled":
        raise ValueError("No validated model adapter exists; MODEL_MODE must remain disabled.")
    operations = operations or Operations(
        settings.operational_db_path,
        threshold=settings.shelter_redirect_threshold,
        validity_seconds=settings.route_validity_seconds,
    )
    key = operator_key(settings)
    if settings.spatial_database_url:
        operations.spatial = SpatialIndex(
            settings.spatial_database_url.get_secret_value(), operations.network
        )
    identity = Identity(operations)
    command = CommandDesk(operations)
    weather = WeatherContext(
        operations.network,
        enabled=settings.weather_enabled,
        api_key=settings.weather_api_key.get_secret_value() if settings.weather_api_key else None,
    )
    realtime = ConnectionManager()
    research = ResearchModels(settings.ml_report_path)
    replay_operations = None
    replay_lock = threading.Lock()
    app = FastAPI(
        title="WERMS Pilot Operations",
        version="0.6.0",
        description=(
            "Connected decision-support pilot with OpenStreetMap roads. "
            "Closures and assembly-site capacities are demonstration data. "
            "Research ML inference and PostGIS spatial constraints are available. "
            "India forecasting is unsupported. Previews do not reserve capacity."
        ),
    )
    app.state.operations = operations
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-Operator-Key", "Authorization"],
    )

    def require_operator(
        x_operator_key: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
    ):
        if x_operator_key and secrets.compare_digest(x_operator_key.encode(), key.encode()):
            return {"username": "bootstrap-admin", "role": "admin", "shelter_id": None}
        if authorization and authorization.startswith("Bearer "):
            return identity.authenticate(authorization[7:])
        raise HTTPException(
            status_code=401,
            detail={
                "code": "OPERATOR_REQUIRED",
                "message": "Valid operator access is required.",
            },
        )

    staff_dependency = Depends(require_operator)

    def require_dispatcher(user=staff_dependency):
        if user["role"] not in ("admin", "dispatcher"):
            raise OperationError("FORBIDDEN", "Dispatcher access is required.", 403)
        return user

    def require_admin(user=staff_dependency):
        if user["role"] != "admin":
            raise OperationError("FORBIDDEN", "Administrator access is required.", 403)
        return user

    def check_shelter(user, shelter_id):
        if user["role"] == "shelter" and user["shelter_id"] != shelter_id:
            raise OperationError("SHELTER_SCOPE", "You can manage only your assigned site.", 403)

    dispatch_dependency = Depends(require_dispatcher)
    admin_dependency = Depends(require_admin)

    @app.exception_handler(OperationError)
    async def operation_error(_request, error: OperationError):
        return JSONResponse(
            status_code=error.status,
            content={
                "detail": {"code": error.code, "message": error.message},
            },
        )

    @app.exception_handler(SpatialUnavailable)
    async def spatial_unavailable(_request, _error):
        return JSONResponse(
            status_code=503,
            content={
                "detail": {
                    "code": "SPATIAL_UNAVAILABLE",
                    "message": "PostGIS is unavailable; exclusion geometry was not evaluated.",
                }
            },
        )

    @app.get("/health/live", tags=["health"])
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready():
        operations.snapshot()
        return {"status": "ready", "store": "sqlite-pilot"}

    @app.get("/api/v1/network", tags=["network"])
    def network():
        return operations.network

    @app.get("/api/v1/context/weather", tags=["context"])
    def weather_context():
        return weather.snapshot()

    @app.get("/api/v1/ml/report", tags=["machine-learning"])
    def ml_report():
        return research.report()

    @app.get("/api/v1/spatial/status", tags=["spatial"])
    def spatial_status():
        return (
            operations.spatial.status()
            if operations.spatial
            else {"status": "not_configured", "engine": "PostGIS"}
        )

    @app.get("/api/v1/fire-exclusions", tags=["spatial"])
    def fire_exclusions():
        return operations.fire_exclusions()

    @app.post("/api/v1/fire-exclusions", tags=["spatial"])
    def publish_fire(request: FireExclusionRequest, user=dispatch_dependency):
        try:
            return operations.publish_fire_exclusion(
                str(request.exclusion_id), request.geometry, request.reason, user["username"]
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.put("/api/v1/fire-exclusions/{exclusion_id}", tags=["spatial"])
    def change_fire(exclusion_id: UUID, request: FireExclusionStatus, user=dispatch_dependency):
        return operations.set_fire_exclusion(str(exclusion_id), request.active, user["username"])

    @app.get("/api/v1/ml/cases/{case_id}", tags=["machine-learning"])
    def ml_case(case_id: str):
        case = research.case(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail="Held-out case was not found.")
        return case

    @app.post("/api/v1/ml/cases/{case_id}/infer", tags=["machine-learning"])
    def ml_infer(case_id: str):
        try:
            result = research.infer(case_id)
        except (RuntimeError, ValueError, ImportError, OSError) as error:
            raise HTTPException(
                status_code=503, detail="Model inference is unavailable."
            ) from error
        if result is None:
            raise HTTPException(status_code=404, detail="Held-out case was not found.")
        return result

    @app.post("/api/v1/ml/cases/{case_id}/route-preview", tags=["machine-learning"])
    def ml_route_replay(case_id: str, request: RouteRequest):
        return replay_ml_route(operations, research, case_id, request)

    @app.post("/api/v1/ml/routing/replay", tags=["machine-learning"])
    def spatial_ml_replay():
        nonlocal replay_operations
        if not settings.spatial_database_url:
            raise OperationError(
                "SPATIAL_UNAVAILABLE", "PostGIS is required for the ML replay.", 503
            )
        case = research.replay_case()
        if case is None:
            raise OperationError(
                "MODEL_REPLAY_UNAVAILABLE", "Build the supplemental replay case first.", 503
            )
        with replay_lock:
            if replay_operations is None:
                network = json.loads(
                    files("werms_api")
                    .joinpath("data/palisades-network.json")
                    .read_text(encoding="utf-8")
                )
                if network["version"] != case["road_version"]:
                    raise OperationError(
                        "ROAD_VERSION_MISMATCH", "Research replay road version differs.", 503
                    )
                network["country"] = "US"
                network["name"] = "US research replay · Pacific Palisades"
                spatial = SpatialIndex(settings.spatial_database_url.get_secret_value(), network)
                replay_operations = Operations(
                    Path(settings.operational_db_path).parent / "firecast-replay.sqlite3",
                    network=network,
                    spatial=spatial,
                )
        nearest = min(
            [
                replay_operations.nodes[preset["node"]]
                for preset in replay_operations.network["origins"]
            ],
            key=lambda n: (
                (n.point.latitude - case["latitude"]) ** 2
                + ((n.point.longitude - case["longitude"]) * 0.83) ** 2
            ),
        )
        result = replay_ml_route(
            replay_operations,
            research,
            case["id"],
            RouteRequest(origin_node_id=nearest.node_id, party_size=4),
        )
        return {
            **result,
            "network": replay_operations.network,
            "case": {
                key: case[key]
                for key in (
                    "id",
                    "latitude",
                    "longitude",
                    "reference_date",
                    "cohort",
                    "purpose",
                    "label",
                )
            },
        }

    @app.post("/api/v1/scenarios/compare", tags=["scenarios"])
    def scenario(request: ScenarioRequest):
        try:
            return compare_scenario(operations, request)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @app.get("/api/v1/snapshot", response_model=SnapshotResponse, tags=["system"])
    def snapshot():
        return operations.snapshot()

    @app.get("/api/v1/system/status", response_model=SystemStatusResponse, tags=["system"])
    def system_status():
        state = operations.snapshot()
        return SystemStatusResponse(
            environment=settings.app_env,
            data_mode=operations.network["data_mode"],
            hazard_version=state.hazard.version,
            road_version=operations.network["version"],
            websocket_clients=realtime.client_count,
        )

    @app.get("/api/v1/hazards", response_model=HazardResponse, tags=["hazards"])
    def hazards():
        return operations.snapshot().hazard

    @app.get("/api/v1/shelters", response_model=list[ShelterResponse], tags=["shelters"])
    def shelters():
        return operations.snapshot().shelters

    @app.post("/api/v1/routes/preview", response_model=list[RoutePreview], tags=["routes"])
    def preview_route(request: RouteRequest):
        return operations.preview(request)

    @app.post("/api/v1/routes", response_model=RouteResponse, status_code=201, tags=["routes"])
    def confirm_route(request: ConfirmRouteRequest):
        return operations.confirm(request)

    @app.get("/api/v1/routes/{route_id}", response_model=RouteResponse, tags=["routes"])
    @app.get("/api/v1/routes/{route_id}/status", response_model=RouteResponse, tags=["routes"])
    def get_route(route_id: UUID):
        return operations.get_route(str(route_id))

    @app.post("/api/v1/routes/{route_id}/cancel", response_model=RouteResponse, tags=["routes"])
    def cancel_route(route_id: UUID):
        return operations.cancel(str(route_id))

    @app.post(
        "/api/v1/routes/{route_id}/arrive",
        response_model=RouteResponse,
        tags=["shelters"],
    )
    def arrive(route_id: UUID, user=staff_dependency):
        return operations.arrive(
            str(route_id), actor=user["username"], shelter_id=user["shelter_id"]
        )

    @app.post("/api/v1/operator/access", tags=["operator"])
    def access(request: OperatorAccessRequest):
        require_operator(request.key)
        return {"status": "authorized"}

    @app.get("/api/v1/operator/audit", dependencies=[Depends(require_admin)], tags=["operator"])
    def audit():
        return operations.audit()

    @app.put(
        "/api/v1/roads/{edge_id}/closure",
        response_model=SnapshotResponse,
        tags=["hazards"],
    )
    async def closure(edge_id: str, request: ClosureRequest, user=dispatch_dependency):
        snapshot = await run_in_threadpool(
            operations.set_closure,
            edge_id,
            request.closed,
            request.reason,
            actor=user["username"],
        )
        # Public events contain shared state only, never private booking capability IDs.
        await realtime.broadcast({"event": "state.changed", "revision": snapshot.revision})
        return snapshot

    @app.post("/api/v1/auth/login", tags=["staff"])
    def login(request: LoginRequest, http: Request):
        return identity.login(
            request.username, request.password, http.client.host if http.client else "unknown"
        )

    @app.get("/api/v1/auth/me", tags=["staff"])
    def me(user=staff_dependency):
        return user

    @app.post("/api/v1/auth/logout", tags=["staff"])
    def logout(authorization: Annotated[str | None, Header()] = None):
        if authorization and authorization.startswith("Bearer "):
            identity.logout(authorization[7:])
        return {"status": "signed-out"}

    @app.get("/api/v1/operator/accounts", dependencies=[Depends(require_admin)], tags=["staff"])
    def accounts():
        return identity.accounts()

    @app.post("/api/v1/operator/accounts", status_code=201, tags=["staff"])
    def create_account(request: AccountRequest, user=admin_dependency):
        return identity.create(request, user["username"])

    @app.post("/api/v1/operator/accounts/{username}/disable", tags=["staff"])
    def disable_account(username: str, user=admin_dependency):
        identity.disable(username, user["username"])
        return {"status": "disabled"}

    @app.put("/api/v1/shelters/{shelter_id}", response_model=SnapshotResponse, tags=["shelters"])
    async def update_shelter(shelter_id: str, request: ShelterUpdate, user=staff_dependency):
        check_shelter(user, shelter_id)
        snapshot = await run_in_threadpool(
            operations.update_shelter, shelter_id, request, user["username"]
        )
        await realtime.broadcast({"event": "state.changed", "revision": snapshot.revision})
        return snapshot

    @app.get("/api/v1/command", dependencies=[Depends(require_operator)], tags=["command"])
    def command_state():
        return command.snapshot()

    @app.post("/api/v1/incidents", status_code=201, tags=["command"])
    def report_incident(request: IncidentRequest, user=dispatch_dependency):
        return command.report(request, user["username"])

    @app.put("/api/v1/incidents/{incident_id}", tags=["command"])
    def update_incident(incident_id: UUID, request: IncidentUpdate, user=dispatch_dependency):
        return command.update_incident(str(incident_id), request, user["username"])

    @app.post("/api/v1/resources", status_code=201, tags=["command"])
    def register_resource(request: ResourceRequest, user=dispatch_dependency):
        return command.register(request, user["username"])

    @app.put("/api/v1/resources/{resource_id}/availability", tags=["command"])
    def resource_availability(resource_id: UUID, offline: bool, user=dispatch_dependency):
        command.availability(str(resource_id), offline, user["username"])
        return {"status": "offline" if offline else "available"}

    @app.post("/api/v1/assignments", status_code=201, tags=["command"])
    def dispatch(request: DispatchRequest, user=dispatch_dependency):
        return command.dispatch(request, user["username"])

    @app.put("/api/v1/assignments/{assignment_id}", tags=["command"])
    def update_assignment(assignment_id: UUID, request: AssignmentUpdate, user=dispatch_dependency):
        command.update_assignment(str(assignment_id), request, user["username"])
        return {"status": request.status}

    @app.websocket("/ws/events")
    async def events(websocket: WebSocket):
        if websocket.headers.get("origin") != settings.web_origin:
            await websocket.close(code=1008)
            return
        await realtime.connect(websocket)
        try:
            snapshot = await run_in_threadpool(operations.snapshot)
            await websocket.send_json({"event": "connected", "revision": snapshot.revision})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            realtime.disconnect(websocket)

    return app


app = create_app()

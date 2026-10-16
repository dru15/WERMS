from __future__ import annotations

import secrets
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
from werms_api.operations import OperationError, Operations
from werms_api.realtime import ConnectionManager
from werms_api.schemas import (
    AccountRequest,
    AssignmentUpdate,
    ClosureRequest,
    ConfirmRouteRequest,
    DispatchRequest,
    HazardResponse,
    IncidentRequest,
    IncidentUpdate,
    LoginRequest,
    OperatorAccessRequest,
    ResourceRequest,
    RoutePreview,
    RouteRequest,
    RouteResponse,
    ShelterResponse,
    ShelterUpdate,
    SnapshotResponse,
    SystemStatusResponse,
)


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
    identity = Identity(operations)
    command = CommandDesk(operations)
    realtime = ConnectionManager()
    app = FastAPI(
        title="WERMS Pilot Operations",
        version="0.4.0",
        description=(
            "Connected decision-support pilot with OpenStreetMap roads. "
            "Closures and assembly-site capacities are demonstration data. "
            "ML is disabled. Previews do not reserve shelter capacity."
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

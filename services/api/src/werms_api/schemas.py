from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class Coordinate(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class RouteRequest(BaseModel):
    origin: Coordinate | None = None
    origin_node_id: str | None = Field(default=None, max_length=100)
    shelter_id: str | None = Field(default=None, max_length=100)
    party_size: int = Field(default=1, ge=1, le=20)
    traffic: bool = True

    @model_validator(mode="after")
    def require_origin(self):
        if (self.origin is None) == (self.origin_node_id is None):
            raise ValueError("Provide exactly one origin coordinate or origin_node_id.")
        return self


class ConfirmRouteRequest(RouteRequest):
    request_id: UUID
    replace_route_id: UUID | None = None


class ScenarioRequest(RouteRequest):
    blocked_edge_ids: list[str] = Field(default_factory=list, max_length=25)
    unavailable_shelter_ids: list[str] = Field(default_factory=list, max_length=10)
    fire_polygon: dict | None = None


class FireExclusionRequest(BaseModel):
    exclusion_id: UUID
    geometry: dict
    reason: str = Field(min_length=3, max_length=300)


class FireExclusionStatus(BaseModel):
    active: bool


class RoutePoint(Coordinate):
    node_id: str


class ShelterResponse(BaseModel):
    shelter_id: str
    node_id: str
    name: str
    location: Coordinate
    capacity: int
    occupancy: int
    reserved_demand: int
    utilization: float
    status: str
    updated_at: datetime


class RoutePreview(BaseModel):
    shelter: ShelterResponse
    path: list[RoutePoint]
    edge_ids: list[str]
    distance_km: float
    estimated_minutes: float
    risk_score: float
    hazard_version: str
    road_version: str
    model_version: str | None = None
    model_mode: Literal["disabled"] = "disabled"
    hazard_source_timestamp: datetime
    created_at: datetime
    valid_until: datetime
    reason_codes: list[str]


class RouteResponse(RoutePreview):
    route_id: str
    status: Literal["valid", "invalid", "expired", "cancelled", "arrived"]
    cause: str | None = None
    party_size: int


class ClosureRequest(BaseModel):
    closed: bool
    reason: str = Field(min_length=3, max_length=300)


class HazardResponse(BaseModel):
    version: str
    source_timestamp: datetime
    blocked_edge_ids: list[str]
    model_version: str | None = None
    model_mode: Literal["disabled"] = "disabled"


class SnapshotResponse(BaseModel):
    hazard: HazardResponse
    shelters: list[ShelterResponse]
    revision: int


class SystemStatusResponse(BaseModel):
    service: Literal["werms-api"] = "werms-api"
    environment: str
    operational_store: Literal["sqlite-pilot"] = "sqlite-pilot"
    data_mode: Literal["fictional-pilot", "osm-pilot"]
    model_mode: Literal["disabled"] = "disabled"
    hazard_version: str
    road_version: str
    websocket_clients: int


class OperatorAccessRequest(BaseModel):
    key: str = Field(min_length=1, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=256)


class AccountRequest(LoginRequest):
    password: str = Field(min_length=12, max_length=256)
    role: Literal["admin", "dispatcher", "shelter"]
    shelter_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def scope(self):
        if (self.role == "shelter") != (self.shelter_id is not None):
            raise ValueError("Only shelter staff must have a shelter_id.")
        return self


class ShelterUpdate(BaseModel):
    occupancy: int = Field(ge=0, le=100000)
    status: Literal["open", "restricted", "closed"]
    expected_updated_at: datetime
    reason: str = Field(min_length=3, max_length=300)


class IncidentRequest(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=3, max_length=2000)
    source: str = Field(min_length=3, max_length=200)
    observed_at: datetime
    priority: Literal["low", "medium", "high", "critical"]
    road_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def time_zone(self):
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must include a timezone.")
        return self


class IncidentUpdate(BaseModel):
    version: int = Field(ge=1)
    status: Literal["reported", "acknowledged", "resolved"]
    priority: Literal["low", "medium", "high", "critical"]
    note: str = Field(min_length=3, max_length=300)


class ResourceRequest(BaseModel):
    name: str = Field(min_length=3, max_length=100)
    kind: Literal["engine", "bus", "ambulance", "supply_team"]


class DispatchRequest(BaseModel):
    request_id: UUID
    resource_id: UUID
    incident_id: UUID
    note: str = Field(min_length=3, max_length=300)


class AssignmentUpdate(BaseModel):
    status: Literal["acknowledged", "resolved", "cancelled"]
    note: str = Field(min_length=3, max_length=300)

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Coordinate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RouteRequest(BaseModel):
    origin: Coordinate
    party_size: int = Field(default=1, ge=1, le=20)


class RoutePoint(Coordinate):
    node_id: str


class ShelterResponse(BaseModel):
    shelter_id: str
    name: str
    location: Coordinate
    capacity: int
    occupancy: int
    reserved_demand: int
    utilization: float
    status: str
    updated_at: datetime


class RouteResponse(BaseModel):
    route_id: str
    status: Literal["valid"] = "valid"
    shelter: ShelterResponse
    path: list[RoutePoint]
    edge_ids: list[str]
    distance_km: float
    estimated_minutes: float
    risk_score: float
    hazard_version: str
    road_version: str
    model_version: str | None
    model_mode: Literal["disabled", "approved"]
    hazard_source_timestamp: datetime
    created_at: datetime
    valid_until: datetime
    reason_codes: list[str]


class RouteStatusResponse(BaseModel):
    route_id: str
    status: Literal["valid", "invalid"]
    cause: str | None = None
    hazard_version: str


class HazardResponse(BaseModel):
    version: str
    source_timestamp: datetime
    blocked_edge_ids: list[str]
    model_version: str | None
    model_mode: Literal["disabled", "approved"]


class SystemStatusResponse(BaseModel):
    service: Literal["werms-api"] = "werms-api"
    environment: str
    operational_store: Literal["in-memory-demo"] = "in-memory-demo"
    model_mode: Literal["disabled", "approved"]
    hazard_version: str
    road_version: str
    websocket_clients: int


class ScenarioAdvanceResponse(BaseModel):
    event: Literal["hazard.updated"] = "hazard.updated"
    hazard_version: str
    newly_blocked_edge_id: str
    invalidated_route_ids: list[str]


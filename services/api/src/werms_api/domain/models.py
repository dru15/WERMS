from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class ShelterStatus(StrEnum):
    OPEN = "open"
    RESTRICTED = "restricted"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class Point:
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class RoadNode:
    node_id: str
    point: Point


@dataclass(frozen=True, slots=True)
class RoadEdge:
    edge_id: str
    source: str
    target: str
    distance_km: float
    travel_minutes: float
    live_risk: float = 0.0
    predictive_risk: float = 0.0
    congestion: float = 0.0
    hard_blocked: bool = False


@dataclass(slots=True)
class Shelter:
    shelter_id: str
    name: str
    node_id: str
    point: Point
    capacity: int
    occupancy: int
    reserved_demand: int = 0
    status: ShelterStatus = ShelterStatus.OPEN
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def utilization(self) -> float:
        return (self.occupancy + self.reserved_demand) / self.capacity

    @property
    def free_capacity(self) -> int:
        return max(0, self.capacity - self.occupancy - self.reserved_demand)


@dataclass(frozen=True, slots=True)
class HazardState:
    version: str
    source_timestamp: datetime
    blocked_edge_ids: frozenset[str]
    model_version: str | None = None


@dataclass(frozen=True, slots=True)
class CostWeights:
    live_hazard: float = 8.0
    predictive_risk: float = 3.0
    congestion: float = 2.0
    data_age: float = 1.0


@dataclass(frozen=True, slots=True)
class RoutePlan:
    shelter_id: str
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    distance_km: float
    estimated_minutes: float
    risk_score: float
    total_cost: float
    reason_codes: tuple[str, ...]


class NoSafeRouteError(RuntimeError):
    """Raised when every shelter candidate violates current constraints."""


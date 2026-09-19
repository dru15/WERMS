from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from werms_api.domain.models import HazardState, Point, RoadEdge, RoadNode, Shelter


@dataclass(slots=True)
class SavedRoute:
    route_id: str
    edge_ids: tuple[str, ...]
    hazard_version: str
    valid: bool = True
    invalidation_cause: str | None = None


class DemoStore:
    """Replaceable operational adapter used for the first runnable milestone."""

    def __init__(self) -> None:
        self.nodes = {
            "n0": RoadNode("n0", Point(34.0522, -118.2437)),
            "n1": RoadNode("n1", Point(34.0610, -118.2300)),
            "n2": RoadNode("n2", Point(34.0700, -118.2160)),
            "n3": RoadNode("n3", Point(34.0450, -118.2200)),
            "n4": RoadNode("n4", Point(34.0800, -118.2000)),
            "n5": RoadNode("n5", Point(34.0380, -118.1950)),
            "n6": RoadNode("n6", Point(34.0600, -118.1800)),
        }
        self.edges = (
            RoadEdge("e01", "n0", "n1", 1.7, 3.2, live_risk=0.10),
            RoadEdge("e10", "n1", "n0", 1.7, 3.2, live_risk=0.10),
            RoadEdge("e12", "n1", "n2", 1.6, 2.9),
            RoadEdge("e21", "n2", "n1", 1.6, 2.9),
            RoadEdge("e24", "n2", "n4", 1.7, 3.1),
            RoadEdge("e42", "n4", "n2", 1.7, 3.1),
            RoadEdge("e03", "n0", "n3", 2.2, 3.8, congestion=0.10),
            RoadEdge("e30", "n3", "n0", 2.2, 3.8, congestion=0.10),
            RoadEdge("e35", "n3", "n5", 2.5, 4.1, live_risk=0.05),
            RoadEdge("e53", "n5", "n3", 2.5, 4.1, live_risk=0.05),
            RoadEdge("e56", "n5", "n6", 2.0, 3.5),
            RoadEdge("e65", "n6", "n5", 2.0, 3.5),
            RoadEdge("e26", "n2", "n6", 2.4, 4.3, congestion=0.15),
            RoadEdge("e62", "n6", "n2", 2.4, 4.3, congestion=0.15),
        )
        self.shelters = {
            "s-north": Shelter(
                "s-north", "North Ridge Shelter", "n4", self.nodes["n4"].point, 120, 54
            ),
            "s-east": Shelter(
                "s-east", "East Valley Shelter", "n6", self.nodes["n6"].point, 90, 69
            ),
        }
        self.hazard = HazardState(
            version="hazard-001",
            source_timestamp=datetime.now(UTC),
            blocked_edge_ids=frozenset(),
            model_version=None,
        )
        self.road_version = "roads-demo-001"
        self.routes: dict[str, SavedRoute] = {}
        self._lock = asyncio.Lock()
        self._scenario_edges = ("e12", "e35", "e24", "e56")
        self._scenario_index = 0

    def nearest_node_id(self, latitude: float, longitude: float) -> str:
        return min(
            self.nodes.values(),
            key=lambda node: (node.point.latitude - latitude) ** 2
            + (node.point.longitude - longitude) ** 2,
        ).node_id

    async def reserve_shelter(self, shelter_id: str, party_size: int, threshold: float) -> Shelter:
        async with self._lock:
            shelter = self.shelters[shelter_id]
            projected = shelter.occupancy + shelter.reserved_demand + party_size
            if projected > shelter.capacity or projected / shelter.capacity >= threshold:
                raise ValueError("Shelter capacity changed before reservation completed.")
            shelter.reserved_demand += party_size
            shelter.updated_at = datetime.now(UTC)
            return shelter

    async def save_route(self, route: SavedRoute) -> None:
        async with self._lock:
            self.routes[route.route_id] = route

    async def advance_hazard(self) -> tuple[str, list[str]]:
        async with self._lock:
            edge_id = self._scenario_edges[self._scenario_index % len(self._scenario_edges)]
            self._scenario_index += 1
            blocked = set(self.hazard.blocked_edge_ids)
            blocked.add(edge_id)
            version_number = int(self.hazard.version.rsplit("-", 1)[1]) + 1
            self.hazard = HazardState(
                version=f"hazard-{version_number:03d}",
                source_timestamp=datetime.now(UTC),
                blocked_edge_ids=frozenset(blocked),
                model_version=self.hazard.model_version,
            )
            invalidated = []
            for route in self.routes.values():
                if route.valid and edge_id in route.edge_ids:
                    route.valid = False
                    route.invalidation_cause = "HARD_HAZARD_INTERSECTION"
                    invalidated.append(route.route_id)
            return edge_id, invalidated

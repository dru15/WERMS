from __future__ import annotations

import heapq
import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime

from werms_api.domain.models import (
    CostWeights,
    HazardState,
    NoSafeRouteError,
    RoadEdge,
    RoadNode,
    RoutePlan,
    Shelter,
    ShelterStatus,
)


def _distance_km(a: RoadNode, b: RoadNode) -> float:
    lat_scale = 111.32
    mean_latitude = math.radians((a.point.latitude + b.point.latitude) / 2)
    lon_scale = 111.32 * math.cos(mean_latitude)
    latitude_delta = (a.point.latitude - b.point.latitude) * lat_scale
    longitude_delta = (a.point.longitude - b.point.longitude) * lon_scale
    return math.hypot(latitude_delta, longitude_delta)


def _edge_cost(
    edge: RoadEdge,
    *,
    hard_blocked: bool,
    data_age_minutes: float,
    weights: CostWeights,
) -> float:
    if hard_blocked or edge.hard_blocked:
        return math.inf
    bounded_age = min(max(data_age_minutes / 30.0, 0.0), 1.0)
    return (
        edge.travel_minutes
        + weights.live_hazard * edge.live_risk
        + weights.predictive_risk * edge.predictive_risk
        + weights.congestion * edge.congestion
        + weights.data_age * bounded_age
    )


def _astar(
    *,
    origin_node_id: str,
    destination_node_id: str,
    nodes: dict[str, RoadNode],
    edges: Iterable[RoadEdge],
    hazard: HazardState,
    now: datetime,
    weights: CostWeights,
) -> tuple[tuple[str, ...], tuple[RoadEdge, ...], float] | None:
    adjacency: dict[str, list[RoadEdge]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.source].append(edge)

    data_age_minutes = max(0.0, (now - hazard.source_timestamp).total_seconds() / 60.0)
    queue: list[tuple[float, float, str]] = [(0.0, 0.0, origin_node_id)]
    came_from: dict[str, tuple[str, RoadEdge]] = {}
    best_cost = {origin_node_id: 0.0}

    while queue:
        _, current_cost, current = heapq.heappop(queue)
        if current == destination_node_id:
            break
        if current_cost > best_cost.get(current, math.inf):
            continue

        for edge in adjacency[current]:
            cost = _edge_cost(
                edge,
                hard_blocked=edge.edge_id in hazard.blocked_edge_ids,
                data_age_minutes=data_age_minutes,
                weights=weights,
            )
            if math.isinf(cost):
                continue
            candidate_cost = current_cost + cost
            if candidate_cost >= best_cost.get(edge.target, math.inf):
                continue
            best_cost[edge.target] = candidate_cost
            came_from[edge.target] = (current, edge)
            heuristic = _distance_km(nodes[edge.target], nodes[destination_node_id])
            heapq.heappush(queue, (candidate_cost + heuristic, candidate_cost, edge.target))

    if destination_node_id not in best_cost:
        return None

    node_path = [destination_node_id]
    edge_path: list[RoadEdge] = []
    cursor = destination_node_id
    while cursor != origin_node_id:
        previous, edge = came_from[cursor]
        node_path.append(previous)
        edge_path.append(edge)
        cursor = previous
    node_path.reverse()
    edge_path.reverse()
    return tuple(node_path), tuple(edge_path), best_cost[destination_node_id]


def calculate_safe_route(
    *,
    origin_node_id: str,
    nodes: dict[str, RoadNode],
    edges: Iterable[RoadEdge],
    shelters: Iterable[Shelter],
    hazard: HazardState,
    redirect_threshold: float,
    now: datetime | None = None,
    weights: CostWeights | None = None,
) -> RoutePlan:
    now = now or datetime.now(UTC)
    weights = weights or CostWeights()
    candidates: list[RoutePlan] = []

    for shelter in shelters:
        if (
            shelter.status is not ShelterStatus.OPEN
            or shelter.free_capacity <= 0
            or shelter.utilization >= redirect_threshold
        ):
            continue
        result = _astar(
            origin_node_id=origin_node_id,
            destination_node_id=shelter.node_id,
            nodes=nodes,
            edges=edges,
            hazard=hazard,
            now=now,
            weights=weights,
        )
        if result is None:
            continue
        node_ids, path_edges, route_cost = result
        distance = sum(edge.distance_km for edge in path_edges)
        estimated_minutes = sum(edge.travel_minutes for edge in path_edges)
        risk_score = sum(
            edge.live_risk + edge.predictive_risk for edge in path_edges
        ) / max(len(path_edges), 1)
        shelter_penalty = 3.0 * shelter.utilization + 0.5 * shelter.reserved_demand
        reason_codes = ["HARD_HAZARDS_EXCLUDED", "CAPACITY_QUALIFIED_SHELTER"]
        if any(edge.live_risk > 0 for edge in path_edges):
            reason_codes.append("LIVE_RISK_PENALTY_APPLIED")
        if any(edge.predictive_risk > 0 for edge in path_edges):
            reason_codes.append("SOFT_RISK_PENALTY_APPLIED")
        candidates.append(
            RoutePlan(
                shelter_id=shelter.shelter_id,
                node_ids=node_ids,
                edge_ids=tuple(edge.edge_id for edge in path_edges),
                distance_km=distance,
                estimated_minutes=estimated_minutes,
                risk_score=risk_score,
                total_cost=route_cost + shelter_penalty,
                reason_codes=tuple(reason_codes),
            )
        )

    if not candidates:
        raise NoSafeRouteError("No capacity-qualified shelter has a safe route.")
    return min(candidates, key=lambda route: route.total_cost)

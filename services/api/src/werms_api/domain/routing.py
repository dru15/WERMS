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
    Point,
    RoadEdge,
    RoadNode,
    RoutePlan,
    Shelter,
    ShelterStatus,
)


def _distance_km(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat, dlon = lat2 - lat1, math.radians(b.longitude - a.longitude)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, h))))


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
        + weights.live_hazard * edge.live_risk * edge.distance_km
        + weights.predictive_risk * edge.predictive_risk * edge.distance_km
        + weights.congestion * edge.congestion
        + weights.data_age * bounded_age * edge.distance_km
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
    turn_restrictions: tuple[dict, ...] = (),
) -> tuple[tuple[str, ...], tuple[RoadEdge, ...], float] | None:
    adjacency: dict[str, list[RoadEdge]] = defaultdict(list)
    # Every traversable edge must cost at least this many minutes per straight-line
    # kilometre. The triangle inequality makes the resulting heuristic consistent,
    # including on imported graphs with unusual speed estimates or turn restrictions.
    lower_bound = math.inf
    for edge in edges:
        adjacency[edge.source].append(edge)
        distance = _distance_km(nodes[edge.source].point, nodes[edge.target].point)
        cost = _edge_cost(
            edge,
            hard_blocked=edge.edge_id in hazard.blocked_edge_ids,
            data_age_minutes=max(0.0, (now - hazard.source_timestamp).total_seconds() / 60),
            weights=weights,
        )
        if math.isnan(cost) or cost < 0:
            raise ValueError("A* requires non-negative, non-NaN edge costs.")
        if distance > 0 and math.isfinite(cost):
            lower_bound = min(lower_bound, cost / distance)
    if not math.isfinite(lower_bound):
        lower_bound = 0.0

    def heuristic(node_id: str) -> float:
        return lower_bound * _distance_km(nodes[node_id].point, nodes[destination_node_id].point)

    rules: dict[str, list[dict]] = defaultdict(list)
    for rule in turn_restrictions:
        rules[rule["via"]].append(rule)
    way_by_edge = {edge.edge_id: edge.way_id for group in adjacency.values() for edge in group}
    data_age_minutes = max(0.0, (now - hazard.source_timestamp).total_seconds() / 60.0)
    start = (origin_node_id, "")
    queue: list[tuple[float, float, str, str]] = [(heuristic(origin_node_id), 0.0, *start)]
    came_from: dict[tuple[str, str], tuple[tuple[str, str], RoadEdge]] = {}
    best_cost = {start: 0.0}
    destination = None

    while queue:
        _, current_cost, current, incoming_edge = heapq.heappop(queue)
        state = (current, incoming_edge)
        if current_cost > best_cost.get(state, math.inf):
            continue
        if current == destination_node_id:
            destination = state
            break

        for edge in adjacency[current]:
            forbidden = False
            for rule in rules[current]:
                if way_by_edge.get(incoming_edge) != rule["from_way"]:
                    continue
                restriction = rule["restriction"]
                to_way_matches = edge.way_id == rule["to_way"]
                if restriction in {"no_u_turn", "only_u_turn"}:
                    to_way_matches = to_way_matches and edge.edge_id == incoming_edge
                elif (
                    restriction == "no_straight_on"
                    and rule["from_way"] == rule["to_way"]
                    or restriction == "only_straight_on"
                    and rule["from_way"] == rule["to_way"]
                ):
                    to_way_matches = to_way_matches and edge.edge_id != incoming_edge
                if (restriction.startswith("no_") and to_way_matches) or (
                    restriction.startswith("only_") and not to_way_matches
                ):
                    forbidden = True
                    break
            if forbidden:
                continue
            cost = _edge_cost(
                edge,
                hard_blocked=edge.edge_id in hazard.blocked_edge_ids,
                data_age_minutes=data_age_minutes,
                weights=weights,
            )
            if math.isinf(cost):
                continue
            candidate_cost = current_cost + cost
            next_state = (edge.target, edge.edge_id)
            if candidate_cost >= best_cost.get(next_state, math.inf):
                continue
            best_cost[next_state] = candidate_cost
            came_from[next_state] = (state, edge)
            heapq.heappush(
                queue, (candidate_cost + heuristic(edge.target), candidate_cost, *next_state)
            )

    if destination is None:
        return None

    node_path = [destination_node_id]
    edge_path: list[RoadEdge] = []
    cursor = destination
    while cursor != start:
        previous, edge = came_from[cursor]
        node_path.append(previous[0])
        edge_path.append(edge)
        cursor = previous
    node_path.reverse()
    edge_path.reverse()
    return tuple(node_path), tuple(edge_path), best_cost[destination]


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
    party_size: int = 1,
    turn_restrictions: tuple[dict, ...] = (),
) -> RoutePlan:
    now = now or datetime.now(UTC)
    weights = weights or CostWeights()
    edges = tuple(edges)
    candidates: list[RoutePlan] = []

    for shelter in shelters:
        if (
            shelter.status is not ShelterStatus.OPEN
            or shelter.free_capacity < party_size
            or (shelter.occupancy + shelter.reserved_demand + party_size) / shelter.capacity
            > redirect_threshold
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
            turn_restrictions=turn_restrictions,
        )
        if result is None:
            continue
        node_ids, path_edges, route_cost = result
        distance = sum(edge.distance_km for edge in path_edges)
        estimated_minutes = sum(edge.travel_minutes for edge in path_edges)
        risk_score = sum(edge.live_risk + edge.predictive_risk for edge in path_edges) / max(
            len(path_edges), 1
        )
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

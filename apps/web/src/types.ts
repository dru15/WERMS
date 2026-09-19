export type Coordinate = {
  latitude: number;
  longitude: number;
};

export type RoutePoint = Coordinate & {
  node_id: string;
};

export type Shelter = {
  shelter_id: string;
  name: string;
  location: Coordinate;
  capacity: number;
  occupancy: number;
  reserved_demand: number;
  utilization: number;
  status: string;
  updated_at: string;
};

export type Route = {
  route_id: string;
  status: "valid";
  shelter: Shelter;
  path: RoutePoint[];
  edge_ids: string[];
  distance_km: number;
  estimated_minutes: number;
  risk_score: number;
  hazard_version: string;
  road_version: string;
  model_version: string | null;
  model_mode: "disabled" | "approved";
  hazard_source_timestamp: string;
  created_at: string;
  valid_until: string;
  reason_codes: string[];
};

export type Hazard = {
  version: string;
  source_timestamp: string;
  blocked_edge_ids: string[];
  model_version: string | null;
  model_mode: "disabled" | "approved";
};

export type SystemStatus = {
  service: "werms-api";
  environment: string;
  operational_store: string;
  model_mode: "disabled" | "approved";
  hazard_version: string;
  road_version: string;
  websocket_clients: number;
};

export type HazardEvent = {
  event: "hazard.updated" | "connected";
  hazard_version: string;
  newly_blocked_edge_id?: string;
  invalidated_route_ids?: string[];
};


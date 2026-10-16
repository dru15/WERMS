export type Coordinate = { latitude: number; longitude: number };
export type RoutePoint = Coordinate & { node_id: string };
export type Shelter = {
  shelter_id: string; node_id: string; name: string; location: Coordinate;
  capacity: number; occupancy: number; reserved_demand: number;
  utilization: number; status: "open" | "restricted" | "closed"; updated_at: string;
};
export type RoutePreview = {
  shelter: Shelter; path: RoutePoint[]; edge_ids: string[];
  distance_km: number; estimated_minutes: number; risk_score: number;
  hazard_version: string; road_version: string;
  model_version: null; model_mode: "disabled";
  hazard_source_timestamp: string; created_at: string; valid_until: string;
  reason_codes: string[];
};
export type Route = RoutePreview & {
  route_id: string; status: "valid" | "invalid" | "expired" | "cancelled" | "arrived";
  cause: string | null; party_size: number;
};
export type Hazard = {
  version: string; source_timestamp: string; blocked_edge_ids: string[];
  model_version: null; model_mode: "disabled";
};
export type Snapshot = { hazard: Hazard; shelters: Shelter[]; revision: number };
export type RouteInput = {
  origin_node_id: string; party_size: number; traffic: boolean; shelter_id?: string;
};

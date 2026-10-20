import { request } from "./api";
import type { RouteInput, RoutePreview } from "./types";

export type Weather = { status: "current" | "stale" | "unavailable" | "disabled"; provider: string; source_url: string;
  message: string | null; data: null | { temperature_c: number; humidity_pct: number; wind_kph: number;
    wind_direction_degrees: number; precipitation_mm: number; valid_at: string; retrieved_at: string; interval_seconds: number } };
export type FirePolygon = { type: "Polygon"; coordinates: number[][][] };
export type ScenarioInput = RouteInput & { blocked_edge_ids: string[]; unavailable_shelter_ids: string[]; fire_polygon?: FirePolygon };
export type ScenarioResult = { mode: "what-if-only"; changes_operational_state: false; road_version: string; snapshot_revision: number;
  created_at: string; inputs: ScenarioInput; baseline: RoutePreview[]; simulated: RoutePreview[];
  outcome: "no_baseline_route" | "no_route" | "rerouted" | "unchanged"; delta_minutes: number | null; delta_km: number | null;
  destination_changed: boolean; reachable_before: number; reachable_after: number; compute_ms: number;
  fire_intersections?: string[]; spatial_engine?: string | null };
export const contextApi = {
  weather: () => request<Weather>("/api/v1/context/weather"),
  scenario: (input: ScenarioInput) => request<ScenarioResult>("/api/v1/scenarios/compare", { method: "POST", body: JSON.stringify(input) }),
};
export function indiaTime(value: string) {
  return new Intl.DateTimeFormat("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true, timeZone: "Asia/Kolkata" }).format(new Date(value));
}

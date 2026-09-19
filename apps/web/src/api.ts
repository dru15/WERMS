import type { Hazard, Route, Shelter, SystemStatus } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = payload.detail?.message ?? payload.detail ?? "Request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json() as Promise<T>;
}

export const api = {
  getStatus: () => request<SystemStatus>("/api/v1/system/status"),
  getHazard: () => request<Hazard>("/api/v1/hazards"),
  getShelters: () => request<Shelter[]>("/api/v1/shelters"),
  createRoute: (latitude: number, longitude: number, partySize: number) =>
    request<Route>("/api/v1/routes", {
      method: "POST",
      body: JSON.stringify({
        origin: { latitude, longitude },
        party_size: partySize,
      }),
    }),
  advanceScenario: () =>
    request<{ hazard_version: string; invalidated_route_ids: string[] }>(
      "/api/v1/demo/scenario/advance",
      { method: "POST" },
    ),
};


import { request, staffHeaders } from "./api";

export type StaffUser = { username: string; role: "admin" | "dispatcher" | "shelter"; shelter_id: string | null; enabled?: number };
export type Incident = { id: string; title: string; description: string; source: string; observed_at: string;
  priority: "low" | "medium" | "high" | "critical"; road_id: string | null; status: "reported" | "acknowledged" | "resolved"; version: number; updated_at: string };
export type Resource = { id: string; name: string; kind: "engine" | "bus" | "ambulance" | "supply_team"; status: "available" | "deployed" | "offline" };
export type Assignment = { id: string; resource_id: string; incident_id: string; status: "dispatched" | "acknowledged" | "resolved" | "cancelled"; note: string; updated_at: string };
export type CommandState = { incidents: Incident[]; resources: Resource[]; assignments: Assignment[] };
export type Audit = { sequence: number; actor: string; action: string; entity_id: string; timestamp: string; details: string };

function call<T>(path: string, key: string, method = "GET", body?: unknown) {
  return request<T>(`/api/v1/${path}`, { method, headers: staffHeaders(key), body: body === undefined ? undefined : JSON.stringify(body) });
}
export const staffApi = {
  login: (username: string, password: string) => request<{ token: string; user: StaffUser; expires_at: string }>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: (key: string) => call("auth/logout", key, "POST"),
  state: (key: string) => call<CommandState>("command", key),
  accounts: (key: string) => call<StaffUser[]>("operator/accounts", key),
  account: (key: string, body: { username: string; password: string; role: StaffUser["role"]; shelter_id: string | null }) => call("operator/accounts", key, "POST", body),
  disable: (key: string, username: string) => call(`operator/accounts/${encodeURIComponent(username)}/disable`, key, "POST"),
  audit: (key: string) => call<Audit[]>("operator/audit", key),
  report: (key: string, body: Omit<Incident, "id" | "status" | "version" | "updated_at">) => call("incidents", key, "POST", body),
  incident: (key: string, incident: Incident, status: Incident["status"], priority: Incident["priority"], note: string) => call(`incidents/${incident.id}`, key, "PUT", { version: incident.version, status, priority, note }),
  resource: (key: string, name: string, kind: Resource["kind"]) => call("resources", key, "POST", { name, kind }),
  availability: (key: string, id: string, offline: boolean) => call(`resources/${id}/availability?offline=${offline}`, key, "PUT"),
  dispatch: (key: string, resource_id: string, incident_id: string, note: string, request_id: string) => call("assignments", key, "POST", { resource_id, incident_id, note, request_id }),
  assignment: (key: string, id: string, status: Assignment["status"], note: string) => call(`assignments/${id}`, key, "PUT", { status, note }),
  shelter: (key: string, id: string, occupancy: number, status: string, expected_updated_at: string, reason: string) => call(`shelters/${encodeURIComponent(id)}`, key, "PUT", { occupancy, status, expected_updated_at, reason }),
};

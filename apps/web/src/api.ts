import type { Network } from "./network";
import type { Route, RouteInput, RoutePreview, Snapshot } from "./types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const WS_URL = import.meta.env.VITE_WS_URL ?? API_URL.replace(/^http/, "ws");

export class ApiError extends Error {
  constructor(message: string, public code: string, public status: number) { super(message); }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init, signal: AbortSignal.timeout(15000),
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("Cannot reach the operations service. Check your connection and retry.", "OFFLINE", 0);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(
      payload.detail?.message ?? (typeof payload.detail === "string" ? payload.detail : "Request was not accepted."),
      payload.detail?.code ?? "REQUEST_FAILED", response.status,
    );
  }
  return response.json() as Promise<T>;
}

export function staffHeaders(credential: string): Record<string, string> {
  return credential.startsWith("session:")
    ? { Authorization: `Bearer ${credential.slice(8)}` }
    : { "X-Operator-Key": credential };
}

export const api = {
  network: () => request<Network>("/api/v1/network"),
  snapshot: () => request<Snapshot>("/api/v1/snapshot"),
  preview: (input: RouteInput) => request<RoutePreview[]>("/api/v1/routes/preview", {
    method: "POST", body: JSON.stringify(input),
  }),
  confirm: (input: RouteInput, requestId: string, replaceRouteId?: string) => request<Route>("/api/v1/routes", {
    method: "POST", body: JSON.stringify({ ...input, request_id: requestId, replace_route_id: replaceRouteId }),
  }),
  route: (id: string) => request<Route>(`/api/v1/routes/${encodeURIComponent(id)}`),
  cancel: (id: string) => request<Route>(`/api/v1/routes/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  arrive: (id: string, key: string) => request<Route>(`/api/v1/routes/${encodeURIComponent(id)}/arrive`, {
    method: "POST", headers: staffHeaders(key),
  }),
  access: (key: string) => request<{ status: string }>("/api/v1/operator/access", {
    method: "POST", body: JSON.stringify({ key }),
  }),
  closure: (id: string, closed: boolean, key: string) => request<Snapshot>(`/api/v1/roads/${encodeURIComponent(id)}/closure`, {
    method: "PUT", headers: staffHeaders(key),
    body: JSON.stringify({ closed, reason: closed ? "Pilot operator confirmed road closure" : "Pilot operator reopened road" }),
  }),
};

export function subscribe(onUpdate: () => void) {
  let socket: WebSocket | undefined;
  let retry: ReturnType<typeof setTimeout> | undefined;
  let stopped = false;
  function connect() {
    if (stopped || typeof WebSocket === "undefined") return;
    socket = new WebSocket(`${WS_URL}/ws/events`);
    socket.onmessage = onUpdate;
    socket.onclose = () => { if (!stopped) retry = setTimeout(connect, 3000); };
    socket.onerror = () => socket?.close();
  }
  connect();
  return () => { stopped = true; clearTimeout(retry); socket?.close(); };
}

import type { RouteInput } from "./types";

export type PendingConfirmation = {
  input: RouteInput; requestId: string; replaceRouteId?: string; fingerprint: string;
};
const KEY = "werms.pending-confirmation.v1";

export function readPending(): PendingConfirmation | undefined {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? "null");
    return value && typeof value.requestId === "string" && typeof value.fingerprint === "string"
      && value.input && typeof value.input.origin_node_id === "string"
      && Number.isInteger(value.input.party_size) ? value : undefined;
  } catch { return undefined; }
}

export function savePending(value: PendingConfirmation) {
  // Persist the idempotency key before sending, so a reload after a lost response
  // recovers the original confirmation instead of creating a second reservation.
  localStorage.setItem(KEY, JSON.stringify(value));
}

export function clearPending(requestId: string) {
  if (readPending()?.requestId === requestId) localStorage.removeItem(KEY);
}

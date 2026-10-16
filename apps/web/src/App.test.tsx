import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "./api";
import App from "./App";
import { readPending, savePending } from "./confirmation";
import type { Network } from "./network";
import { nodes, roads, shelters, origins } from "./simulation";
import type { Route, RoutePreview, Snapshot } from "./types";

vi.mock("./api", async importOriginal => {
  const original = await importOriginal<typeof import("./api")>();
  return { ...original, api: { network: vi.fn(), snapshot: vi.fn(), preview: vi.fn(),
    confirm: vi.fn(), route: vi.fn(), cancel: vi.fn(), access: vi.fn(), closure: vi.fn(), arrive: vi.fn() },
    subscribe: () => () => {} };
});

const network: Network = { version: "test-roads", name: "Service supplied district", data_mode: "fictional-pilot", nodes, roads, shelters, origins };
let state: Snapshot;
let booking: Route;
let preview: RoutePreview;

beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear();
  const now = new Date().toISOString();
  state = { revision: 1, hazard: { version: "hazard-1", source_timestamp: now, blocked_edge_ids: [], model_mode: "disabled", model_version: null },
    shelters: shelters.map(s => ({ shelter_id: s.id, node_id: s.node, name: s.name, location: { latitude: 34, longitude: -118 }, capacity: s.capacity, occupancy: s.occupancy,
      reserved_demand: 0, utilization: s.occupancy / s.capacity, status: "open", updated_at: now })) };
  // Deliberately service-supplied route, rather than invoking browser routing.
  preview = { shelter: state.shelters[0], path: ["n24", "n16", "n8", "n0", "n1", "n2", "n3"].map(node_id => ({ node_id, latitude: 34, longitude: -118 })),
    edge_ids: ["r16-24", "r8-16", "r0-8", "r0-1", "r1-2", "r2-3"], distance_km: 3.6, estimated_minutes: 9,
    risk_score: 0, hazard_version: "hazard-1", road_version: network.version, model_mode: "disabled", model_version: null,
    hazard_source_timestamp: now, created_at: now, valid_until: new Date(Date.now() + 300000).toISOString(), reason_codes: ["HARD_HAZARDS_EXCLUDED"] };
  booking = { ...preview, route_id: "11111111-1111-4111-8111-111111111111", status: "valid", cause: null, party_size: 2,
    shelter: { ...preview.shelter, reserved_demand: 2 } };
  vi.mocked(api.network).mockResolvedValue(network);
  vi.mocked(api.snapshot).mockImplementation(async () => state);
  vi.mocked(api.preview).mockResolvedValue([preview]);
  vi.mocked(api.route).mockImplementation(async () => booking);
  vi.mocked(api.confirm).mockImplementation(async () => {
    state = { ...state, revision: state.revision + 1, shelters: state.shelters.map(s => s.shelter_id === booking.shelter.shelter_id ? booking.shelter : s) };
    return booking;
  });
  vi.mocked(api.access).mockResolvedValue({ status: "authorized" });
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

async function compare() {
  await screen.findByRole("heading", { name: network.name });
  await waitFor(() => expect(screen.getByRole("button", { name: /compare evacuation routes/i })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: /compare evacuation routes/i }));
  return screen.findByRole("button", { name: "Confirm and reserve spaces" });
}

test("uses backend graph and separates preview from confirmed capacity", async () => {
  const { container } = render(<App />);
  const confirm = await compare();
  expect(api.preview).toHaveBeenCalledWith({ origin_node_id: "n24", party_size: 2, traffic: true, shelter_id: undefined });
  expect(api.confirm).not.toHaveBeenCalled();
  const points = preview.path.map(p => nodes.find(n => n.id === p.node_id)).map(p => `${p!.x},${p!.y}`).join(" ");
  expect(container.querySelector("polyline.route-line")).toHaveAttribute("points", points);
  fireEvent.click(confirm);
  await screen.findByRole("button", { name: "Cancel booking" });
  expect(api.confirm).toHaveBeenCalledTimes(1);
  expect(localStorage.getItem("werms.confirmed-plan.v1")).toBe(booking.route_id);
  expect(screen.getByText(/Party size: 2/)).toBeInTheDocument();
});

test("operator closure invalidates an affected booking and stops preview", async () => {
  render(<App />);
  fireEvent.click(await compare());
  await screen.findByRole("button", { name: "Cancel booking" });
  fireEvent.change(screen.getByLabelText("Access key"), { target: { value: "operator-secret" } });
  fireEvent.click(screen.getByRole("button", { name: "Enable operator controls" }));
  await screen.findByText("Operator controls enabled");
  vi.mocked(api.closure).mockImplementation(async id => {
    booking = { ...booking, status: "invalid", cause: "HARD_HAZARD_INTERSECTION", shelter: { ...booking.shelter, reserved_demand: 0 } };
    state = { ...state, revision: 3, hazard: { ...state.hazard, blocked_edge_ids: [id] } };
    return state;
  });
  const road = roads.find(r => r.id === preview.edge_ids[0])!;
  fireEvent.click(screen.getByRole("button", { name: `Close ${road.name} ${road.id}` }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Route interrupted"));
  expect(screen.getByRole("button", { name: "Start preview" })).toBeDisabled();
});

test("backend outage never substitutes a local route", async () => {
  vi.mocked(api.network).mockRejectedValue(new Error("Service offline"));
  render(<App />);
  await screen.findByRole("alert");
  expect(screen.getByRole("alert")).toHaveTextContent("Service offline");
  expect(screen.queryByRole("button", { name: /compare evacuation routes/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Pine Ridge Fire" })).not.toBeInTheDocument();
  expect(api.preview).not.toHaveBeenCalled();
});

test("expired preview cannot be confirmed or animated", async () => {
  vi.mocked(api.preview).mockResolvedValue([{ ...preview, valid_until: "2000-01-01T00:00:00Z" }]);
  render(<App />);
  expect(await compare()).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("Plan expired");
  expect(screen.getByRole("button", { name: "Start preview" })).toBeDisabled();
});

test("reload recovers the original request after a lost confirmation response", async () => {
  const pending = { input: { origin_node_id: "n24", party_size: 2, traffic: true, shelter_id: "north" },
    requestId: "22222222-2222-4222-8222-222222222222", fingerprint: "persisted-request" };
  savePending(pending);
  render(<App />);
  await screen.findByRole("button", { name: "Cancel booking" });
  expect(api.confirm).toHaveBeenCalledWith(pending.input, pending.requestId, undefined);
  expect(readPending()).toBeUndefined();
  expect(localStorage.getItem("werms.confirmed-plan.v1")).toBe(booking.route_id);
});

test("cancel sends a service mutation and releases the displayed booking", async () => {
  render(<App />);
  fireEvent.click(await compare());
  const button = await screen.findByRole("button", { name: "Cancel booking" });
  vi.mocked(api.cancel).mockImplementation(async () => {
    booking = { ...booking, status: "cancelled", shelter: { ...booking.shelter, reserved_demand: 0 } };
    state = { ...state, revision: 3, shelters: state.shelters.map(s => s.shelter_id === "north" ? booking.shelter : s) };
    return booking;
  });
  fireEvent.click(button);
  await waitFor(() => expect(screen.queryByRole("button", { name: "Cancel booking" })).not.toBeInTheDocument());
  expect(api.cancel).toHaveBeenCalledWith(booking.route_id);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.queryByText("Booking · cancelled")).not.toBeInTheDocument();
});

test("slow synchronization completes instead of being superseded by every polling tick", async () => {
  vi.useFakeTimers();
  let resolveSnapshot!: (value: Snapshot) => void;
  const slowSnapshot = new Promise<Snapshot>(resolve => { resolveSnapshot = resolve; });
  vi.mocked(api.snapshot).mockReturnValue(slowSnapshot);
  await act(async () => { render(<App />); });
  await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
  expect(api.snapshot).toHaveBeenCalledTimes(1);
  await act(async () => { resolveSnapshot(state); await slowSnapshot; });
  expect(screen.getByText("Service connected")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /compare evacuation routes/i })).toBeEnabled();
});

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { contextApi } from "../context";
import type { ScenarioResult } from "../context";
import type { Network } from "../network";
import type { RoutePreview } from "../types";
import { ResilienceLab } from "./ResilienceLab";

vi.mock("../context", async original => ({ ...await original<typeof import("../context")>(), contextApi: { scenario: vi.fn() } }));
vi.mock("./RealWorldMap", () => ({ RealWorldMap: () => <div aria-label="Scenario map" /> }));
const network: Network = { name: "Dehradun", version: "india-001", country: "IN", data_mode: "osm-pilot", nodes: [],
  roads: [{ id: "road-1", from: "a", to: "b", name: "Rajpur Road", minutes: 2, km: 1, traffic: 1 }],
  shelters: [{ id: "school", node: "b", name: "School", capacity: 100, occupancy: 0 }], origins: [{ node: "a", name: "Rajpur" }] };
const route: RoutePreview = { shelter: { shelter_id: "school", node_id: "b", name: "School", location: { latitude: 30.3, longitude: 78 }, capacity: 100, occupancy: 0, reserved_demand: 0, utilization: 0, status: "open", updated_at: "2026-10-17T12:00:00Z" },
  path: [{ node_id: "a", latitude: 30.3, longitude: 78 }, { node_id: "b", latitude: 30.31, longitude: 78 }], edge_ids: ["road-1"], distance_km: 1, estimated_minutes: 2, risk_score: 0, hazard_version: "h1", road_version: "india-001", model_mode: "disabled", model_version: null,
  hazard_source_timestamp: "2026-10-17T12:00:00Z", created_at: "2026-10-17T12:00:00Z", valid_until: "2026-10-17T12:05:00Z", reason_codes: [] };
let result: ScenarioResult;
beforeEach(() => {
  vi.resetAllMocks();
  result = { mode: "what-if-only", changes_operational_state: false, road_version: network.version, snapshot_revision: 1,
    created_at: "2026-10-17T12:00:00Z", inputs: { origin_node_id: "a", party_size: 4, traffic: true, blocked_edge_ids: [], unavailable_shelter_ids: [] }, baseline: [route], simulated: [route], outcome: "unchanged", delta_minutes: 0, delta_km: 0, destination_changed: false, reachable_before: 1, reachable_after: 1, compute_ms: 15 };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); vi.restoreAllMocks(); });

test("road exercise blocks a baseline segment and renders the returned comparison", async () => {
  vi.mocked(contextApi.scenario).mockResolvedValueOnce(result).mockResolvedValueOnce({ ...result, outcome: "rerouted", delta_minutes: 3, inputs: { ...result.inputs, blocked_edge_ids: ["road-1"] } });
  render(<ResilienceLab network={network} />);
  fireEvent.click(screen.getByRole("button", { name: /Run disruption exercise/ }));
  await screen.findByText("A different route. A reason for every turn.");
  expect(contextApi.scenario).toHaveBeenLastCalledWith({ ...result.inputs, blocked_edge_ids: ["road-1"] });
  expect(screen.getByText("+3")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Download scenario evidence/ })).toBeInTheDocument();
});

test("compound exercise removes the site and road and shows no-route explicitly", async () => {
  vi.mocked(contextApi.scenario).mockResolvedValueOnce(result).mockResolvedValueOnce({ ...result, outcome: "no_route", simulated: [], delta_minutes: null, delta_km: null, reachable_after: 0 });
  render(<ResilienceLab network={network} />);
  fireEvent.click(screen.getByRole("button", { name: /A compound disruption/ }));
  fireEvent.click(screen.getByRole("button", { name: /Run disruption exercise/ }));
  await screen.findByText("No eligible route survives this scenario.");
  expect(contextApi.scenario).toHaveBeenLastCalledWith({ ...result.inputs, blocked_edge_ids: ["road-1"], unavailable_shelter_ids: ["school"] });
  expect(screen.getByText(/no substitute path was fabricated/)).toBeInTheDocument();
});

test("failed comparison reports an error and releases the run control", async () => {
  vi.mocked(contextApi.scenario).mockRejectedValue(new Error("Service unavailable"));
  render(<ResilienceLab network={network} />);
  fireEvent.click(screen.getByRole("button", { name: /Run disruption exercise/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Service unavailable");
  expect(screen.getByRole("button", { name: /Run disruption exercise/ })).toBeEnabled();
});

test("evidence download keeps its URL alive and exposes the same JSON in the decision record", async () => {
  vi.mocked(contextApi.scenario).mockResolvedValue(result);
  const create = vi.fn((blob: Blob) => { expect(blob).toBeInstanceOf(Blob); return "blob:scenario-evidence"; }), revoke = vi.fn();
  vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: revoke });
  let attached = false, filename = "";
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    attached = this.isConnected; filename = this.download;
  });
  const { container } = render(<ResilienceLab network={network} />);
  fireEvent.click(screen.getByRole("button", { name: /Run disruption exercise/ }));
  const download = await screen.findByRole("button", { name: /Download scenario evidence/ });
  vi.useFakeTimers();
  fireEvent.click(download);
  expect(attached).toBe(true);
  expect(filename).toBe("werms-dehradun-scenario-2026-10-17.json");
  expect(create.mock.calls[0][0]).toBeInstanceOf(Blob);
  expect(revoke).not.toHaveBeenCalled();
  expect(JSON.parse(container.querySelector(".json-evidence")!.textContent!)).toMatchObject({ application: "WERMS India", road_version: network.version, inputs: result.inputs });
  vi.advanceTimersByTime(1000);
  expect(revoke).toHaveBeenCalledWith("blob:scenario-evidence");
});

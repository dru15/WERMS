import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { CommandCentre } from "./CommandCentre";
import { staffApi } from "../staff";
import type { CommandState } from "../staff";
import type { Shelter } from "../types";
vi.mock("./FireExclusionPanel", () => ({FireExclusionPanel: () => null}));

vi.mock("../staff", () => ({ staffApi: { login: vi.fn(), logout: vi.fn(), state: vi.fn(), accounts: vi.fn(), audit: vi.fn(),
  report: vi.fn(), resource: vi.fn(), availability: vi.fn(), dispatch: vi.fn(), assignment: vi.fn(), incident: vi.fn(), shelter: vi.fn(), account: vi.fn() } }));

const shelters: Shelter[] = ["One", "Two"].map((name, i) => ({ shelter_id: `site-${i}`, name, node_id: `n${i}`,
  location: { latitude: 34, longitude: -118 }, capacity: 100, occupancy: 0, reserved_demand: 0, utilization: 0, status: "open", updated_at: new Date().toISOString() }));
const base = { shelters, roads: [], onSession: vi.fn(), onLock: vi.fn(), onRefresh: vi.fn(async () => {}) };
let state: CommandState;

beforeEach(() => {
  vi.resetAllMocks();
  state = { incidents: [{ id: "incident-1", title: "Exercise incident", description: "Training report", source: "Exercise desk", observed_at: new Date().toISOString(), priority: "high", road_id: null, status: "reported", version: 1, updated_at: new Date().toISOString() }],
    resources: [{ id: "resource-1", name: "Engine Alpha", kind: "engine", status: "available" }], assignments: [] };
  vi.mocked(staffApi.state).mockImplementation(async () => state);
  vi.mocked(staffApi.accounts).mockResolvedValue([]); vi.mocked(staffApi.audit).mockResolvedValue([]);
});
afterEach(cleanup);

test("sign-in uses a named account and clears password after success", async () => {
  vi.mocked(staffApi.login).mockResolvedValue({ token: "opaque", expires_at: new Date().toISOString(), user: { username: "dispatch", role: "dispatcher", shelter_id: null } });
  render(<CommandCentre {...base} credential="" />);
  expect(screen.queryByRole("button", { name: "Dispatch selected resource" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: "dispatch" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a-long-password" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await waitFor(() => expect(base.onSession).toHaveBeenCalledWith("session:opaque", { username: "dispatch", role: "dispatcher", shelter_id: null }));
  expect(screen.getByLabelText("Password")).toHaveValue("");
});

test("shelter staff only see their assigned site and no dispatch or account forms", async () => {
  render(<CommandCentre {...base} credential="session:staff" user={{ username: "site-staff", role: "shelter", shelter_id: "site-0" }} />);
  await screen.findByText("Exercise incident");
  expect(screen.getByRole("heading", { name: "One" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Two" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Resource name")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("New username")).not.toBeInTheDocument();
  expect(staffApi.accounts).not.toHaveBeenCalled();
});

test("dispatch retries retain the idempotency ID and acknowledged assignments can complete", async () => {
  vi.mocked(staffApi.dispatch).mockRejectedValueOnce(new Error("Connection interrupted"));
  vi.mocked(staffApi.dispatch).mockImplementationOnce(async () => {
    state = { ...state, resources: [{ ...state.resources[0], status: "deployed" }], assignments: [{ id: "assignment-1", resource_id: "resource-1", incident_id: "incident-1", status: "acknowledged", note: "Unit accepted", updated_at: new Date().toISOString() }] };
  });
  vi.mocked(staffApi.assignment).mockResolvedValue(undefined);
  render(<CommandCentre {...base} credential="session:dispatch" user={{ username: "dispatch", role: "dispatcher", shelter_id: null }} />);
  await screen.findByRole("option", { name: "Engine Alpha · engine" });
  fireEvent.change(screen.getByLabelText("Available resource"), { target: { value: "resource-1" } });
  fireEvent.change(screen.getByLabelText("Active incident"), { target: { value: "incident-1" } });
  fireEvent.change(screen.getByLabelText("Dispatch instructions"), { target: { value: "Exercise response" } });
  fireEvent.click(screen.getByRole("button", { name: "Dispatch selected resource" }));
  await screen.findByRole("alert");
  fireEvent.click(screen.getByRole("button", { name: "Dispatch selected resource" }));
  await screen.findByRole("button", { name: "Complete assignment" });
  expect(vi.mocked(staffApi.dispatch).mock.calls[0][4]).toBe(vi.mocked(staffApi.dispatch).mock.calls[1][4]);
  fireEvent.click(screen.getByRole("button", { name: "Complete assignment" }));
  await waitFor(() => expect(staffApi.assignment).toHaveBeenCalledWith("session:dispatch", "assignment-1", "resolved", expect.any(String)));
});

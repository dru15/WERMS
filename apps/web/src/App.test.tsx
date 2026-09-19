import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import App from "./App";

class MockWebSocket {
  static OPEN = 1;
  addEventListener = vi.fn();
  close = vi.fn();
}

beforeEach(() => {
  vi.stubGlobal("WebSocket", MockWebSocket);
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string | URL | Request) => {
      const url = String(input);
      const payload = url.includes("system/status")
        ? { service: "werms-api", environment: "test", operational_store: "in-memory-demo", model_mode: "disabled", hazard_version: "hazard-001", road_version: "roads-demo-001", websocket_clients: 0 }
        : url.includes("hazards")
          ? { version: "hazard-001", source_timestamp: new Date().toISOString(), blocked_edge_ids: [], model_version: null, model_mode: "disabled" }
          : [];
      return Promise.resolve(new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } }));
    }),
  );
});

test("presents the safety-oriented route action", async () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: /clear guidance/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /find safest route/i })).toBeInTheDocument();
  expect(await screen.findByText(/No unapproved model/i)).toBeInTheDocument();
});


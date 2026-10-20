import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { contextApi } from "../context";
import { IndiaOverview } from "./IndiaOverview";
import type { Network } from "../network";

vi.mock("../context", async original => ({ ...await original<typeof import("../context")>(), contextApi: { weather: vi.fn() } }));
afterEach(cleanup);
const network: Network = { version: "india", name: "Dehradun", data_mode: "osm-pilot", nodes: [], roads: [], origins: [], shelters: [] };

test("weather exposes validity, model provenance, and stale state", async () => {
  vi.mocked(contextApi.weather).mockResolvedValue({ status: "stale", provider: "Open-Meteo", source_url: "https://open-meteo.com/", message: "Provider offline", data: { temperature_c: 24, humidity_pct: 40, wind_kph: 10, wind_direction_degrees: 90, precipitation_mm: 0, interval_seconds: 900, valid_at: "2026-10-17T12:00:00Z", retrieved_at: "2026-10-17T12:05:00Z" } });
  render(<IndiaOverview network={network} onExplore={() => {}} />);
  expect(await screen.findByText("stale")).toBeInTheDocument();
  expect(screen.getByText(/Valid 05:30 pm IST/i)).toBeInTheDocument();
  expect(screen.getByText(/model-derived, not a local station reading/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Weather data by Open-Meteo/ })).toHaveAttribute("href", "https://open-meteo.com/");
});

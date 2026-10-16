import { expect, test } from "vitest";
import { closestRoadNode, type Network } from "./network";

const network: Network = { name: "OSM fixture", version: "test", data_mode: "osm-pilot",
  bounds: [34, -118.1, 34.01, -118],
  nodes: [{ id: "real-point", x: 0, y: 0, latitude: 34.005, longitude: -118.05 }],
  roads: [], shelters: [], origins: [] };

test("map origins must lie inside the imported area and close to mapped roads", () => {
  expect(closestRoadNode(network, 34.0051, -118.0501)?.id).toBe("real-point");
  expect(closestRoadNode(network, 34.009, -118.05)).toBeUndefined();
  expect(closestRoadNode(network, 0, 0)).toBeUndefined();
});

import type { FeatureCollection, LineString } from "geojson";
import type { Network, Plan } from "./network";

export function roadFeatures(network: Network, blocked: string[], simulated: string[], risk:Record<string,number> = {}): FeatureCollection<LineString> {
  const points = Object.fromEntries(network.nodes.map(n => [n.id, n]));
  return { type: "FeatureCollection", features: network.roads.map(road => ({
    type: "Feature", id: road.id, properties: { id: road.id, name: road.name,
      closed: blocked.includes(road.id), simulated: simulated.includes(road.id),
      ...(risk[road.id] === undefined ? {} : {predictive_risk:risk[road.id]}) },
    geometry: { type: "LineString", coordinates: [road.from, road.to].map(id => {
      const point = points[id];
      if (point.longitude === undefined || point.latitude === undefined) throw new Error("Missing road coordinates");
      return [point.longitude, point.latitude];
    }) },
  })) };
}

export function routeFeatures(network: Network, plan?: Plan): FeatureCollection<LineString> {
  const points = Object.fromEntries(network.nodes.map(n => [n.id, n]));
  return { type: "FeatureCollection", features: plan ? [{ type: "Feature", properties: {},
    geometry: { type: "LineString", coordinates: plan.nodes.map(id => [points[id].longitude!, points[id].latitude!]) } }] : [] };
}

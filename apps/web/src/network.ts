export type Point = { id: string; x: number; y: number; latitude?: number; longitude?: number };
export type Road = { id: string; from: string; to: string; name: string; minutes: number; km: number; traffic: number;
  direction?: "both" | "forward" | "reverse"; osm_way_id?: string; highway?: string };
export type MapShelter = { id: string; node: string; name: string; capacity: number; occupancy: number;
  latitude?: number; longitude?: number; access_distance_m?: number; osm_url?: string };
export type Plan = { nodes: string[]; edges: string[]; minutes: number; km: number; shelter: MapShelter };
export type Network = {
  version: string;
  name: string;
  data_mode: "fictional-pilot" | "osm-pilot";
  bounds?: [number, number, number, number];
  source?: { name: string; url: string; license: string; data_timestamp: string; imported_at: string };
  nodes: Point[];
  roads: Road[];
  shelters: MapShelter[];
  origins: { node: string; name: string }[];
};

export function closestRoadNode(network: Network, latitude: number, longitude: number): Point | undefined {
  if (!network.bounds || latitude < network.bounds[0] || latitude > network.bounds[2]
    || longitude < network.bounds[1] || longitude > network.bounds[3]) return undefined;
  let closest: Point | undefined, best = Infinity;
  for (const point of network.nodes) {
    if (point.latitude === undefined || point.longitude === undefined) continue;
    const metres = Math.hypot((point.latitude - latitude) * 111320,
      (point.longitude - longitude) * 111320 * Math.cos(latitude * Math.PI / 180));
    if (metres < best) { best = metres; closest = point; }
  }
  return best <= 200 ? closest : undefined;
}

export function positionOnNetwork(plan: Plan, progress: number, points: Record<string, Point>): Point {
  if (plan.nodes.length === 1) return points[plan.nodes[0]];
  const scaled = Math.max(0, Math.min(1, progress)) * (plan.nodes.length - 1);
  const index = Math.min(plan.nodes.length - 2, Math.floor(scaled));
  const a = points[plan.nodes[index]], b = points[plan.nodes[index + 1]], fraction = scaled - index;
  return { id: "preview", x: a.x + (b.x - a.x) * fraction, y: a.y + (b.y - a.y) * fraction };
}

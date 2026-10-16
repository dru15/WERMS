export type Point = { id: string; x: number; y: number };
export type Road = { id: string; from: string; to: string; name: string; minutes: number; km: number; traffic: number };
export type DemoShelter = { id: string; node: string; name: string; capacity: number; occupancy: number };
export type Plan = { nodes: string[]; edges: string[]; minutes: number; km: number; shelter: DemoShelter };
export const nodes: Point[] = Array.from({ length: 48 }, (_, i) => {
  const row = Math.floor(i / 8), col = i % 8;
  return { id: `n${i}`, x: 80 + col * 108 + Math.sin(row * 1.3 + col) * 13,
    y: 85 + row * 88 + Math.sin(col * .9) * 17 };
});
export const nodeById = Object.fromEntries(nodes.map(n => [n.id, n]));
const names = ["Ridge Avenue", "Canyon Road", "Oak Street", "Main Street", "Valley Boulevard", "Creek Road"];
export const roads: Road[] = nodes.flatMap((node, i) => {
  const row = Math.floor(i / 8), col = i % 8;
  return [col < 7 ? i + 1 : -1, row < 5 ? i + 8 : -1].filter(j => j >= 0).map(j => ({
    id: `r${i}-${j}`, from: node.id, to: `n${j}`,
    name: j === i + 1 ? names[row] : ["Mill Lane", "Pine Street", "Cedar Drive", "Park Road", "River Lane", "Elm Street", "Hill Road", "East Avenue"][col],
    minutes: +(1.1 + ((i + j) % 5) * .24).toFixed(2),
    km: +(.45 + ((i + j) % 4) * .07).toFixed(2), traffic: (i + j) % 7 === 0 ? 1.6 : 1,
  }));
});
export const shelters: DemoShelter[] = [
  { id: "north", node: "n3", name: "North Ridge School", capacity: 160, occupancy: 72 },
  { id: "east", node: "n31", name: "East Valley Centre", capacity: 120, occupancy: 81 },
  { id: "south", node: "n44", name: "Creekside Sports Hall", capacity: 200, occupancy: 113 },
];
export const origins = [{ node: "n24", name: "Old Mill Road" }, { node: "n18", name: "Pine Ridge Market" }, { node: "n41", name: "Creekside residential" }];
export const initialClosures = ["r6-7", "r7-15", "r14-15", "r15-23"];

// Dijkstra operates on the same edges drawn and selected on the map.
export function planRoutes(origin: string, blocked: string[], party: number, traffic: boolean): Plan[] {
  return shelters.filter(s => s.capacity - s.occupancy >= party).flatMap(shelter => {
    const distances = new Map([[origin, 0]]);
    const previous = new Map<string, { node: string; edge: Road }>();
    const remaining = new Set(nodes.map(n => n.id));
    while (remaining.size) {
      const current = [...remaining].reduce((a, b) => (distances.get(a) ?? Infinity) < (distances.get(b) ?? Infinity) ? a : b);
      const distance = distances.get(current);
      if (distance === undefined) break;
      remaining.delete(current);
      if (current === shelter.node) break;
      for (const road of roads) {
        if (blocked.includes(road.id)) continue;
        const next = road.from === current ? road.to : road.to === current ? road.from : undefined;
        if (!next || !remaining.has(next)) continue;
        const cost = distance + road.minutes * (traffic ? road.traffic : 1);
        if (cost < (distances.get(next) ?? Infinity)) {
          distances.set(next, cost); previous.set(next, { node: current, edge: road });
        }
      }
    }
    if (!distances.has(shelter.node)) return [];
    const path = [shelter.node], edges: string[] = [];
    let cursor = shelter.node, km = 0;
    while (cursor !== origin) {
      const step = previous.get(cursor)!;
      edges.unshift(step.edge.id); path.unshift(step.node); km += step.edge.km; cursor = step.node;
    }
    return [{ nodes: path, edges, minutes: Math.round(distances.get(shelter.node)! * 10) / 10, km: Math.round(km * 10) / 10, shelter }];
  }).sort((a, b) => a.minutes - b.minutes);
}

export function positionOnRoute(plan: Plan, progress: number): Point {
  if (plan.nodes.length === 1) return nodeById[plan.nodes[0]];
  const scaled = Math.min(.999999, progress) * (plan.nodes.length - 1);
  const index = Math.floor(scaled), t = scaled - index;
  const a = nodeById[plan.nodes[index]], b = nodeById[plan.nodes[index + 1]];
  return { id: "vehicle", x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t };
}

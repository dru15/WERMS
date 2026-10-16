import { expect, test } from "vitest";
import { initialClosures, origins, planRoutes, roads } from "./simulation";
test("routes only use connected open roads and all origins have alternatives", () => {
  for (const origin of origins) {
    const first = planRoutes(origin.node, initialClosures, 20, true)[0];
    expect(first).toBeDefined();
    const blocked = [...initialClosures, first.edges[0]];
    const alternative = planRoutes(origin.node, blocked, 20, true)[0];
    expect(alternative).toBeDefined();
    expect(alternative.edges.some(e => blocked.includes(e))).toBe(false);
    alternative.edges.forEach((id, i) => {
      const edge = roads.find(r => r.id === id)!;
      expect([edge.from, edge.to]).toContain(alternative.nodes[i]);
      expect([edge.from, edge.to]).toContain(alternative.nodes[i+1]);
    });
  }
});
test("blocked origin returns no route and reset restores access without accumulating reservations", () => {
  const blocked = roads.filter(r => r.from === "n24" || r.to === "n24").map(r => r.id);
  expect(planRoutes("n24", blocked, 2, true)).toHaveLength(0);
  for (let i = 0; i < 100; i++) expect(planRoutes("n24", initialClosures, 2, true)).toHaveLength(3);
});

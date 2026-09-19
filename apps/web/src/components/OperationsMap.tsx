import type { Hazard, Route, Shelter } from "../types";

type Props = {
  route: Route | null;
  shelters: Shelter[];
  hazard: Hazard | null;
  routeInvalidated: boolean;
};

const nodePositions: Record<string, [number, number]> = {
  n0: [80, 330],
  n1: [210, 250],
  n2: [350, 175],
  n3: [225, 400],
  n4: [520, 90],
  n5: [390, 430],
  n6: [570, 320],
};

const edges: Array<[string, string, string]> = [
  ["e01", "n0", "n1"],
  ["e12", "n1", "n2"],
  ["e24", "n2", "n4"],
  ["e03", "n0", "n3"],
  ["e35", "n3", "n5"],
  ["e56", "n5", "n6"],
  ["e26", "n2", "n6"],
];

export function OperationsMap({ route, shelters, hazard, routeInvalidated }: Props) {
  const routeEdges = new Set(route?.edge_ids ?? []);
  const blocked = new Set(hazard?.blocked_edge_ids ?? []);

  return (
    <section className="map-card" aria-label="Operational route map">
      <div className="map-toolbar">
        <div>
          <span className="eyebrow">Operational picture</span>
          <h2>Demo pilot network</h2>
        </div>
        <div className="legend" aria-label="Map legend">
          <span><i className="legend-line route" /> Active route</span>
          <span><i className="legend-line hazard" /> Hard block</span>
          <span><i className="legend-dot" /> Shelter</span>
        </div>
      </div>
      <svg className="operations-map" viewBox="0 0 650 500" role="img">
        <title>WERMS pilot road network with shelters and current route</title>
        <defs>
          <pattern id="grid" width="36" height="36" patternUnits="userSpaceOnUse">
            <path d="M 36 0 L 0 0 0 36" fill="none" stroke="#d7dfda" strokeWidth="1" />
          </pattern>
          <filter id="routeGlow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <rect width="650" height="500" fill="url(#grid)" />
        {hazard?.model_mode === "approved" && (
          <>
            <path
              d="M320 26 C410 8 535 25 635 100 L635 190 C530 160 448 172 380 212 C333 166 295 101 320 26Z"
              className="risk-envelope"
            />
            <text x="438" y="68" className="map-label risk-label">predictive risk envelope</text>
          </>
        )}
        {edges.map(([edgeId, source, target]) => {
          const [x1, y1] = nodePositions[source];
          const [x2, y2] = nodePositions[target];
          const isBlocked = blocked.has(edgeId);
          const isRoute = routeEdges.has(edgeId) || routeEdges.has(`${edgeId[0]}${edgeId[2]}${edgeId[1]}`);
          return (
            <g key={edgeId}>
              <line
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                className={isBlocked ? "road blocked" : isRoute ? "road active" : "road"}
                filter={isRoute && !isBlocked ? "url(#routeGlow)" : undefined}
              />
              {isBlocked && (
                <g transform={`translate(${(x1 + x2) / 2} ${(y1 + y2) / 2})`}>
                  <circle r="12" className="blocked-marker" />
                  <path d="M-5 -5 L5 5 M5 -5 L-5 5" className="blocked-x" />
                </g>
              )}
            </g>
          );
        })}
        {Object.entries(nodePositions).map(([nodeId, [x, y]]) => (
          <circle key={nodeId} cx={x} cy={y} r="5" className="road-node" />
        ))}
        <g transform="translate(80 330)">
          <circle r="15" className="origin-marker" />
          <circle r="5" className="origin-core" />
          <text x="-14" y="32" className="map-label">You</text>
        </g>
        {shelters.map((shelter) => {
          const position = shelter.shelter_id === "s-north" ? nodePositions.n4 : nodePositions.n6;
          return (
            <g key={shelter.shelter_id} transform={`translate(${position[0]} ${position[1]})`}>
              <path d="M0 -19 L17 -4 L13 -4 L13 15 L-13 15 L-13 -4 L-17 -4Z" className="shelter-marker" />
              <text x="-54" y="37" className="map-label">{shelter.name.replace(" Shelter", "")}</text>
            </g>
          );
        })}
        {routeInvalidated && (
          <g className="invalidated-banner">
            <rect x="165" y="450" width="320" height="34" rx="17" />
            <text x="325" y="472" textAnchor="middle">Route invalidated - request updated guidance</text>
          </g>
        )}
      </svg>
    </section>
  );
}

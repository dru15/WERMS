import { lazy, Suspense, useRef, useState } from "react";
import { nodes as trainingNodes, roads as trainingRoads, shelters as trainingShelters } from "../simulation";
import { positionOnNetwork, type Network, type Plan } from "../network";
const RealWorldMap = lazy(() => import("./RealWorldMap").then(m => ({default:m.RealWorldMap})));

type Props = {
  plan?: Plan; blocked?: string[]; origin?: string; progress?: number;
  invalid?: boolean; traffic?: boolean; onTraffic?: () => void;
  onRoad?: (id: string) => void; onShelter?: (id: string) => void;
  network?: Network;
  onOrigin?: (id: string) => void;
};
export function OperationsMap(props: Props) {
  if (props.network?.data_mode === "osm-pilot") return <Suspense fallback={<section className="map-card" role="status">Loading vector map…</section>}><RealWorldMap {...props} network={props.network} /></Suspense>;
  return <TrainingMap {...props} />;
}

function TrainingMap({ plan, blocked = [], origin = "n24", progress = 0, invalid = false,
  traffic = true, onTraffic, onRoad, onShelter, network }: Props) {
  const nodes = network?.nodes ?? trainingNodes;
  const roads = network?.roads ?? trainingRoads;
  const shelters = network?.shelters ?? trainingShelters;
  const nodeById = Object.fromEntries(nodes.map(n => [n.id, n]));
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [hazards, setHazards] = useState(true);
  const [layers, setLayers] = useState(false);
  const [buildings, setBuildings] = useState(true);
  const [showShelters, setShowShelters] = useState(true);
  const drag = useRef<{ x: number; y: number; startX: number; startY: number; moved: boolean } | null>(null);
  const vehicle = plan ? positionOnNetwork(plan, progress, nodeById) : nodeById[origin] ?? nodes[0];
  const width = 940 / zoom, height = 620 / zoom;
  const path = plan?.nodes.map(id => `${nodeById[id].x},${nodeById[id].y}`).join(" ");
  return <section className="map-card">
    <div className="map-toolbar"><div className="map-title"><h2>{network?.name ?? "Pine Ridge district"}</h2><p>Drag to pan · {onRoad ? "select a road to close or reopen it" : "operator access is required to change closures"}</p></div>
      <div className="map-tools">
        <button className={traffic ? "map-tool active" : "map-tool"} aria-pressed={traffic} disabled={!onTraffic} onClick={onTraffic}>Traffic</button>
        <button className={hazards ? "map-tool active" : "map-tool"} aria-pressed={hazards} onClick={() => setHazards(!hazards)}>Hazards</button>
        <button className="map-tool" aria-expanded={layers} onClick={() => setLayers(!layers)}>Layers</button>
      </div>
    </div>
    <div className="map-viewport">
      {layers && <div className="layer-menu">
        <label><input type="checkbox" checked={buildings} onChange={e => setBuildings(e.target.checked)} /> Buildings</label>
        <label><input type="checkbox" checked={showShelters} onChange={e => setShowShelters(e.target.checked)} /> Shelters</label>
        <p>Road closures always remain visible.</p>
      </div>}
      <svg className="operations-map" viewBox={`${470 - width / 2 + offset.x} ${310 - height / 2 + offset.y} ${width} ${height}`}
        aria-label="Interactive district road map" onPointerDown={e => {
          if ((e.target as Element).closest('[role="button"]')) return;
          e.currentTarget.setPointerCapture(e.pointerId);
          drag.current = { x: e.clientX, y: e.clientY, startX: offset.x, startY: offset.y, moved: false };
        }} onPointerMove={e => {
          if (!drag.current) return;
          const rect = e.currentTarget.getBoundingClientRect();
          const scale = Math.min(rect.width / width, rect.height / height);
          drag.current.moved = true;
          setOffset({ x: drag.current.startX - (e.clientX - drag.current.x) / scale, y: drag.current.startY - (e.clientY - drag.current.y) / scale });
        }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
        <rect x="-2000" y="-2000" width="5000" height="5000" fill="#e9ede4" />
        <path d="M0 0H940V140Q740 90 610 60T0 140Z" fill="#d0deca" />
        <path d="M0 500Q260 490 450 560T940 530V700H0Z" fill="#d3dfcd" />
        {[0, 1, 2, 3].map(i => <path key={i} d={`M0 ${30+i*19}Q300 ${90+i*15} 500 ${25+i*17}T1000 ${80+i*17}`} fill="none" stroke="#bbccb5" />)}
        <path d="M-20 573Q230 522 480 574T970 568" fill="none" stroke="#fcfffb" strokeWidth="19" />
        <path d="M-20 573Q230 522 480 574T970 568" fill="none" stroke="#99c6d0" strokeWidth="12" />
        {buildings && nodes.filter((_, i) => i % 8 < 7 && i < 40).map((n, i) => <g key={n.id}>
          {[0, 1, 2].map(j => <rect key={j} x={n.x + 18 + j * 24} y={n.y + 20} width="17" height={22 + i % 3 * 8} rx="2" fill="#d6dbd1" stroke="#c7cec2" />)}
          <rect x={n.x + 20} y={n.y + 57} width="61" height="13" rx="2" fill="#dde2d7" />
        </g>)}
        {hazards && <g className="hazard-layer">
          <path d="M738 0H940V250L865 235 843 168 777 148 751 91Z" fill="#f0b19c" stroke="#c24836" strokeWidth="3" strokeDasharray="7 5" />
          <text x="814" y="43" className="fire-name">PINE RIDGE FIRE</text>
          <text x="803" y="61" className="fire-meta">SIMULATED PERIMETER</text>
        </g>}
        {roads.map(road => {
          const a = nodeById[road.from], b = nodeById[road.to], closed = blocked.includes(road.id);
          return <g key={road.id}>
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#bdc4b9" strokeWidth="12" />
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={closed ? "#c74a3e" : traffic && road.traffic > 1 ? "#edc27c" : "#fffefb"} strokeWidth="8" strokeDasharray={closed ? "7 5" : undefined} />
          </g>;
        })}
        {path && <polyline points={path} fill="none" stroke="white" strokeWidth="13" strokeLinejoin="round" strokeLinecap="round" />}
        {path && <polyline points={path} className={invalid ? "route-line invalid" : "route-line"} fill="none" stroke={invalid ? "#a3aab0" : "#246fed"} strokeWidth="7" strokeLinejoin="round" strokeLinecap="round" />}
        {roads.map(road => {
          const a = nodeById[road.from], b = nodeById[road.to], closed = blocked.includes(road.id);
          return <g key={road.id} role={onRoad ? "button" : undefined} tabIndex={onRoad ? 0 : undefined} aria-label={`${closed ? "Reopen" : "Close"} ${road.name} ${road.id}`}
            onClick={() => onRoad?.(road.id)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onRoad?.(road.id); } }}>
            <title>{road.name} · {closed ? "Closed" : "Open"}{onRoad ? " — select to change closure" : ""}</title>
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth="20" className="road-hit" />
            {closed && <g transform={`translate(${(a.x+b.x)/2} ${(a.y+b.y)/2})`}><circle r="9" fill="#c53c30" stroke="white" strokeWidth="2" /><path d="M-4 0H4" stroke="white" strokeWidth="2" /></g>}
          </g>;
        })}
        <text x="80" y="34" className="place-label major" textAnchor="start">PINE RIDGE</text>
        <text x="365" y="300" className="place-label minor">TOWN CENTRE</text>
        <text x="644" y="478" className="place-label minor">EAST VALLEY</text>
        <text x="390" y="600" className="water-label">SILVER CREEK</text>
        {showShelters && shelters.map(s => {
          const p = nodeById[s.node];
          return <g key={s.id} role="button" tabIndex={0} aria-label={`Route to ${s.name}`}
            onClick={() => onShelter?.(s.id)} onKeyDown={e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onShelter?.(s.id); } }} transform={`translate(${p.x} ${p.y})`} className="clickable-shelter">
            <circle r="17" fill={plan?.shelter.id === s.id ? "#176e50" : "white"} stroke="#176e50" strokeWidth="3" />
            <text textAnchor="middle" y="5" fill={plan?.shelter.id === s.id ? "white" : "#176e50"} fontSize="16" fontWeight="bold">H</text>
            <rect x="-67" y="23" width="134" height="24" rx="5" fill="white" stroke="#d0d9ce" />
            <text textAnchor="middle" y="39" fontSize="10" fill="#294a39">{s.name}</text>
          </g>;
        })}
        <g transform={`translate(${vehicle.x} ${vehicle.y})`} pointerEvents="none">
          <circle r="21" fill="#2674ed" opacity=".15" /><circle r="11" fill="#2674ed" stroke="white" strokeWidth="3" />
          <path d="M0-5 4 4 0 2-4 4Z" fill="white" />
        </g>
      </svg>
      <div className="map-zoom">
        <button aria-label="Zoom in" disabled={zoom >= 3} onClick={() => setZoom(z => Math.min(3, z + .3))}>+</button>
        <button aria-label="Zoom out" disabled={zoom <= 1} onClick={() => setZoom(z => Math.max(1, z - .3))}>−</button>
        <button aria-label="Reset map view" onClick={() => { setZoom(1); setOffset({ x: 0, y: 0 }); }}>⌂</button>
      </div>
      <div className="map-legend"><span><i className="legend-route" /> Route</span><span><i className="legend-fire" /> Fire</span><span><i className="legend-closure" /> Closure</span><span><i className="legend-shelter" /> Shelter</span></div>
      <div className="map-attribution">Fictional {network ? "pilot" : "training"} map · {Math.round(zoom * 100)}% · {nodes.length} junctions / {roads.length} roads</div>
    </div>
  </section>;
}

import { useMemo, useState } from "react";
import { contextApi, indiaTime } from "../context";
import type { ScenarioResult } from "../context";
import type { FirePolygon } from "../context";
import type { Network, Plan } from "../network";
import type { RoutePreview, Snapshot } from "../types";
import { RealWorldMap } from "./RealWorldMap";

function mapPlan(route?: RoutePreview): Plan | undefined {
  return route && { nodes: route.path.map(p => p.node_id), edges: route.edge_ids, minutes: route.estimated_minutes,
    km: route.distance_km, shelter: { id: route.shelter.shelter_id, node: route.shelter.node_id, name: route.shelter.name,
      capacity: route.shelter.capacity, occupancy: route.shelter.occupancy + route.shelter.reserved_demand } };
}
const experiments = [
  { id: "road", icon: "01", title: "A road goes offline", description: "Block a segment on the preferred path. Can the network find another way?" },
  { id: "site", icon: "02", title: "An assembly site closes", description: "Remove the preferred destination. Compare the next capacity-qualified option." },
  { id: "combined", icon: "03", title: "A compound disruption", description: "Lose a road and the preferred site together. Test the harder decision." },
  { id: "fire", icon: "04", title: "A fire perimeter expands", description: "PostGIS intersects a demonstration polygon with real road geometry. Every touching segment is excluded." },
];

export function ResilienceLab({ network, snapshot }: { network: Network; snapshot?: Snapshot }) {
  const [origin, setOrigin] = useState(network.origins[0].node);
  const [party, setParty] = useState(4);
  const [experiment, setExperiment] = useState("road");
  const [result, setResult] = useState<ScenarioResult>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [exportMessage, setExportMessage] = useState("");
  const baseline = result?.baseline[0], simulated = result?.simulated[0];
  const mainPlan = useMemo(() => mapPlan(simulated ?? baseline), [simulated, baseline]);
  const baselinePlan = useMemo(() => simulated ? mapPlan(baseline) : undefined, [baseline, simulated]);
  const changed = Boolean(result && snapshot && result.snapshot_revision !== snapshot.revision);
  async function run() {
    setBusy(true); setError(""); setResult(undefined); setExportMessage("");
    try {
      const input = { origin_node_id: origin, party_size: party, traffic: true, blocked_edge_ids: [], unavailable_shelter_ids: [] };
      const before = await contextApi.scenario(input);
      const preferred = before.baseline[0];
      if (!preferred) { setResult(before); return; }
      const roadId = preferred.edge_ids[Math.floor(preferred.edge_ids.length / 2)];
      const point = preferred.path[Math.floor(preferred.path.length / 2)];
      const x=point.longitude, y=point.latitude, d=.0004;
      const firePolygon: FirePolygon = {type:"Polygon",coordinates:[[[x-d,y-d],[x+d,y-d],[x+d,y+d],[x-d,y+d],[x-d,y-d]]]};
      const next = await contextApi.scenario({ ...input,
        blocked_edge_ids: ["road","combined"].includes(experiment) && roadId ? [roadId] : [],
        unavailable_shelter_ids: ["site","combined"].includes(experiment) ? [preferred.shelter.shelter_id] : [],
        fire_polygon: experiment === "fire" ? firePolygon : undefined,
      });
      setResult(next);
    } catch (e) { setError(e instanceof Error ? e.message : "Simulation failed."); }
    finally { setBusy(false); }
  }
  function exportEvidence() {
    if (!result) return;
    const blob = new Blob([JSON.stringify({ application: "WERMS India", report_version: 1, ...result }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob), link = document.createElement("a");
    link.href = url; link.download = `werms-dehradun-scenario-${result.created_at.slice(0, 10)}.json`;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setExportMessage("Download requested. The same JSON evidence is available in the decision record below.");
  }
  return <section className="resilience-lab" aria-label="Resilience lab">
    <div className="lab-heading"><div><span className="section-kicker">EXPERIMENT / OBSERVE / EXPLAIN</span><h2>Test the road ahead.</h2><p>A real graph. A controlled disruption. A decision you can explain.</p></div><span className="lab-sandbox-badge"><i /> ISOLATED WHAT-IF ANALYSIS</span></div>
    <div className="experiment-options">{experiments.map(e => <button disabled={busy} key={e.id} aria-pressed={experiment === e.id} className={experiment === e.id ? "experiment-card selected" : "experiment-card"} onClick={() => { setExperiment(e.id); setResult(undefined); }}><span>{e.icon}</span><strong>{e.title}</strong><p>{e.description}</p></button>)}</div>
    <div className="lab-controls"><label className="form-label">Scenario starting point<select disabled={busy} value={origin} onChange={e => { setOrigin(e.target.value); setResult(undefined); }}>{!network.origins.some(o => o.node === origin) && <option value={origin}>Selected map location</option>}{network.origins.map(o => <option key={o.node} value={o.node}>{o.name}</option>)}</select></label><label className="form-label">Scenario party size<input type="number" min="1" max="20" disabled={busy} value={party} onChange={e => { setParty(Math.max(1, Math.min(20, Number(e.target.value) || 1))); setResult(undefined); }} /></label><button className="primary-action" disabled={busy} onClick={() => { void run(); }}>{busy ? "Comparing both worlds…" : "Run disruption exercise"}<span>↗</span></button></div>
    <p className="lab-boundary">Uses recorded road and capacity conditions. Simulations never change actual closures, bookings, or occupancy.</p>
    {result?.spatial_engine && <p className="lab-boundary"><strong>{result.spatial_engine}</strong> evaluated the perimeter: {result.fire_intersections?.length} intersecting segments excluded by A*. The perimeter is a controlled demonstration.</p>}
    {error && <p role="alert" className="alert critical">{error}</p>}
    {changed && <p role="status" className="lab-changed">Operational state has changed since this run. Run the exercise again for a current comparison.</p>}
    {result && <>
      <div className="lab-outcome"><div><span className="section-kicker">EXPERIMENT RESULT</span><h3>{result.outcome === "rerouted" ? "A different route. A reason for every turn." : result.outcome === "no_route" ? "No eligible route survives this scenario." : result.outcome === "no_baseline_route" ? "No eligible starting route is available." : "The preferred route holds."}</h3><p>{result.destination_changed ? "The preferred destination also changed after the disruption." : "Compared from the same operational snapshot and party size."}</p></div><button className="secondary-action" onClick={exportEvidence}>Download scenario evidence ↓</button></div>
      {exportMessage && <p role="status" className="lab-boundary">{exportMessage}</p>}
      <div className="lab-metrics"><div><span>REACHABLE DESTINATIONS</span><strong>{result.reachable_before} <small>→</small> {result.reachable_after}</strong></div><div><span>ESTIMATED TIME CHANGE</span><strong>{result.delta_minutes === null ? "N/A" : `${result.delta_minutes > 0 ? "+" : ""}${result.delta_minutes}`}<small>{result.delta_minutes !== null ? " min" : ""}</small></strong></div><div><span>DISTANCE CHANGE</span><strong>{result.delta_km === null ? "N/A" : `${result.delta_km > 0 ? "+" : ""}${result.delta_km}`}<small>{result.delta_km !== null ? " km" : ""}</small></strong></div><div><span>SERVER COMPARISON TIME</span><strong>{Math.round(result.compute_ms)}<small> ms</small></strong></div></div>
      <div className="lab-comparison"><article><span className="comparison-key baseline" /> BASELINE<strong>{baseline?.shelter.name ?? "No eligible destination"}</strong><p>{baseline ? `${baseline.distance_km} km · ${baseline.estimated_minutes} estimated min` : "Review current closures and capacity."}</p></article><article><span className="comparison-key simulated" /> AFTER DISRUPTION<strong>{simulated?.shelter.name ?? "No eligible destination"}</strong><p>{simulated ? `${simulated.distance_km} km · ${simulated.estimated_minutes} estimated min` : "A controlled no-route result; no substitute path was fabricated."}</p></article></div>
    </>}
    <div className="lab-map-legend"><span><i className="baseline" />Baseline route</span><span><i className="simulated" />Scenario route</span><span><i className="blocked" />Simulated closure</span></div>
    <RealWorldMap network={network} plan={mainPlan} comparisonPlan={baselinePlan} blocked={snapshot?.hazard.blocked_edge_ids} scenarioBlocked={[...(result?.inputs.blocked_edge_ids ?? []),...(result?.fire_intersections ?? [])]} firePolygon={result?.inputs.fire_polygon} origin={origin} onOrigin={busy ? undefined : id => { setOrigin(id); setResult(undefined); }} />
    {result ? <details className="lab-method"><summary>Inspect the decision record</summary><dl><dt>Road version</dt><dd>{result.road_version}</dd><dt>Snapshot revision</dt><dd>{result.snapshot_revision}</dd><dt>Created</dt><dd>{indiaTime(result.created_at)} IST</dd><dt>Simulated blocked segment</dt><dd>{result.inputs.blocked_edge_ids.map(id => `${network.roads.find(r => r.id === id)?.name} (${id})`).join(", ") || "None"}</dd><dt>Unavailable site</dt><dd>{result.inputs.unavailable_shelter_ids.map(id => network.shelters.find(s => s.id === id)?.name).join(", ") || "None"}</dd></dl><p>Hazard-aware A* respects imported one-way rules, recorded hard closures, and full-party capacity. Weather is shown as context and does not alter routing. The comparison time is this server request, not a load-test percentile.</p><details><summary>Show raw JSON evidence</summary><pre className="json-evidence">{JSON.stringify({ application: "WERMS India", report_version: 1, ...result }, null, 2)}</pre></details></details> : <div className="lab-empty"><span>READY WHEN YOU ARE</span><h3>See how the response holds up.</h3><p>Choose an experiment above. The lab computes a baseline, applies the selected disruption to a copy of that state, and compares the result.</p></div>}
  </section>;
}

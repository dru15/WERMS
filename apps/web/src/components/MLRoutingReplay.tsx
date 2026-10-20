import {useState} from "react";
import {request} from "../api";
import type {Network,Plan} from "../network";
import {RealWorldMap} from "./RealWorldMap";

type Route = {node_ids:string[];edge_ids:string[];shelter_id:string;distance_km:number;estimated_minutes:number;total_cost:number};
type Replay = Route & {network:Network;baseline:Route;model:string;model_version:string;cohort_probability:number;
  projected_segments:number;covered_route_segments:number;unscored_route_segments:number;risk_scores:Record<string,number>;
  case:{reference_date:string;cohort:string;purpose:string;label:number};origin_node_id:string;spatial_engine:string;scope:string};

function plan(replay:Replay,route:Route):Plan {
  return {nodes:route.node_ids,edges:route.edge_ids,km:route.distance_km,minutes:route.estimated_minutes,
    shelter:replay.network.shelters.find(s=>s.id===route.shelter_id)!};
}

export function MLRoutingReplay() {
  const [result,setResult]=useState<Replay>(),[busy,setBusy]=useState(false),[error,setError]=useState("");
  async function run(){setBusy(true);setError("");try{setResult(await request<Replay>("/api/v1/ml/routing/replay",{method:"POST"}));}catch(e){setError(e instanceof Error?e.message:'Replay failed.');}finally{setBusy(false);}}
  return <section className="ml-panel"><p className="eyebrow">MODEL → POSTGIS → HAZARD-AWARE A*</p><h3>Trace a score into a road decision</h3><p>This separate California replay uses a real, unused-cohort FireCastRL window and real OSM roads. The score adds a distance-weighted soft exposure penalty. Hard exclusions and full-party shelter capacity stay enforced. This historical case is excluded from reported evaluation metrics; the road and capacity snapshot is a current demonstration.</p>
    <button className="primary-action" disabled={busy} onClick={()=>{void run();}}>{busy?'Running inference and spatial routing…':'Run real ML routing replay ↗'}</button>
    {error&&<p role="alert">{error}</p>}
    {result&&<><div className="ml-data-strip"><div><b>{(result.cohort_probability*100).toFixed(1)}%</b><span>selected model cohort score</span></div><div><b>{result.projected_segments}</b><span>roads joined through PostGIS</span></div><div><b>{result.covered_route_segments}</b><span>scored segments on chosen route</span></div><div><b>{result.total_cost.toFixed(2)}</b><span>travel + exposure + capacity cost</span></div></div>
      <p>{result.model} · case reference {result.case.reference_date} · source label {result.case.label?'ignition':'negative'} · {result.case.cohort} cohort · {result.spatial_engine}. {result.node_ids.join('|')===result.baseline.node_ids.join('|')?'The preferred path remains the same after applying the penalty.':'The soft risk penalty changes the preferred path.'} Unscored segments: {result.unscored_route_segments} (unknown, not zero predicted risk).</p>
      <p>Amber roads carry the score inside a 3 km experimental support neighbourhood, not a measured grid footprint. Blue is the ML-informed route; dashed purple is the baseline. A model score is not a route-safety probability. This replay creates no booking.</p>
      <RealWorldMap network={result.network} plan={plan(result,result)} comparisonPlan={plan(result,result.baseline)} origin={result.origin_node_id} riskScores={result.risk_scores}/>
    </>}
  </section>;
}

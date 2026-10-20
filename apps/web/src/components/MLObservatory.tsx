import { useEffect, useState } from "react";
import { request } from "../api";
import {MLRoutingReplay} from "./MLRoutingReplay";

type Metrics = { auroc: number; auprc: number; recall: number; f1: number; brier: number; ece: number; prevalence: number; samples: number;
  reliability_bins: { mean_probability: number | null; observed_frequency: number | null; count: number }[] };
type ModelResult = { id: string; name: string; calibrated: Metrics; uncalibrated: Metrics; seconds: number };
type Report = { status: string; message?: string; source_url: string; coverage: string;
  dataset?: { windows: number; raw_rows: number; accepted: number; quarantined: number; sha256: string };
  splits?: Record<string, { samples: number; positives: number; years: string }>;
  models: ModelResult[]; cases: { id: string; label: number; reference_date: string }[]; version?: string; champion?: string; routing_replay?:{id:string} };
type Case = { id: string; label: number; reference_date: string; latitude: number; longitude: number;
  variables: string[]; dates: string[]; sequence: number[][]; predictions: Record<string, number> };
const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
type Inference = { predictions: Record<string,number>; elapsed_ms: number; method: string;
  sensitivity: Record<string, {variable: string; probability_delta: number}[]>; case_id: string };

export function MLObservatory() {
  const [report, setReport] = useState<Report>(), [error, setError] = useState("");
  const [selected, setSelected] = useState(""), [model, setModel] = useState("");
  const [sample, setSample] = useState<Case>(), [variable, setVariable] = useState("vpd");
  const [inference, setInference] = useState<Inference>(), [running, setRunning] = useState(false);
  useEffect(() => { let active = true; request<Report>("/api/v1/ml/report").then(r => {
    if (!active) return; setReport(r); setSelected(r.cases[0]?.id ?? ""); setModel(r.models[0]?.id ?? "");
  }).catch(e => { if (active) setError(String(e.message)); }); return () => { active = false; }; }, []);
  useEffect(() => { if (!selected) return; let active = true;
    request<Case>(`/api/v1/ml/cases/${encodeURIComponent(selected)}`).then(r => { if (active) setSample(r); })
      .catch(e => { if (active) setError(e.message); }); return () => { active = false; };
  }, [selected]);
  const result = report?.models.find(m => m.id === model);
  const values = sample?.sequence.map(row => row[sample.variables.indexOf(variable)]) ?? [];
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  async function infer() {
    setRunning(true); setError("");
    try { setInference(await request<Inference>(`/api/v1/ml/cases/${encodeURIComponent(selected)}/infer`, {method:"POST"})); }
    catch(e) { setError(e instanceof Error ? e.message : "Inference failed"); }
    finally { setRunning(false); }
  }
  return <div className="ml-observatory">
    <section className="ml-hero"><div><p className="eyebrow">WERMS / MACHINE LEARNING OBSERVATORY</p>
      <h2>See the evidence.<br/><em>Follow the prediction.</em></h2>
      <p>From sixty days of environmental history to an auditable ignition score. Inspect the data, compare three model families, and test probability calibration.</p></div>
      <div className="ml-architecture"><span>01 / GRIDMET + IRWIN</span><b>60 days × 15 variables</b><span>02 / CAUSAL SEQUENCES</span><b>Logistic · Boosted trees · GRU</b><span>03 / CALIBRATION + EVALUATION</span><b>Spatial risk → hazard-aware A*</b></div></section>
    <div className="ml-coverage"><strong>Coverage boundary</strong><p>FireCastRL covers the continental US. Its probabilities are research results, not calibrated India forecasts. Dehradun routing keeps hard closures and capacity rules; US scores are not silently transferred.</p></div>
    {error && <p role="alert">{error}</p>}
    {!report && !error && <p role="status">Loading experiment evidence…</p>}
    {report && report.status !== "evaluated" && <section className="ml-panel"><p className="eyebrow">TRAINING STATUS</p><h3>No trained result published yet</h3><p>{report.message}</p><a href={report.source_url} target="_blank" rel="noreferrer">Inspect the public FireCastRL source ↗</a></section>}
    {report?.dataset && <section className="ml-data-strip" aria-label="Verified dataset counts">{[
      [report.dataset.windows.toLocaleString(), "audited event windows"], [report.dataset.raw_rows.toLocaleString(), "source temporal records"],
      [report.dataset.accepted.toLocaleString(), "causal sequences accepted"], [report.dataset.quarantined.toLocaleString(), "windows quarantined"],
    ].map(([value, label]) => <div key={label}><b>{value}</b><span>{label}</span></div>)}</section>}
    {!!report?.models.length && <>
      <section className="ml-panel"><div className="ml-section-title"><div><p className="eyebrow">SAME SPLITS / UNTOUCHED TEST</p><h3>Model comparison</h3></div><span>{report.version}</span></div>
        <div className="ml-model-grid">{report.models.map(m => <button key={m.id} className={`ml-model-card ${model === m.id ? "selected" : ""}`} onClick={() => setModel(m.id)} aria-pressed={model === m.id}>
          <h4>{m.name}</h4>{report.champion===m.id&&<span>VALIDATION-SELECTED MODEL</span>}<p>AUROC <b>{m.calibrated.auroc.toFixed(3)}</b></p><div className="ml-score-bar"><i style={{width: pct(m.calibrated.auroc)}}/></div>
          <dl>{([['AUPRC',m.calibrated.auprc],['Recall',m.calibrated.recall],['F1',m.calibrated.f1],['Brier ↓',m.calibrated.brier]] as const).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value.toFixed(3)}</dd></div>)}</dl>
          <span>{m.seconds.toFixed(1)} s training · select to inspect</span></button>)}</div><p>Test cohort: {report.models[0].calibrated.samples} cases · ignition prevalence {pct(report.models[0].calibrated.prevalence)} · no-skill AUPRC {report.models[0].calibrated.prevalence.toFixed(3)}. The selected model follows validation AUPRC; test results do not decide the winner. Calibration error remains substantial under this prevalence shift.</p></section>
      {result && <section className="ml-panel ml-calibration"><div><p className="eyebrow">SEPARATE-COHORT PLATT CALIBRATION</p><h3>Does 70% mean 70%?</h3><p>Each point compares a probability bin with its observed frequency in the held-out test cohort. The diagonal is perfect calibration.</p><p><strong>{result.name}</strong><br/>ECE: {result.uncalibrated.ece.toFixed(3)} → {result.calibrated.ece.toFixed(3)}<br/>Brier: {result.uncalibrated.brier.toFixed(3)} → {result.calibrated.brier.toFixed(3)}</p><small>Case-control sampling changes prevalence. Calibration here describes the released cohort; it does not establish population wildfire incidence.</small></div>
        <svg viewBox="0 0 360 300" role="img" aria-label={`${result.name} probability calibration curve`}><path d="M45 20V255H325" fill="none" stroke="#9baaa2"/><path d="M45 255L325 20" stroke="#b3bdb6" strokeDasharray="5 5"/>{[result.uncalibrated,result.calibrated].map((metrics,i)=><g key={i} fill={i ? '#177c59':'#aa8865'}>{metrics.reliability_bins.filter(b=>b.count).map((b,j)=><circle key={j} cx={45+280*b.mean_probability!} cy={255-235*b.observed_frequency!} r={4+Math.min(5,Math.sqrt(b.count)/20)}><title>{`${i ? 'Calibrated':'Raw'}: predicted ${pct(b.mean_probability!)}, observed ${pct(b.observed_frequency!)}, n=${b.count}`}</title></circle>)}</g>)}<text x="125" y="288">Predicted probability</text><text x="18" y="18">Observed frequency</text><text x="48" y="245" fill="#aa8865">● raw</text><text x="48" y="225" fill="#177c59">● calibrated</text></svg></section>}
      <section className="ml-panel"><p className="eyebrow">HELD-OUT CASE EXPLORER</p><h3>Sixty days before the reference date</h3>
        <div className="ml-case-controls"><label>Test case<select value={selected} onChange={e=>setSelected(e.target.value)}>{report.cases.map(c=><option key={c.id} value={c.id}>{c.reference_date} · {c.label ? 'ignition':'negative'} · {c.id}</option>)}</select></label><label>Environmental variable<select value={variable} onChange={e=>setVariable(e.target.value)}>{(sample?.variables ?? ['vpd']).map(v=><option key={v}>{v}</option>)}</select></label></div>
        {sample && <><p>{sample.latitude.toFixed(3)}°, {sample.longitude.toFixed(3)}° · Reference {sample.reference_date} · Actual label: <strong>{sample.label ? 'ignition':'negative'}</strong></p>
          <svg className="ml-sequence" viewBox="0 0 800 180" role="img" aria-label={`60-day ${variable} history excluding the reference date`}><path d="M35 15V150H780" fill="none" stroke="#a7b6ab"/><polyline points={values.map((v,i)=>`${35+i*745/59},${145-(v-min)/span*125}`).join(' ')} fill="none" stroke="#177c59" strokeWidth="2.5"/><text x="35" y="174">t−60</text><text x="740" y="174">t−1</text><text x="40" y="15">{variable} · {min.toFixed(2)} to {max.toFixed(2)} (standardized units)</text></svg>
          <div className="ml-predictions">{report.models.map(m=><div key={m.id}><span>{m.name}</span><b>{pct(sample.predictions[m.id])}</b><small>calibrated cohort probability</small></div>)}</div></>}
        {sample && <div className="ml-live-inference"><button className="primary-action" disabled={running || sample.id !== selected} onClick={() => {void infer();}}>{running ? 'Computing model outputs…' : 'Run all three models + explain sensitivity ↗'}</button>
          {inference?.case_id === selected && <><p>Fresh CPU inference · {inference.elapsed_ms} ms · {inference.method}</p><div className="ml-predictions">{report.models.map(m=><div key={m.id}><span>{m.name}</span><b>{pct(inference.predictions[m.id])}</b>{inference.sensitivity[m.id].map(s=><small key={s.variable}>{s.variable}: {s.probability_delta >= 0 ? '+' : ''}{(s.probability_delta*100).toFixed(2)} percentage points</small>)}</div>)}</div></>}
        </div>}
      </section>
      <section className="ml-panel"><p className="eyebrow">REPRODUCIBILITY RECORD</p><h3>Chronology and geography stay separated</h3><div className="ml-splits">{Object.entries(report.splits ?? {}).map(([key,s])=><div key={key}><strong>{key}</strong><b>{s.samples.toLocaleString()}</b><span>{s.years} · {s.positives.toLocaleString()} positives</span></div>)}</div><p>Preprocessing fits training only. Early stopping and decision thresholds use validation. Probability calibration uses a separate calibration cohort. Test labels are used only for the final report.</p><details><summary>Dataset fingerprint and source</summary><p className="ml-hash">SHA-256 {report.dataset?.sha256}</p><a href={report.source_url} target="_blank" rel="noreferrer">FireCastRL public release ↗</a></details></section>
    </>}
    {report?.routing_replay&&<MLRoutingReplay/>}
  </div>;
}

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import { staffApi } from "../staff";
import type { Audit, CommandState, Incident, Resource, StaffUser } from "../staff";
import type { Shelter } from "../types";
import { FireExclusionPanel } from "./FireExclusionPanel";

type Props = { credential: string; user?: StaffUser; shelters: Shelter[];
  roads: { id: string; name: string }[]; onSession: (key: string, user: StaffUser) => void;
  onLock: () => void; onRefresh: () => Promise<void> };

function ShelterEditor({ shelter, credential, run, disabled }: {
  shelter: Shelter; credential: string; run: (action: () => Promise<unknown>, message: string) => Promise<void>; disabled: boolean;
}) {
  const [occupancy, setOccupancy] = useState(shelter.occupancy);
  const [status, setStatus] = useState(shelter.status);
  const [reason, setReason] = useState("");
  return <form className="command-card" onSubmit={e => { e.preventDefault(); void run(() => staffApi.shelter(credential, shelter.shelter_id, occupancy, status, shelter.updated_at, reason), "Assembly site updated. Incoming bookings were rechecked."); }}>
    <h3>{shelter.name}</h3><p>{shelter.reserved_demand} reserved · {shelter.capacity} capacity</p>
    <label className="form-label">Checked-in occupancy<input type="number" min="0" max={shelter.capacity} required value={occupancy} onChange={e => setOccupancy(Number(e.target.value))} /></label>
    <label className="form-label">Site status<select value={status} onChange={e => setStatus(e.target.value as Shelter["status"])}><option value="open">Open</option><option value="restricted">Restricted · no new bookings</option><option value="closed">Closed · invalidate incoming bookings</option></select></label>
    <label className="form-label">Reason for site update<input required minLength={3} maxLength={300} value={reason} onChange={e => setReason(e.target.value)} /></label>
    <button className="secondary-action" disabled={disabled}>Save site update</button>
  </form>;
}

export function CommandCentre({ credential, user, shelters, roads, onSession, onLock, onRefresh }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [bootstrap, setBootstrap] = useState("");
  const [state, setState] = useState<CommandState>();
  const [accounts, setAccounts] = useState<StaffUser[]>([]);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const serial = useRef(0);
  const acting = useRef(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [source, setSource] = useState("");
  const [priority, setPriority] = useState<Incident["priority"]>("high");
  const [road, setRoad] = useState("");
  const [observed, setObserved] = useState("");
  const [resourceName, setResourceName] = useState("");
  const [kind, setKind] = useState<Resource["kind"]>("engine");
  const [resourceId, setResourceId] = useState("");
  const [incidentId, setIncidentId] = useState("");
  const [note, setNote] = useState("");
  const [accountName, setAccountName] = useState("");
  const [accountPassword, setAccountPassword] = useState("");
  const [role, setRole] = useState<StaffUser["role"]>("dispatcher");
  const [site, setSite] = useState("");
  const [arrival, setArrival] = useState("");
  const pendingDispatch = useRef<{ fingerprint: string; id: string } | undefined>(undefined);
  const dispatcher = user?.role === "admin" || user?.role === "dispatcher";

  async function load() {
    if (!credential) return;
    const generation = ++serial.current;
    const next = await staffApi.state(credential);
    if (generation !== serial.current) return;
    setState(next); setError("");
    if (user?.role === "admin") {
      const [nextAccounts, nextAudit] = await Promise.all([staffApi.accounts(credential), staffApi.audit(credential)]);
      if (generation === serial.current) { setAccounts(nextAccounts); setAudit(nextAudit); }
    }
  }
  const loadRef = useRef(load);
  useEffect(() => { loadRef.current = load; });
  useEffect(() => {
    let stopped = false;
    const invalidate = () => { ++serial.current; };
    const poll = async () => {
      if (acting.current) return;
      try { await loadRef.current(); } catch (e) {
        if (!stopped) { setError(e instanceof Error ? e.message : "Command updates unavailable."); if (e instanceof ApiError && e.status === 401) setState(undefined); }
      }
    };
    void poll(); const timer = setInterval(() => { void poll(); }, 8000);
    return () => { stopped = true; invalidate(); clearInterval(timer); };
  }, [credential]);

  async function run(action: () => Promise<unknown>, success: string) {
    if (acting.current) return;
    acting.current = true; ++serial.current; setBusy(true); setError("");
    try { await action(); setMessage(success); await Promise.all([load(), onRefresh()]); }
    catch (e) { setError(e instanceof Error ? e.message : "Action failed."); }
    finally { acting.current = false; setBusy(false); }
  }
  async function signOut() {
    setBusy(true);
    try { await staffApi.logout(credential); }
    catch { setError("Local staff access was locked. The service could not confirm session revocation."); }
    finally { ++serial.current; setState(undefined); setAudit([]); setAccounts([]); onLock(); setBusy(false); }
  }

  return <section className="command-centre" aria-label="Command centre">
    <div className="command-heading"><div><span className="section-kicker">Shared incident and resource workspace</span><h2>Command centre</h2></div>{credential && <button className="secondary-action" disabled={busy} onClick={() => { void signOut(); }}>Sign out of staff access</button>}</div>
    <p>Reports and inventory here are entered by project operators. Reporting an incident does not close a road; a dispatcher must explicitly update the map closure.</p>
    {message && <p role="status" className="activity-message">{message}</p>}
    {error && <p role="alert" className="alert critical">{error} Refresh before relying on displayed command state.</p>}
    {!credential ? <div className="command-grid">
      <form className="command-card" onSubmit={e => { e.preventDefault(); void run(async () => { const session = await staffApi.login(username, password); setPassword(""); onSession(`session:${session.token}`, session.user); }, "Staff access enabled for this tab."); }}>
        <h3>Staff sign-in</h3><label className="form-label">Username<input autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)} /></label>
        <label className="form-label">Password<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
        <button className="primary-action" disabled={busy}>Sign in</button>
      </form>
      <form className="command-card" onSubmit={e => { e.preventDefault(); void run(async () => { await api.access(bootstrap); onSession(bootstrap, { username: "bootstrap-admin", role: "admin", shelter_id: null }); setBootstrap(""); }, "Administrator access enabled. Create named staff accounts below."); }}>
        <h3>First-time administrator setup</h3><p>Use the local operator key generated when the API first starts. Create staff accounts after unlocking.</p>
        <label className="form-label">Administrator setup key<input type="password" autoComplete="off" value={bootstrap} required onChange={e => setBootstrap(e.target.value)} /></label>
        <button className="secondary-action" disabled={busy}>Unlock administration</button>
      </form>
    </div> : <>
      <p className="staff-identity">Signed in as <strong>{user?.username ?? "operator"}</strong> · {user?.role ?? "admin"} · session expires after eight hours for named accounts</p>
      <button className="secondary-action" disabled={busy} onClick={() => { void run(async () => {}, "Command state refreshed."); }}>Refresh command state</button>
      <div className="command-grid">
        {dispatcher && <form className="command-card" onSubmit={e => { e.preventDefault(); void run(async () => { await staffApi.report(credential, { title, description, source, priority, road_id: road || null, observed_at: new Date(observed).toISOString() }); setTitle(""); setDescription(""); }, "Incident reported with its source and observation time."); }}>
          <h3>Report an incident</h3>
          <label className="form-label">Incident title<input required minLength={3} maxLength={120} value={title} onChange={e => setTitle(e.target.value)} /></label>
          <label className="form-label">Description<textarea required minLength={3} maxLength={2000} value={description} onChange={e => setDescription(e.target.value)} /></label>
          <label className="form-label">Report source<input required minLength={3} maxLength={200} placeholder="Exercise report / operator observation" value={source} onChange={e => setSource(e.target.value)} /></label>
          <label className="form-label">Observed at · your local time<input type="datetime-local" required value={observed} onChange={e => setObserved(e.target.value)} /></label>
          <label className="form-label">Priority<select value={priority} onChange={e => setPriority(e.target.value as Incident["priority"])}>{["low", "medium", "high", "critical"].map(p => <option key={p}>{p}</option>)}</select></label>
          <label className="form-label">Affected road · optional<select value={road} onChange={e => setRoad(e.target.value)}><option value="">No road specified</option>{roads.map(r => <option key={r.id} value={r.id}>{r.name} · {r.id}</option>)}</select></label>
          <button className="primary-action" disabled={busy}>Save incident report</button>
        </form>}
        {dispatcher && <div className="command-card"><form onSubmit={e => { e.preventDefault(); void run(async () => { await staffApi.resource(credential, resourceName, kind); setResourceName(""); }, "Resource registered as available."); }}>
          <h3>Resource inventory</h3><label className="form-label">Resource name<input required minLength={3} maxLength={100} value={resourceName} onChange={e => setResourceName(e.target.value)} /></label>
          <label className="form-label">Resource type<select value={kind} onChange={e => setKind(e.target.value as Resource["kind"])}><option value="engine">Fire engine</option><option value="bus">Evacuation bus</option><option value="ambulance">Ambulance</option><option value="supply_team">Supply team</option></select></label>
          <button className="secondary-action" disabled={busy}>Register resource</button></form>
          <ul className="command-list">{state?.resources.map(r => <li key={r.id}><strong>{r.name}</strong><span>{r.kind.replaceAll("_", " ")} · {r.status}</span>{r.status !== "deployed" && <button disabled={busy} onClick={() => { void run(() => staffApi.availability(credential, r.id, r.status !== "offline"), "Resource availability updated."); }}>{r.status === "offline" ? "Mark available" : "Take offline"}</button>}</li>)}</ul>
          {state?.resources.length === 0 && <p>No resources registered yet.</p>}
        </div>}
        {dispatcher && <form className="command-card" onSubmit={e => { e.preventDefault(); const fingerprint = JSON.stringify([resourceId, incidentId, note]); if (pendingDispatch.current?.fingerprint !== fingerprint) pendingDispatch.current = { fingerprint, id: crypto.randomUUID() }; const requestId = pendingDispatch.current.id; void run(async () => { await staffApi.dispatch(credential, resourceId, incidentId, note, requestId); pendingDispatch.current = undefined; setNote(""); }, "Resource dispatched. Await acknowledgement before completing the assignment."); }}>
          <h3>Dispatch a resource</h3><label className="form-label">Available resource<select required value={resourceId} onChange={e => setResourceId(e.target.value)}><option value="">Choose resource</option>{state?.resources.filter(r => r.status === "available").map(r => <option key={r.id} value={r.id}>{r.name} · {r.kind}</option>)}</select></label>
          <label className="form-label">Active incident<select required value={incidentId} onChange={e => setIncidentId(e.target.value)}><option value="">Choose incident</option>{state?.incidents.filter(i => i.status !== "resolved").map(i => <option key={i.id} value={i.id}>{i.title} · {i.priority}</option>)}</select></label>
          <label className="form-label">Dispatch instructions<textarea required minLength={3} maxLength={300} value={note} onChange={e => setNote(e.target.value)} /></label>
          <button className="primary-action" disabled={busy || !state}>Dispatch selected resource</button><p>Assignments reserve the unit atomically. Instructions and acknowledgements are recorded here; external radio delivery is outside this pilot.</p>
        </form>}
      </div>
      <section className="command-section"><h3>Incident board</h3>{state?.incidents.length === 0 && <p>No incidents reported yet.</p>}<div className="command-grid">{state?.incidents.map(i => <article className="command-card" key={i.id}><span className={`priority-badge ${i.priority}`}>{i.priority} · {i.status}</span><h4>{i.title}</h4><p>{i.description}</p><p className="preview-note">Source: {i.source}<br />Observed {new Date(i.observed_at).toLocaleString()}{i.road_id && <><br />Road: {roads.find(r => r.id === i.road_id)?.name ?? i.road_id}</>}</p>{dispatcher && i.status !== "resolved" && <div className="command-actions">
        <button disabled={busy} onClick={() => { void run(() => staffApi.incident(credential, i, i.status === "reported" ? "acknowledged" : "resolved", i.priority, i.status === "reported" ? "Operator acknowledged report" : "Operator resolved incident"), "Incident status updated."); }}>{i.status === "reported" ? "Acknowledge report" : "Resolve incident"}</button>
        {i.priority !== "critical" && <button disabled={busy} onClick={() => { void run(() => staffApi.incident(credential, i, i.status, "critical", "Operator escalated incident to critical"), "Incident escalated to critical priority."); }}>Escalate to critical</button>}
      </div>}</article>)}</div></section>
      <section className="command-section"><h3>Assignment board</h3>{state?.assignments.length === 0 && <p>No assignments yet.</p>}<div className="command-grid">{state?.assignments.map(a => <article className="command-card" key={a.id}><span className="route-state ready">{a.status}</span><h4>{state.resources.find(r => r.id === a.resource_id)?.name}</h4><p>{state.incidents.find(i => i.id === a.incident_id)?.title}</p><p>{a.note}</p><small>Updated {new Date(a.updated_at).toLocaleString()}</small>{dispatcher && ["dispatched", "acknowledged"].includes(a.status) && <div className="command-actions"><button disabled={busy} onClick={() => { void run(() => staffApi.assignment(credential, a.id, a.status === "dispatched" ? "acknowledged" : "resolved", a.status === "dispatched" ? "Operator recorded unit acknowledgement" : "Operator recorded completed assignment"), "Assignment updated."); }}>{a.status === "dispatched" ? "Acknowledge assignment" : "Complete assignment"}</button><button disabled={busy} onClick={() => { void run(() => staffApi.assignment(credential, a.id, "cancelled", "Operator cancelled assignment"), "Assignment cancelled; resource released."); }}>Cancel assignment</button></div>}</article>)}</div></section>
      <section className="command-section"><h3>Assembly-site administration</h3><p>Restricted sites stop new bookings. Closing a site also invalidates active incoming bookings. Occupancy corrections require a reason.</p><div className="command-grid">{shelters.filter(s => user?.role !== "shelter" || s.shelter_id === user.shelter_id).map(s => <ShelterEditor key={`${s.shelter_id}-${s.updated_at}`} shelter={s} credential={credential} run={run} disabled={busy} />)}
        <form className="command-card" onSubmit={e => { e.preventDefault(); void run(async () => { await api.arrive(arrival.trim(), credential); setArrival(""); }, "Party checked in. Repeating the same booking does not add people twice."); }}><h3>Check in a booking</h3><label className="form-label">Arrival booking code<input required value={arrival} onChange={e => setArrival(e.target.value)} /></label><button className="primary-action" disabled={busy}>Check in booking</button></form>
      </div></section>
      {user?.role === "admin" && <section className="command-section"><h3>Staff administration</h3><div className="command-grid"><form className="command-card" onSubmit={e => { e.preventDefault(); void run(async () => { await staffApi.account(credential, { username: accountName, password: accountPassword, role, shelter_id: role === "shelter" ? site : null }); setAccountName(""); setAccountPassword(""); }, "Named staff account created."); }}>
        <label className="form-label">New username<input required minLength={3} maxLength={64} pattern="[a-zA-Z0-9_.-]+" value={accountName} onChange={e => setAccountName(e.target.value)} /></label>
        <label className="form-label">Initial password · at least 12 characters<input type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={accountPassword} onChange={e => setAccountPassword(e.target.value)} /></label>
        <label className="form-label">Staff role<select value={role} onChange={e => setRole(e.target.value as StaffUser["role"])}><option value="dispatcher">Dispatcher</option><option value="shelter">Shelter staff</option><option value="admin">Administrator</option></select></label>
        {role === "shelter" && <label className="form-label">Assigned assembly site<select required value={site} onChange={e => setSite(e.target.value)}><option value="">Choose site</option>{shelters.map(s => <option key={s.shelter_id} value={s.shelter_id}>{s.name}</option>)}</select></label>}
        <button className="primary-action" disabled={busy}>Create staff account</button>
      </form><div className="command-card"><h4>Registered staff</h4><ul className="command-list">{accounts.map(a => <li key={a.username}><strong>{a.username}</strong><span>{a.role} · {a.enabled ? "enabled" : "disabled"}</span>{Boolean(a.enabled) && a.username !== user.username && <button disabled={busy} onClick={() => { void run(() => staffApi.disable(credential, a.username), "Account disabled and sessions revoked."); }}>Disable account</button>}</li>)}</ul></div></div>
      <details className="audit-log"><summary>Audit trail · latest 100 events</summary><ol>{audit.map(a => <li key={a.sequence}><strong>{a.action}</strong> · {a.actor}<br /><small>{new Date(a.timestamp).toLocaleString()} · {a.entity_id}</small><p>{a.details}</p></li>)}</ol></details></section>}
    </>}
    {dispatcher && <FireExclusionPanel credential={credential} onRefresh={onRefresh} />}
  </section>;
}

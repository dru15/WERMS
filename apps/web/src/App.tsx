import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { clearPending, readPending, savePending } from "./confirmation";
import { OperationsMap } from "./components/OperationsMap";
import { CommandCentre } from "./components/CommandCentre";
import type { StaffUser } from "./staff";
import type { Plan } from "./network";
import type { RouteInput, RoutePreview } from "./types";
import { useOperations } from "./useOperations";

export default function App() {
  const { network, snapshot, route, connection, error, lastSync, refresh, remember } = useOperations();
  const [tab, setTab] = useState("Operations");
  const [origin, setOrigin] = useState("");
  const [party, setParty] = useState(2);
  const [traffic, setTraffic] = useState(true);
  const [plans, setPlans] = useState<RoutePreview[]>([]);
  const [selected, setSelected] = useState<RoutePreview>();
  const [progress, setProgress] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("Choose a starting point and compare destinations. Your saved booking appears below.");
  const [events, setEvents] = useState<string[]>([]);
  const [now, setNow] = useState(() => Date.now());
  const [keyInput, setKeyInput] = useState("");
  const [operatorKey, setOperatorKey] = useState("");
  const [staffUser, setStaffUser] = useState<StaffUser>();
  const [arrivalCode, setArrivalCode] = useState("");
  const previewSerial = useRef(0);
  const confirmation = useRef<{ fingerprint: string; id: string } | undefined>(undefined);
  const blocked = snapshot?.hazard.blocked_edge_ids ?? [];
  const displayed = selected ?? (route?.status === "cancelled" ? undefined : route);
  const selectedOrigin = origin || network?.origins[0].node || "";
  const connected = connection === "connected" && lastSync !== undefined && now - lastSync < 20000;
  const expired = Boolean(displayed && Date.parse(displayed.valid_until) <= now);
  const invalid = Boolean(displayed && (expired || displayed.edge_ids.some(e => blocked.includes(e))
    || (!selected && route && route.status !== "valid" && route.status !== "arrived")));
  const viewPlan: Plan | undefined = useMemo(() => displayed && ({
    nodes: displayed.path.map(p => p.node_id), edges: displayed.edge_ids,
    minutes: displayed.estimated_minutes, km: displayed.distance_km,
    shelter: { id: displayed.shelter.shelter_id, node: displayed.shelter.node_id,
      name: displayed.shelter.name, capacity: displayed.shelter.capacity,
      occupancy: displayed.shelter.occupancy + displayed.shelter.reserved_demand },
  }), [displayed]);
  const realWorld = network?.data_mode === "osm-pilot";
  const mapNetwork = realWorld ? network : network && { ...network, shelters: network.shelters.map(s => {
    const state = snapshot?.shelters.find(item => item.shelter_id === s.id);
    return { ...s, occupancy: state ? state.occupancy + state.reserved_demand : s.occupancy };
  }) };

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (!playing || invalid || !connected) return;
    const timer = setInterval(() => setProgress(p => Math.min(1, p + 0.008)), 180);
    return () => clearInterval(timer);
  }, [playing, invalid, connected]);

  function log(text: string) { setMessage(text); setEvents(list => [text, ...list].slice(0, 6)); }
  function clearPreview() {
    ++previewSerial.current; setSelected(undefined); setPlans([]); setProgress(0); setPlaying(false);
    confirmation.current = undefined;
  }
  function input(shelterId?: string): RouteInput {
    return { origin_node_id: selectedOrigin, party_size: party, traffic, shelter_id: shelterId };
  }
  async function perform(action: () => Promise<void>) {
    setBusy(true);
    try { await action(); } catch (e) { log(e instanceof Error ? e.message : "Action failed. Retry after checking the connection."); }
    finally { setBusy(false); }
  }
  async function calculate(destination?: string) {
    const generation = ++previewSerial.current;
    setPlaying(false); setProgress(0); setBusy(true);
    try {
      const next = await api.preview(input());
      if (generation !== previewSerial.current) return;
      setPlans(next);
      const chosen = destination ? next.find(p => p.shelter.shelter_id === destination) : next[0];
      setSelected(chosen); setTab("Operations"); confirmation.current = undefined;
      log(chosen ? `Preview ready for ${chosen.shelter.name}. Confirm to reserve ${party} spaces.`
        : "That shelter cannot currently accommodate your party. Choose another destination.");
    } catch (e) {
      if (generation === previewSerial.current) { setPlans([]); setSelected(undefined); log(e instanceof Error ? e.message : "No route available."); }
    } finally { if (generation === previewSerial.current) setBusy(false); }
  }
  async function confirm() {
    if (!selected || invalid) return;
    const request = input(selected.shelter.shelter_id);
    const previous = route && route.status !== "arrived" && route.status !== "cancelled" ? route.route_id : undefined;
    const fingerprint = JSON.stringify([request, previous]);
    if (confirmation.current?.fingerprint !== fingerprint) confirmation.current = { fingerprint, id: crypto.randomUUID() };
    const requestId = confirmation.current.id;
    await perform(async () => {
      const pending = readPending();
      if (pending && pending.fingerprint !== fingerprint) {
        throw new Error("A previous confirmation is still being recovered. Refresh state before confirming another plan.");
      }
      savePending({ input: request, requestId, replaceRouteId: previous, fingerprint });
      const booking = await api.confirm(request, requestId, previous).catch(e => {
        if (e instanceof ApiError && e.status >= 400 && e.status < 500) clearPending(requestId);
        throw e;
      });
      remember(booking); clearPending(requestId); setSelected(undefined); setPlans([]); setProgress(0); setPlaying(false);
      log(booking.status === "valid" ? `Confirmed: ${booking.party_size} spaces reserved at ${booking.shelter.name}.`
        : `The previous confirmation is now ${booking.status}. Compare routes for a new booking.`);
      await refresh();
    });
  }
  async function closeRoad(id: string) {
    if (!operatorKey || busy) return;
    await perform(async () => {
      await api.closure(id, !blocked.includes(id), operatorKey);
      clearPreview();
      log(`${network?.roads.find(r => r.id === id)?.name}: ${blocked.includes(id) ? "reopened" : "closed"}. Current bookings are being checked.`);
      await refresh();
    });
  }
  const reserved = snapshot?.shelters.reduce((sum, s) => sum + s.reserved_demand, 0) ?? 0;

  return <div className="app-shell">
    <header className="topbar">
      <a href="#main" className="brand" onClick={() => setTab("Operations")}><span className="brand-flame">◈</span><span><strong>WERMS</strong><small>Wildfire operations</small></span></a>
      <nav className="primary-nav" aria-label="Primary navigation">{["Operations", "Routes", "Shelters", "Command centre"].map(t => <button key={t} className={tab === t ? "active" : ""} aria-current={tab === t ? "page" : undefined} onClick={() => setTab(t)}>{t}</button>)}</nav>
      <div className="system-strip"><span className={connected ? "status-dot live" : "status-dot"} /><strong>{connection === "loading" ? "Connecting" : connected ? "Service connected" : "Updates unavailable"}</strong><button className="reset-button" disabled={busy} onClick={() => { void refresh(); }}>Refresh state</button></div>
    </header>
    <section className="incident-bar">
      <div className="incident-identity"><span className="incident-icon">◆</span><div><span className="incident-kicker">{!network ? "Connecting to operations service" : realWorld ? "Real-world road pilot / Los Angeles" : "Connected pilot / PR-04"}</span><h1>{!network ? "Loading operations" : realWorld ? "Pacific Palisades operations" : "Pine Ridge Fire"}</h1></div><span className="severity-badge">{!network ? "Awaiting network" : realWorld ? "Demo incident controls" : "Fictional incident"}</span></div>
      <div className="incident-metrics"><div><span>Road network</span><strong>{network?.roads.length ?? "—"} segments</strong></div><div><span>Closures</span><strong>{snapshot ? blocked.length : "—"}</strong></div><div><span>Reserved spaces</span><strong>{snapshot ? reserved : "—"}</strong></div></div>
    </section>
    <main className="app-main" id="main">
      <div className="simulation-notice">{!network ? "Connecting to the shared operations service. Route planning becomes available when its road network and current state arrive." : realWorld ? "Real OpenStreetMap geography and roads. Routing is limited to the marked pilot area. Closures, assembly-site capacities, and travel times are demonstration estimates; these are not verified emergency shelters." : "Connected research pilot. Roads, incidents, travel times, and shelters are fictional. Bookings and road changes are shared and saved by the service."}</div>
      {error && <div className="alert critical" role="alert"><strong>Operations unavailable</strong><span>{error} Displayed plans are unverified until updates resume.</span></div>}
      <div className="activity-message" role="status">{message}</div>
      {invalid && <div className="alert critical" role="alert"><strong>{expired ? "Plan expired" : "Route interrupted"}</strong><span>Compare routes and confirm a new plan. This path is no longer eligible for guidance.</span></div>}
      {!network ? <section className="connection-panel"><h2>{connection === "loading" ? "Loading pilot network…" : "Connect to the operations service"}</h2><p>The app will retry automatically. No local route is substituted for service data.</p><button className="primary-action" onClick={() => { void refresh(); }}>Retry connection</button></section> : tab === "Command centre" ? <CommandCentre credential={operatorKey} user={staffUser} shelters={snapshot?.shelters ?? []} roads={network.roads} onSession={(key, user) => { setOperatorKey(key); setStaffUser(user); }} onLock={() => { setOperatorKey(""); setStaffUser(undefined); }} onRefresh={refresh} /> : <div className="workspace-grid">
        <OperationsMap network={mapNetwork} plan={viewPlan} blocked={blocked} origin={displayed?.path[0]?.node_id ?? selectedOrigin} progress={progress} invalid={invalid || !connected} traffic={traffic}
          onOrigin={id => { if (!busy) { setOrigin(id); clearPreview(); log("Starting point selected on the real road network. Compare routes to continue."); } }}
          onTraffic={busy ? undefined : () => { setTraffic(t => !t); clearPreview(); log("Traffic preference changed. Compare routes to apply it."); }}
          onRoad={operatorKey && staffUser?.role !== "shelter" && connected && !busy ? id => { void closeRoad(id); } : undefined}
          onShelter={id => { if (connected && !busy) void calculate(id); }} />
        <aside className="route-planner">
          <div className="planner-header"><div><span className="section-kicker">{tab === "Operations" ? "Evacuation planner" : "Pilot operations"}</span><h2>{tab === "Operations" ? "Evacuation route" : tab}</h2></div><span className={invalid ? "route-state invalid" : "route-state ready"}>{!connected ? "Unverified" : invalid ? "Invalid" : selected ? "Preview" : route?.status === "arrived" ? "Checked in" : route?.status === "valid" ? "Reserved" : "Plan a route"}</span></div>
          <div className="interactive-panel">
            {(tab === "Operations" || tab === "Routes") && <>
              <label className="form-label">Starting point<select disabled={busy} value={selectedOrigin} onChange={e => { setOrigin(e.target.value); clearPreview(); }}>{origin && !network.origins.some(o => o.node === origin) && <option value={origin}>Selected map location</option>}{network.origins.map(o => <option key={o.node} value={o.node}>{o.name}</option>)}</select></label>
              <label className="form-label">People travelling<input disabled={busy} type="number" min="1" max="20" value={party} onChange={e => { setParty(Math.max(1, Math.min(20, Number(e.target.value) || 1))); clearPreview(); }} /></label>
              <button className="primary-action" disabled={!connected || busy} onClick={() => { void calculate(); }}>{busy ? "Working…" : "Compare evacuation routes"} <span>→</span></button>
              {displayed && <div className="selected-plan"><span className="section-kicker">{selected ? "Preview · no spaces held" : `Booking · ${route?.status}`}</span><h3>{displayed.shelter.name}</h3>
                <div className="journey-metrics"><strong>{displayed.estimated_minutes}<small>min estimated</small></strong><strong>{displayed.distance_km}<small>km</small></strong><strong>{Math.max(0, displayed.shelter.capacity - displayed.shelter.occupancy - displayed.shelter.reserved_demand)}<small>unreserved spaces</small></strong></div>
                <p>{selected ? "Capacity is checked again when you confirm." : `Party size: ${route?.party_size}. Your booking is shared with the shelter.`}</p>
                {realWorld && <p>Demonstration assembly site. The route ends at its nearest mapped road access point; site access is not verified.</p>}
                <p className="preview-note">{selected ? "Preview expires" : "Booking expires"}: {new Date(displayed.valid_until).toLocaleTimeString()} · {displayed.hazard_version}</p>
                <p className="preview-note">Pilot closure state last changed: {new Date(displayed.hazard_source_timestamp).toLocaleString()}{now - Date.parse(displayed.hazard_source_timestamp) > 1800000 ? " · older than 30 minutes" : ""}</p>
                {selected && <button className="primary-action" disabled={invalid || !connected || busy} onClick={() => { void confirm(); }}>{route?.status === "valid" ? "Replace booking with this route" : "Confirm and reserve spaces"}</button>}
                {!selected && route?.status === "valid" && <><p className="booking-code">Booking code <code>{route.route_id}</code></p><button className="secondary-action" disabled={busy || !connected} onClick={() => { void perform(async () => { remember(await api.cancel(route.route_id)); log("Booking cancelled. Its shelter spaces are released."); await refresh(); }); }}>Cancel booking</button></>}
                <progress max="1" value={progress} aria-label="Journey preview progress" />
                <button className="secondary-action" disabled={invalid || !connected || busy || (!selected && route?.status !== "valid")} onClick={() => { if (progress >= 1) setProgress(0); setPlaying(p => progress >= 1 ? true : !p); }}>{playing && !invalid && connected && progress < 1 ? "Pause preview" : "Start preview"}</button>
                <p className="preview-note">Accelerated visual preview · {Math.round(progress * 100)}% · does not check you in</p>
              </div>}
              {plans.length > 0 && <section className="route-options"><h3>Compare destinations</h3>{plans.map(p => <button key={p.shelter.shelter_id} disabled={busy} className={selected?.shelter.shelter_id === p.shelter.shelter_id ? "option selected" : "option"} onClick={() => { setSelected(p); setProgress(0); setPlaying(false); confirmation.current = undefined; }}><span>{p.shelter.name}<small>{p.distance_km} km · {p.edge_ids.length} road segments</small></span><strong>{p.estimated_minutes} min</strong></button>)}</section>}
              {displayed && !invalid && <details className="directions-details"><summary>View route directions</summary><ol>{displayed.edge_ids.map((id, i) => <li key={id}>Follow {network.roads.find(r => r.id === id)?.name}{i === displayed.edge_ids.length - 1 ? ` to ${displayed.shelter.name}` : ""}.</li>)}</ol></details>}
            </>}
            {tab === "Shelters" && <>
              {snapshot?.shelters.map(s => <article className="shelter-detail" key={s.shelter_id}><span className="route-state ready">{s.status}</span><h3>{s.name}</h3><p>{s.occupancy} checked in · {s.reserved_demand} reserved · {s.capacity} total</p><progress value={s.occupancy + s.reserved_demand} max={s.capacity} /><button className="secondary-action" disabled={busy || !connected} onClick={() => { void calculate(s.shelter_id); }}>Preview route to shelter</button></article>)}
              {operatorKey && <form className="shelter-detail" onSubmit={e => { e.preventDefault(); void perform(async () => { const booking = await api.arrive(arrivalCode.trim(), operatorKey); if (booking.route_id === route?.route_id) remember(booking); log(`Checked in ${booking.party_size} people at ${booking.shelter.name}.`); setArrivalCode(""); await refresh(); }); }}><h3>Shelter check-in</h3><label className="form-label">Booking code<input value={arrivalCode} onChange={e => setArrivalCode(e.target.value)} required /></label><button className="primary-action" disabled={busy || !connected}>Check in party</button></form>}
            </>}
            <details className="operator-panel"><summary>{operatorKey ? "Operator controls enabled" : "Operator access"}</summary>{operatorKey ? <><p>{staffUser?.role === "shelter" ? "You can check in bookings for your assigned site." : "You can update closures on the map and check in bookings from Shelters."} Open Command centre for staff workflows.</p><button className="secondary-action" onClick={() => { setOperatorKey(""); setKeyInput(""); setStaffUser(undefined); }}>Lock operator controls</button></> : <form onSubmit={e => { e.preventDefault(); void perform(async () => { await api.access(keyInput); setOperatorKey(keyInput); setStaffUser({ username: "bootstrap-admin", role: "admin", shelter_id: null }); setKeyInput(""); log("Operator controls enabled for this browser session."); }); }}><p>Staff can sign in with a named account from Command centre.</p><label className="form-label">Access key<input type="password" autoComplete="off" required value={keyInput} onChange={e => setKeyInput(e.target.value)} /></label><button className="secondary-action" disabled={busy || !connected}>Enable operator controls</button></form>}</details>
            <section className="event-panel"><h3>Activity</h3>{events.length ? <ul>{events.map((event, i) => <li key={`${i}-${event}`}>{event}</li>)}</ul> : <p>Actions in this browser appear here.</p>}</section>
          </div>
        </aside>
      </div>}
      <footer className="simulation-footer">{!network ? "Loading road network" : realWorld ? "OpenStreetMap road pilot" : "Fictional pilot"} · Predictive models disabled · {lastSync ? `Last synchronized ${new Date(lastSync).toLocaleTimeString()}` : "Awaiting service state"} · Not for real evacuation guidance</footer>
    </main>
  </div>;
}

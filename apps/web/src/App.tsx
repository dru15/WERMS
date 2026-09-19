import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { OperationsMap } from "./components/OperationsMap";
import type { Hazard, HazardEvent, Route, Shelter, SystemStatus } from "./types";

const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";

function formatAge(timestamp?: string) {
  if (!timestamp) return "unknown";
  const seconds = Math.max(0, Math.round((Date.now() - Date.parse(timestamp)) / 1000));
  return seconds < 60 ? `${seconds}s ago` : `${Math.floor(seconds / 60)}m ago`;
}

function App() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [hazard, setHazard] = useState<Hazard | null>(null);
  const [shelters, setShelters] = useState<Shelter[]>([]);
  const [route, setRoute] = useState<Route | null>(null);
  const [partySize, setPartySize] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [routeInvalidated, setRouteInvalidated] = useState(false);
  const [eventLog, setEventLog] = useState<string[]>([]);
  const routeRef = useRef<Route | null>(null);

  const refresh = useCallback(async () => {
    const [nextStatus, nextHazard, nextShelters] = await Promise.all([
      api.getStatus(),
      api.getHazard(),
      api.getShelters(),
    ]);
    setStatus(nextStatus);
    setHazard(nextHazard);
    setShelters(nextShelters);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.getStatus(), api.getHazard(), api.getShelters()])
      .then(([nextStatus, nextHazard, nextShelters]) => {
        if (cancelled) return;
        setStatus(nextStatus);
        setHazard(nextHazard);
        setShelters(nextShelters);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "API unavailable");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const socket = new WebSocket(`${WS_URL}/ws/events`);
    socket.addEventListener("open", () => setConnected(true));
    socket.addEventListener("close", () => setConnected(false));
    socket.addEventListener("message", (message) => {
      const event = JSON.parse(message.data) as HazardEvent;
      setEventLog((current) => [`${event.event} · ${event.hazard_version}`, ...current].slice(0, 5));
      if (event.event === "hazard.updated") {
        const activeRoute = routeRef.current;
        setRouteInvalidated(Boolean(activeRoute && event.invalidated_route_ids?.includes(activeRoute.route_id)));
        refresh().catch(() => undefined);
      }
    });
    return () => socket.close();
  }, [refresh]);

  const requestRoute = async () => {
    setLoading(true);
    setError(null);
    try {
      const nextRoute = await api.createRoute(34.0522, -118.2437, partySize);
      routeRef.current = nextRoute;
      setRoute(nextRoute);
      setRouteInvalidated(false);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to calculate route");
    } finally {
      setLoading(false);
    }
  };

  const advanceScenario = async () => {
    setError(null);
    try {
      const event = await api.advanceScenario();
      if (route && event.invalidated_route_ids.includes(route.route_id)) {
        setRouteInvalidated(true);
      }
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unable to advance scenario");
    }
  };

  const freshness = useMemo(() => formatAge(hazard?.source_timestamp), [hazard]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <a href="#main" className="brand" aria-label="WERMS home">
          <span className="brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span><strong>WERMS</strong><small>Wildfire operations</small></span>
        </a>
        <div className="system-strip">
          <span className={connected ? "status-dot live" : "status-dot"} />
          {connected ? "Realtime connected" : "Realtime offline"}
          <span className="divider" />
          Hazard {hazard?.version ?? "loading"}
        </div>
      </header>

      <main id="main">
        <section className="hero">
          <div>
            <span className="eyebrow">Decision-support prototype</span>
            <h1>Clear guidance when conditions change.</h1>
            <p>
              Routes exclude confirmed hazards, account for shelter load, and carry the versions
              and freshness needed to explain every decision.
            </p>
          </div>
          <div className="freshness-card">
            <span>Hazard intelligence</span>
            <strong>{freshness}</strong>
            <small>{hazard?.blocked_edge_ids.length ?? 0} hard road blocks</small>
          </div>
        </section>

        {error && <div className="alert error" role="alert">{error}</div>}
        {routeInvalidated && (
          <div className="alert warning" role="alert">
            Conditions changed on your route. Stop and request updated guidance.
          </div>
        )}

        <div className="workspace-grid">
          <OperationsMap
            route={route}
            shelters={shelters}
            hazard={hazard}
            routeInvalidated={routeInvalidated}
          />

          <aside className="control-stack">
            <section className="panel route-panel">
              <span className="eyebrow">Civilian guidance</span>
              <h2>{route ? route.shelter.name : "Request a safe route"}</h2>
              {route ? (
                <>
                  <div className="route-metrics">
                    <div><strong>{route.estimated_minutes}</strong><span>minutes</span></div>
                    <div><strong>{route.distance_km}</strong><span>kilometres</span></div>
                    <div><strong>{Math.round(route.risk_score * 100)}</strong><span>risk index</span></div>
                  </div>
                  <dl className="decision-meta">
                    <div><dt>Route state</dt><dd className={routeInvalidated ? "danger" : "safe"}>{routeInvalidated ? "Invalid" : "Valid"}</dd></div>
                    <div><dt>Model</dt><dd>{route.model_mode === "approved" ? route.model_version : "Live-only fallback"}</dd></div>
                    <div><dt>Valid until</dt><dd>{new Date(route.valid_until).toLocaleTimeString()}</dd></div>
                  </dl>
                </>
              ) : (
                <p className="muted">The demo uses a fixed pilot origin. Browser GPS integration follows in the client-resilience milestone.</p>
              )}
              <label className="field">
                Party size
                <input
                  type="number"
                  min="1"
                  max="20"
                  value={partySize}
                  onChange={(event) => setPartySize(Number(event.target.value))}
                />
              </label>
              <button className="primary-action" onClick={requestRoute} disabled={loading}>
                {loading ? "Checking current conditions…" : routeInvalidated ? "Request updated route" : "Find safest route"}
              </button>
            </section>

            <section className="panel operator-panel">
              <div className="panel-heading">
                <div><span className="eyebrow">Dispatcher demo</span><h2>Live scenario</h2></div>
                <button className="secondary-action" onClick={advanceScenario}>Advance fireline</button>
              </div>
              <ul className="event-log" aria-live="polite">
                {eventLog.length ? eventLog.map((event, index) => <li key={`${event}-${index}`}>{event}</li>) : <li>Waiting for operational events</li>}
              </ul>
            </section>
          </aside>
        </div>

        <section className="summary-grid" aria-label="Operational summary">
          <article>
            <span className="metric-kicker">Open shelters</span>
            <strong>{shelters.filter((shelter) => shelter.status === "open").length}</strong>
            <small>90% redirect threshold</small>
          </article>
          <article>
            <span className="metric-kicker">Routing state</span>
            <strong>{status?.road_version ?? "—"}</strong>
            <small>Versioned graph snapshot</small>
          </article>
          <article>
            <span className="metric-kicker">Predictive model</span>
            <strong>{status?.model_mode === "approved" ? "Approved" : "Disabled"}</strong>
            <small>No unapproved model in the safety path</small>
          </article>
        </section>
      </main>
    </div>
  );
}

export default App;

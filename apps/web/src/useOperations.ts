import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, subscribe } from "./api";
import { clearPending, readPending } from "./confirmation";
import type { Network } from "./network";
import type { Route, Snapshot } from "./types";

const BOOKING_KEY = "werms.confirmed-plan.v1";
function savedId() { try { return localStorage.getItem(BOOKING_KEY); } catch { return null; } }

export function useOperations() {
  const [network, setNetwork] = useState<Network>();
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [route, setRoute] = useState<Route>();
  const [connection, setConnection] = useState<"loading" | "connected" | "offline">("loading");
  const [error, setError] = useState<string>();
  const [lastSync, setLastSync] = useState<number>();
  const networkRef = useRef<Network | undefined>(undefined);
  const routeId = useRef<string | null>(savedId());
  const serial = useRef(0);
  const alive = useRef(false);
  const inFlight = useRef(false);
  const resyncAfter = useRef(false);

  const refresh = useCallback(async function synchronize() {
    if (inFlight.current) { resyncAfter.current = true; return; }
    inFlight.current = true;
    const version = ++serial.current;
    let id = routeId.current;
    try {
      const pending = readPending();
      if (pending) {
        try {
          const recovered = await api.confirm(pending.input, pending.requestId, pending.replaceRouteId);
          if (!alive.current || version !== serial.current) return;
          routeId.current = recovered.route_id;
          id = recovered.route_id;
          localStorage.setItem(BOOKING_KEY, recovered.route_id);
          clearPending(pending.requestId);
        } catch (e) {
          if (e instanceof ApiError && e.status >= 400 && e.status < 500) clearPending(pending.requestId);
          else throw e;
        }
      }
      const [graph, state, booking] = await Promise.all([
        networkRef.current ? Promise.resolve(networkRef.current) : api.network(),
        api.snapshot(),
        id ? api.route(id).catch(e => {
          if (e instanceof ApiError && e.status === 404) {
            if (routeId.current === id) {
              routeId.current = null;
              try { localStorage.removeItem(BOOKING_KEY); } catch { /* Memory still works. */ }
            }
            return undefined;
          }
          throw e;
        }) : Promise.resolve(undefined),
      ]);
      if (!alive.current || version !== serial.current) return;
      networkRef.current = graph;
      setNetwork(graph);
      setSnapshot(previous => !previous || state.revision > previous.revision ? state : previous);
      if (id === routeId.current || routeId.current === null) setRoute(booking);
      setConnection("connected"); setError(undefined); setLastSync(Date.now());
    } catch (e) {
      if (!alive.current || version !== serial.current) return;
      setConnection("offline"); setError(e instanceof Error ? e.message : "Unable to synchronize operations.");
    } finally {
      inFlight.current = false;
      if (resyncAfter.current && alive.current) {
        resyncAfter.current = false;
        queueMicrotask(() => { void synchronize(); });
      }
    }
  }, []);

  useEffect(() => {
    const currentSerial = serial;
    alive.current = true;
    void refresh();
    const poll = setInterval(() => { void refresh(); }, 5000);
    const stop = subscribe(() => { void refresh(); });
    const focused = () => { if (document.visibilityState === "visible") void refresh(); };
    document.addEventListener("visibilitychange", focused);
    return () => {
      alive.current = false; ++currentSerial.current; clearInterval(poll); stop();
      document.removeEventListener("visibilitychange", focused);
    };
  }, [refresh]);

  const remember = useCallback((booking: Route) => {
    ++serial.current;
    routeId.current = booking.route_id;
    try { localStorage.setItem(BOOKING_KEY, booking.route_id); } catch { /* Memory still works. */ }
    setRoute(booking);
  }, []);

  return { network, snapshot, route, connection, error, lastSync, refresh, remember };
}

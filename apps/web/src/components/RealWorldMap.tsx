import { useEffect, useRef, useState } from "react";
import * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import { closestRoadNode, type Network, type Plan } from "../network";

export type RealWorldMapProps = {
  network: Network; plan?: Plan; blocked?: string[]; origin?: string; progress?: number;
  invalid?: boolean; onRoad?: (id: string) => void; onShelter?: (id: string) => void;
  onOrigin?: (id: string) => void;
};

function label(text: string) { const element = document.createElement("span"); element.textContent = text; return element; }
function coordinate(point: { latitude?: number; longitude?: number }): L.LatLngTuple {
  if (point.latitude === undefined || point.longitude === undefined) throw new Error("Mapped point needs real coordinates.");
  return [point.latitude, point.longitude];
}

export function RealWorldMap({ network, plan, blocked = [], origin, progress = 0, invalid = false,
  onRoad, onShelter, onOrigin }: RealWorldMapProps) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | undefined>(undefined);
  const roadsRef = useRef<L.LayerGroup | undefined>(undefined);
  const routeRef = useRef<L.LayerGroup | undefined>(undefined);
  const sitesRef = useRef<L.LayerGroup | undefined>(undefined);
  const markerRef = useRef<L.CircleMarker | undefined>(undefined);
  const fittedPath = useRef("");
  const handlers = useRef({ onRoad, onShelter, onOrigin });
  const [showRoads, setShowRoads] = useState(true);
  const [showSites, setShowSites] = useState(true);
  const [tileError, setTileError] = useState(false);
  const [selectionMessage, setSelectionMessage] = useState("Select a road inside the pilot boundary to set your starting point.");
  const operator = Boolean(onRoad);

  useEffect(() => { handlers.current = { onRoad, onShelter, onOrigin }; }, [onRoad, onShelter, onOrigin]);
  useEffect(() => {
    if (!container.current || !network.bounds) return;
    const [south, west, north, east] = network.bounds;
    const map = L.map(container.current, { scrollWheelZoom: false, zoomControl: true, preferCanvas: true });
    mapRef.current = map;
    map.fitBounds([[south, west], [north, east]], { padding: [16, 16] });
    const tileUrl = import.meta.env.VITE_MAP_TILE_URL ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
    const tiles = L.tileLayer(tileUrl, { maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      updateWhenIdle: true, keepBuffer: 1 }).addTo(map);
    tiles.on("tileerror", () => setTileError(true));
    L.control.scale({ imperial: false }).addTo(map);
    L.rectangle([[south, west], [north, east]], { color: "#546c5d", weight: 2,
      dashArray: "6 6", fill: false, interactive: false }).addTo(map);
    roadsRef.current = L.layerGroup().addTo(map);
    routeRef.current = L.layerGroup().addTo(map);
    sitesRef.current = L.layerGroup().addTo(map);
    const chooser = (event: L.LeafletMouseEvent) => {
      const nearest = closestRoadNode(network, event.latlng.lat, event.latlng.lng);
      if (!nearest) { setSelectionMessage("Choose a mapped road within the dashed pilot boundary, within 200 m of the network."); return; }
      handlers.current.onOrigin?.(nearest.id);
      setSelectionMessage(`Starting point: ${nearest.latitude?.toFixed(5)}, ${nearest.longitude?.toFixed(5)}.`);
    };
    map.on("click", chooser);
    const observer = new ResizeObserver(() => map.invalidateSize({ pan: false }));
    observer.observe(container.current);
    return () => { observer.disconnect(); map.remove(); mapRef.current = undefined;
      roadsRef.current = undefined; sitesRef.current = undefined; routeRef.current = undefined; markerRef.current = undefined; fittedPath.current = ""; };
  }, [network]);

  useEffect(() => {
    const group = roadsRef.current, map = mapRef.current;
    if (!group || !map) return;
    group.clearLayers();
    const points = Object.fromEntries(network.nodes.map(n => [n.id, n]));
    for (const road of network.roads) {
      const closed = blocked.includes(road.id);
      if (!showRoads && !closed) continue;
      const line = L.polyline([coordinate(points[road.from]), coordinate(points[road.to])], {
        color: closed ? "#c43d32" : "#356d99", weight: closed ? 6 : 4,
        opacity: closed ? 0.95 : operator ? 0.45 : 0.18,
        dashArray: closed ? "8 5" : undefined, interactive: operator,
      }).addTo(group);
      if (operator) {
        line.bindTooltip(label(`${road.name} · ${closed ? "Closed: select to reopen" : "Select to close"}`));
        line.on("click", event => { if (event.originalEvent) L.DomEvent.stopPropagation(event.originalEvent);
          handlers.current.onRoad?.(road.id); });
      }
    }
  }, [network, blocked, showRoads, operator]);

  useEffect(() => {
    const group = sitesRef.current;
    if (!group) return;
    group.clearLayers();
    if (!showSites) return;
    for (const site of network.shelters) {
      const marker = L.marker(coordinate(site), { icon: L.divIcon({ className: "assembly-marker",
        html: '<span aria-hidden="true">A</span>', iconSize: [30, 30], iconAnchor: [15, 15] }),
        title: `Demo assembly site: ${site.name}`, keyboard: true }).addTo(group);
      marker.bindTooltip(label(`${site.name} · demonstration assembly site`));
      marker.on("click", () => handlers.current.onShelter?.(site.id));
    }
  }, [network, showSites]);

  useEffect(() => {
    const group = routeRef.current, map = mapRef.current;
    if (!group || !map) return;
    group.clearLayers();
    const points = Object.fromEntries(network.nodes.map(n => [n.id, n]));
    if (plan) {
      const path = plan.nodes.map(id => coordinate(points[id]));
      L.polyline(path, { color: "white", weight: 9, interactive: false }).addTo(group);
      L.polyline(path, { color: invalid ? "#7b8580" : "#1769e0", weight: 5,
        dashArray: invalid ? "8 5" : undefined, interactive: false }).addTo(group);
      const signature = plan.nodes.join("|");
      if (path.length > 1 && signature !== fittedPath.current) {
        map.fitBounds(L.latLngBounds(path).pad(0.25), { maxZoom: 17, animate: false });
        fittedPath.current = signature;
      }
    }
  }, [network, plan, invalid]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const points = Object.fromEntries(network.nodes.map(n => [n.id, n]));
    let location: L.LatLngTuple | undefined;
    if (plan?.nodes.length) {
      const scaled = Math.min(1, Math.max(0, progress)) * (plan.nodes.length - 1);
      const index = Math.min(Math.floor(scaled), Math.max(0, plan.nodes.length - 2));
      const a = coordinate(points[plan.nodes[index]]), b = coordinate(points[plan.nodes[Math.min(index + 1, plan.nodes.length - 1)]]);
      const fraction = scaled - index;
      location = [a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction];
    } else if (origin && points[origin]) location = coordinate(points[origin]);
    if (!location) return;
    if (!markerRef.current) markerRef.current = L.circleMarker(location, { radius: 8, color: "white", weight: 3, fillColor: "#1769e0", fillOpacity: 1, interactive: false }).addTo(map);
    else markerRef.current.setLatLng(location);
  }, [network, plan, origin, progress]);

  return <section className="map-card real-map-card">
    <div className="map-toolbar"><div className="map-title"><h2>{network.name}</h2><p>OpenStreetMap roads · select a starting point on the map</p></div>
      <div className="map-tools"><button className={showRoads ? "map-tool active" : "map-tool"} aria-pressed={showRoads} onClick={() => setShowRoads(s => !s)}>Road network</button><button className={showSites ? "map-tool active" : "map-tool"} aria-pressed={showSites} onClick={() => setShowSites(s => !s)}>Assembly sites</button><button className="map-tool" onClick={() => {
        if (network.bounds) mapRef.current?.fitBounds([[network.bounds[0], network.bounds[1]], [network.bounds[2], network.bounds[3]]]);
      }}>Pilot area</button></div>
    </div>
    <div className="real-world-map" ref={container} role="region" aria-label="Real-world OpenStreetMap road map" />
    {tileError && <div className="map-status" role="status">Some basemap tiles are unavailable. The imported road network remains visible.</div>}
    <div className="map-status" role="status">{operator ? "Operator mode: select a highlighted road to close or reopen it." : selectionMessage}</div>
    <div className="map-source">Road extract: {network.source?.data_timestamp ? new Date(network.source.data_timestamp).toLocaleDateString() : "OpenStreetMap"} · <a href="https://www.openstreetmap.org/fixthemap" target="_blank" rel="noreferrer">Report a map issue</a> · Assembly sites and closures are demonstration data.</div>
  </section>;
}

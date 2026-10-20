import { useEffect, useRef, useState } from "react";
import { Map as VectorMap, Marker, NavigationControl, ScaleControl, setWorkerUrl,
  type GeoJSONSource, type StyleSpecification } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { closestRoadNode, type Network, type Plan } from "../network";
import { roadFeatures, routeFeatures } from "../mapData";
import type { FirePolygon } from "../context";

setWorkerUrl(workerUrl);
const EMPTY: string[] = [];
const EMPTY_RISK: Record<string,number> = {};
const VECTOR_STYLE = import.meta.env.VITE_MAP_STYLE_URL ?? "https://tiles.openfreemap.org/styles/liberty";
const LOCAL_STYLE: StyleSpecification = { version: 8, sources: {}, layers: [
  { id: "background", type: "background", paint: { "background-color": "#edf1e5" } },
] };
export type RealWorldMapProps = {
  network: Network; plan?: Plan; blocked?: string[]; origin?: string; progress?: number;
  invalid?: boolean; onRoad?: (id: string) => void; onShelter?: (id: string) => void;
  onOrigin?: (id: string) => void; comparisonPlan?: Plan; scenarioBlocked?: string[];
  firePolygon?: FirePolygon;
  riskScores?:Record<string,number>;
};

export function RealWorldMap(props: RealWorldMapProps) {
  const { network, plan, blocked = EMPTY, origin, progress = 0, invalid = false,
    onRoad, onShelter, onOrigin, comparisonPlan, scenarioBlocked = EMPTY, firePolygon, riskScores=EMPTY_RISK } = props;
  const container = useRef<HTMLDivElement>(null), mapRef = useRef<VectorMap | undefined>(undefined);
  const handlers = useRef({ onRoad, onShelter, onOrigin });
  const [showRoads, setShowRoads] = useState(true), [showSites, setShowSites] = useState(true);
  const [ready, setReady] = useState(0), [basemap, setBasemap] = useState("loading");
  const [retry, setRetry] = useState(0);
  const [message, setMessage] = useState("Select a road inside the pilot boundary to set your starting point.");
  const fitted = useRef("");
  const operator = Boolean(onRoad);
  useEffect(() => { handlers.current = { onRoad, onShelter, onOrigin }; }, [onRoad, onShelter, onOrigin]);

  useEffect(() => {
    if (!container.current || !network.bounds) return;
    const [s, w, n, e] = network.bounds;
    let map: VectorMap;
    try {
      map = new VectorMap({ container: container.current, style: LOCAL_STYLE, attributionControl: false,
        bounds: [[w, s], [e, n]], fitBoundsOptions: { padding: 35 }, maxZoom: 20,
        canvasContextAttributes: { antialias: true }, scrollZoom: false });
    } catch {
      container.current.textContent = "This device cannot initialize the WebGL map. Route details remain available below.";
      return;
    }
    mapRef.current = map;
    map.addControl(new NavigationControl({ visualizePitch: true }), "top-right");
    map.addControl(new ScaleControl({ unit: "metric" }));
    map.on("idle", () => {
      const ownSources = new Set(["roads","route","comparison","pilot-boundary","fire-perimeter","local-context"]);
      const geographicFeatures = map.queryRenderedFeatures().filter(feature => !ownSources.has(feature.source));
      if (geographicFeatures.length) setBasemap("vector");
    });
    map.on("error", () => setBasemap("unavailable"));
    map.on("style.load", () => {
      map.addSource("local-context", {type:"geojson",data:network.context ?? {type:"FeatureCollection",features:[]}});
      map.addLayer({id:"local-land",type:"fill",source:"local-context",filter:["==",["geometry-type"],"Polygon"],paint:{"fill-color":["match",["get","kind"],"water","#bdd8df","building","#d7dbd0","#d8e6c9"],"fill-opacity":.9}});
      map.addLayer({id:"local-water",type:"line",source:"local-context",filter:["==",["geometry-type"],"LineString"],paint:{"line-color":"#a7cbd5","line-width":2}});
      map.addSource("pilot-boundary", { type: "geojson", data: { type: "Feature", properties: {},
        geometry: { type: "LineString", coordinates: [[w, s], [e, s], [e, n], [w, n], [w, s]] } } });
      map.addLayer({ id: "pilot-boundary", type: "line", source: "pilot-boundary",
        paint: { "line-color": "#426959", "line-width": 2, "line-dasharray": [3, 3] } });
      map.addSource("fire-perimeter", {type:"geojson", data:{type:"FeatureCollection",features:[]}});
      map.addLayer({id:"fire-perimeter",type:"fill",source:"fire-perimeter",paint:{"fill-color":"#df5b31","fill-opacity":.25}});
      map.addLayer({id:"fire-boundary",type:"line",source:"fire-perimeter",paint:{"line-color":"#c43d32","line-width":2,"line-dasharray":[3,2]}});
      for (const id of ["roads", "route", "comparison"]) {
        map.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      }
      map.addLayer({ id: "roads", source: "roads", type: "line", paint: {
        "line-color": ["case", ["get", "closed"], "#c43d32", ["get", "simulated"], "#d97706", ["has","predictive_risk"], ["interpolate",["linear"],["get","predictive_risk"],0,"#c9ac50",1,"#a33c29"], "#356d99"],
        "line-width": ["case", ["any", ["get", "closed"], ["get", "simulated"]], 6, 2],
        "line-opacity": ["case", ["any", ["get", "closed"], ["get", "simulated"], ["has","predictive_risk"]], .85, .25],
      } });
      map.addLayer({ id: "road-hit", source: "roads", type: "line", paint: { "line-width": 16, "line-opacity": 0 } });
      map.addLayer({ id: "comparison", source: "comparison", type: "line", paint: {
        "line-color": "#705c89", "line-width": 5, "line-dasharray": [3, 2], "line-opacity": .8 } });
      map.addLayer({ id: "route-halo", source: "route", type: "line", paint: { "line-color": "white", "line-width": 9 } });
      map.addLayer({ id: "route", source: "route", type: "line", paint: { "line-color": "#1769e0", "line-width": 5 } });
      setReady(x => x + 1);
    });
    map.on("click", event => {
      const hit = map.getLayer("road-hit") ? map.queryRenderedFeatures(event.point, { layers: ["road-hit"] })[0] : undefined;
      if (handlers.current.onRoad && hit?.properties?.id) { handlers.current.onRoad(String(hit.properties.id)); return; }
      if (!handlers.current.onOrigin) return;
      const nearest = closestRoadNode(network, event.lngLat.lat, event.lngLat.lng);
      if (!nearest) { setMessage("Choose a mapped road inside the pilot boundary, within 200 m of the network."); return; }
      handlers.current.onOrigin?.(nearest.id);
      setMessage(`Starting point: ${nearest.latitude?.toFixed(5)}, ${nearest.longitude?.toFixed(5)}.`);
    });
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(container.current);
    return () => { observer.disconnect(); map.remove(); mapRef.current = undefined; fitted.current = ""; };
  }, [network]);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    fetch(VECTOR_STYLE, { signal: controller.signal }).then(async response => {
      if (!response.ok) throw new Error("Provider unavailable");
      const style = await response.json() as StyleSpecification;
      if (style.version !== 8 || !style.sources || !Array.isArray(style.layers)) throw new Error("Invalid style");
      mapRef.current?.setStyle(style);
    }).catch(() => { if (!controller.signal.aborted || mapRef.current) setBasemap("unavailable"); })
      .finally(() => clearTimeout(timeout));
    return () => { controller.abort(); clearTimeout(timeout); };
  }, [network, retry]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.getSource("roads") || !map.getSource("fire-perimeter")) return;
    const roads = roadFeatures(network, blocked, scenarioBlocked, riskScores);
    if (!showRoads) roads.features = roads.features.filter(f => f.properties?.closed || f.properties?.simulated);
    (map.getSource("roads") as GeoJSONSource).setData(roads);
    (map.getSource("route") as GeoJSONSource).setData(routeFeatures(network, plan));
    (map.getSource("comparison") as GeoJSONSource).setData(routeFeatures(network, comparisonPlan));
    (map.getSource("fire-perimeter") as GeoJSONSource).setData({type:"FeatureCollection",features:firePolygon ? [{type:"Feature",properties:{},geometry:firePolygon}] : []});
    map.setPaintProperty("route", "line-color", invalid ? "#7b8580" : "#1769e0");
    map.setLayoutProperty("local-land","visibility",basemap==='vector'?'none':'visible');
    map.setLayoutProperty("local-water","visibility",basemap==='vector'?'none':'visible');
    map.setPaintProperty("roads","line-opacity",["case",["any",["get","closed"],["get","simulated"],["has","predictive_risk"]],.9,basemap==='vector'?.25:.7]);
    const signature = (plan?.nodes.join("|") ?? "") + (comparisonPlan?.nodes.join("|") ?? "");
    if (signature && signature !== fitted.current) {
      const points = [...routeFeatures(network, plan).features, ...routeFeatures(network, comparisonPlan).features]
        .flatMap(f => f.geometry.coordinates);
      if (points.length > 1) map.fitBounds([[Math.min(...points.map(p => p[0])), Math.min(...points.map(p => p[1]))],
        [Math.max(...points.map(p => p[0])), Math.max(...points.map(p => p[1]))]], { padding: 55, maxZoom: 17, duration: 0 });
      fitted.current = signature;
    }
  }, [network, plan, comparisonPlan, blocked, scenarioBlocked, showRoads, invalid, ready, firePolygon, riskScores, basemap]);

  useEffect(()=>{
    const map=mapRef.current;
    if(!map || basemap==='vector' || !showRoads) return;
    const points=Object.fromEntries(network.nodes.map(n=>[n.id,n]));
    const names=new Set<string>(),anchors:{lat:number;lon:number}[]=[],labels:Marker[]=[];
    for(const road of [...network.roads].sort((a,b)=>b.km-a.km)){
      if(names.has(road.name) || road.name.toLowerCase()===road.highway?.replaceAll('_',' ') || road.km<.03)continue;
      const a=points[road.from],b=points[road.to],lat=(a.latitude!+b.latitude!)/2,lon=(a.longitude!+b.longitude!)/2;
      if(anchors.some(p=>Math.hypot((p.lat-lat)*111,(p.lon-lon)*95)<.18))continue;
      const element=document.createElement('span');element.className='vector-local-label';element.textContent=road.name;element.setAttribute('aria-hidden','true');
      labels.push(new Marker({element,anchor:'center'}).setLngLat([lon,lat]).addTo(map));names.add(road.name);anchors.push({lat,lon});
      if(labels.length===10)break;
    }
    return()=>labels.forEach(label=>label.remove());
  },[network,basemap,showRoads,ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !showSites) return;
    const markers = network.shelters.map(site => {
      const element = document.createElement("button"); element.className = "vector-site";
      element.textContent = "A"; element.title = `Demo assembly site: ${site.name}`;
      element.setAttribute("aria-label", element.title);
      element.onclick = event => { event.stopPropagation(); handlers.current.onShelter?.(site.id); };
      return new Marker({ element }).setLngLat([site.longitude!, site.latitude!]).addTo(map);
    });
    return () => markers.forEach(marker => marker.remove());
  }, [network, showSites, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const points = Object.fromEntries(network.nodes.map(n => [n.id, n]));
    const path = plan?.nodes.length ? plan.nodes : origin ? [origin] : [];
    if (!path.length) return;
    const scaled = Math.min(1, Math.max(0, progress)) * (path.length - 1), index = Math.floor(scaled);
    const a = points[path[index]], b = points[path[Math.min(index + 1, path.length - 1)]], f = scaled - index;
    if (!a || !b) return;
    const element = document.createElement("div"); element.className = "vector-origin";
    const marker = new Marker({ element }).setLngLat([a.longitude! + (b.longitude! - a.longitude!) * f,
      a.latitude! + (b.latitude! - a.latitude!) * f]).addTo(map);
    return () => { marker.remove(); };
  }, [network, plan, origin, progress, ready]);

  return <section className="map-card real-map-card">
    <div className="map-toolbar"><div className="map-title"><h2>{network.name}</h2><p>Vector map · crisp at every zoom · {onOrigin ? "select a starting point" : "pan and zoom to inspect"}</p></div>
      <div className="map-tools"><button className={`map-tool ${showRoads ? "active" : ""}`} aria-pressed={showRoads} onClick={() => setShowRoads(s => !s)}>Road network</button>
        <button className={`map-tool ${showSites ? "active" : ""}`} aria-pressed={showSites} onClick={() => setShowSites(s => !s)}>Assembly sites</button>
        <button className="map-tool" onClick={() => { const b = network.bounds; if (b) mapRef.current?.fitBounds([[b[1], b[0]], [b[3], b[2]]], { padding: 35 }); }}>Pilot area</button></div></div>
    <div className="real-world-map" ref={container} role="region" aria-label="Real-world OpenStreetMap road map" data-basemap={basemap} />
    {basemap !== "vector" && <div className="map-status" role="status">{basemap === "loading" ? "Loading detailed vector basemap…" : `Online basemap unavailable. Local OSM roads and ${network.context?.features.length ?? 0} mapped context features remain visible inside the pilot.`}
      {basemap === "unavailable" && <button className="map-tool" onClick={() => { setBasemap("loading"); setRetry(x => x + 1); }}>Retry basemap</button>}</div>}
    <div className="map-status" role="status">{operator ? "Operator mode: select a highlighted road to close or reopen it." : onOrigin ? message : "Pan and zoom to inspect this scenario. Its starting point is fixed for this comparison."}</div>
    <div className="map-source"><a href="https://openfreemap.org/" target="_blank" rel="noreferrer">OpenFreeMap</a> · © <a href="https://www.openmaptiles.org/" target="_blank" rel="noreferrer">OpenMapTiles</a> · © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a> · Assembly sites and closures are demonstration data.</div>
  </section>;
}

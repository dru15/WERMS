import { useEffect, useState } from "react";
import { contextApi, indiaTime } from "../context";
import type { Weather } from "../context";
import type { Network } from "../network";

export function IndiaOverview({ network, onExplore }: { network: Network; onExplore: () => void }) {
  const [weather, setWeather] = useState<Weather>();
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    async function load() {
      try { const next = await contextApi.weather(); if (active) { setWeather(next); setError(""); } }
      catch (e) { if (active) setError(e instanceof Error ? e.message : "Weather unavailable."); }
    }
    void load(); const timer = setInterval(() => { void load(); }, 600000);
    return () => { active = false; clearInterval(timer); };
  }, []);
  const data = weather?.data;
  return <section className="india-overview" aria-label="India pilot overview">
    <div className="mission-story">
      <div className="mission-eyebrow"><span className="india-tricolour" aria-hidden="true" /> UTTARAKHAND FIELD LAB <span>01 / DEHRADUN</span></div>
      <h2>Every road is a decision.<br /><span>Make the next one count.</span></h2>
      <p>Explore the Rajpur–Malsi forest fringe. Compare evacuation options, coordinate capacity, and test how a disruption changes the response.</p>
      <div className="mission-actions"><button onClick={onExplore}>Explore resilience lab <span aria-hidden="true">↗</span></button><span className="mission-hindi" lang="hi">जंगल से जीवन तक</span></div>
      <div className="mission-proof"><span><strong>{network.nodes.length.toLocaleString("en-IN")}</strong> mapped nodes</span><span><strong>{network.roads.length.toLocaleString("en-IN")}</strong> road segments</span><span><strong>IST</strong> local context</span></div>
      <svg className="mission-contours" viewBox="0 0 500 300" aria-hidden="true"><path d="M-60 270Q80-100 230 90T560-60M-60 300Q80-70 230 120T560-30M-60 330Q80-40 230 150T560 0M-60 360Q80-10 230 180T560 30M-60 390Q80 20 230 210T560 60M-60 420Q80 50 230 240T560 90" /></svg>
    </div>
    <aside className="weather-card" aria-label="Model weather context">
      <div className="weather-heading"><span>MODEL WEATHER CONTEXT</span><span className={`weather-state ${error || weather?.status === "stale" ? "stale" : ""}`}>{error ? "Unavailable" : weather?.status ?? "Connecting"}</span></div>
      {data ? <><div className="weather-main"><strong>{Math.round(data.temperature_c)}<small>°C</small></strong><div><span>Dehradun pilot centre</span><p>Valid {indiaTime(data.valid_at)} IST</p></div></div>
        <div className="weather-readings"><div><span>Humidity</span><strong>{data.humidity_pct}%</strong></div><div><span>Wind at 10 m</span><strong>{data.wind_kph} <small>km/h</small></strong></div><div><span>Precipitation</span><strong>{data.precipitation_mm} <small>mm / {data.interval_seconds / 60} min</small></strong></div></div>
        <p className="weather-provenance">Retrieved {indiaTime(data.retrieved_at)} IST · model-derived, not a local station reading</p>
      </> : <div className="weather-empty"><strong>{weather?.status === "disabled" ? "Weather is disabled" : error || weather?.status === "unavailable" ? "Weather feed unavailable" : "Connecting to Open-Meteo…"}</strong><p>Routing remains available using recorded road and capacity conditions.</p></div>}
      {(error || weather?.message) && <p className="weather-error" role="status">{error || weather?.message}</p>}
      <div className="weather-credit"><a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Weather data by Open-Meteo ↗</a><span>Context only · not a fire prediction</span></div>
    </aside>
  </section>;
}

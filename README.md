# WERMS

Wildfire Evacuation and Resource Management System is a safety-oriented research prototype for hazard-aware evacuation routing, shelter load balancing, emergency-resource coordination, and calibrated predictive risk.

The repository begins with a working vertical slice: a civilian route request is evaluated against hard hazards, soft risk, congestion, data age, and shelter capacity; the route is versioned; a simulated hazard update invalidates affected routes and is pushed to the browser over WebSockets.

## Safety boundary

WERMS is decision-support software, not an emergency authority. An ML score may increase route cost but may never reopen an edge blocked by a confirmed hazard or closure. The application exposes freshness and version metadata so a route is never presented without the state that justified it.

## Repository layout

```text
apps/web/          React and TypeScript web client
services/api/      FastAPI application and routing domain
ml/                Training-plane contracts and future approved artifacts
docs/              Requirements baseline and architecture decisions
scripts/           Local environment helpers
```

## Local development

Prerequisites: Python 3.12+ and Node.js 22+. Docker Desktop is optional for the first demo and required when the PostGIS/Redis adapters are enabled.

```powershell
Copy-Item .env.example .env
./scripts/bootstrap.ps1
./scripts/dev.ps1
```

Open `http://localhost:5173`. The API documentation is at `http://localhost:8000/docs`.

The current milestone deliberately uses an in-memory operational adapter so it runs without Docker. The production-shaped PostGIS and Redis services are declared in `compose.yaml` and are activated in the next persistence milestone.

## Verification

```powershell
./scripts/verify.ps1
```

## Delivery roadmap

1. Foundation and safe-routing vertical slice.
2. PostGIS schema, migrations, OpenStreetMap pilot graph, and Redis event adapter.
3. FireCastRL acquisition, causal-window validation, baseline models, GRU, calibration, and model card.
4. NASA FIRMS/weather ingestion with provenance and stale-data degradation.
5. Dispatcher authentication, shelter/resource workflows, audit log, load tests, and deployment hardening.

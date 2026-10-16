# WERMS

Wildfire Evacuation and Resource Management System is a decision-support research application with a **real OpenStreetMap basemap and imported Pacific Palisades road network**. The backend computes routes on the same mapped roads displayed by the client, with shared road closures and durable bookings. Incident closures, assembly-site capacity, occupancy, and travel times remain demonstration estimates. Mapped landmarks are not verified emergency shelters. Predictive models are disabled; this is not for real emergency guidance.

## Working application

- One backend-owned OSM extract: 1,029 mapped nodes, 1,110 physical road segments, 289 one-way segments, and 19 turn restrictions. The map uses real coordinates and OSM tiles with visible attribution.
- Select a starting point directly on the map or use a pilot-area preset. Map viewing is global; route calculation is restricted to the marked pilot boundary and proximity to an imported road.
- Compare destinations without reserving capacity. Confirming a plan checks the entire party against shelter capacity and the configured 90% allocation threshold.
- Confirmed plans persist across browser refresh and API restart. Retries use an idempotency key; an interrupted confirmation is recovered after reload using the original key.
- Replace a booking atomically. If the replacement fails, the old booking remains intact.
- Expiry, cancellation, and closure invalidation release reserved demand. Reopening a road does not revive invalidated plans.
- Protected operator controls close/reopen roads and check parties into shelters. Arrival converts reserved demand to occupancy exactly once.
- WebSocket closure signals and five-second state polling resynchronize clients. Disconnection pauses route previews and marks guidance unverified.
- Audit records persist confirmations, arrivals, cancellations, expiry, and closure changes.
- Named staff accounts with administrator, dispatcher, and site-scoped shelter roles; eight-hour revocable sessions, password hashing, and persisted login throttling.
- Command centre with sourced, timestamped incident reports, acknowledgement, escalation, and resolution. A report never silently becomes a road closure.
- Register resource units, mark availability, dispatch atomically, acknowledge assignments, complete/cancel, and release the unit. Duplicate requests cannot allocate a unit twice.
- Edit site status and checked-in occupancy with a reason, reservation-aware capacity checks, and stale-update protection. Closing a site invalidates its incoming bookings.

Bookings expire after five minutes by default, as do their associated routes. The journey animation is an accelerated preview, not GPS tracking or arrival confirmation. A booking code grants access to that plan and cancellation; share it only with the relevant shelter operator.

The operational client never silently substitutes browser-local routing when the service is unavailable. The older `simulation.ts` remains an isolated training/reference module used by standalone map and simulation tests.

## Run locally

Prerequisites: Python 3.12+ and Node.js 22+. Docker is not required for the current SQLite pilot.

On first setup, create `.env` from `.env.example` if no `.env` exists, then bootstrap:

```powershell
./scripts/bootstrap.ps1
./scripts/dev.ps1
```

Open [the application](http://localhost:5173) and [API documentation](http://localhost:8000/docs). The development script starts both services and stops its API process when the web process exits. Alternatively, use two terminals:

```powershell
.\.venv\Scripts\python.exe -m uvicorn werms_api.main:app --app-dir services/api/src --reload --port 8000
```

```powershell
npm run dev:web
```

By default operational state is stored at `data/operational/palisades.sqlite3`. `OPERATIONAL_DB_PATH` overrides this location. State is seeded once; refreshing the app or restarting the API does not reset closures, occupancy, or bookings. The earlier fictional pilot's database is retained separately; its booking IDs do not transfer to a different real-road graph.

## Operator access

In development, the API generates a random access key in `data/operational/operator.key`. Open that local file yourself, enter its contents in the app's **Operator access** form, and enable the controls. The key remains in browser memory and is cleared by reloading or locking the controls; it is never sent in a URL or stored in browser local storage. The operational data directory is ignored by Git.

An operator can select a road on the map to close/reopen it and enter a booking code under **Shelters → Shelter check-in**. The activity list is local to the browser; the persistent audit history is available from the protected `/api/v1/operator/audit` endpoint.

Open **Command centre → First-time administrator setup**, unlock using that key, and create named staff accounts. Passwords require at least 12 characters and are stored as salted PBKDF2-SHA256 hashes (600,000 iterations). Sign out, then use **Staff sign-in**. Staff sessions expire after eight hours, remain only in tab memory, and can be revoked by signing out or disabling an account. Reloading requires signing in again. Five failed login attempts per username or client address cause a 15-minute throttle. The bootstrap key remains an administrator recovery credential; protect it separately.

Administrators manage accounts and view audits. Dispatchers manage closures, incidents, resources, and sites. Shelter staff can update and check in bookings only for their assigned site. The API enforces these rules independently of the interface. Inventory starts empty; register exercise resources yourself rather than presenting fabricated units as operational.

For remote hosting, explicitly configure a random `OPERATOR_API_KEY` of at least 24 characters and terminate HTTPS in front of the service. Startup rejects production without that secret. This remains a research pilot, not a public emergency service.

## Data consistency

SQLite transactions serialize preview state reads, booking selection, replacement, and capacity updates. A reservation is the demand of an active confirmed plan; it cannot accumulate independently of the booking. The server enforces expiry when serving or mutating operational state, even after downtime. Preview requests do not allocate spaces.

The routing domain excludes every hard-closed physical road, respects imported one-way directions, and keeps incoming-edge state to enforce node-based turn restrictions. Its search uses a zero heuristic (Dijkstra). Haversine distances and OSM/class-derived speed estimates produce approximate travel times; there is no live traffic feed. Freshness cost scales by distance so OSM shape-point density cannot distort it. ML cannot reopen a hard closure, and startup rejects an approved-model setting because no validated inference adapter exists yet.

Route validity is a prototype contract against recorded pilot conditions, not a real-world safety certificate. The client shows when those conditions were last changed and flags an age above 30 minutes. No satellite stream or predictive fire spread is claimed. Routes stop at the nearest mapped road point to a demonstration assembly site; building access is not verified.

## Real-world map data

The packaged extract was acquired from the official OpenStreetMap bounding-box API after public Overpass endpoints timed out. Its provenance, licence, raw-source SHA-256, acquisition time, and full reconstruction command are documented in [the data README](services/api/src/werms_api/data/README.md). The graph is served through `/api/v1/network`; ordinary route requests use this local extract, not an external directions API.

Leaflet requests only normal visible-viewport tiles from OpenStreetMap, with attribution, browser caching, and no bulk prefetch/offline tile download. `VITE_MAP_TILE_URL` allows a different compatible raster provider. Tile outages display a status message while the imported road overlay remains available. Road imports filter private/prohibited access, construction, conditional rules, and unsupported complex turn maneuvers conservatively; they are not a replacement for a fully validated navigation engine.

The three initial demonstration destinations are the OSM-mapped Palisades Branch Los Angeles Public Library, Palisades Recreation Center, and Palisades Charter High School. Their capacities are synthetic and their current operation/suitability is not verified. © OpenStreetMap contributors; the included road/place derivative is distributed under ODbL 1.0.

## Verification

```powershell
./scripts/verify.ps1
```

The checks cover API contracts, role/site permissions, session revocation and throttling, incident transitions, concurrent resource allocation, preview/confirmation separation, graph/path agreement, idempotent confirmations/check-in, expiry, atomic replacement rollback, restart durability, unsupported origins, and controlled no-route outcomes. Frontend tests verify backend path rendering, confirmation recovery, outage behavior, closure invalidation, expiry, cancellation, staff sign-in, scoped site controls, and dispatch retries. The verification script also runs lint and a production web build. Each verification run gets a fresh ignored workspace temporary directory to avoid Windows ownership conflicts. Vitest uses process workers because thread workers time out on this workstation.

Use [the demonstration guide](docs/demo-guide.md) for a repeatable end-to-end project presentation. The [release scope](docs/release-scope.md) records what is implemented and which research claims still require evidence.

## Containers and persistence

`docker compose up --build` runs the pilot API and web app with a `pilot-data` volume mounted at `/app/data/operational`. The non-root API container has a writable operational directory. The OSM JSON extract is included in the installed Python package. PostGIS and Redis are retained under the optional `spatial` Compose profile; they are not adapters used by this milestone.

Container execution has not been verified on this workstation because Docker is unavailable. For remote hosting, configure browser-visible API/WebSocket build URLs, the actual `WEB_ORIGIN`, HTTPS, and persistent storage. Use one pilot instance; do not give replicas separate SQLite files.

To back up this milestone, stop the API cleanly and copy the SQLite file to a protected location. Restore while the API is stopped. Protect the operator key separately. Database schema version 1 is initialized automatically; a different road version requires an explicit migration rather than silently reseeding occupied shelters.

## Repository

```text
apps/web/       React/TypeScript application
services/api/   FastAPI, routing domain, shared network, transactional operations
ml/             Future reproducible training plane
docs/           Requirements, planning history, architecture decisions
```

## Next milestones

1. Additional pilot areas and a PostGIS adapter with versioned migrations.
2. Fire/weather ingestion with provenance, validation, replay, and a justified freshness policy.
3. Validated baseline predictive models, calibration, model cards, and explicit artifact approval.
4. Realistic scenario benchmarks, accessibility/user evaluation, deployment hardening, and an evidence-based novelty investigation.

The earlier seven-day plan is retained in `docs/final-project-plan.md` as a planning snapshot. The user has removed the deadline constraint; implementation now follows verified milestones.

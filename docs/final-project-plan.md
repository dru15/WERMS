# WERMS: seven-day final project plan

Prepared 14 October 2026. Scope: one developer working with Codex, software only, submission in about one week. The priority is a dependable working application. Patentability is a later investigation, not a promised outcome of this sprint.

**Scope update:** The user subsequently removed the deadline constraint and authorized implementation with quality as the priority. The schedule and audit below preserve the original planning snapshot; they are no longer the active delivery deadline. The connected shared-network and transactional booking milestone is now implemented. See `README.md` and ADR 0002 for current behavior and remaining work.

**Real-map milestone:** At the user's subsequent request, the active map now displays real OpenStreetMap geography and uses a packaged Pacific Palisades road extract, including one-way and turn constraints. The fictional-map findings below describe the earlier audit only. See ADR 0003 and the packaged data README for provenance and the distinction between real roads and demonstration incident/capacity data.

## Recommended outcome

Deliver a deployed or reliably launchable wildfire evacuation **decision-support research application for one bounded pilot area**, with three working roles: evacuee, dispatcher, and shelter operator. A user requests a route; the backend excludes closed roads, selects a shelter that can accommodate the entire party, and issues a capacity reservation. A dispatcher changes a closure; affected routes become invalid. A shelter operator checks the party in. The same state survives browser refresh and service restart.

Use a small real road network if acquisition can be completed promptly. Use clearly identified replayed or simulated incidents and demonstration shelters. Real roads do not make synthetic shelter locations or incident data authoritative. The final demo should make this distinction visible. No claim of certified emergency guidance or verified live fire prediction.

Keep React/TypeScript and FastAPI. Avoid a rewrite. Prioritize one complete journey over additional dashboards. A responsive web application is sufficient; native mobile apps and hardware are outside this submission.

## What actually exists

Findings are based on the working tree, including existing uncommitted work, rather than only the committed version.

- **Interactive frontend:** `apps/web/src/App.tsx`, `simulation.ts`, and `components/OperationsMap.tsx` provide a usable training interface. There are 48 fictional junctions, 82 road segments, three shelters, closures, route comparison, and an animated journey. Routing runs locally in the browser. The current app imports the simulation, not the API client.
- **API foundation:** `services/api/src/werms_api/main.py` exposes health, hazards, shelters, route creation, route status, a scenario update, and WebSocket events. The separate demo graph has seven nodes and two shelters. This graph and the frontend graph are different.
- **Routing core:** `domain/routing.py` excludes blocked edges, applies deterministic risk/congestion penalties, and ranks shelters. Route responses contain versions, timestamps, reason codes, and a validity deadline.
- **Partial shelter control:** `store.py` guards a capacity increment with an in-process lock. There are no individual reservation records, expiry, cancellation, arrival, or release workflows. Repeated requests accumulate reserved demand.
- **Resource screen:** assignment is a browser-local toggle. There is no durable dispatch/acknowledgement workflow.
- **Infrastructure:** bootstrap, verification, containers, and CI are present. PostGIS and Redis are declared in Compose but the operational code still uses `DemoStore`. No Docker executable was found in the current shell during this audit.
- **ML:** `ml/` contains a plan, not trained models or an inference service. The expected approved-model mode remains disabled.
- **External feeds, real geography, authentication, audit persistence, and offline recovery:** not implemented in the inspected application paths.

These are usable foundations, but they do not yet constitute a connected operational application. Do not assign an arbitrary percentage-complete score: integration, persistence, and failure behavior dominate the remaining work.

Verification during this audit: API lint and all five API tests passed; frontend lint passed; all five frontend tests passed on rerun; the production web build passed. The initial full verification run stopped on a Vitest worker-start timeout, so record that intermittent runner issue rather than claiming the complete verification script passed uninterrupted. Existing tests verify the current prototype and do not establish the planned multi-client, persistent workflows.

## Scope to freeze today

**Required for submission:** one shared map/graph, API-connected routing, persistent closures/shelters/reservations/routes, three role workflows, basic protected operator access, route expiry/invalidation, controlled no-route results, a small durable resource assignment flow, clear source freshness, responsive UI, meaningful tests, and repeatable launch/demo instructions.

**Conditional:** one external fire-data adapter with a cached replay. Add it only after the connected core works. The demo must work without a network feed. Automatic feed-to-road closure decisions require an explicit uncertainty policy; an operator-confirmed closure is adequate for this sprint.

**Defer:** GRU/attention training, reinforcement learning, nationwide coverage, crowdsourced live traffic, predictive fire arrival, native mobile apps, push/SMS services, microservices, Redis scaling, advanced responder tracking, and a patent filing. Any existing presentation that describes these as completed must be corrected.

## Application design

### Evacuee

Choose a point on the pilot map or use permitted device location; allow a manual alternative. Enter party size. Show the selected shelter, estimated travel time, route, reservation state, latest source update, and a brief reason for the choice. Reject origins outside the supported area rather than snapping arbitrary world coordinates to the nearest demo node. Show loading, connection failure, full shelters, and no eligible route as deliberate states.

Separate **compare/preview routes** from **confirm evacuation plan**. A preview must not consume shelter capacity. Confirmation receives an opaque plan/reservation token; duplicate confirmation returns the same result. On arrival, provide the operator with the reservation code. GPS and calculated ETAs remain estimates, not verified tracking.

### Dispatcher

Sign in; inspect the shared map, active closures, source timestamps, shelter capacity, and affected routes. Close/reopen a road or enter a validated incident through the API. Record actor, time, and reason. Dispatch an available unit and show pending acknowledgement. Confirmed closures always take precedence over soft risk. Keep simulated scenario controls explicitly in demonstration mode.

### Shelter operator

Sign in; see occupancy and active reservations. Check in by reservation code, release/cancel a booking, adjust occupancy with a recorded reason, and restrict/close a shelter. The database must prevent overcapacity even if two users confirm at once. Capacity and reservation data must be shared across clients.

### Minimal resource workflow

Persist `available -> assigned -> acknowledged -> resolved -> available`, with one incident and one or two demonstration units. Record who assigned/acknowledged the unit. Reject double assignment. No claim of actual emergency-service connectivity. This completes a small part of the resource-management promise without building fleet tracking.

## Architecture and data choices

Use one FastAPI service and one authoritative routing module. The client draws the exact edge IDs and coordinates that the backend routes over. The existing simulation can remain an explicitly separate training mode; it must not become an independent operational authority.

The baseline names PostGIS as the long-term store. **For this one-week single-instance submission, propose SQLite transactions plus a versioned GeoJSON road snapshot if PostGIS setup would cost the first day.** This is a deliberate temporary departure to record when implementing, not a claim that PostGIS is already integrated. SQLite is appropriate for this bounded demo; do not deploy several API replicas against local database files. If PostGIS is already readily available, retain it and use the same transaction requirements. Redis is unnecessary for a single API process.

Minimum records: users/roles, road snapshot and versions, closures/hazard observations with provenance, shelters, reservations, routes, incidents, units/assignments, and audit events. Store creation/expiry timestamps. Include persistent storage in the deployment and demonstrate backup/restore. Keep keys and passwords out of source control; use tested password hashing and server-side role checks, not a client-only role selector.

Create route and reservation state consistently: evaluate against a versioned snapshot, commit a reservation only if capacity and hazard versions are still eligible, then issue the plan. On a conflict, re-evaluate another candidate or return a clear retry result. A successful shelter increment followed by a failed route save must not leak capacity.

Events need sequence/version metadata. WebSockets update connected clients; reconnect must fetch current route/status and shelter state so missed events do not preserve an invalid route. A short polling fallback is acceptable. Cache the app shell and last plan for read-only offline display if time permits; mark it stale and do not create offline bookings or assert current safety.

## Seven-day execution order

Dates below assume work starts 14 October and submission is around 21 October. Keep 21 October as final submission/buffer time rather than scheduling a new feature that morning. These are focused work blocks, not a guarantee; re-scope if available working hours are lower.

### Day 1 — 14 October: one connected route

Define graph and route contracts. Export a single pilot graph to the API and render that same graph in the client. Prefer a bounded OpenStreetMap snapshot with source/license attribution; timebox acquisition to half a day. If blocked, first integrate the existing graph and label it fictional. Do not block all integration waiting for geography.

Wire `api.ts` into an operational flow. Fetch map, shelters, closures, and system status. Submit a route and display its backend response. Align edge IDs, shelter IDs, units, and coordinate systems. Preserve useful current UI work.

**Exit evidence:** browser action creates a backend route; the displayed path contains exactly the returned edges. Refresh reloads backend state. Backend-down produces a visible error, not a silent local route.

### Day 2 — 15 October: persistence and correct bookings

Replace `DemoStore` for operational data with the selected database adapter. Implement preview, idempotent confirmation, per-party reservation expiry, cancellation, and arrival. Make route selection party-size aware and retry eligible shelters on capacity conflict. Apply the existing configured capacity policy consistently.

**Exit evidence:** service restart preserves state; a group that cannot fit is not booked; concurrent confirmations do not overbook; duplicate confirmation and retries do not duplicate reservations; cancellation/expiry releases capacity once.

### Day 3 — 16 October: changing conditions and validity

Implement operator closure updates and affected-route invalidation, route expiry in both status responses and UI, event reconnect/resync, and stale-source behavior. Add supported-area validation. Validate routing against a Dijkstra reference: the current backend heuristic adds kilometres to a minutes-based cost, so its admissibility is not established. Use a zero heuristic initially or a proven time lower bound before claiming optimality.

**Exit evidence:** closing a used edge invalidates that plan on another client; closing an unrelated edge does not unnecessarily invalidate it; an expired route never reports valid; a missed event is recovered on reconnect; all exits blocked returns a controlled no-route result.

### Day 4 — 17 October: real role workflows

Implement dispatcher and shelter-operator access and server-side authorization. Complete check-in, occupancy changes, shelter closure, audit records, and the minimal resource lifecycle. Keep private plan/reservation data scoped to its holder and authorized operators.

**Exit evidence:** a public client cannot change a closure, occupancy, or assignment; shelter changes affect routing; check-in converts reserved demand into occupancy exactly once; two dispatchers cannot assign the same unit twice; audit history identifies the operation and actor.

### Day 5 — 18 October: data provenance and usable screens

Finish real pilot geography if still outstanding. Add a replayable hazard input containing coordinates, observation time, ingestion time, source, confidence, and validation status. Quarantine malformed inputs. If the core is stable, add one NASA FIRMS fetch adapter behind that contract. Keep source failure and stale-data state visible.

Simplify mobile layouts, labels, route confirmation, shelter check-in, and no-route messages. Check keyboard access and contrast. Remove misleading live/AI claims. Have two or three people try the key workflows without coaching, if available.

**Exit evidence:** recorded incidents can be replayed reproducibly; a source outage leaves the application usable with an explicit degraded state; a user can find and confirm a plan on a phone-size screen; synthetic and externally sourced data remain distinguishable.

### Day 6 — 19 October: verification and deployment

Run the meaningful integration, concurrency, expiry, authorization, and recovery checks. Measure route API p95 on a stated graph and workload; use the existing two-second prototype target as a target, not an achieved claim. Exercise modest concurrent demand; record the actual achieved results and hardware.

Package a local launch with seed data and a persistent database. Deploy to one server with persistent storage and HTTPS if available; provide the exact local fallback. Verify restart, configuration, log handling, and backup/restore. An ephemeral hosting filesystem is not a durable database deployment.

**Exit evidence:** another machine or a clean setup can run the application from documented instructions; the hosted/local setup persists data; the complete demonstration works with external feeds disabled.

### Day 7 — 20 October: freeze and submission

Fix blockers only. Record the demo, finish the architecture diagram and report, capture actual results, and align the slides with implemented features. Prepare a short known-limitations section. Rehearse the failure scenario and local fallback. Reserve submission day for packaging and checks.

**Exit evidence:** source, launch instructions, demo recording, tests/results, screenshots, report, and slides form one consistent deliverable. No unexplained dependency on the developer's current shell or browser state.

## Reliability gaps to address first

1. **Two graphs and two routing authorities:** the current frontend and backend disagree structurally. A single shared graph and backend-generated plans are the first prerequisite.
2. **Unbounded reservations:** the backend increments demand without reservation identities or release. A preview/reservation distinction, idempotency, and expiry are mandatory before real users share the service.
3. **Capacity selection ignores party size:** candidate selection checks only whether some capacity exists; the later reservation can fail even when another shelter fits. Rank eligible full-party candidates and handle concurrent conflicts.
4. **Hazard/reservation/route consistency:** routing, reserving, and route save are separate operations. Implement a coherent version check and transaction so route publication and booking do not describe incompatible state.
5. **Expiry is metadata only:** the saved route has no expiry field, and route-status currently checks only its boolean validity. Enforce expiry in the server and client.
6. **Freshness is a score, not a complete policy:** the current age penalty saturates and does not establish reliable source availability or refusal behavior. Define degraded/expired states; adding cost alone does not make an old route current.
7. **Geographic and heuristic validity:** reject unsupported origins, respect one-way roads and units, and compare path costs to a trusted reference. Geographic distance is not automatically an admissible time heuristic.
8. **Missing protected mutations:** persistent closure, occupancy, and dispatch endpoints need authorization and auditability.

## What makes this a strong final project

The convincing demonstration is a multi-client sequence:

1. Evacuee A previews and confirms a plan for a party of four.
2. A shelter operator sees the reservation; a second evacuee sees reduced remaining capacity.
3. A dispatcher closes an edge on A's path. A sees the route invalidation and requests another plan; its old booking is transferred or released correctly.
4. Another shelter fills/closes; new requests choose another eligible destination, or show no route when none exists.
5. The operator checks in A once; replaying that action does not inflate occupancy.
6. A dispatcher assigns a demonstration resource and acknowledges/resolves the assignment.
7. Disconnect and reconnect a client, then restart the API. The app resynchronizes and persistent bookings remain correct.

Measure hard-closure violations (target zero in the tested suite), capacity violations (target zero), duplicate reservation count (target zero), route/invalidation latency, expiry behavior, and task completion in usability trials. Describe these as measured prototype results, not proof of real-world evacuation safety.

## Patent ambition: the honest path

Do not spend this submission week on a patent form or expensive hardware. Build the mechanisms and collect evidence first. A narrow research hypothesis for later work is **a protocol that couples freshness-dependent route validity with expiring shelter reservations and consistent selective invalidation under delayed updates**. The engineering benefit to investigate is fewer stale plans and orphaned reservations with bounded recomputation and update latency. This is a candidate to test and search, not an established novel invention.

Dynamic evacuation routing already appears in [US7349768B2](https://patents.google.com/patent/US7349768B2/en). Joint evacuation/resource planning with time-dependent unavailable road links appears in [WO2016119007A1](https://patents.google.com/patent/WO2016119007A1/en). Adding A*, ML, shelter capacity, or time-dependent closure handling does not by itself establish novelty. These two records are only an initial screen; a later search must compare actual claim elements across patents and publications.

Assuming an Indian filing, novelty, inventive step, industrial applicability, and statutory exclusions matter. Section 3(k) excludes computer programmes per se and algorithms; a software project title or an AI feature is insufficient. See [IP India's patent basics](https://ipindia.gov.in/basics-of-patents), [WIPO's Section 3(k) description](https://www.wipo.int/ip-development/en/agenda/flexibilities/details.jsp?id=8825), and [IP India's current guidelines index](https://ipindia.gov.in/resource/patents-resources-guidelines), which lists the CRI 2025 guidelines. A patent professional or institutional IP cell should evaluate any proposed claims and existing public disclosures before detailed public release of a future invention. A working application and a granted patent are different deliverables.

After submission, compare the candidate mechanism with fixed-expiry plans, whole-network invalidation, and independent shelter bookings under identical delayed/reordered event scenarios. Include a baseline that already handles timed road closures so the experiment does not credit existing methods as new. Report distributions over reproducible seeds and ablations, including increased refusal/longer routes. Only then decide whether there is a defensible invention.

## Data and ML boundaries

NASA FIRMS provides satellite active-fire detections; these are not exact fire perimeters. Spatial resolution, confidence, and latency need to be considered before inferring a road closure. For this sprint, pair observation displays with explicit operator closures or labeled replay policies. See the [NASA FIRMS map notes](https://firms.modaps.eosdis.nasa.gov/map/?os=firetv) and [NASA's discussion of detections versus perimeter boundaries](https://forum.earthdata.nasa.gov/viewtopic.php?sid=f9129e54a5c95057d70a7d9136472bf2&t=5200).

The [FireCastRL paper](https://arxiv.org/abs/2601.14238) addresses wildfire ignition forecasting and suppression simulation. A daily occurrence predictor does not directly provide fire arrival time on each road. Do not connect a classifier score to a minute-level safety guarantee. Keep predictive mode disabled for this submission; an evaluated baseline model is a later milestone, with dataset/license verification and causal splits already described in `ml/README.md`.

## Submission checklist

- Working three-role application with the complete shared-state demonstration.
- Persistent database and versioned graph/seed inputs with attribution.
- Reproducible setup, deployment/configuration guide, backup/restore, and a local fallback.
- Relevant passing tests and a short results file stating graph size, workload, hardware, and limitations.
- Architecture/data-flow diagram, endpoint summary, and concise explanation of routing and booking decisions.
- Demo video, screenshots, final report, and slides matching actual implemented behavior.
- Clear distinction between implemented functionality, simulated inputs, measured results, and future research.

The first implementation task is the Day 1 shared-graph/API vertical slice. Start there; adding more visual features before that will not close the largest delivery gap.

# WERMS Implementation Requirements Baseline

## Decision

The September DA2 research design and the latest behavioral diagrams form the implementation baseline. Earlier SRS documents remain useful for stakeholder intent, WebSocket delivery, offline resilience, and usability, but their Firebase/NoSQL choice is superseded by the later PostgreSQL/PostGIS design.

WERMS will be implemented as a modular monorepo with a React and TypeScript web client, a Python FastAPI operations service, PostgreSQL with PostGIS for durable spatial state, Redis for short-lived cache and event delivery, and a separate offline ML training plane.

## Non-negotiable safety invariants

- A returned route contains no edge intersecting an active hard hazard or authoritative closure.
- ML-derived risk is soft evidence. It may add caution but cannot remove a hard restriction.
- Every route records hazard, road, shelter, and model versions plus a validity deadline.
- Stale or unavailable live data is visible to the user; the system does not silently claim that old state is current.
- Shelter assignment uses effective occupancy, including short-lived reservations, and never exceeds allowed capacity.
- No-safe-route is a valid controlled outcome.
- Public views do not expose precise responder locations or individual civilian trajectories.

## Core use cases

### UC-01 Calculate dynamic evacuation route

Capture or accept a location, reject invalid or stale input, rank eligible shelters, exclude hard-blocked edges, apply risk-aware A*, return an explainable versioned route, and invalidate it when relevant state changes.

### UC-02 Ingest and process telemetry

Fetch fire and weather data independently, use configured fallbacks, validate schema/units/coordinates/timestamps, quarantine invalid data, retain provenance, publish a new hazard version, and invalidate only affected active routes.

### UC-03 Allocate emergency resources

Find a suitable available unit, reserve it atomically, calculate a responder route that avoids hazards and civilian bottlenecks, transmit the assignment, and commit only after acknowledgement or escalation handling.

### UC-04 Manage shelter capacity

Validate arrivals, update occupancy atomically, restrict assignments at the configured threshold, and redirect only incoming routes when a safe alternative exists. The current default is 90%, resolving the older 95% requirement in favor of the latest behavioral specification.

## Quality targets

- Safety: zero hard-hazard violations in automated invariant tests.
- API latency: initial prototype p95 at or below 2 seconds with a prebuilt graph; the older 500 ms algorithm-only target remains an internal benchmark.
- Freshness: every hazard and route response includes source time and version.
- Auditability: route inputs, weights, versions, outcome, and reason codes are reconstructable.
- Accessibility: the civilian flow remains high contrast, one-action oriented, keyboard usable, and understandable without technical terminology.
- Reproducibility: data version, split manifest, preprocessing configuration, random seed, model metrics, calibration artifact, and approval state are retained.

## ML boundary

The training task uses only the 60 days before the reference day across the 15 FireCastRL/GRIDMET variables. Reference-day and post-event rows are excluded. Related rows remain grouped during chronological and geographic splits. Logistic regression and gradient-boosted trees are mandatory baselines before a two-layer GRU with attention pooling is considered. Selection includes calibration quality (Brier score and ECE), not AUROC alone.

Until an artifact passes validation and is marked approved, runtime responses report `model_mode=disabled` and route using live hard hazards plus deterministic risk only.

## First milestone acceptance

- The browser can request a route and display the selected shelter, risk, versions, and validity.
- The API computes a route with a real A* implementation and cannot traverse blocked edges.
- A simulated hazard update is delivered over WebSockets and invalidates an affected route.
- Automated tests cover hard-hazard exclusion, controlled no-route behavior, and the API contract.
- The repository contains reproducible bootstrap, verification, container, and CI configuration.


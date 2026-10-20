# Presenting WERMS in interviews

Lead with a concrete problem: road availability and destination capacity change independently, so a route that looks short can be unusable by the time a party arrives. WERMS combines a real Indian road graph with transactional reservations and explainable scenario comparisons. It is a research demonstrator; do not describe it as a deployed public emergency platform.

## A focused five-minute walkthrough

Start on the Dehradun overview. Show actual Rajpur–Malsi roads and clearly sourced weather context. Compare destinations, confirm a booking, reload, and show its reservation persists. Explain why previews do not hold capacity and why booking retries use the same idempotency key.

Switch to the resilience lab. Run a road disruption and inspect the baseline/scenario overlays, changed reachability, compute time, graph version and snapshot revision. Run the compound disruption; a controlled no-route result is meaningful. Download the evidence and show that actual closures and reservations did not change.

Open the command centre and demonstrate named staff access, a site-scoped check-in, or a resource dispatch/acknowledgement/completion. Finish with the tests and benchmark rather than more screens.

## Engineering decisions to explain

- The planner uses A* with incoming-edge state for turn restrictions. Its geographic lower bound is derived from the minimum actual edge-cost/geodesic-distance ratio, making it admissible even when speed estimates are unusual. Randomized exhaustive comparisons verify optimality. Soft exposure and freshness costs scale with distance rather than OSM shape-point count.
- Active reservations are derived from active bookings. SQLite transactions serialize capacity and allocation decisions across independent connections; idempotent retry is separate from concurrency control.
- A partial unique index prevents two active resource assignments for one unit. Acknowledgement and completion are explicit lifecycle transitions.
- API role checks and site scope protect mutations independently of hidden UI controls. Password hashes, opaque session digests, expiry, revocation and persisted login throttling address different threats.
- Weather requests validate units and validity time, share a bounded cache, and degrade visibly. Weather context does not become an invented fire probability.
- Scenario analysis reuses the production planner on a coherent snapshot while prohibiting operational writes. Versioned JSON evidence makes comparisons explainable.
- PostGIS indexes roads and evaluates fire polygons/model-score neighbourhoods. SQLite serializes publication, route invalidation and capacity so no distributed commit is needed. A full PostgreSQL operational-store migration, distributed delivery, external identity and authoritative feeds remain future deployment work.

## Defensible resume wording

“Built an India-focused React/TypeScript and FastAPI decision-support application on a 4,480-node OpenStreetMap graph, with turn-aware routing, transactional capacity reservations, role-scoped staff workflows and non-destructive disruption analysis.”

“Built a causal wildfire-research pipeline over 9.51M daily records and 126,799 source windows, yielding 126,442 validated 60-day sequences across 15 environmental variables; enforced geographic/temporal separation and training-only preprocessing.”

“Compared Logistic Regression, boosted trees and a two-layer GRU with AUROC 0.841/0.863/0.891 on a frozen 841-case test cohort; evaluated AUPRC, recall, F1 and calibration, selecting the champion using validation only.”

“Integrated genuine model scores with real OSM roads, PostGIS and hazard-aware A* in a research replay; implemented hard fire exclusions, durable capacity reservations and idempotent operational workflows. Measured 164.32 ms local warm-planner p95 across 60 sequential India-pilot calls.”

The measured numbers belong to the checked-in benchmark environment and method. Do not turn them into production throughput or end-user safety claims. Do not invent user counts, deployment adoption, ML accuracy, government partnerships, patent status, or personal ownership of work you cannot explain. Read and modify the implementation yourself before using it as interview evidence.

## Questions to be ready for

Explain a retry after a lost response, simultaneous bookings for the final available spaces, a site closing during travel, a revoked staff session, a stale weather provider, and why reopening a road does not revive a previously invalidated plan. Discuss how you would migrate one coherent SQLite state store to PostGIS without losing reservation consistency. Distinguish your measured latency from an HTTP benchmark and a load test.

For the ML demonstration, open the AI observatory and run actual inference before showing sensitivity and the US routing replay. Be ready to explain why 9.51M rows are not independent examples; why 126,799 differs from the source's advertised 126,800; why synthesized negatives and absent incident IDs limit validity; why a positive-heavy test cohort inflates the AUPRC baseline; and why residual ECE/India geographic shift block operational probability claims. The replay's unchanged path is legitimate evidence that a penalty was applied without forcing a dramatic answer. Its experimental spatial neighbourhood is not a measured grid footprint or proof of route safety. See the model card for every quoted figure.

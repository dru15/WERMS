# ADR 0001 System Shape

## Status

Accepted for the foundation milestone.

## Context

The project is developed by one person but has enterprise concerns: spatial queries, burst traffic, live updates, offline ML training, strict safety invariants, and auditable decisions. Beginning with many independently deployed microservices would add operational complexity before the domain boundaries are proven.

## Decision

Use a modular operations service with explicit domain ports, plus a separate web application and offline ML plane. Keep module boundaries aligned with ingestion, hazard fusion, routing, shelter allocation, resources, events, and model registry. Extract a module into a service only after independent scaling, failure isolation, or release cadence justifies it.

Use PostgreSQL/PostGIS as the authoritative store for spatial and operational state, Redis for disposable cache/event acceleration, WebSockets for client updates, and container images for reproducible deployment. The first runnable slice uses an in-memory adapter behind the same domain boundary because Docker is not installed on the current workstation.

## Consequences

The project gets one deployable backend during early development, transaction boundaries remain manageable, and tests can exercise safety behavior without infrastructure. Later PostGIS/Redis adapters can replace in-memory adapters without changing the route contract. ML training cannot block the operational read path, and an unavailable model degrades to a clearly labeled deterministic mode.


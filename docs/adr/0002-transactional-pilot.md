# Transactional pilot operations

Use a backend-owned network and one transaction for confirmed plan selection, capacity reservation, replacement, and persistence. Previews never reserve capacity, and expiry or invalidation releases a booking; this avoids the previous disconnected graphs and unbounded reservation increments.

The runnable local pilot uses SQLite with explicit transactions and a schema version because Docker/PostGIS is unavailable on the current workstation. This adapter is a single-server pilot foundation; PostGIS remains the intended adapter for real spatial ingestion and scaled operation. It supersedes the in-memory operational milestone in ADR 0001, not the long-term spatial architecture. Do not deploy independent database files per replica.

Operator mutations require a secret supplied separately from public route capability IDs. In development a local operator key is generated beside the database; production requires explicit secret configuration. The initial single-scope access design is extended by ADR 0004 with named accounts, role checks, and site-scoped sessions.

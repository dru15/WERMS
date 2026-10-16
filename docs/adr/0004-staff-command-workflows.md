# Staff and command workflows

Extend the local pilot database with additive account, session, login-attempt, incident, resource, and assignment tables. Keep all capacity and allocation decisions inside the same serialized SQLite transaction boundary. Existing operational data and schema version 1 remain readable; no road graph, booking, or occupancy is reseeded.

Use administrator-provisioned named accounts, salted PBKDF2-SHA256 passwords, and random opaque sessions whose digests are stored server-side. Sessions last eight hours and can be revoked. Persist failed login attempts across restarts, and throttle by both normalized username and client address. Keep the development operator key as a bootstrap/recovery administrator, with explicit configuration required for remote production mode. This local identity adapter is intentionally independent of a future institutional identity provider.

Enforce role checks at API boundaries and shelter scope again inside the arrival transaction. Administrators manage accounts and audits, dispatchers manage shared operational mutations, and shelter staff manage only their assigned site. Do not place staff credentials in URLs or browser persistent storage. Public route IDs remain unguessable booking capabilities and are excluded from public change events.

Incident reports retain source and observation time. A report is unverified operational input and cannot automatically close a road. Dispatcher closure actions remain explicit. Incident versions protect against lost updates; resolution requires acknowledgement and completion/cancellation of active assignments. Escalation raises priority without inventing external notification delivery.

Represent inventory as individual named units. A partial unique index plus a transaction prevents more than one active assignment per unit. Dispatch request IDs support retry; acknowledgement precedes completion, and completion/cancellation releases the unit. These are recorded command-desk actions rather than proof of external responder delivery or live GPS tracking.

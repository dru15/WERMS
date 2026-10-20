# WERMS

**Wildfire Evacuation and Resource Management System** combines an India-focused operations application with a reproducible wildfire-ML research pipeline. The main pilot covers Rajpur–Malsi, Dehradun, Uttarakhand: **4,480 real OpenStreetMap nodes and 4,547 physical road segments**. It includes vector mapping, hazard-aware A*, durable shelter reservations, staff workflows, and PostGIS fire-perimeter constraints.

The AI observatory serves three genuinely trained models, calibration evidence, held-out sequences, fresh CPU inference, sensitivity analysis, and a separate US spatial routing replay. **FireCastRL is a US dataset. Its scores are not validated India forecasts.** Closures, capacities, occupancy, travel estimates, and assembly-site suitability remain demonstration conditions. This is a research application, not emergency guidance or an established patent.

## What works

- Sharp MapLibre/OpenFreeMap vector maps with real roads, labels, land cover, source attribution, visible provider failure and retry. Local OSM context retains 127 mapped building/land/water features in Dehradun and 481 in the US replay during provider outages. Pan globally; route only inside the imported pilot.
- Turn-aware A* with a consistent geographic heuristic derived from actual graph costs. Hard road/fire exclusions precede search; full-party capacity and the configured 90% admission threshold constrain destinations. Soft exposure costs scale with distance.
- Preview without allocation; confirm with durable, idempotent reservations; recover interrupted confirmation after reload; replace atomically; cancel, expire, invalidate and check in exactly once.
- Administrator, dispatcher and site-scoped shelter accounts; salted PBKDF2 password hashes, eight-hour revocable sessions, login throttling and persistent audits. API permissions are independent of hidden controls.
- Incident reporting/acknowledgement/escalation/resolution, resource registration and atomic dispatch/acknowledgement/completion/cancellation, and reservation-aware site administration.
- A resilience lab comparing road, site, compound and fire-perimeter disruptions without changing operational state. It exports the actual comparison evidence.
- PostGIS-indexed OSM geometry, topological polygon validation and boundary-inclusive `ST_Intersects`. Publishing a perimeter atomically invalidates affected bookings and releases capacity. Saved constraints survive a spatial-service outage; new geometry fails visibly.
- Sourced Open-Meteo model weather for the fixed pilot centre, with IST timestamps, validation, cache/backoff and explicit stale/unavailable states. Weather context is not a fire probability.

## Real ML evidence

The downloaded public release contains **126,799 windows and 9,509,925 daily rows**, rather than the advertised 126,800 windows. Its measured reference-day classes are **33,471 positive / 93,328 negative**, also different from the release summary. See the [source audit](docs/research/firecastrl-source-audit.md) and [measured data manifest](docs/benchmarks/firecastrl-data-audit.json).

The pipeline validates ordered 75-day blocks, derives the reference date, excludes the reference and following 14 days from predictors, converts observed Kelvin temperatures to Celsius, quarantines 343 invalid-temperature windows and removes 14 duplicate windows. It produces **126,442 causal 60×15 sequences**. Chronology, geographic groups and exact input hashes are checked across splits; preprocessing fits training only. Original incident-family IDs are absent, so residual source-label leakage cannot be disproved.

The frozen run uses 58,307 training, 1,129 validation, 1,013 calibration and 841 test cases; other location/year combinations remain unused. Test AUROC:

- Logistic Regression: **0.841**.
- Gradient-Boosted Trees: **0.863**.
- Two-layer GRU with temporal attention: **0.891**.

The report also records AUPRC, recall, precision, F1, Brier, ECE, confusion matrices, reliability bins and precision–recall curves. **Boosted trees were selected by validation AUPRC**, despite the GRU's higher test AUROC. Test prevalence is 87.99%, so its no-skill AUPRC is 0.880. Substantial calibration error remains under prevalence shift; cohort probabilities are not population fire incidence. The [model card](docs/model-card.md) explains these limits.

Open **AI observatory** to inspect the actual run and execute all three models with last-seven-day ablation sensitivity. Its California replay projects an unused source case through PostGIS onto real OSM roads and into A* costs. The 3 km experimental support neighbourhood is not a measured GRIDMET footprint. The replay creates no booking, never transfers US scores to India, and does not contribute to benchmark accuracy. See [ML routing evidence](docs/benchmarks/ml-routing-replay.json).

## Run locally

Python 3.12+ and Node.js 22+ are required. Copy `.env.example` to `.env` only if no local `.env` exists.

```powershell
./scripts/bootstrap.ps1
./scripts/dev.ps1
```

Open [the app](http://localhost:5173/) and [API docs](http://localhost:8000/docs). Bootstrap installs CPU PyTorch and the ML/spatial dependencies. With no trained artifacts the observatory explicitly reports that no evaluation is published. No scores are fabricated.

Operational data lives at `data/operational/dehradun.sqlite3`; raw data, training output, local credentials and temporary runtimes are ignored by Git. A verified **974 KB research model bundle** is included in the Python package for a working fresh-clone AI demo. Its attribution, hashes and research-only status are in `services/api/src/werms_api/data/research/firecastrl-v1/`. Leave `ML_REPORT_PATH` blank to use it; an explicit missing custom run reports unavailable instead of invented scores. Preserve old California/fictional databases separately. **Schema 2 adds fire exclusions and prevents an older release silently opening a store whose constraints it cannot enforce.** A graph-version change still requires explicit migration or a new database.

In development, open `data/operational/operator.key` yourself and enter it under **Operator access** or **Command centre → First-time administrator setup**. Create named accounts, then use staff sign-in. Credentials stay in tab memory; reload requires sign-in. Booking codes grant plan access/cancellation and should be protected. Remote hosting requires an explicit strong `OPERATOR_API_KEY`, HTTPS and correct browser API/WebSocket URLs.

## Train the public dataset

On Windows, the bounded resumable downloader uses the official public Kaggle endpoint:

```powershell
.\.venv\Scripts\python.exe scripts/fetch_research_assets.py dataset
./scripts/run_ml_pipeline.ps1
.\.venv\Scripts\python.exe scripts/build_ml_replay.py
```

The explicit cross-platform training steps are `python -m ml.prepare --source <CSV>` and `python -m ml.train`. Completed output directories are immutable; choose a new `--output` and update `ML_REPORT_PATH` for another run. Local training output is in `artifacts/models/firecastrl-v1/`; the measured report is checked in at [firecastrl-run.json](docs/benchmarks/firecastrl-run.json). The app defaults to the packaged verified research run, so dataset download is needed only for reproduction/retraining. `scripts/publish_research_models.py` verifies an explicit artifact allowlist before publishing that small bundle. See [ML instructions](ml/README.md) for the contract and Windows TLS recovery. Never load model artifacts from untrusted uploads.

## Run native PostGIS without Docker

The tested Windows setup uses official portable PostgreSQL 17.11 and PostGIS 3.6.2 archives inside this workspace, a limited application role and a localhost-only cluster. It installs no Windows service.

```powershell
.\.venv\Scripts\python.exe scripts/fetch_research_assets.py postgres --core
.\.venv\Scripts\python.exe scripts/fetch_research_assets.py postgis
.\.venv\Scripts\python.exe scripts/start_local_postgis.py
```

Keep that terminal running. It writes a private `SPATIAL_DATABASE_URL` into ignored `.env`; restart the API afterwards. Ctrl+C shuts down this project's cluster. Without PostGIS, ordinary road/capacity operations still work, but spatial scenarios and ML routing replay are unavailable. [Runtime provenance](docs/research/postgis-runtime.md) documents sources and licensing.

PostGIS evaluates geometry; SQLite serializes publication, invalidation, capacity and booking state. This avoids a distributed commit. Existing exclusions are immutable geometry-to-edge projections tied to the imported road version; disabling one never revives old bookings. This is not a migration of the entire operational store to PostgreSQL.

## Verification and measurement

```powershell
./scripts/verify.ps1
```

The checks cover causal windows, split separation, saved-model inference parity, A* optimality against exhaustive search, hard exclusions, capacity/concurrency, idempotency, outage behavior, role scope, booking recovery and frontend interactions. A real PostGIS integration test runs when `WERMS_TEST_SPATIAL_URL` is supplied; it is otherwise explicitly skipped.

The [A* benchmark](docs/benchmarks/dehradun-astar.json) records 60 warm sequential planner calls, 180 destination routes, median **131.34 ms**, p95 **164.32 ms**, and zero blocked-edge violations in three disruption checks. These are local planner measurements, not HTTP load, throughput or safety certification. The earlier Dijkstra benchmark remains historical evidence. [Demo guide](docs/demo-guide.md), [portfolio walkthrough](docs/portfolio-guide.md), and [release scope](docs/release-scope.md) describe the implemented boundaries.

## Data, services and deployment limits

Road provenance/reconstruction is in the [data README](services/api/src/werms_api/data/README.md). © OpenStreetMap contributors, ODbL 1.0; OpenFreeMap/OpenMapTiles attribution remains visible. The mapped Scholars Home School, Central Park and Dehradun Zoo destinations are demonstration assembly sites with synthetic capacity, not verified emergency shelters. No live traffic, satellite-fire, FSI/ISRO/NDMA integration or endorsement is claimed.

Open-Meteo's free hosted endpoint is subject to its [non-commercial terms](https://open-meteo.com/en/terms). Supply appropriate paid access through `WEATHER_API_KEY`, or disable weather, for uses outside those terms. Provider outages never become invented low-risk forecasts.

Compose now wires a PostGIS service and read-only model-artifact mount into the API; Redis remains optional and unused. The CPU inference image is configured, but **container execution has not been verified because Docker is absent**. Native Windows execution is tested. Production still needs authoritative India hazard/weather histories, geographic model validation, verified shelters, external security/user evaluation, operational deployment hardening and a prior-art investigation. Patentability and real evacuation safety are not established.

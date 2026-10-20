# Versioned OpenStreetMap road extracts

## Active India pilot

`dehradun-network.json` contains the Rajpur–Malsi, Dehradun, Uttarakhand derivative: 4,480 mapped road nodes, 4,547 physical segments, one-way rules and one imported node-based turn restriction. Its boundary is south/west/north/east `[30.357, 78.063, 30.391, 78.088]`. Initial demonstration destinations are Scholars Home School, Central Park and Dehradun Zoo (Malsi Deer Park), at their mapped coordinates with a nearby road access point. Capacities are synthetic; no official shelter status, emergency suitability or building access is verified.

© OpenStreetMap contributors. This road/place derivative is distributed under [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), with [OSM attribution and licensing](https://www.openstreetmap.org/copyright). Source code has a separate licence. Only road/place fields needed by the application are compiled; source contact details are not included.

The manifest retains the official bounded API URL, raw-source SHA-256, import/acquisition timestamps, country, timezone, origin presets and graph version. Acquisition time is not a road-survey date. Rebuild the same profile from the retained ignored raw file with:

```powershell
.\.venv\Scripts\python.exe -X utf8 scripts\import_osm_network.py --profile dehradun --site "Scholars Home School" --site "Central Park" --site "Dehradun Zoo (Malsi Deer Park)"
```

Add `--fetch --osm-api` for a fresh bounded download. The India graph uses a separate `data/operational/dehradun.sqlite3` database. Keep previous databases rather than reusing bookings on changed geometry.

## Archived California pilot

`palisades-network.json` contains a bounded derivative of OpenStreetMap data for Pacific Palisades, Los Angeles. © OpenStreetMap contributors. The road and mapped-place data is distributed under the [Open Database License, ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/); see [OSM attribution and licensing](https://www.openstreetmap.org/copyright).

The included derivative database is available here in machine-readable form. The application's source code is separate from this data licence. Demonstration capacities and occupancy are WERMS seed values, not authoritative emergency information.

The extract contains 1,029 mapped nodes, 1,110 physical road segments (289 one-way segments), and 19 node-based turn restrictions. The initial assembly destinations are the OSM-mapped Palisades Branch Los Angeles Public Library, Palisades Recreation Center, and Palisades Charter High School; their operation, suitability, opening status, and access are not verified.

Acquisition uses one bounded official OSM API request. The manifest includes its exact URL, download time, raw-source SHA-256, licence, and import time. The API has no dataset-wide observation timestamp, so `data_timestamp` is explicitly marked `timestamp_mode=download-time`. It is the extract acquisition time, not a guarantee that every road attribute was surveyed then.

Rebuild from a retained raw extract with:

```powershell
.\.venv\Scripts\python.exe scripts\import_osm_network.py --profile palisades --site "Palisades Branch Los Angeles Public Library" --site "Palisades Recreation Center" --site "Palisades Charter High School"
```

To fetch a new bounded extract first, add `--fetch --osm-api`. Overpass queries and a documented mirror are also supported by `--endpoint`, but the OSM API was used for this snapshot after Overpass timeouts. Raw downloads are stored under ignored `data/raw/`; no end-user route request calls the import API.

The importer uses Haversine road lengths, recorded one-way direction, public motor-vehicle access, node-based turn restrictions, and static speed estimates. Ways with complex via-way restrictions, conditional rules, private/prohibited access, or construction are excluded conservatively. It does not implement all navigation restrictions, lane semantics, live road conditions, or verified building access. Unsupported one-way tag values must not be treated as bidirectional. Assembly markers use mapped-place coordinates; routing ends at the nearest imported road node.

The graph version hashes the compiled geometry, road rules, origins, and assembly configuration. A new version requires an explicit database migration or a separate `OPERATIONAL_DB_PATH`. Do not silently reseed existing reservations on a new network.

## Local vector context

After rebuilding a road extract, run `python scripts/build_map_context.py` to add real building, green-space and water geometry from the same archived OSM response. The script checks the raw-source SHA-256 before changing display context. It preserves every routing node, edge, origin, site and road version. Dehradun has 127 context features; Palisades has 481. The vector renderer uses these plus local road labels when the online basemap is unavailable; coverage is limited to the extracted pilot. No map-provider tiles are bulk downloaded. The existing ODbL/source attribution applies.

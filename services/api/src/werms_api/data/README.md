# Pacific Palisades road extract

`palisades-network.json` contains a bounded derivative of OpenStreetMap data for Pacific Palisades, Los Angeles. © OpenStreetMap contributors. The road and mapped-place data is distributed under the [Open Database License, ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/); see [OSM attribution and licensing](https://www.openstreetmap.org/copyright).

The included derivative database is available here in machine-readable form. The application's source code is separate from this data licence. Demonstration capacities and occupancy are WERMS seed values, not authoritative emergency information.

The extract contains 1,029 mapped nodes, 1,110 physical road segments (289 one-way segments), and 19 node-based turn restrictions. The initial assembly destinations are the OSM-mapped Palisades Branch Los Angeles Public Library, Palisades Recreation Center, and Palisades Charter High School; their operation, suitability, opening status, and access are not verified.

Acquisition uses one bounded official OSM API request. The manifest includes its exact URL, download time, raw-source SHA-256, licence, and import time. The API has no dataset-wide observation timestamp, so `data_timestamp` is explicitly marked `timestamp_mode=download-time`. It is the extract acquisition time, not a guarantee that every road attribute was surveyed then.

Rebuild from a retained raw extract with:

```powershell
.\.venv\Scripts\python.exe scripts\import_osm_network.py --site "Palisades Branch Los Angeles Public Library" --site "Palisades Recreation Center" --site "Palisades Charter High School"
```

To fetch a new bounded extract first, add `--fetch --osm-api`. Overpass queries and a documented mirror are also supported by `--endpoint`, but the OSM API was used for this snapshot after Overpass timeouts. Raw downloads are stored under ignored `data/raw/`; no end-user route request calls the import API.

The importer uses Haversine road lengths, recorded one-way direction, public motor-vehicle access, node-based turn restrictions, and static speed estimates. Ways with complex via-way restrictions, conditional rules, private/prohibited access, or construction are excluded conservatively. It does not implement all navigation restrictions, lane semantics, live road conditions, or verified building access. Unsupported one-way tag values must not be treated as bidirectional. Assembly markers use mapped-place coordinates; routing ends at the nearest imported road node.

The graph version hashes the compiled geometry, road rules, origins, and assembly configuration. A new version requires an explicit database migration or a separate `OPERATIONAL_DB_PATH`. Do not silently reseed existing reservations on a new network.

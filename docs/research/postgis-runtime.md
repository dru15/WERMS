# Portable PostGIS runtime for WERMS

Initial source research on 20 October 2026. The portable runtime was subsequently installed and run locally: PostgreSQL 17.11 and PostGIS 3.6.2, with a limited application role and 4,547 indexed Dehradun segments. A real boundary-contact/invalid-polygon integration test passed. [Measured spatial evidence](../benchmarks/postgis-spatial.json) records an index-assisted query, seven perimeter intersections, a three-to-two destination reroute and zero hard-constraint violations. The research/setup discussion below distinguishes its original recommendations from this later execution evidence.

## Viable Windows packages

PostgreSQL offers Windows binary archives through EDB. PostGIS explicitly recommends those binaries when registry installation is unavailable; its ZIP packages can be copied into the corresponding PostgreSQL installation. Match the PostgreSQL **major version and x64 architecture**, rather than mixing a pg16 extension bundle with pg17. [PostgreSQL Windows downloads](https://www.postgresql.org/download/windows/), [EDB binary downloads](https://www.enterprisedb.com/download-postgresql-binaries), [PostGIS portable-install guidance](https://postgis.net/documentation/getting_started/install_windows/unreleased_versions/)

The following two URLs returned HTTP 200 with `Content-Type: application/zip` to HEAD requests during this audit:

- [PostgreSQL 17.11-5 Windows x64 binary ZIP](https://get.enterprisedb.com/postgresql/postgresql-17.11-5-windows-x64-binaries.zip): **381,531,864 bytes**, approximately 363.9 MiB. PostgreSQL's [application metadata](https://www.postgresql.org/applications-v2.xml) identified `postgresql_17`, `windows-x64`, version `17.11-5` at audit time. This metadata advertises the installer, so the ZIP URL was additionally checked directly.
- [PostGIS 3.6.2 bundle for PostgreSQL 17 x64](https://download.osgeo.org/postgis/windows/pg17/postgis-bundle-pg17-3.6.2x64.zip): **123,959,035 bytes**, approximately 118.2 MiB. The [official OSGeo cache directory](https://download-cache.osgeo.org/postgis/windows/pg17/) lists the same named archive and size. [PostGIS release instructions](https://postgis.net/documentation/getting_started/install_windows/released_versions/) describe these ZIP files as the extension binaries.

Allow approximately **482.1 MiB of downloads**, plus space for extracted packages and a separate database cluster. Expanded size has not been measured. Download over HTTPS, record a local SHA-256 in a reproducibility manifest, and preserve bundled licence notices. A locally computed checksum detects subsequent changes to that downloaded artifact; it is not an independently published publisher checksum. OSGeo exposes an MD5 companion file, which is useful for accidental corruption checks but should not be represented as a security signature.

PostgreSQL uses the permissive PostgreSQL License. PostGIS is generally GPL version 2 or later; its bundled dependencies carry additional licences. Preserve their notices if redistributing a runtime. [PostgreSQL licence](https://www.postgresql.org/about/licence/), [PostGIS source licence inventory](https://github.com/postgis/postgis/blob/master/LICENSE.TXT)

## Workspace layout and lifecycle

Proposed ignored paths are `tools/postgresql/pgsql/` for binaries, `data/operational/postgis/` for the cluster, `data/operational/postgis.log` for logs, and a separate ignored bootstrap password file. Extract the PostgreSQL ZIP, inspect the PostGIS ZIP layout, then copy its corresponding `bin`, `lib`, and `share` contents into that `pgsql` root. Do not install a Windows service. Missing Microsoft Visual C++ runtime DLLs remain a possible prerequisite to check by executing `postgres.exe --version`; this audit did not install or validate those libraries.

The following PowerShell command pattern is derived from the official `initdb` and `pg_ctl` interfaces. Before execution, resolve paths inside this workspace, check that port 55432 is unused, create parent directories, generate a private bootstrap password file, and check every native command exit code. `initdb` is one-time only: do not run it against an existing cluster. [initdb reference](https://www.postgresql.org/docs/17/app-initdb.html), [pg_ctl reference](https://www.postgresql.org/docs/17/app-pg-ctl.html)

```powershell
$taskPgBin = 'C:\Users\hp\Desktop\Coding\WERMS\tools\postgresql\pgsql\bin'
$taskPgData = 'C:\Users\hp\Desktop\Coding\WERMS\data\operational\postgis'
$taskPgLog = 'C:\Users\hp\Desktop\Coding\WERMS\data\operational\postgis.log'
$taskPgPasswordFile = 'C:\Users\hp\Desktop\Coding\WERMS\data\operational\postgis-bootstrap.secret'

& "$taskPgBin\initdb.exe" -D $taskPgData -U werms_admin --encoding=UTF8 --locale=C --auth=scram-sha-256 --pwfile=$taskPgPasswordFile
& "$taskPgBin\pg_ctl.exe" -D $taskPgData -l $taskPgLog -o '-h 127.0.0.1 -p 55432' -w start
& "$taskPgBin\pg_isready.exe" -h 127.0.0.1 -p 55432
& "$taskPgBin\psql.exe" -h 127.0.0.1 -p 55432 -U werms_admin -d postgres -v ON_ERROR_STOP=1 -c 'CREATE DATABASE werms;'
& "$taskPgBin\psql.exe" -h 127.0.0.1 -p 55432 -U werms_admin -d werms -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION postgis; SELECT PostGIS_Full_Version();'

# Controlled shutdown of this cluster only:
& "$taskPgBin\pg_ctl.exe" -D $taskPgData -m fast -w stop
```

Supply client credentials using an appropriately protected passfile or environment scoped to the process; never print passwords or commit connection secrets. The application should use a separate limited database role after extension/schema setup. Ordinary `pg_ctl start` launches a background server; `pg_ctl register` is the separate Windows-service operation and is unnecessary here. Keep durable writes and normal shutdown enabled rather than copying the documentation's performance-test example that disables `fsync`. [pg_ctl lifecycle](https://www.postgresql.org/docs/17/app-pg-ctl.html), [server startup and ownership](https://www.postgresql.org/docs/17/server-start.html)

## Minimal spatial contract

The following is a proposed WERMS schema, not a claim that the source documentation supplies this application model. Keep the existing versioned road graph's IDs and full segment geometry. Coordinates must be longitude, latitude with SRID 4326. Store hard fire exclusion polygons separately from soft ML risk cells. Spatial indexes use GiST. [PostGIS data management and indexes](https://postgis.net/docs/using_postgis_dbmanagement.html#build-indexes)

```sql
CREATE TABLE road_segments (
    road_version text NOT NULL,
    edge_id text NOT NULL,
    geom geometry(LineString, 4326) NOT NULL,
    PRIMARY KEY (road_version, edge_id),
    CHECK (NOT ST_IsEmpty(geom) AND ST_IsValid(geom))
);
CREATE INDEX road_segments_geom_gix ON road_segments USING gist (geom);

CREATE TABLE fire_exclusions (
    exclusion_id text PRIMARY KEY,
    hazard_version text NOT NULL,
    geom geometry(MultiPolygon, 4326) NOT NULL,
    active boolean NOT NULL DEFAULT true,
    valid_from timestamptz NOT NULL,
    valid_until timestamptz,
    CHECK (NOT ST_IsEmpty(geom) AND ST_IsValid(geom)),
    CHECK (valid_until IS NULL OR valid_until > valid_from)
);
CREATE INDEX fire_exclusions_geom_gix ON fire_exclusions USING gist (geom);
```

Use parameterized queries to ingest GeoJSON **geometry fragments**, rather than whole Features/FeatureCollections. For example, `ST_SetSRID(ST_GeomFromGeoJSON($1::jsonb),4326)` for an accepted LineString and `ST_Multi(...)` for accepted Polygon/MultiPolygon exclusions. Validate types, finite coordinates, geographic bounds, size and vertex limits before insertion. `ST_IsValid` checks two-dimensional topological validity; it does not establish that a polygon is a real fire or lies within the pilot. Reject invalid polygons rather than silently changing their meaning with automatic repairs. [GeoJSON constructor](https://postgis.net/docs/ST_GeomFromGeoJSON.html), [validity predicate](https://postgis.net/docs/ST_IsValid.html)

For a frozen road/hazard version and planning timestamp, return hard-blocked edge IDs with a spatial join:

```sql
SELECT r.edge_id
FROM road_segments AS r
WHERE r.road_version = $1
  AND EXISTS (
    SELECT 1
    FROM fire_exclusions AS f
    WHERE f.hazard_version = $2
      AND f.active
      AND f.valid_from <= $3::timestamptz
      AND (f.valid_until IS NULL OR f.valid_until > $3::timestamptz)
      AND ST_Intersects(r.geom, f.geom)
  );
```

`ST_Intersects` includes boundaries: touching the exclusion counts as blocked. It includes an index-aware bounding-box prefilter, followed by the actual geometry test; bounding-box overlap alone must not decide closure. [ST_Intersects semantics and indexing](https://postgis.net/docs/ST_Intersects.html)

Application integration decisions: union these IDs with explicit road closures and graph hard blocks before A* expansion; a high or low ML score must never reopen them. Hold one coherent hazard revision through preview and revalidate it at reservation confirmation. A configured PostGIS outage or graph-version mismatch should produce a visible unavailable state, rather than quietly dropping exclusion constraints. A generic geometry overlay that never influences the planner does not satisfy the intended PostGIS integration.

## Evidence required after implementation

Record `SELECT version(), PostGIS_Full_Version()` from the actual runtime, imported road count/version, and `EXPLAIN (ANALYZE, BUFFERS)` for a representative spatial intersection. Exercise intersecting, boundary-touching and disjoint roads; verify no selected route traverses any blocked edge; verify explicit road closures remain enforced without a polygon. Check extension failure, database outage, malformed polygons and version changes. Only then describe local PostGIS integration as tested. This research task performed package-header checks and documentation review only.

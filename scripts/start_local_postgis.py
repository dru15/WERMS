"""Extract and run the official private workspace PostGIS runtime on localhost.

No Windows service is installed. Credentials live only in ignored local files.
Keep this command running; Ctrl+C shuts down this project's cluster gracefully.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
PGSQL = ROOT / "tmp/runtime/postgresql/pgsql"
DATA = ROOT / "data/operational/postgis"
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def run(name, *args):
    log = ROOT / "tmp" / f"pg-cli-{uuid4().hex}.log"
    with log.open("w+b") as stream:
        result = subprocess.run(
            [str(PGSQL / "bin" / f"{name}.exe"), *map(str, args)],
            creationflags=NO_WINDOW,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=120,
        )
        stream.seek(0)
        output = stream.read().decode("utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(f"{name} failed: {output[-1500:]}")
    return output.strip()


def main():
    deadline = time.monotonic() + 7200
    print("Waiting for verified PostgreSQL core and PostGIS archive.", flush=True)
    bundle = ROOT / "tmp/postgis-download/postgis.zip"
    while (
        not (PGSQL / "bin/postgres.exe").exists()
        or not bundle.with_suffix(".zip.manifest.json").exists()
    ):
        if time.monotonic() > deadline:
            raise RuntimeError("Runtime downloads did not complete.")
        time.sleep(2)
    marker = PGSQL / ".postgis-installed.json"
    expected_bundle = json.loads(
        bundle.with_suffix(".zip.manifest.json").read_text(encoding="utf-8")
    )["sha256"]
    installed = (
        json.loads(marker.read_text(encoding="utf-8")).get("sha256") if marker.exists() else None
    )
    if installed != expected_bundle or not (PGSQL / "share/extension/postgis.control").exists():
        with zipfile.ZipFile(bundle) as archive:
            for entry in archive.infolist():
                parts = Path(entry.filename).parts
                folders = [i for i, p in enumerate(parts) if p in {"bin", "lib", "share"}]
                if not folders or entry.is_dir():
                    continue
                relative = Path(*parts[folders[0] :])
                target = (PGSQL / relative).resolve()
                if not target.is_relative_to(PGSQL.resolve()):
                    raise ValueError("Unsafe archive path.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
        marker.write_text(json.dumps({"sha256": expected_bundle}), encoding="utf-8")
    print(run("postgres", "--version"), flush=True)
    credential_file = ROOT / "data/operational/postgis-credentials.secret.json"
    credential_file.parent.mkdir(parents=True, exist_ok=True)
    if credential_file.exists():
        credentials = json.loads(credential_file.read_text(encoding="utf-8"))
    else:
        credentials = {"admin": secrets.token_urlsafe(36), "application": secrets.token_urlsafe(36)}
        credential_file.write_text(json.dumps(credentials), encoding="utf-8")
        credential_file.chmod(0o600)
    if not (DATA / "PG_VERSION").exists():
        password_file = credential_file.with_suffix(".init-password")
        password_file.write_text(credentials["admin"], encoding="utf-8")
        try:
            run(
                "initdb",
                "-D",
                DATA,
                "-U",
                "werms_admin",
                "--encoding=UTF8",
                "--locale=C",
                "--auth=scram-sha-256",
                f"--pwfile={password_file}",
            )
        finally:
            password_file.unlink(missing_ok=True)
    running = False
    try:
        with psycopg.connect(
            host="127.0.0.1",
            port=55432,
            user="werms_admin",
            password=credentials["admin"],
            dbname="postgres",
            connect_timeout=3,
        ):
            running = True
    except psycopg.OperationalError:
        pass
    if not running:
        run(
            "pg_ctl",
            "-D",
            DATA,
            "-l",
            ROOT / "data/operational/postgis.log",
            "-o",
            "-h 127.0.0.1 -p 55432",
            "-w",
            "start",
        )
    try:
        with psycopg.connect(
            host="127.0.0.1",
            port=55432,
            user="werms_admin",
            password=credentials["admin"],
            dbname="postgres",
            autocommit=True,
            connect_timeout=5,
        ) as db:
            if not db.execute("SELECT 1 FROM pg_database WHERE datname='werms'").fetchone():
                db.execute("CREATE DATABASE werms")
        with psycopg.connect(
            host="127.0.0.1",
            port=55432,
            user="werms_admin",
            password=credentials["admin"],
            dbname="werms",
            autocommit=True,
            connect_timeout=5,
        ) as db:
            db.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            if not db.execute("SELECT 1 FROM pg_roles WHERE rolname='werms_spatial'").fetchone():
                db.execute(
                    sql.SQL("CREATE ROLE werms_spatial LOGIN PASSWORD {}").format(
                        sql.Literal(credentials["application"])
                    )
                )
            db.execute("CREATE SCHEMA IF NOT EXISTS werms_spatial AUTHORIZATION werms_spatial")
            db.execute(
                "ALTER ROLE werms_spatial IN DATABASE werms SET search_path=werms_spatial,public"
            )
            version = db.execute("SELECT PostGIS_Full_Version()").fetchone()[0]
        env = ROOT / ".env"
        lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
        url = f"postgresql://werms_spatial:{credentials['application']}@127.0.0.1:55432/werms"
        lines = [line for line in lines if not line.startswith("SPATIAL_DATABASE_URL=")]
        lines.append(f"SPATIAL_DATABASE_URL={url}")
        env.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"PostGIS ready on 127.0.0.1:55432. {version}", flush=True)
        (ROOT / "tmp/postgis-runtime.json").write_text(
            json.dumps({"status": "ready", "version": version, "port": 55432}), encoding="utf-8"
        )
        while True:
            time.sleep(5)
    finally:
        print(run("pg_ctl", "-D", DATA, "-m", "fast", "-w", "stop"), flush=True)


if __name__ == "__main__":
    main()

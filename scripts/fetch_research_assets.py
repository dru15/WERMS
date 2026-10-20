"""Resumable, bounded parallel downloads of this project's fixed public research assets.

Run with dataset, postgres, or postgis. Parts are verified by HTTP Content-Range
and length before assembly; source SHA-256 records the exact downloaded release.
No executable files are run and no system directories are modified.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import struct
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    "torch": (
        "https://files.pythonhosted.org/packages/18/cf/ae99bd066571656185be0d88ee70abc58467b76f2f7c8bfeb48735a71fe6/torch-2.6.0-cp312-cp312-win_amd64.whl",
        204120469,
        "tmp/ml-wheels/torch-2.6.0-cp312-cp312-win_amd64.whl",
    ),
    "dataset": (
        "https://www.kaggle.com/api/v1/datasets/download/firecastrl/us-wildfire-dataset/Wildfire_Dataset.csv",
        1132250555,
        "data/raw/firecastrl/Wildfire_Dataset.csv",
    ),
    "postgres": (
        "https://get.enterprisedb.com/postgresql/postgresql-17.11-5-windows-x64-binaries.zip",
        381531864,
        "tmp/postgis-download/postgresql.zip",
    ),
    "postgis": (
        "https://download-cache.osgeo.org/postgis/windows/pg17/postgis-bundle-pg17-3.6.2x64.zip",
        123959035,
        "tmp/postgis-download/postgis.zip",
    ),
}


def fetch(name, core=False):
    url, size, relative = ASSETS[name]
    core_marker = ROOT / "tmp/runtime/postgresql/pgsql/.core-installed.json"
    if core and core_marker.exists():
        installed = json.loads(core_marker.read_text(encoding="utf-8"))
        if (
            installed == {"source": url, "bytes": size}
            and (core_marker.parent / "bin/postgres.exe").exists()
        ):
            print(
                "Verified PostgreSQL core is already installed; preserving the runtime.", flush=True
            )
            return
    target = ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    parts = ROOT / "tmp" / "asset-parts" / name
    parts.mkdir(parents=True, exist_ok=True)
    chunk_size = 8 * 1024 * 1024
    ranges = [(i, min(i + chunk_size, size) - 1) for i in range(0, size, chunk_size)]
    selected_entries = None
    probe = ROOT / "tmp" / "postgis-download" / "postgres-core-sparse.zip"
    if core:
        if name != "postgres":
            raise ValueError("Core selection applies only to the PostgreSQL archive.")
        tail = parts / "central-directory.bin"
        tail_size = 1024 * 1024
        subprocess.run(
            [
                "curl.exe",
                "-sS",
                "-L",
                "--fail",
                "--max-time",
                "180",
                "--range",
                f"{size - tail_size}-{size - 1}",
                url,
                "-o",
                str(tail),
            ],
            check=True,
        )
        if tail.stat().st_size != tail_size:
            raise RuntimeError("The official archive did not return the requested directory range.")
        data = tail.read_bytes()
        eocd = data.rfind(b"PK\x05\x06")
        if eocd < 0:
            raise RuntimeError("Archive end-of-directory record is missing.")
        fields = struct.unpack("<4s4H2LH", data[eocd : eocd + 22])
        if fields[6] < size - tail_size:
            tail_size = size - fields[6]
            subprocess.run(
                [
                    "curl.exe",
                    "-sS",
                    "-L",
                    "--fail",
                    "--max-time",
                    "240",
                    "--range",
                    f"{size - tail_size}-{size - 1}",
                    url,
                    "-o",
                    str(tail),
                ],
                check=True,
            )
            if tail.stat().st_size != tail_size:
                raise RuntimeError("Incomplete central directory.")
        with probe.open("wb") as stream:
            stream.seek(size - tail_size)
            stream.write(tail.read_bytes())
        with zipfile.ZipFile(probe) as archive:
            selected_entries = [
                entry
                for entry in archive.infolist()
                if entry.filename.startswith(("pgsql/bin/", "pgsql/lib/", "pgsql/share/"))
                or entry.filename.lower().endswith(("license", "copyright"))
            ]
        required = set()
        for entry in selected_entries:
            first = entry.header_offset // chunk_size
            last = min(size - 1, entry.header_offset + entry.compress_size + 66000) // chunk_size
            required.update(range(first, last + 1))
        ranges = [(start, end) for start, end in ranges if start // chunk_size in required]
        print(
            f"Core runtime: {len(selected_entries)} entries; "
            f"{sum(b - a + 1 for a, b in ranges):,} download bytes",
            flush=True,
        )

    def part(bounds):
        start, end = bounds
        path, header = parts / f"{start:012}.part", parts / f"{start:012}.headers"
        expected = end - start + 1
        if path.exists() and path.stat().st_size == expected:
            return path
        for attempt in range(12):
            prefix = path.stat().st_size if path.exists() else 0
            if prefix > expected:
                raise RuntimeError("Unexpected oversized download part.")
            previous_headers = header.read_text(encoding="utf-8").lower() if header.exists() else ""
            if prefix and "content-range: bytes " not in previous_headers:
                raise RuntimeError("Cannot resume a part without verified range headers.")
            effective_start = start + prefix
            tail = path.with_suffix(".tail")
            result = subprocess.run(
                [
                    "curl.exe",
                    "-sS",
                    "-L",
                    "--fail",
                    "--connect-timeout",
                    "20",
                    "--max-time",
                    "120",
                    "--range",
                    f"{effective_start}-{end}",
                    "-D",
                    str(header),
                    url,
                    "-o",
                    str(tail),
                ],
                capture_output=True,
                text=True,
            )
            response_headers = header.read_text(encoding="utf-8").lower() if header.exists() else ""
            if (
                tail.exists()
                and tail.stat().st_size <= expected - prefix
                and f"content-range: bytes {effective_start}-{end}/{size}" in response_headers
            ):
                with path.open("ab") as output, tail.open("rb") as downloaded:
                    while block := downloaded.read(1024 * 1024):
                        output.write(block)
                tail.unlink()
            if path.exists() and path.stat().st_size == expected:
                print(f"{name}: verified bytes {start:,}..{end:,}", flush=True)
                return path
            print(f"{name}: retry {attempt + 1} for {start:,}; {result.stderr[-160:]}", flush=True)
        raise RuntimeError(f"Could not verify part {name} {start}-{end}; re-run to resume.")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        completed = list(executor.map(part, ranges))
    if core:
        with probe.open("r+b") as stream:
            for (start, _), path in zip(ranges, completed, strict=True):
                stream.seek(start)
                stream.write(path.read_bytes())
        destination = ROOT / "tmp" / "runtime" / "postgresql"
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(probe) as archive:
            for entry in selected_entries:
                resolved = (destination / entry.filename).resolve()
                if not resolved.is_relative_to(destination.resolve()):
                    raise ValueError("Unsafe archive path.")
                archive.extract(entry, destination)
        core_marker.write_text(json.dumps({"source": url, "bytes": size}), encoding="utf-8")
        print(f"Extracted CRC-verified PostgreSQL core to {destination}", flush=True)
        return
    temporary = target.with_suffix(target.suffix + ".assembling")
    digest = hashlib.sha256()
    with temporary.open("wb") as output:
        for path in completed:
            with path.open("rb") as input_file:
                while block := input_file.read(1024 * 1024):
                    output.write(block)
                    digest.update(block)
    if temporary.stat().st_size != size:
        raise RuntimeError("Assembled size mismatch.")
    temporary.replace(target)
    if (
        name == "torch"
        and digest.hexdigest() != "7e1448426d0ba3620408218b50aa6ada88aeae34f7a239ba5431f6c8774b1239"
    ):
        raise RuntimeError("Torch wheel checksum differs from official PyPI metadata.")
    manifest = {
        "source": url,
        "bytes": size,
        "sha256": digest.hexdigest(),
        "checksum_scope": "Computed local fingerprint, not a publisher signature",
    }
    target.with_suffix(target.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Completed {name}: {target} SHA256 {digest.hexdigest()}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("asset", choices=ASSETS)
    parser.add_argument("--core", action="store_true")
    args = parser.parse_args()
    fetch(args.asset, core=args.core)

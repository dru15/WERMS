"""Download pinned official PyPI wheels using Windows' curl TLS backend.

Useful on this workstation where Python/OpenSSL handshakes time out. Every wheel
is matched against Python's supported tags and verified against PyPI's SHA-256.
No alternate index, certificate bypass, or credentials are used.
"""

import argparse
import concurrent.futures
import hashlib
import json
import subprocess
from pathlib import Path

from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename

PINS = {
    "setuptools": "78.1.1",
    "numpy": "2.2.6",
    "pandas": "2.2.3",
    "scikit-learn": "1.6.1",
    "scipy": "1.15.2",
    "joblib": "1.4.2",
    "threadpoolctl": "3.6.0",
    "python-dateutil": "2.9.0.post0",
    "pytz": "2025.1",
    "tzdata": "2025.1",
    "six": "1.17.0",
    "torch": "2.6.0",
    "filelock": "3.18.0",
    "typing-extensions": "4.13.2",
    "networkx": "3.4.2",
    "jinja2": "3.1.6",
    "MarkupSafe": "3.0.2",
    "fsspec": "2025.3.2",
    "sympy": "1.13.1",
    "mpmath": "1.3.0",
    "pyarrow": "19.0.1",
    "psycopg": "3.2.6",
    "psycopg-binary": "3.2.6",
    "psutil": "7.0.0",
}
ROOT = Path(__file__).resolve().parents[1] / "tmp" / "ml-wheels"
TAGS = set(sys_tags())


def download(name_version):
    name, version = name_version
    metadata = ROOT / f"{name}-{version}.json"
    subprocess.run(
        [
            "curl.exe",
            "-sS",
            "--fail",
            "-L",
            "--retry",
            "2",
            "--max-time",
            "120",
            f"https://pypi.org/pypi/{name}/{version}/json",
            "-o",
            str(metadata),
        ],
        check=True,
    )
    release = json.loads(metadata.read_text(encoding="utf-8"))
    choices = [
        f
        for f in release["urls"]
        if f["filename"].endswith(".whl") and parse_wheel_filename(f["filename"])[3] & TAGS
    ]
    if not choices:
        raise RuntimeError(f"No compatible official wheel: {name} {version}")
    wheel = choices[0]
    target = ROOT / wheel["filename"]
    expected = wheel["digests"]["sha256"]
    if (
        not target.exists()
        or hashlib.file_digest(target.open("rb"), "sha256").hexdigest() != expected
    ):
        if name == "torch":
            from fetch_research_assets import fetch

            fetch("torch")
        else:
            subprocess.run(
                [
                    "curl.exe",
                    "-sS",
                    "--fail",
                    "-L",
                    "--retry",
                    "2",
                    "--max-time",
                    "900",
                    wheel["url"],
                    "-o",
                    str(target),
                ],
                check=True,
            )
    with target.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise RuntimeError(f"Checksum mismatch: {target.name}")
    print(f"Verified {target.name}", flush=True)
    return {"name": name, "version": version, "file": target.name, "sha256": actual}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", choices=PINS)
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        selected = {args.package: PINS[args.package]} if args.package else PINS
        records = list(pool.map(download, selected.items()))
    (ROOT / "manifest.json").write_text(json.dumps(records, indent=2), encoding="utf-8")

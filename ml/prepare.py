"""Audit the released ordered 75-day CSV and construct strictly causal sequences.

The release has no event ID. Every block is validated independently; an invalid
ordering stops ingestion rather than silently assigning labels to another event.
Post-reference rows validate the source contract but are never model inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from ml.features import VARIABLES

SPLIT_POLICY = {
    "train": "reference <= 2020-12-31; SHA256(1-degree cell) bucket 0..5",
    "validation": "2021-03-02..2022-12-31; cell bucket 6",
    "calibration": "2023-03-02..2023-12-31; cell bucket 7",
    "test": "2024-03-02..2025-12-31; cell bucket 8..9",
    "unused": "Other cell/year combinations; 60-day temporal purge at each later period boundary",
    "caveat": (
        "No original incident IDs are released. Geographic blocking mitigates offset-negative "
        "families; it cannot prove absence of all source-label leakage."
    ),
}


def assign_split(latitude: float, longitude: float, reference: str) -> tuple[str, str]:
    cell = f"{math.floor(latitude)}:{math.floor(longitude)}"
    bucket = int(hashlib.sha256(f"werms-42:{cell}".encode()).hexdigest()[:8], 16) % 10
    name = "unused"
    if reference <= "2020-12-31" and bucket < 6:
        name = "train"
    elif "2021-03-02" <= reference <= "2022-12-31" and bucket == 6:
        name = "validation"
    elif "2023-03-02" <= reference <= "2023-12-31" and bucket == 7:
        name = "calibration"
    elif "2024-03-02" <= reference <= "2025-12-31" and bucket >= 8:
        name = "test"
    return cell, name


def validate_window(frame: pd.DataFrame):
    if len(frame) != 75:
        raise ValueError(
            "Incomplete 75-day window; source ordering cannot be inferred safely."
        )
    if frame.latitude.nunique() != 1 or frame.longitude.nunique() != 1:
        raise ValueError(
            "Coordinate changes inside a 75-row block: source contract mismatch."
        )
    days = pd.to_datetime(frame.datetime, format="%Y-%m-%d", errors="raise").to_numpy(
        "datetime64[D]"
    )
    if not np.all(np.diff(days) == np.timedelta64(1, "D")):
        raise ValueError(
            "Non-daily dates inside a source block: source contract mismatch."
        )
    labels = frame.Wildfire.astype(str).str.strip().str.lower().to_numpy()
    if not np.isin(labels, ["yes", "no"]).all() or np.any(labels[:60] != "no"):
        raise ValueError(
            "Unexpected pre-reference labels: quarantine source pending manual audit."
        )
    label = int(labels[60] == "yes")
    if not np.all(labels[60:] == ("yes" if label else "no")):
        raise ValueError("Unexpected post-reference label pattern.")
    sequence = frame[list(VARIABLES)].iloc[:60].to_numpy(dtype=np.float32)
    if not np.isfinite(sequence).all():
        return None, "nonfinite_input"
    # Raw GRIDMET temperatures are Kelvin in the observed release, despite its
    # metadata claiming Celsius. Never guess from a single row or silently mix units.
    temps = sequence[:, [VARIABLES.index("tmmn"), VARIABLES.index("tmmx")]]
    if not np.all((temps >= 180) & (temps <= 350)):
        return None, "unexpected_temperature_units_or_range"
    sequence[:, VARIABLES.index("tmmn")] -= 273.15
    sequence[:, VARIABLES.index("tmmx")] -= 273.15
    latitude, longitude = float(frame.latitude.iloc[0]), float(frame.longitude.iloc[0])
    if not (24 <= latitude <= 50 and -125 <= longitude <= -66):
        return None, "outside_conus_bounds"
    if (
        (sequence[:, 0] < 0).any()
        or (sequence[:, 1:3] < 0).any()
        or (sequence[:, 1:3] > 100).any()
    ):
        return None, "invalid_precipitation_or_humidity"
    reference = str(days[60])
    cell, split = assign_split(latitude, longitude, reference)
    identifier = hashlib.sha256(
        f"{latitude:.8f}:{longitude:.8f}:{reference}".encode()
    ).hexdigest()[:20]
    metadata = {
        "sample_id": identifier,
        "latitude": latitude,
        "longitude": longitude,
        "reference_date": reference,
        "input_start": str(days[0]),
        "input_end": str(days[59]),
        "label": label,
        "geo_group": cell,
        "split": split,
    }
    return (sequence, metadata), None


def prepare(source: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    raw_tensor = output / "sequences.partial.f32"
    with source.open("rb") as stream:
        sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
    metadata, seen, quarantine = [], {}, Counter()
    raw_classes = Counter()
    rows, windows, duplicates, positive = 0, 0, 0, 0
    with raw_tensor.open("wb") as tensor_file:
        for chunk in pd.read_csv(source, chunksize=75000):
            if not set(
                ("latitude", "longitude", "datetime", "Wildfire", *VARIABLES)
            ) <= set(chunk):
                raise ValueError(
                    "Release schema differs from the audited FireCastRL contract."
                )
            rows += len(chunk)
            for start in range(0, len(chunk), 75):
                frame = chunk.iloc[start : start + 75]
                if len(frame) == 75:
                    raw_classes[str(frame.Wildfire.iloc[60]).strip().lower()] += 1
                record, reason = validate_window(frame)
                windows += 1
                if reason:
                    quarantine[reason] += 1
                    continue
                sequence, row = record
                positive += row["label"]
                digest = hashlib.sha256(sequence.tobytes()).hexdigest()
                row["sequence_sha256"] = digest
                previous = seen.get(row["sample_id"])
                if previous:
                    if previous != (row["label"], digest):
                        raise ValueError(
                            "Conflicting labels or inputs for duplicate event key."
                        )
                    duplicates += 1
                    continue
                seen[row["sample_id"]] = (row["label"], digest)
                sequence.tofile(tensor_file)
                metadata.append(row)
            print(
                f"Audited {rows:,} rows; accepted {len(metadata):,} causal windows",
                flush=True,
            )
    if not metadata:
        raise ValueError("No valid training sequences remain.")
    mapped = np.memmap(
        raw_tensor, dtype=np.float32, mode="r", shape=(len(metadata), 60, 15)
    )
    target = np.lib.format.open_memmap(
        output / "sequences.npy", mode="w+", dtype=np.float32, shape=mapped.shape
    )
    for start in range(0, len(metadata), 1024):
        target[start : start + 1024] = mapped[start : start + 1024]
    target.flush()
    del target, mapped
    raw_tensor.unlink()
    frame = pd.DataFrame(metadata)
    frame.to_parquet(output / "metadata.parquet", index=False)
    manifest = {
        "source": source.name,
        "sha256": sha256,
        "source_version": 1,
        "license": "MIT",
        "windows": windows,
        "raw_rows": rows,
        "accepted": len(metadata),
        "quarantined": sum(quarantine.values()),
        "quarantine_reasons": dict(quarantine),
        "duplicates_removed": duplicates,
        "source_positive_windows_before_dedup": positive,
        "raw_reference_day_class_counts": {
            "positive": raw_classes["yes"],
            "negative": raw_classes["no"],
        },
        "advertised_counts": {"windows": 126800, "positive": 50720, "negative": 76080},
        "count_discrepancy": (
            "Measured CSV differs from author summary; observed counts take precedence."
        ),
        "accepted_reference_date_range": [
            str(frame.reference_date.min()),
            str(frame.reference_date.max()),
        ],
        "variables": list(VARIABLES),
        "input_days": 60,
        "excluded_reference_and_future_days": 15,
        "temperature_conversion": (
            "Observed Kelvin values validated 180..350 K then converted to Celsius"
        ),
        "split_policy": SPLIT_POLICY,
        "split_counts": frame.split.value_counts().to_dict(),
        "bounds": [
            float(frame.latitude.min()),
            float(frame.longitude.min()),
            float(frame.latitude.max()),
            float(frame.longitude.max()),
        ],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", type=Path, default=Path("data/raw/firecastrl/Wildfire_Dataset.csv")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/processed/firecastrl-v1")
    )
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output), indent=2))

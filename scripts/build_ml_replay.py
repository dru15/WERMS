"""Select a spatial replay case without using labels or model performance.

This supplemental case is from the unused cohort, separate from the frozen
benchmark. It demonstrates serving and spatial routing, not prospective accuracy.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/firecastrl-v1"
OUTPUT = ROOT / "artifacts/models/firecastrl-v1"


def main():
    network = json.loads(
        (ROOT / "services/api/src/werms_api/data/palisades-network.json").read_text(
            encoding="utf-8"
        )
    )
    frame = pd.read_parquet(DATA / "metadata.parquet")
    candidates = frame[frame.split.eq("unused")].copy()
    south, west, north, east = network["bounds"]
    latitude, longitude = (south + north) / 2, (west + east) / 2
    candidates["distance"] = np.hypot(
        (candidates.latitude - latitude) * 111, (candidates.longitude - longitude) * 92
    )
    index = candidates.distance.idxmin()
    row = frame.loc[index]
    sequences = np.load(DATA / "sequences.npy", mmap_mode="r")
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    record = {
        "id": str(row.sample_id),
        "label": int(row.label),
        "reference_date": str(row.reference_date),
        "latitude": float(row.latitude),
        "longitude": float(row.longitude),
        "variables": manifest["variables"],
        "sequence": np.asarray(sequences[index]).tolist(),
        "cohort": "unused",
        "selection_rule": (
            "Nearest unused-cohort source location to fixed Palisades research footprint; "
            "no label or model-score selection"
        ),
        "purpose": "Spatial routing plumbing replay; excluded from reported evaluation metrics",
        "road_version": network["version"],
    }
    (OUTPUT / "routing-replay-case.json").write_text(
        json.dumps(record, allow_nan=False), encoding="utf-8"
    )
    print({key: record[key] for key in ("id", "reference_date", "cohort", "road_version")})


if __name__ == "__main__":
    main()

"""One causal feature contract shared by training and inference."""

from __future__ import annotations

import numpy as np

VARIABLES = (
    "pr",
    "rmax",
    "rmin",
    "sph",
    "srad",
    "tmmn",
    "tmmx",
    "vs",
    "bi",
    "fm100",
    "fm1000",
    "erc",
    "etr",
    "pet",
    "vpd",
)
DAYS = 60


def tabular_features(sequences: np.ndarray) -> np.ndarray:
    """Summary features retain time structure without exposing coordinates or labels."""
    if sequences.ndim != 3 or sequences.shape[1:] != (DAYS, len(VARIABLES)):
        raise ValueError("Expected [sample, 60 pre-reference days, 15 variables].")
    if not np.isfinite(sequences).all():
        raise ValueError(
            "Non-finite environmental values must be quarantined before training."
        )
    return np.concatenate(
        [
            sequences.mean(axis=1),
            sequences.std(axis=1),
            sequences.min(axis=1),
            sequences.max(axis=1),
            sequences[:, -1],
            sequences[:, -7:].mean(axis=1),
            sequences[:, -30:].mean(axis=1),
            sequences[:, -7:].mean(axis=1) - sequences[:, :7].mean(axis=1),
        ],
        axis=1,
    ).astype(np.float32)


def feature_names() -> list[str]:
    return [
        f"{stat}_{var}"
        for stat in (
            "mean60",
            "std60",
            "min60",
            "max60",
            "last",
            "mean7",
            "mean30",
            "trend",
        )
        for var in VARIABLES
    ]

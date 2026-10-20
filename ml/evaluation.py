"""Untouched-test metrics and validation-only probability calibration."""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)


def logit(probabilities):
    p = np.clip(np.asarray(probabilities), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p)).reshape(-1, 1)


def fit_calibrator(y, probabilities):
    # Fit only on the dedicated calibration split, never on validation or test.
    return LogisticRegression(C=1e6, max_iter=1000).fit(logit(probabilities), y)


def calibrate(model, probabilities):
    return model.predict_proba(logit(probabilities))[:, 1]


def select_threshold(y, probabilities) -> float:
    """Choose F1 threshold on validation only, before test labels are inspected."""
    precision, recall, thresholds = precision_recall_curve(y, probabilities)
    f1 = (
        2
        * precision[:-1]
        * recall[:-1]
        / np.maximum(precision[:-1] + recall[:-1], 1e-12)
    )
    return float(thresholds[int(np.argmax(f1))])


def evaluate(y, probabilities, threshold: float) -> dict:
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(y)
    if len(np.unique(y)) != 2 or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError(
            "Evaluation requires both classes and finite probabilities in [0,1]."
        )
    predicted = p >= threshold
    bins, ece = [], 0.0
    for index in range(10):
        mask = (p >= index / 10) & (p < (index + 1) / 10 if index < 9 else p <= 1)
        count = int(mask.sum())
        confidence = float(p[mask].mean()) if count else None
        frequency = float(y[mask].mean()) if count else None
        if count:
            ece += count / len(y) * abs(confidence - frequency)
        bins.append(
            {
                "lower": index / 10,
                "upper": (index + 1) / 10,
                "count": count,
                "mean_probability": confidence,
                "observed_frequency": frequency,
            }
        )
    precision, recall, _ = precision_recall_curve(y, p)
    take = np.unique(
        np.linspace(0, len(precision) - 1, min(100, len(precision))).astype(int)
    )
    return {
        "auroc": float(roc_auc_score(y, p)),
        "auprc": float(average_precision_score(y, p)),
        "recall": float(recall_score(y, predicted, zero_division=0)),
        "precision": float(precision_score(y, predicted, zero_division=0)),
        "f1": float(f1_score(y, predicted, zero_division=0)),
        "brier": float(brier_score_loss(y, p)),
        "ece": float(ece),
        "threshold": threshold,
        "samples": len(y),
        "prevalence": float(y.mean()),
        "confusion_matrix": confusion_matrix(y, predicted, labels=[0, 1]).tolist(),
        "reliability_bins": bins,
        "precision_recall_curve": [
            {"precision": float(precision[i]), "recall": float(recall[i])} for i in take
        ],
    }

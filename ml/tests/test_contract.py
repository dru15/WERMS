"""Small fabricated fixtures test invariants; they are never training evidence."""

import numpy as np
import pytest

from ml.evaluation import calibrate, evaluate, fit_calibrator, select_threshold
from ml.features import tabular_features


def test_causal_feature_contract_rejects_post_event_rows_and_nonfinite_inputs():
    with pytest.raises(ValueError, match="60"):
        tabular_features(np.zeros((2, 75, 15)))
    x = np.zeros((2, 60, 15))
    x[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="Non-finite"):
        tabular_features(x)


def test_summary_features_preserve_last_day_and_recent_trend():
    x = np.broadcast_to(np.arange(60)[None, :, None], (2, 60, 15))
    features = tabular_features(x)
    assert features.shape == (2, 120)
    assert np.all(features[:, 60:75] == 59)
    assert np.all(features[:, 105:120] == 53)


def test_calibration_and_metrics_include_empty_bins_and_probability_one():
    y = np.array([0, 0, 0, 1, 1, 1])
    p = np.array([0, 0.1, 0.2, 0.8, 0.9, 1])
    threshold = select_threshold(y, p)
    result = evaluate(y, p, threshold)
    assert result["auroc"] == result["auprc"] == result["f1"] == 1
    assert sum(b["count"] for b in result["reliability_bins"]) == len(y)
    fitted = fit_calibrator(y, p)
    calibrated = calibrate(fitted, p)
    assert np.all((calibrated >= 0) & (calibrated <= 1))
    with pytest.raises(ValueError):
        evaluate(y, np.full(6, np.nan), 0.5)

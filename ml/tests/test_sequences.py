import numpy as np
import pandas as pd
import pytest

from ml.features import VARIABLES
from ml.prepare import assign_split, validate_window


def fixture_window():
    frame = pd.DataFrame(np.ones((75, 15)), columns=VARIABLES)
    frame["tmmn"], frame["tmmx"] = 280.0, 300.0
    frame["latitude"], frame["longitude"] = 38.25, -121.25
    frame["datetime"] = pd.date_range("2020-01-01", periods=75).strftime("%Y-%m-%d")
    frame["Wildfire"] = ["No"] * 60 + ["Yes"] * 15
    return frame


def test_reference_and_future_values_cannot_enter_predictors():
    frame = fixture_window()
    (before, meta), _ = validate_window(frame)
    frame.loc[60:, list(VARIABLES)] = 999999.0
    (after, changed_meta), _ = validate_window(frame)
    assert np.array_equal(before, after)
    assert meta == changed_meta
    assert meta["input_end"] < meta["reference_date"]
    assert before[0, VARIABLES.index("tmmn")] == pytest.approx(6.85, abs=1e-4)


def test_label_is_reference_row_not_any_pre_reference_row():
    frame = fixture_window()
    frame["Wildfire"] = "No"
    (sequence, meta), _ = validate_window(frame)
    assert meta["label"] == 0
    frame.loc[60:, "Wildfire"] = "Yes"
    (same_sequence, positive_meta), _ = validate_window(frame)
    assert np.array_equal(sequence, same_sequence)
    assert positive_meta["label"] == 1


def test_ordering_corruption_fails_closed_instead_of_misaligning_labels():
    frame = fixture_window()
    frame.loc[3, "datetime"] = frame.loc[2, "datetime"]
    with pytest.raises(ValueError, match="Non-daily"):
        validate_window(frame)
    frame = fixture_window()
    frame.loc[4, "longitude"] = -120.0
    with pytest.raises(ValueError, match="Coordinate changes"):
        validate_window(frame)


def test_one_geographic_group_can_never_cross_model_splits():
    for latitude in np.arange(25.2, 49, 1):
        assigned = {
            assign_split(latitude, -118.2, date)[1]
            for date in ("2020-01-01", "2021-06-01", "2023-06-01", "2024-06-01")
        }
        assert len(assigned - {"unused"}) <= 1
        assert assign_split(latitude, -118.2, "2023-01-15")[1] == "unused"

"""Integration check against an actual completed run; skipped on a fresh clone."""

from pathlib import Path

import numpy as np
import pytest
from werms_api.ml_research import ResearchModels


@pytest.mark.skipif(
    not Path("artifacts/models/firecastrl-v1/report.json").exists(),
    reason="Requires a completed real training run",
)
def test_saved_model_inference_matches_frozen_heldout_exports():
    research = ResearchModels("artifacts/models/firecastrl-v1")
    for record in research.report()["cases"]:
        case = research.case(record["id"])
        inferred = research.infer(record["id"])
        for model, expected in case["predictions"].items():
            assert np.isclose(inferred["predictions"][model], expected, atol=1e-5)
            assert 0 <= inferred["predictions"][model] <= 1
            assert len(inferred["sensitivity"][model]) == 5


def test_packaged_research_bundle_has_verified_models_and_fresh_inference():
    research = ResearchModels()
    case_id = research.report()["cases"][0]["id"]
    case = research.case(case_id)
    inferred = research.infer(case_id)
    for model, expected in case["predictions"].items():
        assert np.isclose(inferred["predictions"][model], expected, atol=1e-5)

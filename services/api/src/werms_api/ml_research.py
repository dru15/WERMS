"""Read experiment evidence and serve trusted, checksum-verified research models."""

from __future__ import annotations

import hashlib
import json
import threading
from importlib.resources import files
from pathlib import Path
from time import perf_counter


class ResearchModels:
    def __init__(self, directory: str | Path | None = None):
        self.directory = (
            Path(directory)
            if directory
            else Path(str(files("werms_api").joinpath("data/research/firecastrl-v1")))
        )
        self._loaded = None
        self._inference_lock = threading.Lock()

    def report(self) -> dict:
        path = self.directory / "report.json"
        if not path.exists():
            return {
                "status": "not_trained",
                "models": [],
                "cases": [],
                "message": (
                    "The FireCastRL source audit and training pipeline are being prepared. "
                    "No evaluation scores are substituted."
                ),
                "coverage": "Continental United States; not validated for India",
                "india_routing": "out_of_distribution",
                "source_url": "https://www.kaggle.com/datasets/firecastrl/us-wildfire-dataset",
            }
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("schema_version") != 1 or report.get("status") != "evaluated":
            raise ValueError("Unsupported ML experiment export.")
        replay = self.replay_case()
        if replay:
            report["routing_replay"] = {
                key: replay[key]
                for key in ("id", "reference_date", "cohort", "purpose", "road_version")
            }
        return report

    def replay_case(self):
        path = self.directory / "routing-replay-case.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def case(self, case_id: str) -> dict | None:
        replay = self.replay_case()
        if replay and replay["id"] == case_id:
            return replay
        # IDs are taken from the fixed report manifest, never used as file paths.
        if case_id not in {str(case["id"]) for case in self.report().get("cases", [])}:
            return None
        cases = json.loads((self.directory / "cases.json").read_text(encoding="utf-8"))
        return next((case for case in cases if str(case["id"]) == case_id), None)

    def infer(self, case_id: str) -> dict | None:
        case = self.case(case_id)
        if case is None:
            return None
        if not self._inference_lock.acquire(blocking=False):
            raise RuntimeError("Another inference is running. Retry shortly.")
        try:
            return self._infer_case(case)
        finally:
            self._inference_lock.release()

    def _infer_case(self, case):
        import joblib
        import numpy as np
        import torch

        from werms_api.ml_features import VARIABLES, tabular_features
        from werms_api.ml_models import WildfireGRU

        started = perf_counter()
        report = self.report()
        if self._loaded is None:
            for name, expected in report["artifacts"].items():
                if Path(name).name != name:
                    raise ValueError("Invalid model artifact name.")
                with (self.directory / name).open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                        raise ValueError("Model artifact checksum mismatch.")
            models = {
                key: joblib.load(self.directory / f"{key}.joblib")
                for key in ("logistic", "boosted")
            }
            calibrators = {
                key: joblib.load(self.directory / f"{key}-calibration.joblib")
                for key in ("logistic", "boosted", "gru")
            }
            gru = WildfireGRU()
            gru.load_state_dict(
                torch.load(self.directory / "gru.pt", map_location="cpu", weights_only=True)
            )
            gru.eval()
            torch.set_num_threads(4)
            scaler = np.load(self.directory / "sequence-scaler.npz")
            self._loaded = models, calibrators, gru, scaler["mean"], scaler["std"]
        models, calibrators, gru, mean, std = self._loaded
        sequence = np.asarray(case["sequence"], dtype=np.float32)
        variants = np.repeat(sequence[None], 16, axis=0)
        for index in range(15):
            variants[index + 1, -7:, index] = sequence[:-7, index].mean()
        features = tabular_features(variants)
        raw = {key: estimator.predict_proba(features)[:, 1] for key, estimator in models.items()}
        with torch.no_grad():
            raw["gru"] = torch.sigmoid(gru(torch.from_numpy((variants - mean) / std))).numpy()
        predictions, sensitivity = {}, {}
        for key, probabilities in raw.items():
            p = np.clip(probabilities, 1e-6, 1 - 1e-6)
            calibrated = calibrators[key].predict_proba(np.log(p / (1 - p)).reshape(-1, 1))[:, 1]
            predictions[key] = float(calibrated[0])
            impacts = [
                {
                    "variable": variable,
                    "probability_delta": float(calibrated[0] - calibrated[i + 1]),
                }
                for i, variable in enumerate(VARIABLES)
            ]
            sensitivity[key] = sorted(
                impacts, key=lambda impact: abs(impact["probability_delta"]), reverse=True
            )[:5]
        return {
            "case_id": case["id"],
            "model_version": report["version"],
            "predictions": predictions,
            "sensitivity": sensitivity,
            "elapsed_ms": round((perf_counter() - started) * 1000, 2),
            "method": (
                "Last-7-day ablation to earlier-history mean; sensitivity, not causal attribution"
            ),
            "mode": "historical-held-out-research",
            "india_routing": "out_of_distribution",
        }

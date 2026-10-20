"""Run all three models on the same audited cohort: python -m ml.train."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from ml.evaluation import calibrate, evaluate, fit_calibrator, select_threshold
from ml.features import VARIABLES, feature_names, tabular_features


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data", type=Path, default=Path("data/processed/firecastrl-v1")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("artifacts/models/firecastrl-v1")
    )
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "report.json").exists():
        raise ValueError(
            "Published runs are immutable; choose a new --output directory."
        )
    random.seed(args.seed)
    np.random.seed(args.seed)
    x = np.load(args.data / "sequences.npy", mmap_mode="r")
    meta = pd.read_parquet(args.data / "metadata.parquet")
    manifest = json.loads((args.data / "manifest.json").read_text(encoding="utf-8"))
    if x.shape != (len(meta), 60, 15):
        raise ValueError("Prepared tensor does not match its manifest.")
    indices = {
        name: np.flatnonzero(meta.split.eq(name))
        for name in ("train", "validation", "calibration", "test")
    }
    for name, ix in indices.items():
        if len(ix) < 20 or meta.iloc[ix].label.nunique() != 2:
            raise ValueError(f"Insufficient two-class cohort: {name}")
    # Geographic groups and temporal ranges are audited again at the training boundary.
    groups = {name: set(meta.iloc[ix].geo_group) for name, ix in indices.items()}
    input_hashes = {
        name: set(meta.iloc[ix].sequence_sha256) for name, ix in indices.items()
    }
    for a, ga in groups.items():
        for b, gb in groups.items():
            if a != b and ga & gb:
                raise ValueError("Geographic groups cross splits.")
            if a != b and input_hashes[a] & input_hashes[b]:
                raise ValueError("Identical input sequences cross model splits.")
    ordered = list(indices)
    for a, b in pairwise(ordered):
        if (
            meta.iloc[indices[a]].reference_date.max()
            >= meta.iloc[indices[b]].input_start.min()
        ):
            raise ValueError("Temporal windows cross split boundaries.")
    y = meta.label.to_numpy(dtype=np.int64)
    features = np.concatenate(
        [tabular_features(x[i : i + 1024]) for i in range(0, len(x), 1024)]
    )
    report = {
        "schema_version": 1,
        "status": "evaluated",
        "version": f"firecastrl-{args.seed}-{datetime.now(UTC):%Y%m%dT%H%M%S}",
        "created_at": datetime.now(UTC).isoformat(),
        "seed": args.seed,
        "source_url": "https://www.kaggle.com/datasets/firecastrl/us-wildfire-dataset",
        "coverage": "Continental United States; not validated for India",
        "india_routing": "out_of_distribution",
        "dataset": manifest,
        "sampling_caveat": (
            "Case-control cohort with synthesized negatives; reported calibration "
            "is not population incidence."
        ),
        "split_policy": manifest["split_policy"],
        "splits": {},
        "models": [],
        "cases": [],
        "selection_rule": (
            "Champion selected by calibrated validation AUPRC, never by test results."
        ),
    }
    for name, ix in indices.items():
        dates = meta.iloc[ix].reference_date
        report["splits"][name] = {
            "samples": len(ix),
            "positives": int(y[ix].sum()),
            "years": f"{dates.min()} to {dates.max()}",
            "geographic_groups": len(groups[name]),
        }
    all_predictions, validation_scores = {}, {}

    def finish(model_id, name, predict, seconds, extra=None):
        p_cal = predict(indices["calibration"])
        calibration = fit_calibrator(y[indices["calibration"]], p_cal)
        p_val = predict(indices["validation"])
        p_val_cal = calibrate(calibration, p_val)
        raw_threshold = select_threshold(y[indices["validation"]], p_val)
        threshold = select_threshold(y[indices["validation"]], p_val_cal)
        validation_scores[model_id] = evaluate(
            y[indices["validation"]], p_val_cal, threshold
        )["auprc"]
        p_test = predict(indices["test"])
        p_test_cal = calibrate(calibration, p_test)
        record = {
            "id": model_id,
            "name": name,
            "seconds": round(seconds, 3),
            "uncalibrated": evaluate(y[indices["test"]], p_test, raw_threshold),
            "calibrated": evaluate(y[indices["test"]], p_test_cal, threshold),
            "calibration": "Platt fit on separate calibration cohort",
            **(extra or {}),
        }
        report["models"].append(record)
        joblib.dump(calibration, args.output / f"{model_id}-calibration.joblib")
        all_predictions[model_id] = p_test_cal
        print(
            json.dumps(
                {
                    "model": name,
                    "seconds": seconds,
                    "auroc": record["calibrated"]["auroc"],
                    "auprc": record["calibrated"]["auprc"],
                }
            ),
            flush=True,
        )

    tabular = {
        "logistic": (
            "Logistic Regression",
            make_pipeline(
                StandardScaler(),
                LogisticRegression(max_iter=1500, C=1.0, random_state=args.seed),
            ),
        ),
        "boosted": (
            "Gradient-Boosted Trees",
            HistGradientBoostingClassifier(
                max_iter=150,
                max_leaf_nodes=15,
                learning_rate=0.08,
                l2_regularization=1,
                early_stopping=False,
                random_state=args.seed,
            ),
        ),
    }
    for model_id, (name, estimator) in tabular.items():
        started = perf_counter()
        estimator.fit(features[indices["train"]], y[indices["train"]])
        elapsed = perf_counter() - started
        joblib.dump(estimator, args.output / f"{model_id}.joblib")
        finish(
            model_id,
            name,
            lambda ix, fitted=estimator: fitted.predict_proba(features[ix])[:, 1],
            elapsed,
        )

    import torch
    from torch.utils.data import DataLoader, TensorDataset

    from ml.models import WildfireGRU

    torch.manual_seed(args.seed)
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    train_x = np.asarray(x[indices["train"]])
    mean, std = train_x.mean(axis=(0, 1)), train_x.std(axis=(0, 1))
    std = np.maximum(std, 1e-6)
    np.savez(args.output / "sequence-scaler.npz", mean=mean, std=std)
    train_tensor = torch.from_numpy(((train_x - mean) / std).astype(np.float32))
    del train_x
    generator = torch.Generator().manual_seed(args.seed)
    loader = DataLoader(
        TensorDataset(train_tensor, torch.from_numpy(y[indices["train"]]).float()),
        batch_size=256,
        shuffle=True,
        generator=generator,
        num_workers=0,
    )
    gru = WildfireGRU()
    optimizer = torch.optim.AdamW(gru.parameters(), lr=1e-3, weight_decay=1e-3)
    loss_fn = torch.nn.BCEWithLogitsLoss()

    def predict_gru(ix):
        gru.eval()
        batches = []
        with torch.no_grad():
            for start in range(0, len(ix), 512):
                tensor = torch.from_numpy(
                    ((np.asarray(x[ix[start : start + 512]]) - mean) / std).astype(
                        np.float32
                    )
                )
                batches.append(torch.sigmoid(gru(tensor)).numpy())
        return np.concatenate(batches)

    from sklearn.metrics import log_loss

    started = perf_counter()
    best_loss, stale, history = float("inf"), 0, []
    for epoch in range(args.epochs):
        gru.train()
        total, count = 0.0, 0
        for inputs, labels in loader:
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(gru(inputs), labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(gru.parameters(), 1.0)
            optimizer.step()
            total += float(loss.detach()) * len(labels)
            count += len(labels)
        val_loss = float(
            log_loss(y[indices["validation"]], predict_gru(indices["validation"]))
        )
        history.append(
            {
                "epoch": epoch + 1,
                "train_loss": total / count,
                "validation_loss": val_loss,
            }
        )
        print(json.dumps(history[-1]), flush=True)
        if val_loss < best_loss - 1e-4:
            best_loss, stale = val_loss, 0
            torch.save(gru.state_dict(), args.output / "gru.pt")
        else:
            stale += 1
            if stale >= 3:
                break
    gru.load_state_dict(
        torch.load(args.output / "gru.pt", map_location="cpu", weights_only=True)
    )
    finish(
        "gru",
        "2-layer GRU + attention",
        predict_gru,
        perf_counter() - started,
        {"history": history, "hidden_size": 32, "layers": 2},
    )
    report["champion"] = max(validation_scores, key=validation_scores.get)
    report["validation_auprc"] = validation_scores
    test = meta.iloc[indices["test"]].copy()
    for model_id, p in all_predictions.items():
        test[f"p_{model_id}"] = p
    test.to_parquet(args.output / "test-predictions.parquet", index=False)
    rng = np.random.default_rng(args.seed)
    selected = np.sort(rng.choice(len(test), min(20, len(test)), replace=False))
    cases = []
    for local_index in selected:
        row = test.iloc[local_index]
        sequence = x[indices["test"][local_index]]
        record = {
            "id": str(row.sample_id),
            "label": int(row.label),
            "reference_date": str(row.reference_date),
            "latitude": float(row.latitude),
            "longitude": float(row.longitude),
            "variables": list(VARIABLES),
            "dates": pd.date_range(row.input_start, periods=60)
            .strftime("%Y-%m-%d")
            .tolist(),
            "sequence": sequence.tolist(),
            "predictions": {
                k: float(p[local_index]) for k, p in all_predictions.items()
            },
        }
        cases.append(record)
        report["cases"].append(
            {key: record[key] for key in ("id", "label", "reference_date")}
        )
    (args.output / "cases.json").write_text(
        json.dumps(cases, allow_nan=False), encoding="utf-8"
    )
    report["features"] = feature_names()
    report["artifacts"] = {}
    for path in args.output.iterdir():
        if path.suffix in {".joblib", ".pt", ".npz"}:
            with path.open("rb") as file:
                report["artifacts"][path.name] = hashlib.file_digest(
                    file, "sha256"
                ).hexdigest()
    (args.output / "report.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(f"Published experiment {report['version']} to {args.output}", flush=True)


if __name__ == "__main__":
    with threadpool_limits(limits=4):
        main()

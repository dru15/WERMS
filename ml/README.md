# Reproducible wildfire research plane

The public FireCastRL CSV is source-labelled US research data, not an India forecast feed. Its original incident IDs are not released. See `docs/model-card.md` and `docs/research/firecastrl-source-audit.md` before interpreting scores.

## Commands

Install `services/api[dev,ml,spatial]` with Python 3.12. From the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/fetch_research_assets.py dataset
.\.venv\Scripts\python.exe -m ml.prepare
.\.venv\Scripts\python.exe -m ml.train
.\.venv\Scripts\python.exe scripts/build_ml_replay.py
```

`scripts/run_ml_pipeline.ps1` coordinates prepared-data reuse and training. Completed reports are immutable: another run needs `python -m ml.train --output artifacts/models/<new-version>` and a matching `ML_REPORT_PATH`. Set `LOKY_MAX_CPU_COUNT=4` on Windows to avoid the library's unavailable physical-core probe; CPU math libraries are limited to four threads during training.

## Contract

1. `prepare.py` hashes the original CSV and audits every contiguous 75-row block: stable coordinates, consecutive dates, source-label pattern, finite predictors and observed Kelvin temperature ranges. Contract corruption stops processing; invalid input windows are counted separately.
2. The target is the reference-row label at index 60. Inputs are rows 0–59 (`t−60` through `t−1`), never the reference or following fourteen days. `Wildfire`, coordinates and dates are not model features. Future weather cannot affect accepted predictors.
3. Observed Kelvin minimum/maximum temperatures are explicitly converted to Celsius. No imputation from future rows is allowed. The output records measured source counts, quarantines, duplicate removal, variable order, units policy and source fingerprint.
4. One-degree geographic cells receive fixed SHA-256 buckets. Training uses pre-2021 dates/buckets 0–5; validation uses 2021–22/bucket 6; calibration 2023/bucket 7; test 2024–25/buckets 8–9. Later periods have a sixty-day boundary purge. Other combinations remain unused. Training rechecks geographic groups, temporal windows and exact predictor hashes for overlap.
5. Logistic regression and histogram gradient boosting receive 120 causal summary features of the same 15 variables. A two-layer, 32-hidden-unit GRU receives the standardized 60×15 tensor and uses temporal attention. All preprocessing fits training only. The fixed GRU configuration allows twelve epochs, validation-loss checkpointing and three-epoch patience.
6. Platt calibration fits a separate calibration cohort. Validation alone selects each F1 threshold and the champion by AUPRC. Untouched test labels produce AUROC, AUPRC, precision, recall, F1, confusion matrices, Brier, ten-bin ECE, reliability bins and PR curves.
7. Model weights, scalers and calibrators are hashed. Serving uses the same packaged feature/model implementations as training; trusted joblib files are loaded only after hash verification. GRU loading uses `weights_only=True`. Case exports preserve input precision, and a saved-model integration check compares fresh predictions with the frozen test exports.

The measured run's test cohort has 87.99% positives, a substantial prevalence shift. Calibration remains unsuitable for operational probability claims. Missing incident families and synthetic negative construction are residual validity limits, not solved by high AUROC.

## Artifacts and replay

Ignored `data/processed/firecastrl-v1/` contains memory-mapped sequences, sample metadata and the audit manifest. Ignored `artifacts/models/firecastrl-v1/` contains training output, including test predictions and twenty seed-selected held-out case exports. Public reports are copied into `docs/benchmarks/`. `scripts/publish_research_models.py` verifies an explicit model/report/case allowlist and publishes the small research bundle under `services/api/src/werms_api/data/research/firecastrl-v1/`. This tracked package includes attribution and hashes, not raw training data or credentials, and explicitly grants no operational approval. With `ML_REPORT_PATH` blank, serving defaults to that bundle; a custom path selects another completed run.

`build_ml_replay.py` selects an unused-cohort case nearest the fixed California footprint without selecting on label or prediction. It is separate from evaluation. The API uses its genuine boosted-tree score, a declared 3 km experimental neighbourhood, PostGIS spatial joins and real OSM roads to demonstrate soft A* exposure costs. Current demonstration road/capacity conditions are not historical incident reconstruction; the replay cannot create a reservation. India transfer is refused.

## Windows TLS recovery used on this workstation

Python/OpenSSL registry handshakes timed out while Windows curl worked. `scripts/download_ml_dependencies.py` downloads pinned official PyPI wheels and verifies PyPI SHA-256 values; `scripts/fetch_research_assets.py torch` resumes the pinned PyTorch wheel and verifies its published digest. The other fixed assets use verified HTTP byte ranges and local source fingerprints; those fingerprints are not publisher signatures. No certificate checks are disabled and no alternate package index is used.

After the wheels are verified, offline installation can use `python -m pip install --no-index --find-links tmp/ml-wheels ...`. Ordinary environments should use the standard CPU PyTorch index and the declared project extras. The Windows recovery scripts are conveniences, not a dependency on this user's global Python installation.

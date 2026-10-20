# FireCastRL research model card

Run: `firecastrl-42-20261020T164258`, seed 42, CPU, Python 3.12.14, NumPy 2.2.6, scikit-learn 1.6.1, PyTorch 2.6.0. Status: **research only; no operational deployment approval**.

## Intended use and exclusions

Compare wildfire-reference-label classifiers on the public US FireCastRL cohort, inspect input causality/calibration, and demonstrate how genuine model scores can become soft spatial routing costs. This is not a model of fire spread, personal evacuation safety, shelter suitability, or real-time India ignition probability. Neither US operational suitability nor India transfer is established.

The [author-linked release](https://www.kaggle.com/datasets/firecastrl/us-wildfire-dataset) advertises MIT licensing, GRIDMET environmental histories and IRWIN-derived labels with synthesized negatives. The application does not independently verify each label against IRWIN. The [primary-source audit](research/firecastrl-source-audit.md) distinguishes release claims from measured evidence.

## Measured data

The 1,132,250,555-byte CSV has SHA-256 `0be59f7d6a82865c21a37d26b3a390cb8e657b72bcc55750f16b5a4e8bc512ae`. It contains **126,799 ordered 75-day windows / 9,509,925 rows**, with 33,471 positive and 93,328 negative reference labels. These differ from the advertised 126,800 / 50,720 / 76,080 counts. They are dataset labels, not independently verified distinct ignitions.

Preparation quarantined 343 windows whose input temperatures violated the observed Kelvin range, removed 14 exact duplicate event windows and accepted **126,442** sequences. Reference dates span 2014-03-01 to 2025-03-29. [Audit manifest](benchmarks/firecastrl-data-audit.json).

Each target is the label at source-row index 60. Inputs are exclusively the preceding sixty days, in this order: `pr,rmax,rmin,sph,srad,tmmn,tmmx,vs,bi,fm100,fm1000,erc,etr,pet,vpd`. No label, reference-day/future variable, date or coordinate is a predictor. Minimum/maximum temperature values are observed in Kelvin despite release metadata claiming Celsius; preparation checks the range and converts them to Celsius. Other columns remain in released numeric units; the exact upstream mapping of `pet` remains unresolved. No future-row imputation is used.

## Evaluation design

- Train: **58,307**, 11,070 positive, reference 2014-03-01 through 2020-12-31; geographic buckets 0–5.
- Validation: **1,129**, 372 positive, 2021-03-02 through 2022-12-30; bucket 6.
- Calibration: **1,013**, 657 positive, 2023-03-03 through 2023-12-31; bucket 7.
- Test: **841**, 740 positive, 2024-03-02 through 2025-03-24; buckets 8–9.
- Unused: **65,152** other location/year combinations. Processing the full source is distinct from training on every accepted window.

One-degree cells receive fixed SHA-256 buckets. Later periods have sixty-day temporal boundary purges. Training rechecks temporal separation, disjoint geographic groups and disjoint exact input hashes. Scalers fit training only. Original incident-family identifiers are unavailable; spatial blocking and deduplication cannot prove absence of all source-family leakage or label noise.

Logistic regression and histogram gradient boosting use 120 causal summaries of the 15 variables. The GRU uses the full standardized 60×15 tensor, two 32-unit recurrent layers, dropout 0.15 and learned temporal attention. AdamW uses learning rate 0.001, weight decay 0.001, batch 256, gradient clipping 1.0, up to twelve epochs and three-epoch validation-loss patience. This run stopped after eight epochs and restored the epoch-five checkpoint. Hyperparameters were fixed before test scoring; there was no test-driven search.

Platt calibration fits only the separate calibration cohort. Validation selects F1 thresholds and the champion by AUPRC. Final test labels are used for reporting. The [complete report](benchmarks/firecastrl-run.json) includes raw/calibrated metrics, thresholds, confusion matrices, reliability bins and PR curves.

## Results and interpretation

- Logistic Regression: test AUROC **0.8410**, AUPRC **0.9725**, recall **0.7986**, F1 **0.8736**, calibrated Brier **0.1509**, ECE **0.2313**.
- Gradient-Boosted Trees: AUROC **0.8627**, AUPRC **0.9743**, recall **0.8162**, F1 **0.8863**, Brier **0.1471**, ECE **0.2358**.
- Two-layer GRU + attention: AUROC **0.8914**, AUPRC **0.9815**, recall **0.8595**, F1 **0.9073**, Brier **0.1524**, ECE **0.2519**.

**Boosted trees are the validation-selected champion**, with validation AUPRC 0.5068 versus logistic 0.4796 and GRU 0.4432. The higher GRU test AUROC does not retroactively change selection.

Test prevalence is **87.99%**, so a no-skill AUPRC is approximately **0.880**. Training prevalence is approximately 19%, calibration approximately 65%. The cohort's prevalence/temporal/geographic shifts strongly affect probability meaning. Platt calibration improves test Brier/ECE over raw scores but leaves substantial error. High AUPRC on this positive-heavy cohort must not be described as operational precision or real population ignition probability. No confidence intervals, external India validation, prospective trial or independent population-prior correction are claimed.

## Serving and routing

The API verifies model-file SHA-256 values before loading trusted local artifacts; joblib is not an untrusted-upload format. GRU loading uses `weights_only=True`. Training and serving share feature/model implementations. Twenty seed-selected test exports preserve input precision; the saved-model integration check verifies fresh predictions against those frozen exports. Seven-day ablation replaces one variable's last week with its earlier-history mean. Resulting score changes are sensitivity, not causal explanations or validated counterfactual forecasts.

A separate unused-cohort case at the fixed California research footprint is selected spatially, without choosing on label or score. It does not enter the reported test metrics. Its historical model score is projected with PostGIS into a declared **3 km experimental support neighbourhood**, not a known GRIDMET cell boundary. Real OSM roads, current demonstration capacity/closure state and hazard-aware A* form an integration replay, not historical incident reconstruction. Exposure cost scales with distance; hard exclusions and capacity take precedence. Unknown roads are explicitly reported as unscored. The replay creates no booking and the India routing API refuses US-score transfer. [Recorded replay](benchmarks/ml-routing-replay.json).

## Before operational approval

Obtain authoritative India predictor histories with verified variable/unit equivalence and incident-family labels; evaluate spatial/temporal generalization, sampling bias and population calibration; validate fire/closure freshness and authoritative shelters; perform prospective/user/security evaluation; and define explicit deployment acceptance gates. The existing `MODEL_MODE=approved` path remains rejected. The delivered research evidence does not establish patent novelty or evacuation safety.

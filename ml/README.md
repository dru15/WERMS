# WERMS ML Plane

This directory is reserved for the offline, reproducible training plane. It does not contain a fake pretrained model.

The first ML milestone will begin only after the FireCastRL dataset is downloaded and its actual schema, license, checksums, grouping keys, and year coverage are recorded. The required experiment order is:

1. Causal 60-day window builder using only `t-60` through `t-1`.
2. Grouped chronological/geographic split manifest.
3. Logistic-regression baseline.
4. Gradient-boosted-tree baseline.
5. Two-layer GRU with attention pooling.
6. Validation-only Platt or isotonic calibration.
7. Untouched test evaluation, model card, and approval record.

Approved artifacts will be written under `artifacts/models/<model-version>/`; that path is intentionally ignored by Git.


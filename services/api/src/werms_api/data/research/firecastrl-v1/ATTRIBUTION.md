# WERMS research artifacts

These models were trained locally by WERMS, not supplied as pretrained models by
FireCastRL's authors. They are research-only and are not approved India forecasts.

Source: https://www.kaggle.com/datasets/firecastrl/us-wildfire-dataset (release v1,
MIT declared by the publisher). Authors: Shaurya Mathur, Shreyas Bellary Manjunath,
Nitin Kulkarni and Alina Vereshchaka. Paper: Spatiotemporal Wildfire Prediction and
Reinforcement Learning for Helitack Suppression, ICMLA 2025,
DOI 10.1109/ICMLA66185.2025.00111. Project: https://sites.google.com/view/firecastrl/

Dataset counts and class counts differ from the release description; use the
measured report/model card. The twenty test cases preserve input precision.
The supplemental routing case is outside the evaluation cohort and never affects
reported accuracy. Raw data and training caches are not included.

Only load trusted local serialized models. File fingerprints support integrity;
they do not establish statistical validity, publisher signatures or safety.

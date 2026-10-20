# FireCastRL source audit and vector-map sources

Research checked on 20 October 2026. The initial source investigation below separates author claims from sampled evidence. Subsequent full-file verification is recorded in the measured-results section.

## Completed local verification

The complete 1,132,250,555-byte public CSV was downloaded and fingerprinted as SHA-256 `0be59f7d6a82865c21a37d26b3a390cb8e657b72bcc55750f16b5a4e8bc512ae`. Its measured counts are **126,799 windows / 9,509,925 rows**, with **33,471 positive / 93,328 negative** reference labels. These differ from the advertised totals and class counts. Preparation accepted 126,442 causal sequences after quarantining 343 invalid-temperature windows and removing 14 duplicates. See [the audit manifest](../benchmarks/firecastrl-data-audit.json), [actual model evaluation](../benchmarks/firecastrl-run.json) and [model card](../model-card.md). Earlier “not yet verified” language in the initial research describes its sampling stage, not the completed pipeline.

## Confirmed public release

The [authors' project site](https://sites.google.com/view/firecastrl) links to [Kaggle: `firecastrl/us-wildfire-dataset`](https://www.kaggle.com/datasets/firecastrl/us-wildfire-dataset). The [paper, arXiv v1](https://arxiv.org/html/2601.14238v1), reports 126,800 event windows: 50,720 positive and 76,080 negative, with 75 daily rows per window and 15 environmental variables. Arithmetic gives 9,510,000 expected rows, explaining the rounded “9.5 million” claim. **This is not 9.5 million independent ignition examples or a measured local file count.**

Actionable endpoints:

- [Official Kaggle metadata API](https://www.kaggle.com/api/v1/datasets/view/firecastrl/us-wildfire-dataset)
- [Direct `Wildfire_Dataset.csv` download](https://www.kaggle.com/api/v1/datasets/download/firecastrl/us-wildfire-dataset/Wildfire_Dataset.csv)
- [Dataset archive endpoint](https://www.kaggle.com/api/v1/datasets/download/firecastrl/us-wildfire-dataset) (not downloaded or inspected by this audit)
- [Author-associated simulation repository](https://github.com/aisystems-lab/wildfire-env); the former `aisystems-lab/firecast-rl` URL redirects here. Its MIT licence concerns that repository, not proof of dataset provenance.

The main implementation agent fetched public metadata into `tmp/firecastrl-metadata.json` and an unauthenticated 8,192-byte CSV range into `tmp/firecastrl-header.bin`; I inspected both local evidence files. Metadata identifies dataset ID 8258645, version 1, last updated 2025-09-12, `licenseName: MIT`, and `totalBytes: 1132250555` (reported size, not a verified downloaded size). The metadata file listing is empty, so the actual CSV endpoint and header—not that listing—establish the filename. Preserve a metadata snapshot, full downloaded file size and SHA-256 in the eventual manifest. [Kaggle release metadata](https://www.kaggle.com/api/v1/datasets/view/firecastrl/us-wildfire-dataset)

## Actual sampled schema and important contradictions

The sampled CSV contains exactly this header:

```text
latitude,longitude,datetime,Wildfire,pr,rmax,rmin,sph,srad,tmmn,tmmx,vs,bi,fm100,fm1000,erc,etr,pet,vpd
```

Its first rows have repeated coordinates `48.1284309990626,-97.276685`, consecutive dates beginning `2018-08-15`, and label `No`. There is **no explicit event ID, window ID, ignition/reference date or source incident ID** in the header. Full-file ordering, 75-row boundaries and uniqueness remain to be checked. [Actual CSV source](https://www.kaggle.com/api/v1/datasets/download/firecastrl/us-wildfire-dataset/Wildfire_Dataset.csv)

Kaggle describes each window precisely as 60 pre-reference rows labelled `No`, one reference row and 14 later rows labelled `Yes` for positive events. Thus the published 75-day input includes future data. A causal 60-day experiment is a new processing choice, not reproduction of the published 75-day classifier. [Kaggle metadata](https://www.kaggle.com/api/v1/datasets/view/firecastrl/us-wildfire-dataset)

**Temperature conflict:** metadata calls `tmmn/tmmx` Celsius, but the observed first row is `282.0,301.6`. Those values agree with GRIDMET's documented Kelvin representation, not plausible ambient Celsius. The [official Earth Engine GRIDMET catalogue](https://developers.google.com/earth-engine/datasets/catalog/IDAHO_EPSCOR_GRIDMET) specifies Kelvin, wind in m/s, humidity in percent, specific humidity as mass fraction, radiation W/m² and VPD kPa. It defines `etr` as **alfalfa reference evapotranspiration**, whereas the paper calls it actual evapotranspiration. The release's `pet` mapping also needs confirmation. Keep raw values; explicitly document any Kelvin-to-Celsius conversion and unresolved semantics.

## Grouping and forecasting recommendations

These are implementation requirements derived from the evidence, not assertions that the downloaded file already satisfies them:

1. Stream the entire file and establish whether each contiguous 75-row block has constant coordinates, unique daily dates, consecutive day increments and a valid label pattern. Fail closed on malformed blocks. Never reconstruct windows using latitude/longitude alone: the release deliberately includes yearly negatives at positive locations.
2. Once validated, derive `reference_date` from block start + 60 days and `target` from the reference row. Save source-block ordinal as a stable local provenance key and fingerprint coordinates/reference date. Do not use the pre-event `No` labels as the event target.
3. Use only rows `t-60` through `t-1` as predictors. Exclude reference/post-event data, label-derived features and future aggregates. Fit imputers, scalers and calibrators on their designated training/validation data only.
4. Split by reference year with a temporal purge sufficient to prevent shared predictor dates across splits; additionally report a geographic holdout. Related positive/yearly-negative locations must remain grouped in spatial experiments. Record how duplicate or overlapping windows are handled.
5. Audit actual row/window/class counts, date limits, coordinates, missing values and duplicates. Compare them against author claims without replacing observed counts with paper numbers. Synthetic negatives mean class frequency is not natural wildfire prevalence.

## India applicability

[GRIDMET's producer](https://www.climatologylab.org/gridmet.html) describes a daily ~4-km product covering the contiguous US, with a real-time extension into southern British Columbia—not India. It warns about sub-grid microclimates, terrain effects on wind and preliminary recent data; its day is midnight-to-midnight Mountain Standard Time. Its copyright waiver is separate from the Kaggle release's MIT declaration.

Consequently, a FireCastRL-trained model is a **US research benchmark**. Moving it onto Uttarakhand and substituting Open-Meteo values would change geography, feature definitions, temporal aggregation, fire-index assumptions and target distribution. That is an unvalidated transfer experiment. India deployment needs compatible historical predictors, Indian event labels, causal alignment, local calibration and an independent Indian test set. Keep such a model separate from route safety decisions and never claim Indian forecast accuracy from a US test score.

## OpenFreeMap and MapLibre for map quality

[OpenFreeMap's official quickstart](https://openfreemap.org/quick_start/) supports MapLibre with style URL `https://tiles.openfreemap.org/styles/liberty` and provides Vite/CSS setup. Use its complete style JSON, rather than inventing a raster URL from a vector endpoint. [MapLibre's official documentation](https://maplibre.org/maplibre-gl-js/docs/) covers map lifecycle, GeoJSON sources/layers, markers, attribution and WebGL support.

[OpenFreeMap's official policy](https://openfreemap.org/) allows commercial usage and its public instance requires no API key or registration, with no stated map-view/request limits and no SLA guarantee. Attribution is required: OpenMapTiles and OpenStreetMap; standard MapLibre handling includes it automatically. Do not hide it. OpenFreeMap infrastructure is MIT-licensed; underlying map data and included projects retain their own licences. Offline downloads have separate limits: at most 3,000 tiles or 50 MB per download, at most four concurrent requests and a unique application User-Agent. This application should perform ordinary interactive viewing, without bulk prefetching.

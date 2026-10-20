"""Package the small, verified research run for a working fresh-clone demo.

This is a research release, not operational model approval. Only an explicit
allowlist is copied; raw data, credentials and general training output stay local.
"""

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/models/firecastrl-v1"
DESTINATION = ROOT / "services/api/src/werms_api/data/research/firecastrl-v1"
NOTICE = """# WERMS research artifacts

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
"""


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    report = json.loads((SOURCE / "report.json").read_text(encoding="utf-8"))
    names = [*report["artifacts"], "report.json", "cases.json", "routing-replay-case.json"]
    if any(Path(name).name != name for name in names):
        raise ValueError("Unsafe artifact name.")
    for name, expected in report["artifacts"].items():
        if digest(SOURCE / name) != expected:
            raise ValueError(f"Model checksum mismatch: {name}")
    if DESTINATION.exists():
        manifest = json.loads((DESTINATION / "bundle.json").read_text(encoding="utf-8"))
        if all(
            digest(DESTINATION / name) == expected for name, expected in manifest["files"].items()
        ) and all(digest(SOURCE / name) == digest(DESTINATION / name) for name in names):
            print("The same verified research bundle is already published.")
            return
        raise ValueError("Published research bundles are immutable; choose a new version.")
    temporary = ROOT / "tmp" / f"research-bundle-{uuid4().hex}"
    temporary.mkdir(parents=True)
    for name in names:
        shutil.copyfile(SOURCE / name, temporary / name)
    (temporary / "ATTRIBUTION.md").write_text(NOTICE, encoding="utf-8")
    manifest = {
        "model_version": report["version"],
        "research_only": True,
        "operational_approval": False,
        "source_csv_sha256": report["dataset"]["sha256"],
        "published_at": datetime.now(UTC).isoformat(),
        "files": {path.name: digest(path) for path in temporary.iterdir()},
    }
    (temporary / "bundle.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if not temporary.resolve().is_relative_to(
        ROOT.resolve()
    ) or not DESTINATION.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError("Bundle publication must stay inside the workspace.")
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    temporary.rename(DESTINATION)
    total_bytes = sum(p.stat().st_size for p in DESTINATION.iterdir())
    print(f"Published verified research bundle: {total_bytes:,} bytes")


if __name__ == "__main__":
    main()

"""Build the English annual hospitalization manuscript package."""
from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.hospitalization_publication import build_publication_package  # noqa: E402


if __name__ == "__main__":
    result = build_publication_package(
        REPO_ROOT,
        baseline_dir=Path(
            "data/processed/cl/santiago/santiago_communes/analysis/hospitalizations/annual_v2"
        ),
        extension_dir=Path(
            "data/processed/cl/santiago/santiago_communes/analysis/hospitalizations/annual_v2_controls_v2_1"
        ),
        output_dir=Path("manuscript/hospitalization_annual_v2"),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

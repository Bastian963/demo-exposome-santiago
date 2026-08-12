from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import pandas as pd

from exposome.hospitalization_publication import (
    BASELINE_FINGERPRINT,
    practical_relevance,
    statistical_evidence,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "manuscript/hospitalization_annual_v2"


class HospitalizationPublicationEvidenceTests(unittest.TestCase):
    def _supported_row(self) -> dict[str, object]:
        return {
            "status": "ok",
            "exposure": "wind",
            "window": "primary",
            "outcome_family": "primary",
            "diagnostics_passed": True,
            "loo_sign_stable": True,
            "loo_pareto_k_high_count": 2,
            "loo_exact_reloo_completed": 2,
            "residual_moran_p": 0.05,
            "negative_control_status": "clear",
            "ppml_q_value": 0.049999,
            "probability_within_direction": 0.975,
            "rr_within_hdi_low": 0.90,
            "rr_within_hdi_high": 0.99,
        }

    def test_supported_boundaries_are_prespecified(self) -> None:
        row = self._supported_row()
        self.assertEqual(statistical_evidence(row), "supported")
        row["ppml_q_value"] = 0.05
        self.assertEqual(statistical_evidence(row), "suggestive")
        row = self._supported_row()
        row["probability_within_direction"] = 0.974999
        self.assertEqual(statistical_evidence(row), "suggestive")

    def test_moran_and_negative_control_failures_are_unstable(self) -> None:
        row = self._supported_row()
        row["residual_moran_p"] = 0.049999
        self.assertEqual(statistical_evidence(row), "unstable")
        row = self._supported_row()
        row["negative_control_status"] = "failed"
        self.assertEqual(statistical_evidence(row), "unstable")

    def test_nonprimary_exposure_cannot_be_supported(self) -> None:
        row = self._supported_row()
        row["exposure"] = "no2"
        self.assertEqual(statistical_evidence(row), "suggestive")

    def test_rope_boundaries_form_a_separate_axis(self) -> None:
        self.assertEqual(practical_relevance(0.05), "practically_relevant")
        self.assertEqual(practical_relevance(0.050001), "magnitude_uncertain")
        self.assertEqual(practical_relevance(0.949999), "magnitude_uncertain")
        self.assertEqual(practical_relevance(0.95), "practically_negligible")
        self.assertEqual(practical_relevance(pd.NA), "not_available")

    def test_materialized_package_manifest_hashes_every_declared_file(self) -> None:
        manifest = json.loads(
            (PACKAGE / "results_manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["baseline_fingerprint"], BASELINE_FINGERPRINT)
        self.assertEqual(manifest["model_inventory"]["combined"], 158)
        self.assertEqual(manifest["negative_control_inventory"]["combined"], 18)
        for asset in manifest["files"]:
            path = PACKAGE / asset["path"]
            self.assertTrue(path.is_file(), path)
            self.assertEqual(path.stat().st_size, asset["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), asset["sha256"])


if __name__ == "__main__":
    unittest.main()

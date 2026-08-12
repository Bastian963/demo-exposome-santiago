"""Tests for the spatial autocorrelation analysis (Moran's I + LISA)."""
from __future__ import annotations

import json
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "processed"
FIG_DIR = REPO_ROOT / "figures"

SA_JSON = DATA_DIR / "spatial_autocorrelation.json"
FIG_LISA = FIG_DIR / "spatial_autocorrelation_lisa.png"
FIG_BAR = FIG_DIR / "spatial_autocorrelation_bar.png"


class SpatialAutocorrelationTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if SA_JSON.exists():
            cls.summary = json.loads(SA_JSON.read_text())
        else:
            cls.summary = None

    def test_json_exists(self) -> None:
        self.assertTrue(SA_JSON.exists(), f"Missing: {SA_JSON}")

    def test_lisa_figure_exists(self) -> None:
        self.assertTrue(FIG_LISA.exists(), f"Missing: {FIG_LISA}")
        self.assertGreater(FIG_LISA.stat().st_size, 30_000)

    def test_bar_figure_exists(self) -> None:
        self.assertTrue(FIG_BAR.exists(), f"Missing: {FIG_BAR}")
        self.assertGreater(FIG_BAR.stat().st_size, 30_000)

    def test_summary_has_at_least_12_layers(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        self.assertGreaterEqual(len(self.summary["layers"]), 12)

    def test_morans_i_in_range(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        for label, layer in self.summary["layers"].items():
            I = layer["I"]
            self.assertGreaterEqual(I, -1.0,
                                    f"{label} Moran's I < -1.0: {I}")
            self.assertLessEqual(I, 1.0,
                                 f"{label} Moran's I > 1.0: {I}")

    def test_p_value_in_range(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        for label, layer in self.summary["layers"].items():
            p = layer["p_value"]
            self.assertGreaterEqual(p, 0.0,
                                    f"{label} p_value < 0: {p}")
            self.assertLessEqual(p, 1.0,
                                 f"{label} p_value > 1: {p}")

    def test_at_least_5_layers_significant_positive(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        n_sig_pos = sum(
            1 for layer in self.summary["layers"].values()
            if layer["p_value"] < 0.05 and layer["I"] > 0
        )
        self.assertGreaterEqual(
            n_sig_pos, 5,
            f"only {n_sig_pos} layers have significant positive I; "
            "expected >= 5 (most exposome indicators cluster spatially)",
        )

    def test_lisa_classifications_sum_to_52(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        for label, layer in self.summary["layers"].items():
            total = (
                layer["n_HH"] + layer["n_LL"]
                + layer["n_HL"] + layer["n_LH"]
                + layer["n_NS"]
            )
            self.assertEqual(
                total, 52,
                f"{label} LISA counts sum to {total}, expected 52",
            )

    def test_ranked_by_I_sorted(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        Is = [r["I"] for r in self.summary["ranked_by_I"]]
        for a, b in zip(Is, Is[1:]):
            self.assertGreaterEqual(
                a, b,
                "ranked_by_I not sorted descending",
            )

    def test_method_documents_weights(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        self.assertIn("Queen", self.summary["method"])
        self.assertIn("permutation", self.summary["method"].lower())


if __name__ == "__main__":
    unittest.main()

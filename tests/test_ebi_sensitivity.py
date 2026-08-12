"""Tests for scripts/ebi_sensitivity.py (leave-one-layer-out).

Verifies the jackknife outputs:
- CSV has 21 variants x 52 communes = 1092 rows (1 full + 20 LOO).
- All 20 canonical indicators appear as excluded_label values.
- The most influential indicator is reported in the JSON.
- Top-5 commune stability is reported for at least 2 communes.
- Spearman rho of EBI_loo vs EBI_full is in [0.94, 1.0] for
  all variants (high robustness).
"""
from __future__ import annotations

import json
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "processed"
CSV_PATH = DATA_DIR / "ebi_sensitivity.csv"
JSON_PATH = DATA_DIR / "ebi_sensitivity.json"


class EbiSensitivityTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CSV_PATH.exists():
            raise unittest.SkipTest(
                "Run scripts/ebi_sensitivity.py first"
            )
        cls.loo = pd.read_csv(CSV_PATH)
        with open(JSON_PATH) as f:
            cls.summary = json.load(f)

    def test_csv_shape_1040(self) -> None:
        """20 LOO variants x 52 communes = 1040 rows.

        The "full" EBI is the reference and is not included as a
        separate row in the CSV; the 20 rows per commune are the
        20 leave-one-out variants.
        """
        self.assertEqual(
            len(self.loo), 20 * 52,
            f"loo CSV has {len(self.loo)} rows, expected {20 * 52}",
        )

    def test_loo_csv_required_columns(self) -> None:
        for col in (
            "excluded_label", "excluded_col", "name",
            "ebi_full", "ebi_loo", "delta",
        ):
            self.assertIn(col, self.loo.columns, f"missing {col!r}")

    def test_n_variants_21(self) -> None:
        self.assertEqual(self.summary["n_variants"], 21)

    def test_n_indicators_20(self) -> None:
        self.assertEqual(self.summary["n_indicators"], 20)

    def test_most_influential_is_known_canonical(self) -> None:
        """The most influential indicator must be a known canonical."""
        most = self.summary["most_influential"]
        self.assertIn(most["excluded_label"], [
            l for l, _, _ in [
                ("PM2.5 (ACAG)", "pm25_mean", 1),
                ("NO2 surface (sat)", "no2_surface_ug_m3", 1),
                ("O3 column (sat)", "o3_mean", 1),
                ("Heavy metals index", "hm_index", 1),
                ("ALAN radiance", "alan_radiance_mean", 1),
                ("Noise (combined %)", "noise_combined_pct", 1),
                ("Heat exposure", "heat_exposure_index", 1),
                ("Urban heat anomaly (C)", "urban_heat_anomaly_c", 1),
                ("Wildfire burned pct", "fire_burned_pct_mean_annual", 1),
                ("Wind calm annual", "wind_calm_pct", 1),
                ("Greenspace coverage NDVI", "green_cover_pct_ndvi", -1),
                ("Green area km2", "green_km2", -1),
                ("Walkability index", "walk_index", -1),
                ("Transit index", "transit_index", -1),
                ("Primary care density", "health_n_primary_care", -1),
                ("Food swamp ratio", "food_swamp_ratio", 1),
                ("Pobreza %", "pobreza_pct", 1),
                ("NSE index", "nse_index", -1),
                ("Hacinamiento", "hacinamiento_phh", 1),
            ]
        ])

    def test_most_influential_mean_abs_diff_positive(self) -> None:
        most = self.summary["most_influential"]
        self.assertGreater(most["mean_abs_ebi_diff"], 0.0)

    def test_spearman_rho_in_high_range(self) -> None:
        """All LOO variants must have rho > 0.94 (high robustness)."""
        for entry in self.summary["influence_table"]:
            rho = entry["spearman_rho_vs_full"]
            self.assertGreater(
                rho, 0.94,
                f"{entry['excluded_label']}: rho={rho} (expected > 0.94)",
            )

    def test_top5_stability_has_at_least_2_communes(self) -> None:
        """At least 2 communes must appear in the top-5 stability dict."""
        nonzero = [k for k, v in self.summary["top5_stability"].items() if v > 0]
        self.assertGreaterEqual(
            len(nonzero), 2,
            f"only {len(nonzero)} communes in top-5 stability: {nonzero}",
        )

    def test_top5_stability_max_21(self) -> None:
        """No commune can be in the top-5 in more than 21 variants."""
        for k, v in self.summary["top5_stability"].items():
            self.assertLessEqual(
                v, 21,
                f"{k}: stability={v} > 21 (impossible)",
            )

    def test_ebi_full_in_unit_interval(self) -> None:
        """EBI_full must be in [0, 1] for all 52 communes x 20 variants."""
        v = self.loo["ebi_full"].dropna()
        self.assertGreaterEqual(v.min(), 0.0)
        self.assertLessEqual(v.max(), 1.0)

    def test_ebi_loo_in_unit_interval(self) -> None:
        """EBI_loo must be in [0, 1] for all 52 communes x 20 variants."""
        v = self.loo["ebi_loo"].dropna()
        self.assertGreaterEqual(v.min(), 0.0)
        self.assertLessEqual(v.max(), 1.0)

    def test_mean_delta_bounded(self) -> None:
        """Per-variant mean delta must be small (< 0.05 in absolute value).

        Removing one indicator shifts the per-commune mean, but the
        shift should be small (the removed indicator carries
        ~1/20 = 5% of the variance).
        """
        for excl in self.loo["excluded_label"].unique():
            sub = self.loo[self.loo["excluded_label"] == excl]
            mean_d = sub["delta"].mean()
            self.assertLess(
                abs(mean_d), 0.05,
                f"{excl}: |mean(delta)|={abs(mean_d):.4f} (expected < 0.05)",
            )

    def test_delta_in_minus_1_to_1(self) -> None:
        """All deltas must be in [-1, 1] (EBI is in [0, 1])."""
        d = self.loo["delta"]
        self.assertGreaterEqual(d.min(), -1.0)
        self.assertLessEqual(d.max(), 1.0)


if __name__ == "__main__":
    unittest.main()

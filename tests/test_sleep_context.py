"""Tests for the sleep-circadian context exposome layer (no network, master-driven)."""
from __future__ import annotations

import json
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "processed"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"
MASTER_GEOJSON = DATA_DIR / "santiago_exposome_master.geojson"

EXPECTED_COLUMNS = [
    "name",
    "area_km2",
    "sleep_alan_log",
    "sleep_tropical_nights_20c",
    "sleep_summer_tmin_c",
    "sleep_exposure_index",
    "sleep_vulnerability_index",
    "sleep_context_index",
]


class SleepContextLayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "santiago_sleep_context.csv"
        cls.geojson_path = DATA_DIR / "santiago_sleep_context.geojson"
        cls.metadata_path = DATA_DIR / "santiago_sleep_context_metadata.json"
        if not cls.csv_path.exists():
            raise unittest.SkipTest(
                f"Missing canonical CSV at {cls.csv_path}; run scripts/run_sleep_context.py first."
            )
        cls.df = pd.read_csv(cls.csv_path)
        if not cls.metadata_path.exists():
            cls.metadata = None
        else:
            cls.metadata = json.loads(cls.metadata_path.read_text(encoding="utf-8"))
        cls.master = pd.read_csv(MASTER_CSV) if MASTER_CSV.exists() else None

    def test_csv_has_52_communes(self) -> None:
        self.assertEqual(len(self.df), 52)
        self.assertEqual(self.df["name"].nunique(), 52)
        self.assertEqual(self.df["name"].isna().sum(), 0)
        self.assertEqual(self.df["name"].duplicated().sum(), 0)

    def test_csv_columns_complete(self) -> None:
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, self.df.columns, f"missing column: {col}")
        numeric = [c for c in EXPECTED_COLUMNS if c != "name"]
        self.assertEqual(self.df[numeric].isna().sum().sum(), 0)

    def test_metadata_coherence(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata file not yet visible")
        self.assertEqual(self.metadata["n_rows"], 52)
        self.assertIn("warning", self.metadata)
        self.assertIn("environmental sleep-circadian context", self.metadata["warning"])
        # Method block must document the 0.70/0.30 weighting and the
        # 1/3 split for each of the 3 components.
        method = self.metadata["method"]
        self.assertIn("0.70", method["sleep_context_index"])
        self.assertIn("0.30", method["sleep_context_index"])
        weights = self.metadata["weights"]
        self.assertAlmostEqual(
            weights["sleep_context_index"]["sleep_exposure_index"], 0.70, places=6
        )
        self.assertAlmostEqual(
            weights["sleep_context_index"]["sleep_vulnerability_index"], 0.30, places=6
        )
        for grp in ("exposure_index", "vulnerability_index"):
            for v in weights[grp].values():
                self.assertAlmostEqual(v, 1.0 / 3.0, places=6)

    def test_indices_bounded_zero_one_hundred(self) -> None:
        """All 0-100 percentile-rank indices must lie within [0, 100]."""
        for col in (
            "sleep_exposure_index",
            "sleep_vulnerability_index",
            "sleep_context_index",
        ):
            v = self.df[col]
            self.assertGreaterEqual(float(v.min()), 0.0)
            self.assertLessEqual(float(v.max()), 100.0)
            self.assertEqual(v.isna().sum(), 0)

    def test_percentile_rank_invariants(self) -> None:
        """Each 0-100 index is a mean of 3 percentile ranks → mean ≈ 50.

        Individual percentile ranks of 52 distinct values span the full
        [0, 100] interval with mean exactly 50. The *index* is the mean of
        three such ranks, so its mean is also ~50, but its min and max are
        not guaranteed to be exactly 0 / 100 (depends on whether one
        commune is worst in all three components).
        """
        for col in (
            "sleep_exposure_index",
            "sleep_vulnerability_index",
            "sleep_context_index",
        ):
            mean = float(self.df[col].mean())
            self.assertAlmostEqual(mean, 50.0, delta=2.0)
            # The mean over 52 communes of 3 percentile ranks concentrates
            # in the central band; the index should not collapse to a
            # single value or saturate.
            self.assertGreater(float(self.df[col].max() - self.df[col].min()), 50.0)

    def test_context_index_weighted_composition(self) -> None:
        """sleep_context_index == 0.70 * exposure + 0.30 * vulnerability.

        The CSV is rounded to 4 decimal places, so allow a tolerance of
        1e-3 (well below the precision at which 70/30 weighting matters).
        """
        expected = (
            0.70 * self.df["sleep_exposure_index"]
            + 0.30 * self.df["sleep_vulnerability_index"]
        )
        diff = (self.df["sleep_context_index"] - expected).abs().max()
        self.assertLessEqual(
            float(diff), 1e-3, f"weighted composition off by {diff}"
        )

    def test_alan_log_transform(self) -> None:
        """sleep_alan_log == log1p(master.alan_radiance_pop_weighted)."""
        if self.master is None:
            self.skipTest("Master CSV missing")
        m = self.df.merge(
            self.master[["name", "alan_radiance_pop_weighted"]], on="name"
        )
        expected = np.log1p(m["alan_radiance_pop_weighted"]).round(4)
        actual = m["sleep_alan_log"]
        diff = (actual - expected).abs().max()
        self.assertLessEqual(float(diff), 1e-3)

    def test_urban_rural_contrast(self) -> None:
        """Lower-SES urban communes dominate the high-risk end; rural cold
        communes dominate the low-risk end.

        The index is the mean of three environmental risk components
        (ALAN, tropical nights, summer Tmin) and three vulnerability
        components (overcrowding, older population, lower SES). The
        highest-risk communes are dense, lower-SES urban areas (San
        Joaquín, La Granja, San Ramón) where ALAN, nights and Tmin all
        co-occur with vulnerability. The lowest-risk communes are the
        cold, rural south (Buin, María Pinto, San José de Maipo) where
        Tmin is low and tropical nights are 0.

        Note: dense central communes like Santiago and Providencia do NOT
        top the index because their NSE is high (low -NSE rank pulls the
        vulnerability down). This is a feature, not a bug — the layer
        captures co-exposure, not ALAN alone.
        """
        high = self.df.loc[
            self.df["name"].isin(
                ["San Joaquín", "La Granja", "San Ramón", "San Miguel"]
            ),
            "sleep_context_index",
        ]
        low = self.df.loc[
            self.df["name"].isin(
                ["Buin", "María Pinto", "San José de Maipo", "Peñaflor"]
            ),
            "sleep_context_index",
        ]
        self.assertEqual(len(high), 4)
        self.assertEqual(len(low), 4)
        # The mean of the high-risk group must be substantially above the
        # mean of the low-risk group (separation > 30 percentile points).
        self.assertGreater(
            float(high.mean()) - float(low.mean()),
            30.0,
            f"urban vs rural contrast too small: high={high.mean():.1f}, low={low.mean():.1f}",
        )
        # San José de Maipo is the coldest commune (lowest Tmin = 6.46 C)
        # and has 0 tropical nights, so its sleep_exposure_index must be
        # the floor of the 52 communes.
        sjm = self.df.loc[self.df["name"] == "San José de Maipo"]
        self.assertEqual(len(sjm), 1)
        self.assertEqual(
            float(sjm["sleep_exposure_index"].iloc[0]),
            float(self.df["sleep_exposure_index"].min()),
        )
        # San Joaquín is in the top 5 of sleep_context_index (densely
        # populated, lower-SES, warm, light-polluted).
        sj = self.df.loc[self.df["name"] == "San Joaquín", "sleep_context_index"]
        self.assertEqual(len(sj), 1)
        rank = (self.df["sleep_context_index"] > float(sj.iloc[0])).sum() + 1
        self.assertLessEqual(rank, 5)

    def test_tropical_nights_consistency(self) -> None:
        """sleep_tropical_nights_20c must match the Open-Meteo climate input."""
        if self.master is None:
            self.skipTest("Master CSV missing")
        m = self.df.merge(
            self.master[["name", "om_tropical_nights_20c"]], on="name"
        )
        diff = (m["sleep_tropical_nights_20c"] - m["om_tropical_nights_20c"]).abs().max()
        self.assertLessEqual(float(diff), 1e-6)

    def test_master_integration(self) -> None:
        if not MASTER_CSV.exists():
            self.skipTest("Master CSV missing; run scripts/build_master_exposome.py first.")
        master_cols = pd.read_csv(MASTER_CSV, nrows=0).columns
        core = [
            "sleep_alan_log",
            "sleep_tropical_nights_20c",
            "sleep_summer_tmin_c",
            "sleep_exposure_index",
            "sleep_vulnerability_index",
            "sleep_context_index",
        ]
        for col in core:
            self.assertIn(col, master_cols, f"master missing core col: {col}")
        # The 3 percentiles must propagate as finite numbers in the master.
        master_df = pd.read_csv(MASTER_CSV)
        for col in core:
            self.assertEqual(master_df[col].isna().sum(), 0)


class SleepContextHelpersTest(unittest.TestCase):
    """Unit tests for the sleep_context module helpers (no I/O)."""

    def test_rank_percentile_uniform(self) -> None:
        """For N > 1 distinct values, percentile ranks span [0, 100] with mean 50."""
        from exposome.sleep_context import _rank_percentile

        s = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])
        r = _rank_percentile(s)
        self.assertAlmostEqual(float(r.min()), 0.0, places=6)
        self.assertAlmostEqual(float(r.max()), 100.0, places=6)
        self.assertAlmostEqual(float(r.mean()), 50.0, places=6)

    def test_rank_percentile_single_value(self) -> None:
        """N == 1: there is no contrast; the lone value is set to 100.0."""
        from exposome.sleep_context import _rank_percentile

        s = pd.Series([42.0])
        r = _rank_percentile(s)
        self.assertEqual(len(r), 1)
        self.assertEqual(float(r.iloc[0]), 100.0)

    def test_compute_sleep_context_synthetic(self) -> None:
        """Hand-built master: known ALAN/NSE → known percentile ranks → known index."""
        from exposome.sleep_context import compute_sleep_context

        master = pd.DataFrame(
            {
                "name": ["A", "B", "C", "D"],
                "area_km2": [1.0, 2.0, 3.0, 4.0],
                "alan_radiance_pop_weighted": [0.0, 10.0, 100.0, 1000.0],
                "om_tropical_nights_20c": [0, 5, 10, 20],
                "om_tmin_mean_summer_c": [10.0, 12.0, 14.0, 16.0],
                "hacinamiento_phh": [0.05, 0.10, 0.20, 0.40],
                "demo_pct_pop_65_plus": [10.0, 20.0, 30.0, 40.0],
                "nse_index": [-1.0, 0.0, 1.0, 2.0],  # higher = better SES
            }
        )
        out = compute_sleep_context(master)

        # 4 communes → percentile ranks 0, 33.33, 66.67, 100.
        # Exposure: mean(percentile(ALAN), percentile(nights), percentile(Tmin))
        # For commune A (lowest everywhere): exposure = mean(0, 0, 0) = 0.
        self.assertAlmostEqual(float(out.loc[out["name"] == "A", "sleep_exposure_index"].iloc[0]), 0.0, places=2)
        # For commune D (highest everywhere): exposure = 100.
        self.assertAlmostEqual(float(out.loc[out["name"] == "D", "sleep_exposure_index"].iloc[0]), 100.0, places=2)
        # Vulnerability: mean(pct(overcrowding), pct(pop_65+), pct(-NSE)).
        # -NSE for A,B,C,D is 2,1,0,-2 → pct(-NSE) is 100,66.67,33.33,0
        # (inverse direction: lower SES = higher risk).
        # For commune A: pct(hacinamiento)=0, pct(pop_65+)=0, pct(-NSE)=100
        # → vulnerability = 33.33
        v_a = float(out.loc[out["name"] == "A", "sleep_vulnerability_index"].iloc[0])
        self.assertAlmostEqual(v_a, 100.0 / 3.0, places=2)
        # For commune D: pct(hacinamiento)=100, pct(pop_65+)=100, pct(-NSE)=0
        # → vulnerability = 200/3 = 66.67
        v_d = float(out.loc[out["name"] == "D", "sleep_vulnerability_index"].iloc[0])
        self.assertAlmostEqual(v_d, 200.0 / 3.0, places=2)
        # sleep_context_index = 0.7 * exposure + 0.3 * vulnerability
        ctx_a = float(out.loc[out["name"] == "A", "sleep_context_index"].iloc[0])
        self.assertAlmostEqual(ctx_a, 0.7 * 0.0 + 0.3 * (100.0 / 3.0), places=2)

    def test_compute_sleep_context_higher_means_higher_risk(self) -> None:
        """Higher inputs (ALAN, nights, Tmin, hacinamiento, pop_65+, low NSE)
        must always yield a higher sleep_context_index, by construction."""
        from exposome.sleep_context import compute_sleep_context

        master = pd.DataFrame(
            {
                "name": ["low", "high"],
                "area_km2": [1.0, 1.0],
                "alan_radiance_pop_weighted": [1.0, 1000.0],
                "om_tropical_nights_20c": [0, 20],
                "om_tmin_mean_summer_c": [10.0, 18.0],
                "hacinamiento_phh": [0.05, 0.40],
                "demo_pct_pop_65_plus": [5.0, 40.0],
                "nse_index": [2.0, -2.0],  # high = low risk → -NSE = -2 (rank 0)
            }
        )
        out = compute_sleep_context(master)
        low = float(out.loc[out["name"] == "low", "sleep_context_index"].iloc[0])
        high = float(out.loc[out["name"] == "high", "sleep_context_index"].iloc[0])
        self.assertLess(low, high)
        # Both exposure and vulnerability reach 0 (low) and 100 (high)
        # because the two communes saturate every component on opposite
        # ends. So context must be 0 and 100 exactly.
        self.assertAlmostEqual(low, 0.0, places=2)
        self.assertAlmostEqual(high, 100.0, places=2)


if __name__ == "__main__":
    unittest.main()

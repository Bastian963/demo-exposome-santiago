"""Tests for the social_infrastructure exposome layer (OSM, no network, cache-first)."""
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
CACHE_DIR = REPO_ROOT / "cache"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"
DEMO_CSV = DATA_DIR / "santiago_demography.csv"

EXPECTED_COLUMNS = [
    "name",
    "social_n_total",
    "social_n_total_raw",
    "social_n_library",
    "social_n_cultural",
    "social_n_community",
    "social_n_senior",
    "social_n_sports",
    "social_n_public_space",
    "social_n_sports_raw",
    "social_n_public_space_raw",
    "social_private_or_customer_excluded_n",
    "social_category_diversity",
    "social_civic_diversity",
    "social_density_per_km2",
    "social_points_per_10k",
    "social_points_per_10k_raw",
    "social_civic_points_per_10k",
    "social_recreation_points_per_10k",
    "social_mean_nearest_m",
    "social_median_nearest_m",
    "social_p90_nearest_m",
    "social_coverage_500m",
    "social_coverage_1000m",
    "social_n_access_grid",
    "social_civic_index",
    "social_access_index",
    "social_recreation_index",
    "social_index",
]

SOCIAL_INDEX_WEIGHTS = {"civic": 0.45, "access": 0.35, "recreation": 0.20}


class SocialInfrastructureLayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "santiago_social_infrastructure.csv"
        cls.geojson_path = DATA_DIR / "santiago_social_infrastructure.geojson"
        cls.metadata_path = DATA_DIR / "santiago_social_infrastructure_metadata.json"
        if not cls.csv_path.exists():
            raise unittest.SkipTest(
                f"Missing canonical CSV at {cls.csv_path}; run scripts/run_social_infrastructure.py first."
            )
        cls.df = pd.read_csv(cls.csv_path)
        if not cls.metadata_path.exists():
            cls.metadata = None
        else:
            cls.metadata = json.loads(cls.metadata_path.read_text(encoding="utf-8"))

    def test_csv_has_52_communes(self) -> None:
        self.assertEqual(len(self.df), 52)
        self.assertEqual(self.df["name"].nunique(), 52)
        self.assertEqual(self.df["name"].isna().sum(), 0)
        self.assertEqual(self.df["name"].duplicated().sum(), 0)

    def test_csv_columns_complete(self) -> None:
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, self.df.columns, f"missing column: {col}")
        # The 29 columns must be fully populated; 0 is a valid count
        # (communes with no OSM-tagged social infrastructure).
        numeric = [c for c in EXPECTED_COLUMNS if c != "name"]
        self.assertEqual(self.df[numeric].isna().sum().sum(), 0)

    def test_metadata_coherence(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata file not yet visible")
        self.assertEqual(self.metadata["n_communes"], 52)
        self.assertEqual(
            self.metadata["source"],
            "OpenStreetMap via direct Overpass queries plus existing greenspace OSM cache",
        )
        # All 29 columns are listed.
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, self.metadata["columns"])
        # The "warning" field must declare that this is an ecological
        # proxy, not a direct measure of loneliness or cognition.
        self.assertIn("Ecological proxy", self.metadata["warning"])
        # brain_health_relevance covers the three pathways.
        for key in ("social_isolation", "cognitive_stimulation", "physical_activity"):
            self.assertIn(key, self.metadata["brain_health_relevance"])

    def test_social_index_bounded(self) -> None:
        idx = self.df["social_index"]
        self.assertEqual(idx.isna().sum(), 0)
        self.assertGreaterEqual(float(idx.min()), 0.0)
        self.assertLessEqual(float(idx.max()), 100.0)
        # Sub-indices also bounded 0-100.
        for col in ("social_civic_index", "social_access_index", "social_recreation_index"):
            v = self.df[col]
            self.assertGreaterEqual(float(v.min()), 0.0)
            self.assertLessEqual(float(v.max()), 100.0)

    def test_social_index_weighted_composition(self) -> None:
        """social_index = 0.45*civic + 0.35*access + 0.20*recreation."""
        w = SOCIAL_INDEX_WEIGHTS
        expected = (
            w["civic"] * self.df["social_civic_index"]
            + w["access"] * self.df["social_access_index"]
            + w["recreation"] * self.df["social_recreation_index"]
        )
        # CSV is rounded to 1 decimal; allow 1e-1 tolerance.
        diff = (self.df["social_index"] - expected).abs().max()
        self.assertLessEqual(
            float(diff), 0.1, f"weighted composition off by {diff}"
        )

    def test_top5_bot5_match_metadata(self) -> None:
        """The top5 / bot5 embedded in metadata must match the CSV."""
        if self.metadata is None:
            self.skipTest("metadata not visible")
        top_meta = {name for name, _ in self.metadata["top5_most_accessible"]}
        bot_meta = {name for name, _ in self.metadata["bot5_least_accessible"]}
        # Top 5 from the actual data
        top_data = set(self.df.nlargest(5, "social_index")["name"])
        bot_data = set(self.df.nsmallest(5, "social_index")["name"])
        self.assertEqual(top_meta, top_data)
        self.assertEqual(bot_meta, bot_data)

    def test_providencia_santiago_top(self) -> None:
        """Dense central communes (Santiago, Providencia) should rank
        near the top of social infrastructure, given the heavy OSM
        mapping in central Santiago."""
        top10 = set(self.df.nlargest(10, "social_index")["name"])
        self.assertIn("Providencia", top10)
        self.assertIn("Santiago", top10)

    def test_rural_low_access(self) -> None:
        """Rural Andean / south communes (San Pedro, Alhué, María Pinto)
        should rank near the bottom of social infrastructure."""
        bot10 = set(self.df.nsmallest(10, "social_index")["name"])
        for rural in ("San Pedro", "Alhué", "María Pinto"):
            self.assertIn(rural, bot10)

    def test_category_diversity_semantics(self) -> None:
        """social_category_diversity counts the number of non-zero
        categories (library, cultural, community, senior, sports,
        public_space) per commune."""
        cat_cols = [
            "social_n_library",
            "social_n_cultural",
            "social_n_community",
            "social_n_senior",
            "social_n_sports",
            "social_n_public_space",
        ]
        expected = (self.df[cat_cols] > 0).sum(axis=1).astype(int)
        diff = (self.df["social_category_diversity"] - expected).abs().max()
        self.assertLessEqual(int(diff), 0)
        # Bounded 0..6 (6 categories).
        self.assertEqual(int(self.df["social_category_diversity"].max()), 6)
        self.assertGreaterEqual(int(self.df["social_category_diversity"].min()), 0)

    def test_curated_le_raw(self) -> None:
        """Curated totals (excludes access-restricted) <= raw totals."""
        self.assertTrue(
            (self.df["social_n_total"] <= self.df["social_n_total_raw"]).all(),
            "curated social_n_total > raw in some communes",
        )
        # The number of excluded features per commune is non-negative.
        self.assertTrue(
            (self.df["social_private_or_customer_excluded_n"] >= 0).all()
        )

    def test_points_per_10k_denominator(self) -> None:
        """social_points_per_10k = social_n_total / population * 10000.

        Cross-checks against the population source (demography layer).
        """
        demo = pd.read_csv(DEMO_CSV) if DEMO_CSV.exists() else None
        if demo is None:
            self.skipTest("Demography CSV missing")
        merged = self.df[["name", "social_n_total", "social_points_per_10k"]].merge(
            demo[["name", "pop_total"]], on="name"
        )
        expected = merged["social_n_total"] / merged["pop_total"] * 10_000
        # CSV is rounded to 3 decimals.
        diff = (merged["social_points_per_10k"] - expected).abs().max()
        self.assertLessEqual(
            float(diff), 1e-2, f"points_per_10k off by {diff}"
        )

    def test_coverage_thresholds_bounded(self) -> None:
        """Coverage fractions are in [0, 1]."""
        for col in ("social_coverage_500m", "social_coverage_1000m"):
            v = self.df[col]
            self.assertGreaterEqual(float(v.min()), 0.0)
            self.assertLessEqual(float(v.max()), 1.0)
            self.assertEqual(v.isna().sum(), 0)

    def test_distance_cap_enforced(self) -> None:
        """All distances <= no_data_dist_m (99999 m). The cap is the
        upper bound; communes with no nearby infrastructure are set
        to the cap value (or near it)."""
        cap = 99999.0
        for col in ("social_mean_nearest_m", "social_median_nearest_m", "social_p90_nearest_m"):
            v = self.df[col]
            self.assertTrue((v <= cap).all(), f"{col} exceeds distance cap")
            # Mean distance must be at least 0.
            self.assertGreaterEqual(float(v.min()), 0.0)

    def test_master_integration(self) -> None:
        if not MASTER_CSV.exists():
            self.skipTest("Master CSV missing")
        master_cols = pd.read_csv(MASTER_CSV, nrows=0).columns
        # The master builder picks a subset of 17 social_* columns (see
        # LAYER_SPECS). The 12 that flow into the master are:
        core = [
            "social_n_total",
            "social_n_library",
            "social_n_cultural",
            "social_n_community",
            "social_n_senior",
            "social_n_sports",
            "social_n_public_space",
            "social_category_diversity",
            "social_density_per_km2",
            "social_points_per_10k",
            "social_mean_nearest_m",
            "social_median_nearest_m",
            "social_p90_nearest_m",
            "social_coverage_500m",
            "social_coverage_1000m",
            "social_n_access_grid",
            "social_index",
        ]
        for col in core:
            self.assertIn(col, master_cols, f"master missing col: {col}")
        # The master values must equal the CSV values.
        master_df = pd.read_csv(MASTER_CSV)
        for col in core:
            merged = self.df[["name", col]].merge(
                master_df[["name", col]], on="name", suffixes=("_src", "_master")
            )
            diff = (merged[f"{col}_src"] - merged[f"{col}_master"]).abs().max()
            self.assertLessEqual(
                float(diff), 1e-6, f"master vs src for {col} diverges by {diff}"
            )


class SocialInfrastructureHelpersTest(unittest.TestCase):
    """Unit tests for the social_infrastructure module helpers (no I/O)."""

    def test_zscore_meaning(self) -> None:
        """z-score: mean 0, std 1; positive=True preserves sign."""
        from exposome.social_infrastructure import _zscore

        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        z = _zscore(s, positive=True)
        self.assertAlmostEqual(float(z.mean()), 0.0, places=6)
        self.assertAlmostEqual(float(z.std(ddof=0)), 1.0, places=6)

    def test_zscore_flip(self) -> None:
        """positive=False flips sign (used for distance so closer = higher)."""
        from exposome.social_infrastructure import _zscore

        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        z_pos = _zscore(s, positive=True)
        z_neg = _zscore(s, positive=False)
        # Negative is the mirror of positive.
        self.assertAlmostEqual(float((z_pos + z_neg).abs().max()), 0.0, places=6)

    def test_zscore_zero_std(self) -> None:
        """Constant series → z = 0 for every entry (no contrast)."""
        from exposome.social_infrastructure import _zscore

        s = pd.Series([5.0, 5.0, 5.0, 5.0])
        z = _zscore(s)
        self.assertTrue((z == 0.0).all())

    def test_rescale_0_100(self) -> None:
        """Min → 0, Max → 100, linear in between."""
        from exposome.social_infrastructure import _rescale_0_100

        s = pd.Series([10.0, 20.0, 30.0, 40.0])
        r = _rescale_0_100(s)
        self.assertAlmostEqual(float(r.min()), 0.0, places=6)
        self.assertAlmostEqual(float(r.max()), 100.0, places=6)
        self.assertAlmostEqual(float(r.iloc[1]), 100.0 / 3.0, places=6)

    def test_rescale_constant(self) -> None:
        """Constant series → all values 50 (mid-point)."""
        from exposome.social_infrastructure import _rescale_0_100

        s = pd.Series([7.0, 7.0, 7.0])
        r = _rescale_0_100(s)
        self.assertTrue((r == 50.0).all())

    def test_winsorize_upper(self) -> None:
        """_winsorize_upper clips values above the quantile threshold."""
        from exposome.social_infrastructure import _winsorize_upper

        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 100.0])  # 100 is a clear outlier
        w = _winsorize_upper(s, quantile=0.90)
        # P90 of [1,2,3,4,5,100] is ≈ 60.5. 100 is clipped to that.
        self.assertEqual(float(w.max()), float(s.quantile(0.90)))
        # Lower values are unchanged.
        self.assertEqual(float(w.iloc[0]), 1.0)


if __name__ == "__main__":
    unittest.main()

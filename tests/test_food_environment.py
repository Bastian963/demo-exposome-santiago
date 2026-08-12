"""Tests for the food environment exposome layer (OSM retail outlets).

All tests are offline; they validate the on-disk CSVs, the master
integration, and the documented metadata. The coverage gap documented
in `data/processed/santiago_food_environment_metadata.json` is asserted
explicitly to lock in the current state and prevent silent regressions
if the data is regenerated with different OSM coverage.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.food_environment import (  # noqa: E402
    _fetch_region_features,
    _geometry_only_cache_frame,
)

DATA_DIR = REPO_ROOT / "data" / "processed"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"
MASTER_GEOJSON = DATA_DIR / "santiago_exposome_master.geojson"
FIG_DIR = REPO_ROOT / "figures"
DOC_DIR = REPO_ROOT / "docs"

EXPECTED_COLUMNS = [
    "name",
    "food_n_supermarket",
    "food_n_greengrocer",
    "food_n_marketplace",
    "food_n_fastfood",
    "food_n_convenience",
    "food_n_healthy",
    "food_n_unhealthy",
    "food_healthy_density",
    "food_unhealthy_density",
    "food_mrfei",
    "food_swamp_ratio",
    "food_mean_dist_supermarket_m",
    "food_index",
]

KNOWN_COMMUNES = {
    "Santiago", "Providencia", "Las Condes", "Vitacura",
    "Ñuñoa", "Maipú", "Puente Alto", "La Florida",
    "Alhué", "San José de Maipo", "Lo Barnechea", "Pirque",
}

RUN_ARTIFACT_TESTS = os.environ.get("EXPOSOME_RUN_ARTIFACT_TESTS") == "1"

_BBOX = (-58.6, -34.8, -58.3, -34.5)


class FetchRegionFeaturesFailModeTests(unittest.TestCase):
    """Offline coverage for the fail-explicit vs genuinely-empty distinction.

    A tag that OSM genuinely does not map in a region (see the module
    docstring, e.g. fast_food/convenience in Santiago) must return an empty
    frame without retrying. A tag whose *query itself* fails after every
    Overpass mirror/attempt is exhausted must raise instead of silently
    returning that same empty frame -- otherwise a transient outage is
    indistinguishable from a real zero and corrupts mRFEI with fabricated
    zero-counts (this previously happened after cdmx_native's Overpass
    outage on 2026-07-17).
    """

    def setUp(self) -> None:
        sleep_patch = patch("exposome.osm_fetch.time.sleep")
        sleep_patch.start()
        self.addCleanup(sleep_patch.stop)

    def test_genuinely_empty_result_returns_immediately_without_retry(self) -> None:
        calls = {"n": 0}

        def fake_features_from_bbox(bbox, tags):
            calls["n"] += 1
            import geopandas as gpd

            return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")

        with patch("exposome.food_environment.ox.features_from_bbox", side_effect=fake_features_from_bbox):
            result = _fetch_region_features(_BBOX, {"amenity": "fast_food"}, "fast_food")

        self.assertEqual(len(result), 0)
        self.assertEqual(calls["n"], 1)

    def test_exhausted_overpass_retries_raise_instead_of_returning_empty(self) -> None:
        def always_fails(bbox, tags):
            raise ConnectionError("Max retries exceeded")

        with patch("exposome.food_environment.ox.features_from_bbox", side_effect=always_fails):
            with self.assertRaises(ConnectionError):
                _fetch_region_features(_BBOX, {"shop": "supermarket"}, "supermarket")


class FoodEnvironmentCacheTests(unittest.TestCase):
    def test_raw_osm_columns_that_fiona_rejects_are_not_cached(self) -> None:
        raw = gpd.GeoDataFrame(
            {
                "currency:MXN": ["yes"],
                "shop": ["convenience"],
                "geometry": [Point(-99.13, 19.43)],
            },
            crs="EPSG:4326",
        )

        cached = _geometry_only_cache_frame(raw)

        self.assertEqual(list(cached.columns), ["geometry"])
        self.assertEqual(len(cached), 1)
        self.assertEqual(cached.crs.to_string(), "EPSG:4326")

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_path = Path(tmp_dir) / "cdmx_food_convenience.geojson"
            cached.to_file(cache_path, driver="GeoJSON")
            reloaded = gpd.read_file(cache_path)

        self.assertEqual(len(reloaded), 1)
        self.assertNotIn("currency:MXN", reloaded.columns)


@unittest.skipUnless(RUN_ARTIFACT_TESTS, "requires materialized Santiago output artifacts")
class FoodEnvironmentLayerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "santiago_food_environment.csv"
        cls.geojson_path = DATA_DIR / "santiago_food_environment.geojson"
        cls.metadata_path = DATA_DIR / "santiago_food_environment_metadata.json"
        cls.doc_path = DOC_DIR / "food_environment_methodology.md"
        cls.fig_path = FIG_DIR / "food_environment_santiago_4panel.png"

        if cls.csv_path.exists():
            cls.df = pd.read_csv(cls.csv_path)
        else:
            cls.df = None
        if cls.metadata_path.exists():
            cls.metadata = json.loads(cls.metadata_path.read_text())
        else:
            cls.metadata = None

    def test_csv_exists(self) -> None:
        self.assertTrue(self.csv_path.exists(), f"Missing: {self.csv_path}")

    def test_geojson_exists(self) -> None:
        self.assertTrue(self.geojson_path.exists(), f"Missing: {self.geojson_path}")

    def test_metadata_exists(self) -> None:
        self.assertTrue(self.metadata_path.exists(), f"Missing: {self.metadata_path}")

    def test_documentation_exists(self) -> None:
        self.assertTrue(self.doc_path.exists(), f"Missing: {self.doc_path}")
        text = self.doc_path.read_text()
        self.assertGreater(len(text), 1500, "Methodology doc is too short.")

    def test_figure_exists(self) -> None:
        self.assertTrue(self.fig_path.exists(), f"Missing: {self.fig_path}")
        self.assertGreater(self.fig_path.stat().st_size, 50_000)

    def test_csv_shape(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(self.df.shape[0], 52, f"Expected 52 communes, got {self.df.shape[0]}")
        self.assertEqual(self.df.shape[1], len(EXPECTED_COLUMNS))

    def test_required_columns(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, self.df.columns, f"Missing column: {col}")

    def test_unique_names(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(self.df["name"].nunique(), 52)
        self.assertEqual(self.df["name"].isna().sum(), 0)

    def test_known_communes_present(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        names = set(self.df["name"].astype(str))
        for k in KNOWN_COMMUNES:
            self.assertIn(k, names, f"Known commune missing: {k}")

    def test_supermarket_count_positive(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        total = int(self.df["food_n_supermarket"].sum())
        self.assertGreater(total, 500, f"Only {total} supermarkets; expected > 500")
        self.assertLess(total, 1500, f"{total} supermarkets is implausibly high")

    def test_food_n_greengrocer_all_zero(self) -> None:
        """Document the OSM coverage gap: greengrocer is empty in OSM Chile."""
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(int(self.df["food_n_greengrocer"].sum()), 0,
                         "greengrocer coverage changed; update coverage_gap documentation.")

    def test_food_n_marketplace_all_zero(self) -> None:
        """Document the OSM coverage gap: marketplace is empty in OSM Chile."""
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(int(self.df["food_n_marketplace"].sum()), 0,
                         "marketplace coverage changed; update coverage_gap documentation.")

    def test_food_n_fastfood_all_zero(self) -> None:
        """Document the OSM coverage gap: fast_food is empty in OSM Chile."""
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(int(self.df["food_n_fastfood"].sum()), 0,
                         "fast_food coverage changed; update coverage_gap documentation.")

    def test_food_n_convenience_all_zero(self) -> None:
        """Document the OSM coverage gap: convenience is empty in OSM Chile."""
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(int(self.df["food_n_convenience"].sum()), 0,
                         "convenience coverage changed; update coverage_gap documentation.")

    def test_food_n_unhealthy_all_zero(self) -> None:
        """Derived from the gap: unhealthy = fastfood + convenience = 0 everywhere."""
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(int(self.df["food_n_unhealthy"].sum()), 0)

    def test_food_swamp_ratio_all_zero(self) -> None:
        """Derived from the gap: swamp ratio is degenerate (0 everywhere)."""
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertTrue((self.df["food_swamp_ratio"] == 0).all())

    def test_food_mrfei_near_degenerate(self) -> None:
        """At least 50/52 communes have mrfei=100 (only Alhué has mrfei=0)."""
        if self.df is None:
            self.skipTest("CSV not visible")
        n_full = int((self.df["food_mrfei"] == 100).sum())
        self.assertGreaterEqual(n_full, 50,
                                f"Only {n_full}/52 communes have mrfei=100; coverage may have changed.")

    def test_food_index_range(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertGreaterEqual(self.df["food_index"].min(), 0.0)
        self.assertLessEqual(self.df["food_index"].max(), 100.0)
        self.assertGreater(self.df["food_index"].max(), 0.0)

    def test_food_index_extremes(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        top = self.df.nlargest(1, "food_index").iloc[0]
        bot = self.df.nsmallest(1, "food_index").iloc[0]
        self.assertEqual(top["name"], "Santiago", f"Top must be Santiago, got {top['name']}")
        self.assertEqual(bot["name"], "Alhué", f"Bottom must be Alhué, got {bot['name']}")

    def test_food_index_dominance_by_distance(self) -> None:
        """Spearman correlation between food_index and mean_dist_supermarket
        must be strongly negative (documented in metadata: ρ = -0.85).
        A weaker correlation would indicate the index structure has changed."""
        if self.df is None:
            self.skipTest("CSV not visible")
        corr = self.df["food_index"].corr(self.df["food_mean_dist_supermarket_m"],
                                          method="spearman")
        self.assertLess(corr, -0.6,
                        f"Spearman r = {corr:.2f} is weaker than expected; index structure may have changed.")

    def test_no_nans_in_key_columns(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in EXPECTED_COLUMNS:
            self.assertEqual(self.df[col].isna().sum(), 0, f"NaN found in {col}")

    def test_metadata_documents_coverage_gap(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata file not yet visible")
        self.assertIn("coverage_gap", self.metadata)
        gap = self.metadata["coverage_gap"]
        self.assertEqual(gap["status"], "documented_known_gap")
        self.assertIn("greengrocer", gap["categories_with_zero"])
        self.assertIn("marketplace", gap["categories_with_zero"])
        self.assertIn("fast_food", gap["categories_with_zero"])
        self.assertIn("convenience", gap["categories_with_zero"])
        self.assertEqual(gap["totals_observed"]["supermarket"], 596)
        self.assertEqual(gap["totals_observed"]["fast_food"], 0)
        self.assertGreaterEqual(len(gap["remediation_steps"]), 3)
        self.assertIn("estimated_effort_hours", gap)

    def test_metadata_columns_listed(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata file not yet visible")
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, self.metadata.get("columns", []),
                          f"Column {col} missing from metadata.columns")

    def test_in_master_csv(self) -> None:
        if not MASTER_CSV.exists() or self.df is None:
            self.skipTest("master CSV not yet visible")
        master = pd.read_csv(MASTER_CSV, nrows=1)
        for col in ("food_index", "food_n_supermarket", "food_mrfei"):
            self.assertIn(col, master.columns, f"Master missing column: {col}")

    def test_in_master_geojson(self) -> None:
        if not MASTER_GEOJSON.exists() or self.df is None:
            self.skipTest("master GeoJSON not yet visible")
        import geopandas as gpd
        master = gpd.read_file(MASTER_GEOJSON, rows=1)
        for col in ("food_index", "food_n_supermarket"):
            self.assertIn(col, master.columns, f"Master GeoJSON missing column: {col}")


if __name__ == "__main__":
    unittest.main()

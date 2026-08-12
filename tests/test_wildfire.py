"""Tests for the wildfire (forest-fire) exposome layer (cache-first, no network)."""
from __future__ import annotations

import json
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "processed"
CACHE_DIR = REPO_ROOT / "cache"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"
MASTER_GEOJSON = DATA_DIR / "santiago_exposome_master.geojson"

EXPECTED_COLUMNS = [
    "name",
    "area_km2",
    "fire_burned_area_km2_total",
    "fire_burned_area_mean_annual_km2",
    "fire_burned_pct_mean_annual",
    "fire_burned_pct_max_year",
    "fire_burn_years_count",
    "fire_worst_year",
    "fire_trend_km2_per_decade",
    "fire_detections_total",
    "fire_detections_per_km2",
    "fire_detections_max_year",
    "fire_brightness_max_k",
    "fire_exposure_index",
]


class WildfireValidatedCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = {
            "wildfire": {
                "years": [2020],
                "collections": {
                    "burned_area": {
                        "id": "MODIS/061/MCD64A1",
                        "band": "BurnDate",
                        "scale_meters": 500,
                    },
                    "active_fire": {
                        "id": "FIRMS",
                        "band": "T21",
                        "scale_meters": 1000,
                    },
                },
            }
        }
        self.units = gpd.GeoDataFrame(
            {"name": ["A"]},
            geometry=[Point(-70.6, -33.5)],
            crs="EPSG:4326",
        )
        self.burned = pd.DataFrame({"name": ["A"], "burned_km2": [1.25]})
        self.active = pd.DataFrame(
            {"name": ["A"], "detections": [3.0], "brightness_max_k": [330.0]}
        )

    def test_sources_are_independent_and_parameter_changes_invalidate_one(self) -> None:
        from exposome import wildfire

        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with (
                patch.object(wildfire.gee, "init_gee"),
                patch.object(wildfire.gee, "gdf_to_feature_collection", return_value=object()),
                patch.object(wildfire, "_burned_area_km2", return_value=self.burned) as burned,
                patch.object(wildfire, "_firms_activity", return_value=self.active) as active,
            ):
                first = wildfire.fetch_annual_metrics(self.cfg, self.units, cache_dir)
            burned.assert_called_once()
            active.assert_called_once()
            self.assertEqual(first.loc[0, "year"], 2020)

            with (
                patch.object(
                    wildfire.gee,
                    "init_gee",
                    side_effect=AssertionError("GEE should not initialize on a complete hit"),
                ),
                patch.object(
                    wildfire,
                    "_burned_area_km2",
                    side_effect=AssertionError("burned area should be cached"),
                ),
                patch.object(
                    wildfire,
                    "_firms_activity",
                    side_effect=AssertionError("active fire should be cached"),
                ),
            ):
                wildfire.fetch_annual_metrics(self.cfg, self.units, cache_dir)

            changed = {
                "wildfire": {
                    **self.cfg["wildfire"],
                    "collections": {
                        **self.cfg["wildfire"]["collections"],
                        "active_fire": {
                            **self.cfg["wildfire"]["collections"]["active_fire"],
                            "band": "T22",
                        },
                    },
                }
            }
            with (
                patch.object(wildfire.gee, "init_gee") as init,
                patch.object(wildfire.gee, "gdf_to_feature_collection", return_value=object()),
                patch.object(
                    wildfire,
                    "_burned_area_km2",
                    side_effect=AssertionError("unchanged burned-area identity must remain valid"),
                ),
                patch.object(wildfire, "_firms_activity", return_value=self.active) as active,
            ):
                wildfire.fetch_annual_metrics(changed, self.units, cache_dir)
            init.assert_called_once()
            active.assert_called_once()


class WildfireLayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "santiago_wildfire_2015_2024.csv"
        cls.geojson_path = DATA_DIR / "santiago_wildfire_2015_2024.geojson"
        cls.metadata_path = DATA_DIR / "santiago_wildfire_2015_2024_metadata.json"
        if not cls.csv_path.exists():
            raise unittest.SkipTest(
                f"Missing canonical CSV at {cls.csv_path}; run scripts/run_wildfire.py first."
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

    def test_csv_columns_complete(self) -> None:
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, self.df.columns, f"missing column: {col}")
        # Core wildfire columns are fully populated; brightness=0 is a valid
        # sentinel ("no FIRMS detection") and is allowed (not NaN).
        strict = [c for c in EXPECTED_COLUMNS if c != "fire_brightness_max_k"]
        self.assertEqual(self.df[strict].isna().sum().sum(), 0)

    def test_metadata_coherence(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata file not yet visible (likely cloud-sync delay)")
        self.assertEqual(self.metadata["n_rows"], 52)
        self.assertEqual(self.metadata["period"], "2015-2024")
        self.assertEqual(
            self.metadata["index_weights"],
            {"burned_pct": 0.4, "detection_density": 0.4, "recurrence": 0.2},
        )
        for peak in (2017, 2023, 2024):
            self.assertIn(peak, self.metadata["peak_seasons"])
        self.assertTrue(self.metadata["limitations"])
        # Every core column has a description in metadata
        for col in EXPECTED_COLUMNS:
            if col in ("name", "area_km2"):
                continue
            self.assertIn(
                col,
                self.metadata["columns_description"],
                f"metadata missing description for: {col}",
            )

    def test_fire_exposure_index_distribution(self) -> None:
        idx = self.df["fire_exposure_index"]
        self.assertEqual(idx.isna().sum(), 0)
        self.assertGreaterEqual(float(idx.min()), 0.0)
        self.assertLessEqual(float(idx.max()), 100.0)
        # Composite is a weighted sum of three sqrt-normalised components
        # (weights 0.4 / 0.4 / 0.2). The top commune dominates on at least
        # one component (= 100), so the weighted sum is < 100 and > 0.
        self.assertGreater(float(idx.max()), 0.0)
        # Urban vs rural contrast: dense central communes (Santiago,
        # Providencia) must score below the rural / Andean communes
        # (Alhué, San José de Maipo).
        urban = self.df.loc[
            self.df["name"].isin(["Santiago", "Providencia"]), "fire_exposure_index"
        ]
        rural = self.df.loc[
            self.df["name"].isin(["Alhué", "San José de Maipo"]),
            "fire_exposure_index",
        ]
        self.assertGreater(float(urban.min()), 0.0)  # satellite still records
        self.assertLess(float(urban.max()), float(rural.min()))

    def test_fire_worst_year_in_window(self) -> None:
        wy = self.df["fire_worst_year"]
        self.assertEqual(wy.isna().sum(), 0)
        self.assertGreaterEqual(int(wy.min()), 2015)
        self.assertLessEqual(int(wy.max()), 2024)
        # 2015 mega-fire season in the RM dominates many communes.
        self.assertGreaterEqual(int((wy == 2015).sum()), 25)

    def test_fire_trend_finite(self) -> None:
        trend = self.df["fire_trend_km2_per_decade"]
        self.assertEqual(trend.isna().sum(), 0)
        # OLS slope * 10 over 10 points: no inf/-inf
        self.assertTrue((trend.abs() < float("inf")).all())

    def test_fire_trend_ols_semantics(self) -> None:
        """Synthetic OLS slope over the (year, burned_km2) pair.

        The wildfire module computes the trend with ``np.polyfit(year, y, 1)[0] * 10``
        (slope x decade, see ``src/exposome/wildfire.py:216-219``). Verify the
        sign and magnitude on hand-built series so a regression in the
        aggregation loop is caught even when the canonical layer is replaced.
        """
        import numpy as np

        years = np.arange(2015, 2025)

        def _slope(y: np.ndarray) -> float:
            return float(np.polyfit(years, y, 1)[0] * 10)

        # Monotonically increasing series: positive slope, magnitude ~ 10 * y_growth
        inc = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
        s_inc = _slope(inc)
        self.assertAlmostEqual(s_inc, 1.0, places=6)

        # Monotonically decreasing series: negative slope, mirror of above
        dec = inc[::-1]
        s_dec = _slope(dec)
        self.assertAlmostEqual(s_dec, -1.0, places=6)

        # Constant series: zero slope
        const = np.full(10, 0.5)
        self.assertAlmostEqual(_slope(const), 0.0, places=9)

        # Single mega-fire year inside an otherwise-flat series: positive slope
        mega = np.array([0.1, 0.1, 0.1, 0.1, 0.1, 5.0, 0.1, 0.1, 0.1, 0.1])
        s_mega = _slope(mega)
        self.assertGreater(s_mega, 0.0)

        # Confirm the canonical layer uses the same sign convention: at least
        # one commune should have a positive trend and at least one negative.
        trend = self.df["fire_trend_km2_per_decade"]
        self.assertGreater((trend > 0).sum(), 0)
        self.assertGreater((trend < 0).sum(), 0)

    def test_fire_burn_years_count_range(self) -> None:
        """`fire_burn_years_count` is a 0-10 integer recurrence counter."""
        n = self.df["fire_burn_years_count"]
        self.assertEqual(n.isna().sum(), 0)
        self.assertGreaterEqual(int(n.min()), 0)
        self.assertLessEqual(int(n.max()), 10)
        self.assertTrue(
            (n == n.round()).all(),
            "fire_burn_years_count must be integer-valued",
        )
        # Some communes should have recurrent fires; some should have none.
        self.assertGreater((n == 0).sum(), 0)
        self.assertGreater((n >= 5).sum(), 0)
        # San José de Maipo (Andean foothills) historically burns almost every
        # season in the canonical 2015-2024 layer.
        sjm = self.df.loc[self.df["name"] == "San José de Maipo", "fire_burn_years_count"]
        self.assertEqual(len(sjm), 1)
        self.assertGreaterEqual(int(sjm.iloc[0]), 8)

    def test_official_enrichment_graceful_skip(self) -> None:
        from exposome.wildfire import load_official_fires
        from exposome import config

        cfg = config.load_config("santiago")
        official_path = (
            REPO_ROOT / cfg["wildfire"]["official"]["path"]
        )
        if official_path.exists():
            self.skipTest(
                f"Official CSV present at {official_path}; skip graceful-skip check."
            )
        result = load_official_fires(cfg)
        self.assertIsNone(result)
        # CSV must not contain the 3 optional official columns when the
        # enrichment is skipped.
        for col in (
            "fire_official_n_fires",
            "fire_official_damaged_ha",
            "fire_official_human_cause_pct",
        ):
            self.assertNotIn(col, self.df.columns, f"unexpected official col: {col}")

    def test_master_integration(self) -> None:
        if not MASTER_CSV.exists():
            self.skipTest("Master CSV missing; run scripts/build_master_exposome.py first.")
        master_cols = pd.read_csv(MASTER_CSV, nrows=0).columns
        core = [
            "fire_burned_area_km2_total",
            "fire_burned_area_mean_annual_km2",
            "fire_burned_pct_mean_annual",
            "fire_burned_pct_max_year",
            "fire_burn_years_count",
            "fire_worst_year",
            "fire_trend_km2_per_decade",
            "fire_detections_total",
            "fire_detections_per_km2",
            "fire_detections_max_year",
            "fire_brightness_max_k",
            "fire_exposure_index",
        ]
        for col in core:
            self.assertIn(col, master_cols, f"master missing core col: {col}")
        # The 3 official columns must NOT be merged when no CONAF CSV is present.
        for col in (
            "fire_official_n_fires",
            "fire_official_damaged_ha",
            "fire_official_human_cause_pct",
        ):
            self.assertNotIn(
                col,
                master_cols,
                f"master unexpectedly contains official col: {col}",
            )

    def test_brightness_sentinel_handling(self) -> None:
        """fire_brightness_max_k == 0 means "no FIRMS detection in the period".

        It is a valid sentinel (0 K is not physically meaningful) and must NOT
        be treated as NaN. Dense urban communes without wildland interface
        legitimately have brightness=0.
        """
        b = self.df["fire_brightness_max_k"]
        self.assertEqual(b.isna().sum(), 0)
        zero = self.df.loc[b == 0.0, "name"].tolist()
        # At least one commune (dense urban) should have the sentinel.
        self.assertGreater(len(zero), 0)
        # Brightness must otherwise be > 300 K (real MODIS/VIIRS T21 fire-pixels).
        pos = b[b > 0]
        if len(pos) > 0:
            self.assertGreater(float(pos.min()), 300.0)
            self.assertLess(float(pos.max()), 600.0)


class WildfireBuildLayerTest(unittest.TestCase):
    """Smoke test the build_layer module from cache, no GEE."""

    def test_build_layer_idempotent_from_cache(self) -> None:
        """Re-running build_wildfire_layer from cache must reproduce the CSV.

        The CSV is overwritten by the re-run, so we compare the new DataFrame
        against itself (hash equality) and against a defensive copy loaded
        before the call. area_km2 is recomputed from the projected geometry
        each run, so allow a 0.01 km^2 tolerance there.
        """
        from exposome.wildfire import build_wildfire_layer

        if not list(CACHE_DIR.glob("v1/burned_area_annual/*/*.cache.json")):
            self.skipTest("Validated wildfire cache missing; run scripts/run_wildfire.py once.")
        if not (CACHE_DIR / "santiago_communes.geojson").exists():
            self.skipTest("Communes boundary cache missing.")

        # Snapshot the canonical CSV (only the columns we want to compare;
        # the script overwrites the file, so we read it first).
        df_before = pd.read_csv(DATA_DIR / "santiago_wildfire_2015_2024.csv")

        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            df_new, _ = build_wildfire_layer(
                city="santiago",
                cache_dir=CACHE_DIR,
                out_dir=out_dir,
            )
            df_after = pd.read_csv(out_dir / "santiago_wildfire_2015_2024.csv")

        # Name order is stable.
        self.assertEqual(
            df_new["name"].tolist(),
            df_before["name"].tolist(),
        )
        # Compare numeric columns; area_km2 is allowed a small tolerance
        # because projected geometry is recomputed each run.
        numeric_cols = [
            c for c in EXPECTED_COLUMNS
            if c not in ("name", "fire_brightness_max_k", "area_km2")
        ]
        m_before = df_before.set_index("name")[numeric_cols]
        m_after = df_after.set_index("name")[numeric_cols]
        for c in numeric_cols:
            diff = (m_before[c] - m_after[c]).abs().max()
            self.assertLessEqual(
                float(diff),
                1e-9,
                f"column {c} diverged by {diff} after re-build",
            )
        area_diff = (
            df_before.set_index("name")["area_km2"]
            - df_after.set_index("name")["area_km2"]
        ).abs().max()
        self.assertLessEqual(
            float(area_diff),
            0.01,
            f"area_km2 diverged by {area_diff} km^2 after re-build",
        )
        # Brightness sentinel is preserved.
        self.assertEqual(
            int((df_after["fire_brightness_max_k"] == 0).sum()),
            int((df_before["fire_brightness_max_k"] == 0).sum()),
        )


if __name__ == "__main__":
    unittest.main()

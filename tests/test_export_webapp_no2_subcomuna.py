"""Offline tests for scripts/export_webapp_no2_subcomuna.py.

No GEE calls. Covers two things specific to this script (beyond the shared
grid/geometry logic already covered by
tests/test_export_webapp_pm25_subcomuna.py): the column-density -> surface
-concentration conversion, and the per-commune BLH cache-first contract
(``_load_commune_blh`` must reuse ``cache/<city>_blh_<year>.csv`` from the
air_quality_satellite run instead of re-fetching from GEE — same
checkpoint/resume contract as the rest of the pipeline). See
docs/resolution_manifest.md Hallazgo 1.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import export_webapp_no2_subcomuna as mod  # noqa: E402


class No2ColumnToSurfaceTest(unittest.TestCase):
    def test_matches_air_quality_module_formula(self) -> None:
        # Same formula as exposome.air_quality.build_air_quality_layer step 8:
        # no2_surface_ug_m3 = no2_mean * 46.0055 * 1e6 / blh_mean
        column = 0.0001  # mol/m^2, plausible S5P value
        blh = 500.0  # m
        expected = column * mod.M_NO2 * 1.0e6 / blh
        self.assertAlmostEqual(mod._no2_column_to_surface_ugm3(column, blh), expected)

    def test_higher_blh_gives_lower_surface_concentration(self) -> None:
        column = 0.0001
        low_blh = mod._no2_column_to_surface_ugm3(column, 300.0)
        high_blh = mod._no2_column_to_surface_ugm3(column, 1200.0)
        self.assertGreater(low_blh, high_blh)


class LoadCommuneBlhTest(unittest.TestCase):
    def _fixture_communes(self) -> gpd.GeoDataFrame:
        return gpd.GeoDataFrame(
            {"name": ["Santiago", "Maipú", "Vitacura"]},
            geometry=[Point(0, 0).buffer(0.01) for _ in range(3)],
            crs="EPSG:4326",
        )

    def test_cache_hit_skips_fetch_blh_and_fills_nan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            blh_csv = cache_dir / "santiago_blh_2024.csv"
            pd.DataFrame(
                {"name": ["Santiago", "Maipú", "Vitacura"], "blh_mean": [500.0, float("nan"), 700.0]}
            ).to_csv(blh_csv, index=False)

            with patch.object(
                mod, "fetch_blh", side_effect=AssertionError("must not hit GEE when cached")
            ):
                result = mod._load_commune_blh(
                    cfg={}, communes=self._fixture_communes(), cache_dir=cache_dir,
                    city="santiago", year=2024,
                )

        self.assertEqual(set(result.keys()), {"Santiago", "Maipú", "Vitacura"})
        # NaN filled with the regional mean of the other two values (600.0).
        self.assertAlmostEqual(result["Maipú"], 600.0)
        self.assertAlmostEqual(result["Santiago"], 500.0)

    def test_cache_miss_fetches_once_and_writes_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            fetched = pd.DataFrame(
                {"name": ["Santiago", "Maipú", "Vitacura"], "blh_mean": [500.0, 550.0, 700.0]}
            )
            with patch.object(mod, "fetch_blh", return_value=fetched) as fetch_mock, \
                 patch.object(mod.gee, "gdf_to_feature_collection", return_value="fc"):
                result = mod._load_commune_blh(
                    cfg={}, communes=self._fixture_communes(), cache_dir=cache_dir,
                    city="santiago", year=2024,
                )
            fetch_mock.assert_called_once()
            self.assertTrue((cache_dir / "santiago_blh_2024.csv").exists())
            self.assertEqual(result["Maipú"], 550.0)

            # A second call must now hit the cache, not fetch_blh again.
            with patch.object(
                mod, "fetch_blh", side_effect=AssertionError("must not re-fetch once cached")
            ):
                result2 = mod._load_commune_blh(
                    cfg={}, communes=self._fixture_communes(), cache_dir=cache_dir,
                    city="santiago", year=2024,
                )
            self.assertEqual(result2["Maipú"], 550.0)


if __name__ == "__main__":
    unittest.main()

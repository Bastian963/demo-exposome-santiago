"""Tests for the wind exposure layer (ERA5 10-m wind components)."""
from __future__ import annotations

import json
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import pandas as pd
import geopandas as gpd
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.wind import _aggregate_native_pixels, wind_cache_namespace  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "processed"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"
MASTER_GEOJSON = DATA_DIR / "santiago_exposome_master.geojson"
FIG_DIR = REPO_ROOT / "figures"
DOC_DIR = REPO_ROOT / "docs"

EXPECTED_COLUMNS = [
    "name", "area_km2",
    "wind_u_mean", "wind_v_mean", "wind_speed_mean",
    "wind_speed_max_p99", "wind_calm_pct", "wind_dir_prevailing",
    "wind_u_mean_winter", "wind_v_mean_winter",
    "wind_speed_mean_winter", "wind_speed_max_p99_winter",
    "wind_calm_pct_winter", "wind_dir_winter_mean",
    "wind_u_mean_summer", "wind_v_mean_summer",
    "wind_speed_mean_summer", "wind_speed_max_p99_summer",
    "wind_calm_pct_summer", "wind_dir_summer_mean",
]

KNOWN_COMMUNES = {
    "Santiago", "Providencia", "Las Condes", "Vitacura",
    "Ñuñoa", "Maipú", "Puente Alto", "La Florida",
    "Alhué", "San José de Maipo", "Lo Barnechea", "Pirque",
}


class WindCacheNamespaceTest(unittest.TestCase):
    def test_collection_change_cannot_reuse_legacy_cache_namespace(self) -> None:
        self.assertEqual(
            wind_cache_namespace("ECMWF/ERA5_LAND/HOURLY"),
            "ecmwf_era5_land_hourly",
        )
        self.assertNotEqual(
            wind_cache_namespace("ECMWF/ERA5_LAND/HOURLY"),
            wind_cache_namespace("ECMWF/ERA5/HOURLY"),
        )

    def test_native_pixel_intersection_keeps_tiny_coastal_unit(self) -> None:
        centre = gpd.GeoSeries.from_xy([-70.0], [-33.0], crs="EPSG:4326").to_crs("EPSG:32719").iloc[0]
        units = gpd.GeoDataFrame(
            {"name": ["tiny"]},
            geometry=[box(centre.x - 100, centre.y - 100, centre.x + 100, centre.y + 100)],
            crs="EPSG:32719",
        ).to_crs("EPSG:4326")
        cfg = {"crs": {"metric": "EPSG:32719"}, "wind": {"scale_meters": 11_132}}
        out = _aggregate_native_pixels(
            pd.DataFrame({"lon": [-70.0], "lat": [-33.0], "wind_u_mean": [1.5], "wind_v_mean": [-2.0]}),
            units,
            cfg,
            value_columns=["wind_u_mean", "wind_v_mean"],
        )
        self.assertEqual(float(out.loc[0, "wind_u_mean"]), 1.5)
        self.assertEqual(int(out.loc[0, "n_native_wind_pixels"]), 1)
        self.assertFalse(bool(out.loc[0, "used_nearest_wind_fallback"]))


class WindLayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "santiago_wind.csv"
        cls.geojson_path = DATA_DIR / "santiago_wind.geojson"
        cls.metadata_path = DATA_DIR / "santiago_wind_metadata.json"
        cls.fig_path = FIG_DIR / "wind_santiago_4panel.png"

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

    def test_figure_exists(self) -> None:
        self.assertTrue(self.fig_path.exists(), f"Missing: {self.fig_path}")
        self.assertGreater(self.fig_path.stat().st_size, 50_000)

    def test_csv_shape(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(self.df.shape[0], 52, f"Expected 52 rows, got {self.df.shape[0]}")
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

    def test_wind_speed_non_negative(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in ("wind_speed_mean", "wind_speed_max_p99"):
            self.assertGreaterEqual(self.df[col].min(), 0.0,
                                    f"{col} has negative values")

    def test_wind_speed_max_gte_mean(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        diff = self.df["wind_speed_max_p99"] - self.df["wind_speed_mean"]
        self.assertTrue((diff >= -0.01).all(),
                        "p99 wind speed must be >= mean wind speed")

    def test_wind_speed_sane_range(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        # ERA5 10-m wind in central Chile typically 0.5-5 m/s annual mean.
        self.assertGreater(self.df["wind_speed_mean"].min(), 0.3,
                           "wind_speed_mean < 0.3 m/s implausible for inland RM")
        self.assertLess(self.df["wind_speed_mean"].max(), 6.0,
                        "wind_speed_mean > 6 m/s implausible for central Chile")

    def test_wind_calm_pct_in_unit_interval(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertGreaterEqual(self.df["wind_calm_pct"].min(), 0.0)
        self.assertLessEqual(self.df["wind_calm_pct"].max(), 1.0)

    def test_wind_calm_pct_sane(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        # Typical fraction of calm hours in central Chile: 50-90%.
        self.assertGreater(self.df["wind_calm_pct"].median(), 0.4,
                           "median wind_calm_pct < 0.4 is implausible for central Chile")
        self.assertLess(self.df["wind_calm_pct"].median(), 0.95,
                        "median wind_calm_pct > 0.95 is implausible")

    def test_wind_dir_in_range(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        d = self.df["wind_dir_prevailing"]
        self.assertGreaterEqual(d.min(), 0.0)
        self.assertLess(d.max(), 360.0, "wind_dir must be in [0, 360)")

    def test_uv_components_consistent_with_speed(self) -> None:
        """Verify Jensen's inequality property: mean(speed) >= |mean(u,v)|.

        u and v are annual mean components; speed is the per-hour mean
        of sqrt(u^2 + v^2). By Jensen's inequality,
        mean(speed) >= sqrt(mean(u)^2 + mean(v)^2).
        """
        if self.df is None:
            self.skipTest("CSV not visible")
        reconstructed = (self.df["wind_u_mean"] ** 2 + self.df["wind_v_mean"] ** 2) ** 0.5
        # mean(speed) must be >= |mean(u,v)| because the sqrt is concave.
        self.assertTrue(
            (self.df["wind_speed_mean"] >= reconstructed - 0.01).all(),
            f"Jensen violation: some communes have mean(speed) < |mean(u,v)|"
        )

    def test_no_nans_in_key_columns(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in EXPECTED_COLUMNS:
            self.assertEqual(self.df[col].isna().sum(), 0, f"NaN found in {col}")

    def test_geojson_matches_csv(self) -> None:
        if not self.geojson_path.exists() or self.df is None:
            self.skipTest("geojson or csv not visible")
        import geopandas as gpd
        gdf = gpd.read_file(self.geojson_path)
        self.assertEqual(gdf["name"].nunique(), 52)
        self.assertEqual(set(gdf["name"]), set(self.df["name"]))

    def test_jensen_ratio_bounded(self) -> None:
        """Lock-in the observed scalar/vector wind ratio.

        Jensen's inequality gives mean(speed) >= |mean(u,v)|. The ratio
        measures directional variability: ratio=1.0 means constant
        direction, higher = more variable.

        v1.3 (ERA5-Land 11.132 km): median ratio ~3.5. With finer resolution
        each commune captures more of its own directional variability
        (mountain-valley + synoptic regime), so the scalar/vector
        ratio increases. The lower bound (1.5) is preserved as a
        physical floor; the upper bound is relaxed to 5.0 to allow
        9-km-grid ratios.

        If the ratio drifts above 5.0, the calculation may have
        changed (e.g., a column got duplicated or summed twice).
        """
        if self.df is None:
            self.skipTest("CSV not visible")
        import numpy as np
        speed_recon = np.sqrt(
            self.df["wind_u_mean"] ** 2 + self.df["wind_v_mean"] ** 2
        )
        ratio = (self.df["wind_speed_mean"] / speed_recon)
        median_ratio = ratio.median()
        self.assertGreater(
            median_ratio, 1.5,
            f"median Jensen ratio {median_ratio:.2f} too low; "
            "directional variability may have changed",
        )
        self.assertLess(
            median_ratio, 5.0,
            f"median Jensen ratio {median_ratio:.2f} too high; "
            "calculation may have changed (e.g., duplicated column)",
        )

    def test_era5_pixel_sharing(self) -> None:
        """Lock-in the expected number of communes sharing a wind pixel.

        v1.3 (ERA5-Land 11.132 km): at most 5/52 communes should share the
        same wind_speed_mean value. Before v1.3 (ERA5 30 km), 17/52
        shared. If pixel sharing is >= 10, the resolution has
        regressed (e.g., back to 30 km).
        """
        if self.df is None:
            self.skipTest("CSV not visible")
        rounded = self.df["wind_speed_mean"].round(3)
        counts = rounded.value_counts()
        most_common_count = int(counts.iloc[0])
        self.assertLess(
            most_common_count, 10,
            f"{most_common_count} communes share a wind pixel; "
            "resolution may have regressed (e.g., back to 30 km)",
        )

    def test_metadata_documents_calm_threshold(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata not visible")
        self.assertIn("threshold_calm_m_s", self.metadata)
        self.assertEqual(
            self.metadata.get("source"), "ECMWF/ERA5_LAND/HOURLY via GEE"
        )
        self.assertIn("limitation", str(self.metadata).lower())

    def test_in_master_csv(self) -> None:
        if not MASTER_CSV.exists() or self.df is None:
            self.skipTest("master CSV not visible")
        master = pd.read_csv(MASTER_CSV, nrows=1)
        for col in ("wind_speed_mean", "wind_calm_pct", "wind_dir_prevailing"):
            self.assertIn(col, master.columns, f"Master missing column: {col}")

    def test_in_master_geojson(self) -> None:
        if not MASTER_GEOJSON.exists() or self.df is None:
            self.skipTest("master GeoJSON not visible")
        import geopandas as gpd
        master = gpd.read_file(MASTER_GEOJSON, rows=1)
        for col in ("wind_speed_mean", "wind_calm_pct"):
            self.assertIn(col, master.columns, f"Master GeoJSON missing column: {col}")

    def test_seasonal_columns_present(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        seasonal_cols = [
            "wind_u_mean_winter", "wind_v_mean_winter",
            "wind_speed_mean_winter", "wind_speed_max_p99_winter",
            "wind_calm_pct_winter", "wind_dir_winter_mean",
            "wind_u_mean_summer", "wind_v_mean_summer",
            "wind_speed_mean_summer", "wind_speed_max_p99_summer",
            "wind_calm_pct_summer", "wind_dir_summer_mean",
        ]
        for col in seasonal_cols:
            self.assertIn(col, self.df.columns, f"Missing seasonal column: {col}")

    def test_seasonal_speed_sane_range(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in ("wind_speed_mean_winter", "wind_speed_mean_summer"):
            self.assertGreater(self.df[col].min(), 0.3,
                               f"{col} < 0.3 m/s implausible for inland RM")
            self.assertLess(self.df[col].max(), 6.0,
                            f"{col} > 6 m/s implausible for central Chile")

    def test_seasonal_dir_in_range(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in ("wind_dir_winter_mean", "wind_dir_summer_mean"):
            d = self.df[col]
            self.assertGreaterEqual(d.min(), 0.0,
                                    f"{col} has values < 0")
            self.assertLess(d.max(), 360.0,
                            f"{col} has values >= 360")

    def test_winter_calm_ge_annual_calm(self) -> None:
        """Winter in central Chile is the high-stagnation season.

        In Santiago, the mean wind speed is lower in winter than the
        annual mean (Pacific storms are less frequent; subsidence
        inversions are stronger). The seasonal calm fraction should
        be >= the annual calm fraction for the majority of communes.
        A reversal of this ordering would indicate either a season
        definition bug or a zonal-stats drift.
        """
        if self.df is None:
            self.skipTest("CSV not visible")
        ge = (self.df["wind_calm_pct_winter"] >= self.df["wind_calm_pct"] - 0.01)
        ratio = ge.mean()
        self.assertGreater(
            ratio, 0.6,
            f"only {ratio:.0%} of communes have winter calm >= annual calm; "
            "expected >60% (winter stagnation dominates central Chile)",
        )


if __name__ == "__main__":
    unittest.main()

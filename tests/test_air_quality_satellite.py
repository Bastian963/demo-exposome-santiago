"""Tests for the air-quality satellite exposome layer (Plan A++).

Validates the on-disk CSV/GeoJSON/metadata, the new O3 and AE columns,
the WHO ratio scaling, and master integration.
"""
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
FIG_DIR = REPO_ROOT / "figures"
DOC_DIR = REPO_ROOT / "docs"

EXPECTED_COLUMNS = [
    "name", "area_km2",
    "no2_mean", "blh_mean", "aod_mean",
    "ae_470_550_mean", "fine_mode_fraction_mean", "o3_mean",
    "no2_surface_ug_m3", "no2_who_ratio",
]

# Surface O3 (o3_surface_ug_m3, o3_who_ratio) was removed in v1.1:
# S5P O3 is total column (~90% stratospheric), so the column * M / BLH
# formula would over-estimate surface O3 by 5-10x. See
# docs/plan_a_plus_methodology.md, section "O3 limitation: stratospheric
# column". Absolute surface O3 should come from ground stations.
DROPPED_O3_COLUMNS = ("o3_surface_ug_m3", "o3_who_ratio")

KNOWN_COMMUNES = {
    "Santiago", "Providencia", "Las Condes", "Vitacura",
    "Ñuñoa", "Maipú", "Puente Alto", "La Florida",
    "Alhué", "San José de Maipo", "Lo Barnechea", "Pirque",
}


class AirQualitySatelliteLayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "santiago_air_quality_satellite_2024.csv"
        cls.geojson_path = DATA_DIR / "santiago_air_quality_satellite_2024.geojson"
        cls.metadata_path = DATA_DIR / "santiago_air_quality_satellite_2024_metadata.json"
        cls.fig_path = FIG_DIR / "air_quality_satellite_santiago_4panel.png"

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

    def test_no2_mean_positive(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertGreater(self.df["no2_mean"].min(), 0.0)
        self.assertLess(self.df["no2_mean"].max(), 1.0, "no2_mean > 1.0 is implausible")

    def test_no2_surface_ug_m3_sane(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertGreaterEqual(self.df["no2_surface_ug_m3"].min(), 0.0)
        self.assertLessEqual(self.df["no2_surface_ug_m3"].max(), 100.0,
                             "no2_surface_ug_m3 > 100 is implausible for Santiago")

    def test_o3_mean_positive(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertGreater(self.df["o3_mean"].min(), 0.0)
        self.assertLess(self.df["o3_mean"].max(), 1.0, "o3_mean > 1.0 is implausible")

    def test_o3_mean_in_s5p_range(self) -> None:
        """Lock-in that o3_mean is a realistic S5P total column value.

        Typical S5P O3 column for central Chile: 0.10-0.20 mol/m^2
        (~225-450 DU). If o3_mean drifts outside [0.05, 0.30] the
        GEE pipeline has changed.
        """
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertGreater(self.df["o3_mean"].min(), 0.05)
        self.assertLess(self.df["o3_mean"].max(), 0.30)

    def test_o3_surface_columns_dropped(self) -> None:
        """Regression test: surface O3 columns must NOT exist.

        v1.0 emitted o3_surface_ug_m3 (15718-21785 ug/m^3) and
        o3_who_ratio (261-363), both 5-10x above physically plausible
        values because S5P O3 is total column (~90% stratospheric).
        v1.1 drops them. This test fails if they reappear.
        """
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in DROPPED_O3_COLUMNS:
            self.assertNotIn(
                col, self.df.columns,
                f"{col} should have been removed in v1.1; see "
                "docs/plan_a_plus_methodology.md section "
                "'O3 limitation: stratospheric column'",
            )
        if MASTER_CSV.exists():
            master = pd.read_csv(MASTER_CSV, nrows=1)
            for col in DROPPED_O3_COLUMNS:
                self.assertNotIn(
                    col, master.columns,
                    f"master still contains dropped {col}",
                )

    def test_ae_470_550_sane(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        ae = self.df["ae_470_550_mean"]
        self.assertGreaterEqual(ae.min(), 0.0, "AE cannot be negative")
        self.assertLessEqual(ae.max(), 3.5, "AE > 3.5 is rare/impossible for ambient aerosols")
        # AE typical range for tropospheric aerosol over urban areas: 1.0-2.5
        self.assertGreater(ae.median(), 0.5, "median AE implausibly low for Santiago")

    def test_blh_mean_sane(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertGreaterEqual(self.df["blh_mean"].min(), 50.0, "BLH < 50 m is implausible")
        self.assertLessEqual(self.df["blh_mean"].max(), 3000.0, "BLH > 3 km is implausible for inland")

    def test_aod_mean_sane(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertGreaterEqual(self.df["aod_mean"].min(), 0.0)
        self.assertLessEqual(self.df["aod_mean"].max(), 1.0, "AOD > 1.0 is rare (smoke/dust)")

    def test_who_ratios_proportional(self) -> None:
        """Sanity: no2_who_ratio should be > 0 everywhere."""
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in ("no2_who_ratio",):
            self.assertGreater(self.df[col].min(), 0.0, f"{col} has non-positive values")
            self.assertFalse(self.df[col].isna().any(), f"{col} has NaN")

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

    def test_metadata_documents_plan_a_plus_plus(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata not visible")
        self.assertIn("Plan A++", self.metadata.get("method", ""))
        for col in ("resolution_no2_m", "resolution_o3_m", "resolution_aod_m", "resolution_ae_m"):
            self.assertIn(col, self.metadata, f"metadata missing {col}")

    def test_in_master_csv(self) -> None:
        if not MASTER_CSV.exists() or self.df is None:
            self.skipTest("master CSV not visible")
        master = pd.read_csv(MASTER_CSV, nrows=1)
        for col in ("no2_surface_ug_m3", "o3_mean", "ae_470_550_mean", "no2_who_ratio_satellite"):
            self.assertIn(col, master.columns, f"Master missing column: {col}")

    def test_in_master_geojson(self) -> None:
        if not MASTER_GEOJSON.exists() or self.df is None:
            self.skipTest("master GeoJSON not visible")
        import geopandas as gpd
        master = gpd.read_file(MASTER_GEOJSON, rows=1)
        for col in ("no2_surface_ug_m3", "o3_mean", "ae_470_550_mean"):
            self.assertIn(col, master.columns, f"Master GeoJSON missing column: {col}")


if __name__ == "__main__":
    unittest.main()

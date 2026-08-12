"""Tests for the noise exposome layer (MMA Minuta Mapa de Ruido GSU 2023).

All tests are offline; they validate the on-disk CSVs, the master
integration, and the documented metadata.
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
    "name",
    "noise_ld_pop_exposed",
    "noise_ld_pct_exposed",
    "noise_ln_pop_exposed",
    "noise_ln_pct_exposed",
    "noise_combined_pct",
    "noise_in_gsu_map",
]

EXPECTED_GSU_COMMUNES = 35

KNOWN_COMMUNES = {
    "Santiago", "Providencia", "Las Condes", "Vitacura",
    "Maipú", "Puente Alto", "La Florida", "Ñuñoa",
    "Alhué", "San Pedro", "Curacaví",
}


class NoiseLayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "santiago_noise_mma_2023.csv"
        cls.geojson_path = DATA_DIR / "santiago_noise_mma_2023.geojson"
        cls.metadata_path = DATA_DIR / "santiago_noise_mma_2023_metadata.json"
        cls.doc_path = DOC_DIR / "noise_methodology.md"
        cls.fig_path = FIG_DIR / "noise_santiago_4panel.png"

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

    def test_in_gsu_map_binary(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        vals = set(self.df["noise_in_gsu_map"].unique())
        self.assertTrue(vals.issubset({0, 1}), f"noise_in_gsu_map must be 0/1, got {vals}")
        self.assertEqual(int(self.df["noise_in_gsu_map"].sum()), EXPECTED_GSU_COMMUNES)

    def test_pct_columns_in_range(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in ("noise_ld_pct_exposed", "noise_ln_pct_exposed", "noise_combined_pct"):
            self.assertGreaterEqual(self.df[col].min(), 0.0, f"{col} has negative values")
            self.assertLessEqual(self.df[col].max(), 100.0, f"{col} exceeds 100%")

    def test_pop_columns_non_negative(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in ("noise_ld_pop_exposed", "noise_ln_pop_exposed"):
            self.assertGreaterEqual(self.df[col].min(), 0)

    def test_zero_outside_gsu(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        outside = self.df[self.df["noise_in_gsu_map"] == 0]
        for col in (
            "noise_ld_pop_exposed",
            "noise_ld_pct_exposed",
            "noise_ln_pop_exposed",
            "noise_ln_pct_exposed",
            "noise_combined_pct",
        ):
            self.assertTrue(
                (outside[col] == 0).all(),
                f"Communes outside GSU must have {col}=0; got non-zero values",
            )

    def test_known_extremes(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        inside = self.df[self.df["noise_in_gsu_map"] == 1]
        top = inside.nlargest(1, "noise_combined_pct").iloc[0]
        bot_inside = inside.nsmallest(1, "noise_combined_pct").iloc[0]
        self.assertGreater(top["noise_combined_pct"], 15.0)
        self.assertGreaterEqual(bot_inside["noise_combined_pct"], 0.0)
        self.assertIn(top["name"], {"Cerrillos", "Vitacura", "Lo Espejo", "Renca"})

    def test_no_nans_in_key_columns(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in EXPECTED_COLUMNS:
            self.assertEqual(self.df[col].isna().sum(), 0, f"NaN found in {col}")

    def test_metadata_consistent(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata file not yet visible")
        self.assertEqual(self.metadata.get("year"), 2023)
        self.assertEqual(self.metadata.get("n_communes_in_gsu_map"), EXPECTED_GSU_COMMUNES)
        src = self.metadata.get("source", "").upper()
        self.assertTrue(
            "MMA" in src and "SANTIAGO" in src,
            f"Source must reference MMA and Santiago, got: {self.metadata.get('source')}",
        )

    def test_in_master_csv(self) -> None:
        if not MASTER_CSV.exists() or self.df is None:
            self.skipTest("master CSV not yet visible")
        master = pd.read_csv(MASTER_CSV, nrows=1)
        for col in ("noise_combined_pct", "noise_in_gsu_map"):
            self.assertIn(col, master.columns, f"Master missing column: {col}")

    def test_in_master_geojson(self) -> None:
        if not MASTER_GEOJSON.exists() or self.df is None:
            self.skipTest("master GeoJSON not yet visible")
        import geopandas as gpd
        master = gpd.read_file(MASTER_GEOJSON, rows=1)
        for col in ("noise_combined_pct", "noise_in_gsu_map"):
            self.assertIn(col, master.columns, f"Master GeoJSON missing column: {col}")


if __name__ == "__main__":
    unittest.main()

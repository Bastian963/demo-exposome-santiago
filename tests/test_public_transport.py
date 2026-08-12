"""Tests for the public transport exposome layer (OSM bus + Metro)."""
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
    "transit_n_bus_stops",
    "transit_n_metro_stations",
    "transit_n_rail_stations",
    "transit_bus_density",
    "transit_metro_density",
    "transit_mean_dist_bus_m",
    "transit_p90_dist_bus_m",
    "transit_bus_coverage_300m",
    "transit_bus_coverage_500m",
    "transit_mean_dist_metro_m",
    "transit_metro_coverage_1000m",
    "transit_has_metro",
    "transit_index",
]

EXPECTED_METRO_COMMUNES = 27
SENTINEL_NO_METRO_DISTANCE = 50_000.0

KNOWN_COMMUNES = {
    "Santiago", "Providencia", "Las Condes", "Ñuñoa",
    "Maipú", "Puente Alto", "La Florida", "San Miguel",
    "Alhué", "San José de Maipo", "Colina", "Lo Barnechea",
}


class PublicTransportLayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "santiago_public_transport.csv"
        cls.geojson_path = DATA_DIR / "santiago_public_transport.geojson"
        cls.metadata_path = DATA_DIR / "santiago_public_transport_metadata.json"
        cls.doc_path = DOC_DIR / "public_transport_methodology.md"
        cls.fig_path = FIG_DIR / "public_transport_santiago_4panel.png"

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

    def test_transit_index_range(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertGreaterEqual(self.df["transit_index"].min(), 0.0)
        self.assertLessEqual(self.df["transit_index"].max(), 100.0)
        self.assertGreater(self.df["transit_index"].max(), 0.0)

    def test_has_metro_binary(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        vals = set(self.df["transit_has_metro"].unique())
        self.assertTrue(vals.issubset({0, 1}), f"transit_has_metro must be 0/1, got {vals}")
        self.assertEqual(int(self.df["transit_has_metro"].sum()), EXPECTED_METRO_COMMUNES)

    def test_counts_non_negative(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in (
            "transit_n_bus_stops",
            "transit_n_metro_stations",
            "transit_n_rail_stations",
        ):
            self.assertGreaterEqual(self.df[col].min(), 0)
            self.assertGreater(self.df[col].max(), 0, f"{col} all zeros")

    def test_densities_non_negative(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in ("transit_bus_density", "transit_metro_density"):
            self.assertGreaterEqual(self.df[col].min(), 0.0)

    def test_distances_non_negative(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in ("transit_mean_dist_bus_m", "transit_p90_dist_bus_m", "transit_mean_dist_metro_m"):
            self.assertGreaterEqual(self.df[col].min(), 0.0)

    def test_p90_gte_mean_bus(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        diff = self.df["transit_p90_dist_bus_m"] - self.df["transit_mean_dist_bus_m"]
        self.assertTrue((diff >= -0.01).all(), "p90 distance must be >= mean distance")

    def test_coverage_in_unit_interval(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in (
            "transit_bus_coverage_300m",
            "transit_bus_coverage_500m",
            "transit_metro_coverage_1000m",
        ):
            self.assertGreaterEqual(self.df[col].min(), 0.0)
            self.assertLessEqual(self.df[col].max(), 1.0)

    def test_coverage_300m_lte_500m(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        diff = self.df["transit_bus_coverage_500m"] - self.df["transit_bus_coverage_300m"]
        self.assertTrue((diff >= -0.001).all(), "500m coverage must be >= 300m coverage")

    def test_no_metro_sentinel_distance(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        no_metro = self.df[self.df["transit_has_metro"] == 0]
        for col in ("transit_mean_dist_metro_m", "transit_metro_coverage_1000m"):
            self.assertEqual(
                (no_metro[col] == SENTINEL_NO_METRO_DISTANCE).sum()
                if col == "transit_mean_dist_metro_m"
                else (no_metro[col] == 0.0).sum(),
                len(no_metro),
                f"Communes without Metro must have sentinel value in {col}",
            )

    def test_consistency_metro_indicators(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        # transit_n_metro_stations > 0 iff transit_has_metro == 1
        has_metro_flag = self.df["transit_has_metro"] == 1
        has_metro_count = self.df["transit_n_metro_stations"] > 0
        self.assertTrue((has_metro_flag == has_metro_count).all())

    def test_known_extremes(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        top = self.df.nlargest(1, "transit_index").iloc[0]
        bot = self.df.nsmallest(1, "transit_index").iloc[0]
        self.assertEqual(top["name"], "Santiago", f"Top must be Santiago, got {top['name']}")
        self.assertEqual(bot["name"], "San José de Maipo", f"Bottom must be San José de Maipo, got {bot['name']}")

    def test_no_nans_in_key_columns(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in EXPECTED_COLUMNS:
            self.assertEqual(self.df[col].isna().sum(), 0, f"NaN found in {col}")

    def test_metadata_consistent(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata file not yet visible")
        self.assertEqual(self.metadata.get("n_communes"), 52)
        self.assertEqual(self.metadata.get("n_communes_with_metro"), EXPECTED_METRO_COMMUNES)
        self.assertIn("osmnx", self.metadata.get("source", "").lower())
        self.assertEqual(self.metadata.get("crs_metric"), "EPSG:32719")
        self.assertIn("bus_stop", self.metadata.get("osm_tags", {}).get("bus_stop", ""))

    def test_in_master_csv(self) -> None:
        if not MASTER_CSV.exists() or self.df is None:
            self.skipTest("master CSV not yet visible")
        master = pd.read_csv(MASTER_CSV, nrows=1)
        for col in ("transit_index", "transit_has_metro", "transit_n_metro_stations"):
            self.assertIn(col, master.columns, f"Master missing column: {col}")

    def test_in_master_geojson(self) -> None:
        if not MASTER_GEOJSON.exists() or self.df is None:
            self.skipTest("master GeoJSON not yet visible")
        import geopandas as gpd
        master = gpd.read_file(MASTER_GEOJSON, rows=1)
        for col in ("transit_index", "transit_has_metro"):
            self.assertIn(col, master.columns, f"Master GeoJSON missing column: {col}")


if __name__ == "__main__":
    unittest.main()

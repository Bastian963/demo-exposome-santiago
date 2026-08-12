"""Offline contract tests for the study-wide green detail exporter."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon, box

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import export_webapp_green_subcomuna as mod  # noqa: E402


class GreenDetailExporterTest(unittest.TestCase):
    def test_grid_is_study_wide_not_commune_by_commune(self) -> None:
        # Splitting an AOI into adjacent administrative units cannot shift the
        # 1-km grid phase: cells are anchored in the study metric CRS.
        whole = gpd.GeoDataFrame(
            geometry=[box(0, 0, 2000, 1000)], crs="EPSG:3857"
        )
        split = gpd.GeoDataFrame(
            geometry=[box(0, 0, 1000, 1000), box(1000, 0, 2000, 1000)],
            crs="EPSG:3857",
        )
        whole_ids = {cell["cell_id"] for cell in mod._build_cells(whole, metric_crs="EPSG:3857")}
        split_ids = {cell["cell_id"] for cell in mod._build_cells(split, metric_crs="EPSG:3857")}
        self.assertEqual(whole_ids, split_ids)

    def test_checkpoint_round_trips_nullable_completed_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "green_detail_1km.json"
            mod._write_checkpoint(path, {"1km_0_0": 32.5, "1km_1_0": None})
            self.assertEqual(
                mod._load_checkpoint(path), {"1km_0_0": 32.5, "1km_1_0": None}
            )

    def test_reprojection_artifact_is_repaired_before_earth_engine(self) -> None:
        # A bow-tie stands in for a tiny self-intersection made by a CRS
        # transform at an administrative edge. It must not serialize as NaN.
        repaired = mod._valid_polygonal(Polygon([(0, 0), (1, 1), (1, 0), (0, 1)]))
        self.assertIsNotNone(repaired)
        self.assertTrue(repaired.is_valid)
        self.assertFalse(repaired.is_empty)


if __name__ == "__main__":
    unittest.main()

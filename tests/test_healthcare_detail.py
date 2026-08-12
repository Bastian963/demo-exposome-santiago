from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point, box


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.healthcare import (  # noqa: E402
    _write_healthcare_detail_grid,
    nearest_distance_summary,
)


class HealthcareDetailTests(unittest.TestCase):
    def test_detail_is_a_real_stable_grid_not_a_commune_mean(self) -> None:
        cells = gpd.GeoDataFrame(
            {
                "cell_id": ["0:0", "1:0"],
                "name": ["A", "A"],
                "cell_geometry": [box(0, 0, 1000, 1000), box(1000, 0, 2000, 1000)],
            },
            geometry=[Point(500, 500), Point(1500, 500)],
            crs="EPSG:3857",
        )
        facilities = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:3857")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "subcomuna" / "healthcare.geojson"
            _write_healthcare_detail_grid(
                cells,
                facilities,
                spacing_m=1000,
                destination=destination,
                use_ckdtree=True,
            )
            payload = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(payload["grid_alignment"], "study_aoi_metric_grid")
        self.assertFalse(payload["is_synthetic"])
        self.assertEqual(payload["n_features"], 2)
        values = [feature["properties"]["value"] for feature in payload["features"]]
        self.assertNotEqual(values[0], values[1])

    def test_detail_prefers_current_distance_when_grid_has_legacy_value(self) -> None:
        cells = gpd.GeoDataFrame(
            {
                "cell_id": ["0:0"],
                "name": ["A"],
                # A stale analytical value must never be mistaken for the
                # nearest-facility metric written to the public grid.
                "value": [99999.0],
                "cell_geometry": [box(0, 0, 1000, 1000)],
            },
            geometry=[Point(500, 500)],
            crs="EPSG:3857",
        )
        facilities = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:3857")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "subcomuna" / "healthcare.geojson"
            _write_healthcare_detail_grid(
                cells,
                facilities,
                spacing_m=1000,
                destination=destination,
                use_ckdtree=True,
            )
            payload = json.loads(destination.read_text(encoding="utf-8"))
        self.assertLess(payload["features"][0]["properties"]["value"], 1000)

    def test_distance_quantiles_tolerate_duplicate_spatial_indexes(self) -> None:
        grid = gpd.GeoDataFrame(
            {"name": ["A", "A"], "cell_id": ["0:0", "1:0"], "area_weight_m2": [1.0, 1.0]},
            geometry=[Point(0, 0), Point(100, 0)],
            crs="EPSG:3857",
            index=[7, 7],
        )
        facilities = gpd.GeoDataFrame(geometry=[Point(0, 0)], crs="EPSG:3857")
        summary = nearest_distance_summary(
            grid,
            facilities,
            distance_col="nearest_health_m",
            prefix="nearest_health",
            use_ckdtree=True,
        )
        self.assertEqual(float(summary.loc[0, "median_nearest_health_m"]), 0.0)


if __name__ == "__main__":
    unittest.main()

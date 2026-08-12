from __future__ import annotations

import sys
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.spatial_support import INDICATOR_SUPPORT, SPATIAL_SCHEMA_VERSION, indicators_for_bundle, validate_indicator_records  # noqa: E402
from exposome.study_grid import build_study_access_grid, intersect_grid_with_units  # noqa: E402


class SpatialV3Tests(unittest.TestCase):
    def test_every_card_declares_download_observation_analysis_and_rendering(self) -> None:
        for indicator, record in INDICATOR_SUPPORT.items():
            self.assertEqual(set(("downloaded", "observation", "analysis", "rendered")) - set(record), set(), indicator)
        self.assertEqual(SPATIAL_SCHEMA_VERSION, 3)
        self.assertEqual(validate_indicator_records(indicators_for_bundle([])), [])

    def test_no2_distinguishes_download_grid_from_observation_footprint(self) -> None:
        record = INDICATOR_SUPPORT["no2"]
        self.assertEqual(record["downloaded"]["resolution"]["value"], 1113.2)
        self.assertEqual(record["observation"]["resolution"]["x"], 3500)
        self.assertEqual(record["observation"]["resolution"]["y"], 5500)

    def test_aoi_grid_is_invariant_to_a_boundary_split(self) -> None:
        whole = gpd.GeoDataFrame({"name": ["whole"]}, geometry=[box(100, 100, 2100, 1100)], crs="EPSG:3857")
        split = gpd.GeoDataFrame(
            {"name": ["west", "east"]},
            geometry=[box(100, 100, 1100, 1100), box(1100, 100, 2100, 1100)],
            crs="EPSG:3857",
        )
        whole_grid = build_study_access_grid(whole, spacing_m=1000, metric_crs="EPSG:3857")
        split_grid = build_study_access_grid(split, spacing_m=1000, metric_crs="EPSG:3857")
        self.assertEqual(set(whole_grid.cell_id), set(split_grid.cell_id))
        links = intersect_grid_with_units(split_grid, split)
        self.assertEqual(set(links.name), {"west", "east"})
        self.assertTrue((links.intersection_area_m2 > 0).all())

    def test_wildfire_keeps_incompatible_components_separate(self) -> None:
        components = INDICATOR_SUPPORT["wildfire"]["components"]
        self.assertEqual(components["burned_area"]["downloaded"]["resolution"]["value"], 500)
        self.assertEqual(components["active_fire"]["downloaded"]["resolution"]["value"], 1000)


if __name__ == "__main__":
    unittest.main()

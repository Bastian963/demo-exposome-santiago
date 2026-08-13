from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome import gee  # noqa: E402


class GdfToFeatureCollectionTest(unittest.TestCase):
    def test_missing_administrative_properties_are_not_serialized_as_nan(self) -> None:
        frame = gpd.GeoDataFrame(
            {"name": ["unit"], "gna": [np.nan], "optional": [pd.NA]},
            geometry=[Point(-58.4, -34.6)],
            crs="EPSG:4326",
        )
        captured = []

        def fake_feature(geometry, properties):
            captured.append((geometry, properties))
            return properties

        with (
            patch.object(gee.ee, "Feature", side_effect=fake_feature),
            patch.object(gee.ee, "FeatureCollection", side_effect=lambda values: values),
        ):
            result = gee.gdf_to_feature_collection(frame)

        self.assertEqual(result, [{"name": "unit"}])
        self.assertEqual(captured[0][1], {"name": "unit"})


class GeeProjectTest(unittest.TestCase):
    def test_node_environment_selects_quota_project(self) -> None:
        with (
            patch.dict("os.environ", {gee.GEE_PROJECT_ENV: "brainlat"}),
            patch.object(gee.ee, "Initialize") as initialize,
        ):
            gee.init_gee()

        initialize.assert_called_once_with(project="brainlat")

    def test_explicit_project_overrides_node_environment(self) -> None:
        with (
            patch.dict("os.environ", {gee.GEE_PROJECT_ENV: "brainlat"}),
            patch.object(gee.ee, "Initialize") as initialize,
        ):
            gee.init_gee("another-project")

        initialize.assert_called_once_with(project="another-project")


if __name__ == "__main__":
    unittest.main()

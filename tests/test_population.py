from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.population import load_or_fetch_worldpop


class PopulationFallbackTest(unittest.TestCase):
    def test_valid_cache_avoids_gee(self) -> None:
        units = gpd.GeoDataFrame(
            {"name": ["A", "B"]},
            geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
            crs="EPSG:4326",
        )
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "population.csv"
            pd.DataFrame({"name": ["A", "B"], "pop_total": [10, 20]}).to_csv(
                cache, index=False
            )
            with patch("exposome.population.gee.init_gee", side_effect=AssertionError):
                result = load_or_fetch_worldpop({}, units, cache)
        self.assertEqual(result["pop_total"].tolist(), [10, 20])

    def test_stale_cache_requires_configuration(self) -> None:
        units = gpd.GeoDataFrame(
            {"name": ["A"]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:4326"
        )
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "WorldPop configuration"):
                load_or_fetch_worldpop({}, units, Path(tmp) / "missing.csv")


if __name__ == "__main__":
    unittest.main()

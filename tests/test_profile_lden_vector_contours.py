from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from scripts.migrations.profile_lden_vector_contours import LDEN_LAYER, profile_contours


class LdenVectorContourProfileTests(unittest.TestCase):
    def test_profiles_clipped_threshold_contours(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            boundary = root / "boundary.geojson"
            gpd.GeoDataFrame({"id": ["bcn"], "geometry": [box(0, 0, 1000, 1000)]}, crs="EPSG:3035").to_file(
                boundary, driver="GeoJSON"
            )
            source = root / "source.gpkg"
            gpd.GeoDataFrame(
                {
                    "category": ["Lden5054", "Lden5559", "Lden6569"],
                    "geometry": [box(0, 0, 100, 100), box(0, 0, 800, 800), box(500, 0, 1200, 500)],
                },
                crs="EPSG:3035",
            ).to_file(source, layer=LDEN_LAYER, driver="GPKG")
            output = root / "report.json"
            report = profile_contours(source, boundary, output=output)
            self.assertEqual(report["features"], 2)
            self.assertIn("57", report["bands"])
            self.assertIn("67", report["bands"])
            self.assertGreater(report["vertices"], 0)
            self.assertGreater(report["estimated_geojson_bytes"], 0)
            self.assertGreater(report["geoparquet_bytes"], 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["features"], 2)


if __name__ == "__main__":
    unittest.main()

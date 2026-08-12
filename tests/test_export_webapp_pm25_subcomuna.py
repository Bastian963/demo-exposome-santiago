"""Offline tests for scripts/export_webapp_pm25_subcomuna.py.

No GEE calls: covers the pure grid/geometry logic (axis-step inference,
pixel-rectangle construction, offline reload from an existing export) that
turns sampled point values into the webapp's sub-commune squares. See
docs/resolution_manifest.md Hallazgo 1 — this replaces the synthetic
placeholder that used to ship as ``pm25.geojson``.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import Point

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import export_webapp_pm25_subcomuna as mod  # noqa: E402


class SlugifyTest(unittest.TestCase):
    def test_accents_and_spaces(self) -> None:
        self.assertEqual(mod.slugify("San José de Maipo"), "san_jose_de_maipo")
        self.assertEqual(mod.slugify("Ñuñoa"), "nunoa")


class InferAxisStepTest(unittest.TestCase):
    def test_regular_grid_step(self) -> None:
        import pandas as pd

        lons = np.tile(np.arange(0.0, 0.05, 0.01), 5)
        lats = np.repeat(np.arange(0.0, 0.05, 0.01), 5)
        step = mod._infer_axis_step(pd.Series(lons), pd.Series(lats))
        self.assertAlmostEqual(step, 0.01, places=6)


class PointsToNativeRectanglesTest(unittest.TestCase):
    def test_builds_squares_centered_on_pixels(self) -> None:
        import pandas as pd

        cfg = {"crs": {"geographic": "EPSG:4326"}}
        pixels = pd.DataFrame(
            {
                "name": ["Santiago", "Santiago", "Santiago", "Santiago"],
                "value": [10.0, 12.0, 11.0, 13.0],
                "geometry": [
                    {"type": "Point", "coordinates": [-70.65, -33.45]},
                    {"type": "Point", "coordinates": [-70.64, -33.45]},
                    {"type": "Point", "coordinates": [-70.65, -33.44]},
                    {"type": "Point", "coordinates": [-70.64, -33.44]},
                ],
            }
        )
        rectangles, grid_meta = mod._points_to_native_rectangles(pixels, cfg)

        self.assertEqual(len(rectangles), 4)
        self.assertAlmostEqual(grid_meta["pixel_width_deg"], 0.01, places=6)
        self.assertAlmostEqual(grid_meta["pixel_height_deg"], 0.01, places=6)
        # Each feature is a square polygon, not a point.
        self.assertTrue((rectangles.geometry.geom_type == "Polygon").all())
        # The square for (-70.65, -33.45) must be centered there.
        row = rectangles[rectangles["pixel_id"] == "-70.650000_-33.450000"].iloc[0]
        minx, miny, maxx, maxy = row.geometry.bounds
        self.assertAlmostEqual((minx + maxx) / 2, -70.65, places=6)
        self.assertAlmostEqual((miny + maxy) / 2, -33.45, places=6)

    def test_rejects_non_point_geometry(self) -> None:
        import pandas as pd
        from shapely.geometry import box

        cfg = {"crs": {"geographic": "EPSG:4326"}}
        pixels = pd.DataFrame(
            {
                "name": ["Santiago"],
                "value": [10.0],
                "geometry": [box(0, 0, 1, 1).__geo_interface__],
            }
        )
        with self.assertRaises(RuntimeError):
            mod._points_to_native_rectangles(pixels, cfg)


class OfflineReloadTest(unittest.TestCase):
    def test_pixels_from_existing_geojson_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pm25.geojson"
            payload = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"value": 15.5, "commune_name": "Maipú"},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [[-70.8, -33.5], [-70.79, -33.5], [-70.79, -33.49],
                                 [-70.8, -33.49], [-70.8, -33.5]]
                            ],
                        },
                    }
                ],
            }
            path.write_text(json.dumps(payload), encoding="utf-8")
            df = mod._pixels_from_existing_geojson(path)
            self.assertEqual(len(df), 1)
            self.assertEqual(df.iloc[0]["name"], "Maipú")
            self.assertEqual(df.iloc[0]["value"], 15.5)

    def test_raises_on_empty_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pm25.geojson"
            path.write_text(json.dumps({"type": "FeatureCollection", "features": []}))
            with self.assertRaises(RuntimeError):
                mod._pixels_from_existing_geojson(path)


class IterTilesTest(unittest.TestCase):
    def test_tiles_cover_commune_bounds(self) -> None:
        commune = gpd.GeoDataFrame(
            {"name": ["Maipú"]},
            geometry=[Point(-70.75, -33.5).buffer(0.05)],
            crs="EPSG:4326",
        )
        tiles = mod._iter_tiles(commune, tile_size_m=20_000)
        self.assertGreater(len(tiles), 0)
        self.assertTrue((tiles["commune_name"] == "Maipú").all())
        self.assertTrue((tiles["commune_slug"] == "maipu").all())


if __name__ == "__main__":
    unittest.main()

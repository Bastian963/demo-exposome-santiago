"""Offline tests for the coordinate sampler.

Every raster here is synthesised in a temp dir, so the suite never touches
``data/processed`` and never contacts a provider.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from exposome.point_query import (
    PointQueryError,
    flag_out_of_coverage,
    layer_values,
    native_raster_paths,
    raster_values,
    read_points,
    resolve_layers,
)

# A point inside Santiago, used across the raster tests.
SANTIAGO_LON = -70.65
SANTIAGO_LAT = -33.45


def _write_raster(path: Path, *, crs: str, bands: int = 1, fill: float = 7.0) -> None:
    """Write a small raster covering Santiago in the requested CRS."""
    import rasterio
    from rasterio.transform import from_bounds
    from rasterio.warp import transform_bounds

    west, south, east, north = -70.9, -33.7, -70.4, -33.2
    if crs.upper() != "EPSG:4326":
        west, south, east, north = transform_bounds(
            "EPSG:4326", crs, west, south, east, north
        )
    width = height = 20
    data = np.full((bands, height, width), fill, dtype="float32")
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=bands,
        dtype="float32",
        crs=crs,
        transform=from_bounds(west, south, east, north, width, height),
    ) as dst:
        dst.write(data)


class ReadPointsTest(unittest.TestCase):
    def test_single_coordinate_pair(self) -> None:
        frame = read_points(lon=SANTIAGO_LON, lat=SANTIAGO_LAT)
        self.assertEqual(list(frame.columns), ["query_id", "lon", "lat"])
        self.assertEqual(len(frame), 1)

    def test_requires_some_input(self) -> None:
        with self.assertRaises(PointQueryError):
            read_points()

    def test_rejects_coordinates_outside_wgs84(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "points.csv"
            pd.DataFrame([{"id": "a", "lon": 999.0, "lat": 0.0}]).to_csv(path, index=False)
            with self.assertRaises(PointQueryError):
                read_points(path)

    def test_reports_missing_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "points.csv"
            pd.DataFrame([{"id": "a", "x": 1.0}]).to_csv(path, index=False)
            with self.assertRaises(PointQueryError):
                read_points(path)


class ResolveLayersTest(unittest.TestCase):
    def test_defaults_to_study_layers(self) -> None:
        self.assertEqual(resolve_layers(None, ("alan", "wind")), ("alan", "wind"))

    def test_rejects_unknown_layers(self) -> None:
        with self.assertRaises(PointQueryError):
            resolve_layers("not_a_layer", ("alan",))


class RasterCrsTest(unittest.TestCase):
    """Regression tests for the silent-null bug.

    The previous sampler passed raw WGS84 degrees to ``src.index`` whatever the
    raster CRS was, then read with ``boundless=True, masked=True`` so the
    out-of-grid index came back masked and was reported as a null *value*.
    """

    def _sample(self, crs: str, **kwargs) -> pd.DataFrame:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "layer.tif"
            _write_raster(path, crs=crs, **kwargs)
            points = read_points(lon=SANTIAGO_LON, lat=SANTIAGO_LAT)
            return raster_values(path, points, "layer")

    def test_wgs84_raster_reads_its_value(self) -> None:
        frame = self._sample("EPSG:4326")
        self.assertEqual(frame.loc[0, "layer_band_1"], 7.0)

    def test_web_mercator_raster_reads_its_value(self) -> None:
        # This is the case that used to return None: greenspace_multisource is
        # stored in EPSG:3857 in all eight cities that have it.
        frame = self._sample("EPSG:3857")
        self.assertEqual(frame.loc[0, "layer_band_1"], 7.0)

    def test_utm_raster_reads_its_value(self) -> None:
        # greenspace_coverage is stored in UTM in bogota, medellin,
        # valle_aburra, lima and cdmx.
        frame = self._sample("EPSG:32719")
        self.assertEqual(frame.loc[0, "layer_band_1"], 7.0)

    def test_sinusoidal_raster_reads_its_value(self) -> None:
        # The MODIS grid the wildfire components are exported on.
        sinusoidal = (
            "+proj=sinu +lon_0=0 +x_0=0 +y_0=0 +R=6371007.181 +units=m +no_defs"
        )
        frame = self._sample(sinusoidal)
        self.assertEqual(frame.loc[0, "layer_band_1"], 7.0)

    def test_every_band_is_emitted(self) -> None:
        frame = self._sample("EPSG:3857", bands=3)
        self.assertEqual(
            sorted(frame.columns), ["layer_band_1", "layer_band_2", "layer_band_3"]
        )

    def test_point_outside_the_grid_is_null_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "layer.tif"
            _write_raster(path, crs="EPSG:3857")
            points = read_points(lon=0.0, lat=0.0)
            frame = raster_values(path, points, "layer")
            self.assertIsNone(frame.loc[0, "layer_band_1"])


class ComponentProductTest(unittest.TestCase):
    """wildfire exports one product per component, not ``<layer>_native.tif``."""

    def test_components_resolved_from_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            layer_dir = Path(tmp)
            for component in ("burned_area", "active_fire"):
                _write_raster(layer_dir / f"wildfire_{component}_native.tif", crs="EPSG:4326")
            (layer_dir / "metadata.json").write_text(
                json.dumps({
                    "components": [
                        {"component": "burned_area", "output": "wildfire_burned_area_native.tif"},
                        {"component": "active_fire", "output": "wildfire_active_fire_native.tif"},
                    ]
                })
            )
            resolved = native_raster_paths(layer_dir, "wildfire")
            self.assertEqual(
                sorted(prefix for prefix, _ in resolved),
                ["wildfire_active_fire", "wildfire_burned_area"],
            )

    def test_components_resolved_by_glob_without_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            layer_dir = Path(tmp)
            _write_raster(layer_dir / "wildfire_burned_area_native.tif", crs="EPSG:4326")
            resolved = native_raster_paths(layer_dir, "wildfire")
            self.assertEqual([prefix for prefix, _ in resolved], ["wildfire_burned_area"])

    def test_single_product_layer_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            layer_dir = Path(tmp)
            _write_raster(layer_dir / "alan_native.tif", crs="EPSG:4326")
            resolved = native_raster_paths(layer_dir, "alan")
            self.assertEqual([prefix for prefix, _ in resolved], ["alan"])

    def test_missing_products_resolve_to_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(native_raster_paths(Path(tmp), "alan"), [])


class ClimateDispatchTest(unittest.TestCase):
    """climate_heat must prefer its raster; the node products are a fallback."""

    def test_raster_wins_and_declares_its_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            layer_dir = Path(tmp)
            _write_raster(layer_dir / "climate_heat_native.tif", crs="EPSG:4326", bands=3)
            points = read_points(lon=SANTIAGO_LON, lat=SANTIAGO_LAT)
            values = layer_values(layer_dir, "climate_heat", points)
            self.assertEqual(values.loc[0, "climate_heat_source"], "native_raster")
            self.assertEqual(values.loc[0, "climate_heat_band_1"], 7.0)

    def test_missing_products_raise_rather_than_return_nulls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            points = read_points(lon=SANTIAGO_LON, lat=SANTIAGO_LAT)
            with self.assertRaises(FileNotFoundError):
                layer_values(Path(tmp), "alan", points)


class OutOfCoverageTest(unittest.TestCase):
    def test_outside_points_are_flagged_not_rejected(self) -> None:
        from shapely.geometry import box

        aoi = box(-70.9, -33.7, -70.4, -33.2)
        points = pd.DataFrame([
            {"query_id": "inside", "lon": SANTIAGO_LON, "lat": SANTIAGO_LAT},
            {"query_id": "outside", "lon": 0.0, "lat": 0.0},
        ])
        outside = flag_out_of_coverage(points, aoi)
        self.assertEqual(list(outside), [False, True])


if __name__ == "__main__":
    unittest.main()

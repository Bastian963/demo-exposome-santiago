"""Analytic checks on the area-weighted buffer estimator.

Every raster is synthesised in a temp dir; nothing here reads ``data/processed``
or contacts a provider.
"""
from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from exposome.point_buffer import buffer_weights, sample_band, weighted_stats

SANTIAGO_LON = -70.65
SANTIAGO_LAT = -33.45


def _raster(path: Path, *, crs: str, cell: float, size: int = 200, data=None,
            nodata: float | None = None):
    """A ``size`` x ``size`` raster of ``cell``-sized pixels centred on Santiago."""
    import rasterio
    from rasterio.transform import from_origin
    from rasterio.warp import transform as warp_transform

    xs, ys = warp_transform("EPSG:4326", crs, [SANTIAGO_LON], [SANTIAGO_LAT])
    centre_x, centre_y = xs[0], ys[0]
    west = centre_x - (size / 2) * cell
    north = centre_y + (size / 2) * cell
    if data is None:
        data = np.full((size, size), 5.0, dtype="float32")
    profile = {
        "driver": "GTiff",
        "width": size,
        "height": size,
        "count": 1,
        "dtype": "float32",
        "crs": crs,
        "transform": from_origin(west, north, cell, cell),
    }
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)
    return centre_x, centre_y


class WeightGeometryTest(unittest.TestCase):
    """The weights must sum to the disc's area measured in cells."""

    def test_utm_buffer_area_matches_pi_r_squared(self) -> None:
        # UTM is very close to 1 projected unit per ground metre, so the
        # expected weight is pi*r^2 / cell_area with no correction.
        with tempfile.TemporaryDirectory() as tmp:
            import rasterio

            path = Path(tmp) / "utm.tif"
            x, y = _raster(path, crs="EPSG:32719", cell=100.0)
            with rasterio.open(path) as src:
                weights = buffer_weights(src, x, y, 500.0)
            expected = math.pi * 500.0**2 / 100.0**2
            self.assertAlmostEqual(weights.weights.sum(), expected, delta=expected * 0.01)
            self.assertAlmostEqual(weights.expected_total, expected, delta=expected * 0.01)

    def test_web_mercator_buffer_is_corrected_for_latitude(self) -> None:
        """A Mercator metre is not a ground metre.

        At -33.45 degrees the scale factor is 1/cos(lat) ~ 1.198, so a 500 m
        ground buffer spans ~599 Mercator units.  Treating projected units as
        ground metres would cover 78.5 cells instead of ~112.8 — a 30% error in
        area, and every published detail COG is stored in EPSG:3857.
        """
        with tempfile.TemporaryDirectory() as tmp:
            import rasterio

            path = Path(tmp) / "merc.tif"
            x, y = _raster(path, crs="EPSG:3857", cell=100.0)
            with rasterio.open(path) as src:
                weights = buffer_weights(src, x, y, 500.0)

            naive = math.pi * 500.0**2 / 100.0**2
            corrected = naive / math.cos(math.radians(SANTIAGO_LAT)) ** 2
            self.assertAlmostEqual(weights.weights.sum(), corrected, delta=corrected * 0.02)
            self.assertGreater(weights.weights.sum(), naive * 1.2)

    def test_zero_radius_is_the_containing_cell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            import rasterio

            path = Path(tmp) / "cell.tif"
            x, y = _raster(path, crs="EPSG:3857", cell=100.0)
            with rasterio.open(path) as src:
                weights = buffer_weights(src, x, y, 0.0)
            self.assertEqual(len(weights), 1)
            self.assertEqual(weights.weights[0], 1.0)

    def test_weights_are_fractions_not_all_or_nothing(self) -> None:
        # Edge cells must be partially weighted; that is the whole point of
        # area weighting over a centroid test.
        with tempfile.TemporaryDirectory() as tmp:
            import rasterio

            path = Path(tmp) / "frac.tif"
            x, y = _raster(path, crs="EPSG:32719", cell=100.0)
            with rasterio.open(path) as src:
                weights = buffer_weights(src, x, y, 250.0)
            partial = weights.weights[(weights.weights > 0) & (weights.weights < 1)]
            self.assertGreater(partial.size, 0)
            self.assertLessEqual(weights.weights.max(), 1.0)

    def test_disc_smaller_than_a_cell_keeps_its_full_area(self) -> None:
        """Regression: the window must cover the whole disc.

        Deriving the read window with ``round_offsets(floor).round_lengths
        (ceil)`` floors the offset without extending the length, so a disc that
        straddles a cell boundary loses whatever spills past the rounded
        window.  Measured against a real 1113 m PM2.5 COG, a 300 m buffer
        reported ``coverage_fraction`` 0.21 instead of 1.0 and tripped a false
        ``partial_coverage`` flag on every interior address.
        """
        with tempfile.TemporaryDirectory() as tmp:
            import rasterio
            from rasterio.transform import xy

            path = Path(tmp) / "coarse.tif"
            # 1200 m cells, so a 300 m buffer is well inside a single cell.
            x, y = _raster(path, crs="EPSG:32719", cell=1200.0, size=20)
            with rasterio.open(path) as src:
                # Offset the query so the disc straddles a cell boundary, which
                # is the case the old rounding lost.
                edge_x, edge_y = xy(src.transform, 10, 10, offset="ul")
                for probe in ((x, y), (edge_x + 5.0, edge_y - 5.0)):
                    weights = buffer_weights(src, probe[0], probe[1], 300.0)
                    expected = math.pi * 300.0**2 / 1200.0**2
                    self.assertAlmostEqual(
                        weights.weights.sum(), expected, delta=expected * 0.05
                    )
                    self.assertAlmostEqual(
                        weights.weights.sum() / weights.expected_total, 1.0, delta=0.05
                    )

    def test_buffer_entirely_off_the_raster_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            import rasterio
            from rasterio.warp import transform as warp_transform

            path = Path(tmp) / "off.tif"
            _raster(path, crs="EPSG:32719", cell=100.0, size=20)
            with rasterio.open(path) as src:
                xs, ys = warp_transform("EPSG:4326", src.crs.to_string(), [0.0], [0.0])
                self.assertIsNone(buffer_weights(src, xs[0], ys[0], 500.0))


class WeightedStatsTest(unittest.TestCase):
    def test_uniform_values_have_zero_spread(self) -> None:
        stats = weighted_stats(np.array([4.0, 4.0, 4.0]), np.array([1.0, 0.5, 0.25]))
        self.assertAlmostEqual(stats["value"], 4.0)
        self.assertAlmostEqual(stats["sd"], 0.0)
        self.assertEqual(stats["n_cells"], 3)

    def test_weighted_mean_is_not_the_plain_mean(self) -> None:
        stats = weighted_stats(np.array([0.0, 10.0]), np.array([3.0, 1.0]))
        self.assertAlmostEqual(stats["value"], 2.5)

    def test_population_form_standard_deviation(self) -> None:
        # Equal weights on 2 and 4: mean 3, population sd 1.
        stats = weighted_stats(np.array([2.0, 4.0]), np.array([1.0, 1.0]))
        self.assertAlmostEqual(stats["value"], 3.0)
        self.assertAlmostEqual(stats["sd"], 1.0)

    def test_nodata_lowers_coverage(self) -> None:
        stats = weighted_stats(
            np.array([5.0, np.nan]), np.array([1.0, 1.0]), expected_total=2.0
        )
        self.assertAlmostEqual(stats["value"], 5.0)
        self.assertEqual(stats["n_cells"], 1)
        self.assertAlmostEqual(stats["coverage_fraction"], 0.5)

    def test_all_nodata_yields_no_value(self) -> None:
        stats = weighted_stats(
            np.array([np.nan, np.nan]), np.array([1.0, 1.0]), expected_total=2.0
        )
        self.assertIsNone(stats["value"])
        self.assertIsNone(stats["sd"])
        self.assertEqual(stats["n_cells"], 0)
        self.assertEqual(stats["coverage_fraction"], 0.0)

    def test_coverage_is_clamped(self) -> None:
        stats = weighted_stats(np.array([1.0]), np.array([1.0]), expected_total=0.25)
        self.assertEqual(stats["coverage_fraction"], 1.0)


class SampleBandTest(unittest.TestCase):
    def test_uniform_raster_returns_its_constant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            import rasterio

            path = Path(tmp) / "flat.tif"
            x, y = _raster(path, crs="EPSG:3857", cell=100.0)
            with rasterio.open(path) as src:
                weights = buffer_weights(src, x, y, 500.0)
                stats = sample_band(src, 1, weights)
            self.assertAlmostEqual(stats["value"], 5.0, places=6)
            self.assertAlmostEqual(stats["sd"], 0.0, places=6)
            self.assertAlmostEqual(stats["coverage_fraction"], 1.0, delta=0.02)

    def test_symmetric_gradient_averages_to_the_centre(self) -> None:
        # A linear ramp is symmetric about the query point, so the area-weighted
        # mean must return the centre value even though the cells vary.
        size = 200
        ramp = np.tile(np.arange(size, dtype="float32"), (size, 1))
        with tempfile.TemporaryDirectory() as tmp:
            import rasterio

            path = Path(tmp) / "ramp.tif"
            x, y = _raster(path, crs="EPSG:32719", cell=100.0, size=size, data=ramp)
            with rasterio.open(path) as src:
                weights = buffer_weights(src, x, y, 500.0)
                stats = sample_band(src, 1, weights)
                centre = buffer_weights(src, x, y, 0.0)
                centre_stats = sample_band(src, 1, centre)
            self.assertAlmostEqual(stats["value"], centre_stats["value"], delta=0.5)
            self.assertGreater(stats["sd"], 0.0)

    def test_nodata_reduces_coverage_not_the_mean(self) -> None:
        size = 200
        data = np.full((size, size), 5.0, dtype="float32")
        data[: size // 2, :] = -9999.0
        with tempfile.TemporaryDirectory() as tmp:
            import rasterio

            path = Path(tmp) / "masked.tif"
            x, y = _raster(
                path, crs="EPSG:32719", cell=100.0, size=size, data=data, nodata=-9999.0
            )
            with rasterio.open(path) as src:
                weights = buffer_weights(src, x, y, 500.0)
                stats = sample_band(src, 1, weights)
            self.assertAlmostEqual(stats["value"], 5.0, places=6)
            self.assertLess(stats["coverage_fraction"], 0.75)
            self.assertGreater(stats["coverage_fraction"], 0.25)


if __name__ == "__main__":
    unittest.main()

"""Area-weighted sampling of a raster over a neighbourhood.

The estimand is the average of the indicator over ``B(x, r)`` — the containing
cell when ``r = 0``, otherwise the disc of radius ``r`` (ADR 0012 §1):

    v(x, r) = sum(w_i * v_i) / sum(w_i),   w_i = area(cell_i and B(x, r))

Area weights, not "cells whose centroid falls inside", because the latter is
biased whenever ``r`` is comparable to the cell size — which is the regime
almost every layer in this catalog operates in.

Nothing here interpolates.  The weights are computed by rasterizing *only the
mask* of the disc on a subsampled grid, which measures fractional coverage; the
data is never resampled (ADR 0004 §5).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

WGS84 = "EPSG:4326"

#: Each cell is split into ``SUBSAMPLE**2`` test points to estimate the
#: fraction of its area inside the disc.  10 gives ~1% resolution on a single
#: cell's weight, well below the uncertainty of anything downstream.
SUBSAMPLE = 10

#: Segments per quarter circle when polygonising the disc.  64 keeps the
#: polygon's area within ~1e-5 of the true circle.
QUAD_SEGMENTS = 64


@dataclass(frozen=True)
class BufferWeights:
    """Fractional cell weights for one point/radius over one raster."""

    rows: np.ndarray
    cols: np.ndarray
    weights: np.ndarray
    #: Total weight the disc *would* have if the raster covered all of it,
    #: expressed in the same cell-fraction units as ``weights``.
    expected_total: float

    def __len__(self) -> int:
        return int(self.weights.size)


def local_scale(transformer_to_geodetic, x: float, y: float, *, step: float = 1.0
                ) -> tuple[float, float]:
    """Projected units per ground metre at ``(x, y)``, per axis.

    Derived numerically instead of per-CRS special cases, so EPSG:3857, UTM and
    MODIS Sinusoidal are all handled by the same code.  It matters: a Web
    Mercator metre is ``cos(latitude)`` ground metres, so at Santiago a 500 m
    buffer is ~600 projected units.  Treating them as equal would shrink every
    buffer by ~17%.

    Two axes are returned because equal-area projections are not conformal; for
    conformal ones (Mercator, UTM) the two values agree.
    """
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    lon0, lat0 = transformer_to_geodetic.transform(x, y)
    lon_x, lat_x = transformer_to_geodetic.transform(x + step, y)
    lon_y, lat_y = transformer_to_geodetic.transform(x, y + step)
    _, _, ground_x = geod.inv(lon0, lat0, lon_x, lat_x)
    _, _, ground_y = geod.inv(lon0, lat0, lon_y, lat_y)
    scale_x = step / ground_x if ground_x else 1.0
    scale_y = step / ground_y if ground_y else 1.0
    return float(scale_x), float(scale_y)


def _disc(x: float, y: float, semi_x: float, semi_y: float):
    """The neighbourhood as a polygon in the raster's own coordinates.

    A ground-distance disc is an ellipse in projected coordinates whenever the
    two axis scales differ, and in geographic coordinates always (a degree of
    longitude shrinks by ``cos(latitude)``).
    """
    from shapely.affinity import scale
    from shapely.geometry import Point

    unit = Point(x, y).buffer(1.0, quad_segs=QUAD_SEGMENTS)
    return scale(unit, xfact=semi_x, yfact=semi_y, origin=(x, y))


def buffer_weights(src, x: float, y: float, radius_m: float, *,
                   subsample: int = SUBSAMPLE) -> BufferWeights | None:
    """Fractional area weights of every cell of ``src`` inside ``B((x, y), r)``.

    ``x``/``y`` are already in the raster's CRS.  Returns ``None`` when the
    neighbourhood misses the raster entirely.
    """
    from pyproj import CRS, Transformer
    from rasterio import features, windows
    from rasterio.transform import from_bounds

    if radius_m <= 0:
        row, col = src.index(x, y)
        if not (0 <= row < src.height and 0 <= col < src.width):
            return None
        return BufferWeights(
            rows=np.array([int(row)]),
            cols=np.array([int(col)]),
            weights=np.array([1.0]),
            expected_total=1.0,
        )

    to_geodetic = Transformer.from_crs(
        src.crs if src.crs is not None else CRS.from_string(WGS84),
        CRS.from_string(WGS84),
        always_xy=True,
    )
    scale_x, scale_y = local_scale(to_geodetic, x, y)
    semi_x = radius_m * scale_x
    semi_y = radius_m * scale_y
    disc = _disc(x, y, semi_x, semi_y)

    cell_width = abs(src.transform.a)
    cell_height = abs(src.transform.e)
    expected_total = (math.pi * semi_x * semi_y) / (cell_width * cell_height)

    # Derive the window from the disc's corners directly.  Going through
    # ``round_offsets(floor).round_lengths(ceil)`` floors the offset without
    # extending the length to compensate, so a disc straddling a cell boundary
    # loses whatever spills past the rounded window -- which for a buffer
    # smaller than one cell can be most of it.
    minx, miny, maxx, maxy = disc.bounds
    row_start, col_start = src.index(minx, maxy, op=math.floor)
    row_stop, col_stop = src.index(maxx, miny, op=math.ceil)
    window = windows.Window(
        col_off=int(col_start),
        row_off=int(row_start),
        width=max(int(col_stop) - int(col_start), 1),
        height=max(int(row_stop) - int(row_start), 1),
    )
    try:
        # rasterio raises rather than returning a zero-size window when the two
        # do not overlap, which is the ordinary case for a point outside the AOI.
        clipped = window.intersection(windows.Window(0, 0, src.width, src.height))
    except windows.WindowError:
        return None
    if clipped.width <= 0 or clipped.height <= 0:
        return None

    # A disc much smaller than a cell needs a finer test grid or its area is
    # quantised away.  Keep at least ~16 test points across the short axis.
    shortest = 2 * min(semi_x / cell_width, semi_y / cell_height)
    if shortest > 0:
        subsample = int(min(max(subsample, math.ceil(16 / shortest)), 64))

    height = int(clipped.height)
    width = int(clipped.width)
    bounds = windows.bounds(clipped, src.transform)
    fine_transform = from_bounds(*bounds, width * subsample, height * subsample)
    mask = features.rasterize(
        [(disc, 1)],
        out_shape=(height * subsample, width * subsample),
        transform=fine_transform,
        fill=0,
        dtype="uint8",
        all_touched=False,
    )
    fractions = mask.reshape(height, subsample, width, subsample).mean(axis=(1, 3))

    local_rows, local_cols = np.nonzero(fractions)
    if local_rows.size == 0:
        return None
    return BufferWeights(
        rows=local_rows + int(clipped.row_off),
        cols=local_cols + int(clipped.col_off),
        weights=fractions[local_rows, local_cols].astype(float),
        expected_total=float(expected_total),
    )


def weighted_stats(values: np.ndarray, weights: np.ndarray, *,
                   expected_total: float | None = None) -> dict[str, Any]:
    """Weighted mean, spread and coverage over the contributing cells.

    ``sd`` is the population-form weighted standard deviation.  The weights are
    area fractions, not sampling weights: the quantity being described is the
    actual variation inside this neighbourhood, so no ``n-1`` style correction
    applies.

    ``coverage_fraction`` divides the valid weight by the weight the
    neighbourhood *should* have had, so a buffer half over the sea or off the
    edge of a city reports 0.5 rather than silently averaging what remains.
    """
    values = np.asarray(values, dtype="float64")
    weights = np.asarray(weights, dtype="float64")
    valid = np.isfinite(values) & (weights > 0)

    total_weight = float(weights[valid].sum())
    denominator = expected_total if expected_total else float(weights.sum())
    coverage = (total_weight / denominator) if denominator else 0.0

    if total_weight <= 0:
        return {
            "value": None,
            "sd": None,
            "n_cells": 0,
            "coverage_fraction": 0.0,
        }

    subset_values = values[valid]
    subset_weights = weights[valid]
    mean = float((subset_values * subset_weights).sum() / total_weight)
    variance = float((subset_weights * (subset_values - mean) ** 2).sum() / total_weight)
    return {
        "value": mean,
        "sd": math.sqrt(max(variance, 0.0)),
        "n_cells": int(valid.sum()),
        # A disc can overhang the raster, so clamp instead of reporting >1.
        "coverage_fraction": float(min(coverage, 1.0)),
    }


def sample_band(src, band: int, weights: BufferWeights) -> dict[str, Any]:
    """Read one band over the weighted cells and reduce it."""
    from rasterio.windows import Window

    row_min = int(weights.rows.min())
    row_max = int(weights.rows.max())
    col_min = int(weights.cols.min())
    col_max = int(weights.cols.max())
    window = Window(col_min, row_min, col_max - col_min + 1, row_max - row_min + 1)
    block = src.read(band, window=window, masked=True)
    values = block[weights.rows - row_min, weights.cols - col_min]
    filled = np.where(np.ma.getmaskarray(values), np.nan, np.ma.getdata(values))
    return weighted_stats(filled, weights.weights, expected_total=weights.expected_total)

"""Stable, AOI-wide metric grids for vector-access indicators.

The grid origin is the metric CRS origin, not an administrative polygon.  A
change in commune boundaries can therefore only change intersection weights;
it cannot change the cells at which OSM/network metrics are evaluated.
"""
from __future__ import annotations

from typing import Iterable

import geopandas as gpd
import pandas as pd

from .spatial_detail import build_aligned_metric_grid


def build_study_access_grid(
    spatial_units: gpd.GeoDataFrame,
    *,
    spacing_m: float = 1000,
    metric_crs: str,
) -> gpd.GeoDataFrame:
    """Return clipped AOI cells with stable ids and full-cell sample centres."""
    cells = build_aligned_metric_grid(spatial_units, spacing_m=spacing_m, metric_crs=metric_crs)
    cells = cells.copy()
    cells["cell_area_m2"] = cells["sample_geometry"].map(lambda geometry: geometry.area)
    cells["covered_area_m2"] = cells.geometry.area
    cells["sample_point"] = cells["sample_geometry"].map(
        lambda geometry: geometry.representative_point()
    )
    return cells


def intersect_grid_with_units(
    grid: gpd.GeoDataFrame,
    spatial_units: gpd.GeoDataFrame,
    *,
    name_column: str = "name",
) -> gpd.GeoDataFrame:
    """Map each stable cell to units with area-fraction weights.

    This intentionally retains every intersection, including tiny units.  It
    has no point fallback and is invariant to splitting/dissolving units.
    """
    resolved_name = name_column
    if resolved_name not in spatial_units.columns and "spatial_name" in spatial_units.columns:
        resolved_name = "spatial_name"
    units = spatial_units[[resolved_name, "geometry"]].to_crs(grid.crs).copy()
    if resolved_name != name_column:
        units = units.rename(columns={resolved_name: name_column})
    cells = grid[["cell_id", "cell_area_m2", "geometry"]].copy()
    result = gpd.overlay(cells, units, how="intersection", keep_geom_type=True)
    if result.empty:
        return result
    result["intersection_area_m2"] = result.geometry.area
    result["cell_weight"] = result["intersection_area_m2"] / result["cell_area_m2"]
    return result


def area_weighted_unit_mean(
    grid_values: pd.DataFrame,
    intersections: gpd.GeoDataFrame,
    value_columns: Iterable[str],
    *,
    name_column: str = "name",
) -> pd.DataFrame:
    """Aggregate cell metrics to administrative units by intersection area."""
    columns = list(value_columns)
    joined = intersections.drop(columns="geometry").merge(grid_values[["cell_id", *columns]], on="cell_id", how="left")
    rows = []
    for name, group in joined.groupby(name_column, dropna=False):
        weights = group["intersection_area_m2"]
        rows.append({
            name_column: name,
            **{column: float((group[column] * weights).sum() / weights.sum()) for column in columns},
            "n_access_grid": int(group["cell_id"].nunique()),
        })
    return pd.DataFrame(rows)

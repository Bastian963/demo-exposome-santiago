"""Handle Chilean postal codes (ZIP codes) for exposome assignment.

Chilean postal codes (códigos postales) are 7-digit numeric codes.
They are not as granular as US ZIP codes; a single code may cover
a neighborhood or several city blocks.

Since we don't have a national polygon dataset, we support:
1. Geocoding a list of postal codes to lat/lon (using a reference table)
2. Creating a prediction grid and assigning postal codes by proximity
3. Using communes as fallback when postal codes are unavailable
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point


def load_postal_code_reference(path: Path) -> pd.DataFrame:
    """Load a reference table of postal codes with lat/lon.

    Expected columns: zipcode, city, commune, lat, lon
    """
    df = pd.read_csv(path)
    return df


def postal_codes_to_gdf(df: pd.DataFrame) -> gpd.GeoDataFrame:
    """Convert postal code reference to GeoDataFrame."""
    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
        crs="EPSG:4326",
    )
    return gdf


def assign_grid_to_postal_codes(
    grid_gdf: gpd.GeoDataFrame,
    postal_gdf: gpd.GeoDataFrame,
    buffer_m: int = 2_000,
) -> gpd.GeoDataFrame:
    """Assign grid cells to nearest postal code within a buffer.

    Returns grid_gdf with added postal_code column.
    """
    # Reproject to metric for distance calculation
    grid_m = grid_gdf.to_crs("EPSG:32719")
    postal_m = postal_gdf.to_crs("EPSG:32719")

    # Spatial join: nearest within buffer
    joined = grid_m.sjoin_nearest(
        postal_m[["zipcode", "geometry"]],
        how="left",
        max_distance=buffer_m,
    )

    grid_gdf = grid_gdf.copy()
    grid_gdf["zipcode"] = joined["zipcode"].values
    return grid_gdf


def aggregate_predictions_to_postal_codes(
    grid_predictions: pd.DataFrame,
    grid_gdf: gpd.GeoDataFrame,
    agg_cols: list[str] | None = None,
) -> pd.DataFrame:
    """Aggregate grid-cell predictions to postal-code level.

    Parameters
    ----------
    grid_predictions : pd.DataFrame
        Long-format with grid_id, date, {predicted vars}
    grid_gdf : gpd.GeoDataFrame
        Grid cells with grid_id and assigned zipcode
    agg_cols : list[str] | None
        Columns to aggregate (e.g., ["tmax_pred", "tmin_pred"])

    Returns
    -------
    pd.DataFrame
        Long-format with zipcode, date, mean predictions
    """
    if agg_cols is None:
        agg_cols = [c for c in grid_predictions.columns if c not in ["grid_id", "date"]]

    merged = grid_predictions.merge(grid_gdf[["grid_id", "zipcode"]], on="grid_id", how="left")
    merged = merged.dropna(subset=["zipcode"])

    grouped = merged.groupby(["zipcode", "date"])[agg_cols].mean().reset_index()
    return grouped

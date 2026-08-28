"""Statistical downscaling of ERA5-Land to ~1 km using satellite + covariates.

Trains a LightGBM or Random Forest model using:
- Target: DMC/SINCA station observations (Tmax, Tmin)
- Predictors: ERA5-Land interpolated + elevation + land cover + NDVI + MODIS LST

Applies the model to a 1 km prediction grid and averages to zip-code level.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd


def build_prediction_grid(
    bbox: dict[str, float],
    resolution_m: int = 1_000,
    crs: str = "EPSG:32719",
) -> gpd.GeoDataFrame:
    """Create a regular fishnet grid over the study area.

    Returns a GeoDataFrame with grid cell geometries and centroid coordinates.
    """
    # TODO: implement fishnet generation
    raise NotImplementedError("Implement fishnet grid")


def extract_covariates(
    grid: gpd.GeoDataFrame,
    cfg: dict[str, Any],
) -> gpd.GeoDataFrame:
    """Extract spatial covariates for each grid cell.

    Covariates:
    - elevation (SRTM/ETOPO1 via GEE)
    - % built-up, % tree, % water (ESA WorldCover)
    - mean NDVI (Sentinel-2)
    - MODIS LST day/night mean (summer)
    - distance to city center
    - lat/lon
    """
    # TODO: implement GEE extraction of covariates
    raise NotImplementedError("Implement covariate extraction")


def train_downscaling_model(
    station_df: pd.DataFrame,
    predictor_df: pd.DataFrame,
    target_col: str = "tmax",
    model_type: str = "lightgbm",
) -> Any:
    """Train a downscaling model.

    Parameters
    ----------
    station_df : pd.DataFrame
        Station observations with lat/lon/date/target.
    predictor_df : pd.DataFrame
        Same rows with predictor columns from ERA5-Land + covariates.
    target_col : str
        "tmax" or "tmin".
    model_type : str
        "lightgbm" or "random_forest".

    Returns
    -------
    Trained model object (fitted sklearn or lightgbm regressor).
    """
    # TODO: implement model training with CV
    raise NotImplementedError("Implement model training")


def predict_grid_daily(
    model: Any,
    grid_covariates: pd.DataFrame,
    era5land_daily: pd.DataFrame,
) -> pd.DataFrame:
    """Apply trained model to predict daily temperature at grid cells.

    Returns long-format DataFrame: grid_id, date, tmax_pred, tmin_pred.
    """
    # TODO: merge covariates + ERA5-Land, predict, return
    raise NotImplementedError("Implement grid prediction")


def aggregate_to_zipcodes(
    grid_predictions: pd.DataFrame,
    zipcodes_gdf: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Average grid-cell predictions to zip-code level.

    Uses area-weighted or simple mean of cells intersecting each zip code.
    """
    # TODO: spatial join + groupby
    raise NotImplementedError("Implement zip-code aggregation")

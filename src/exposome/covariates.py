"""Extract spatial covariates for downscaling model.

Sources:
- Elevation: SRTM / NASADEM via GEE
- Land cover: ESA WorldCover 2021
- Greenness: Sentinel-2 NDVI
- Urban form: distance to city center, impervious proxy
"""
from __future__ import annotations

from typing import Any

import ee
import geopandas as gpd
import pandas as pd

from .. import gee

ESA_WORLDCOVER = "ESA/WorldCover/v200"
SRTM = "USGS/SRTMGL1_003"
NASADEM = "NASA/NASADEM_HGT/001"


def fetch_elevation(
    regions_fc: ee.FeatureCollection,
    scale: int = 30,
) -> pd.DataFrame:
    """Fetch mean elevation per region from NASADEM."""
    img = ee.Image(NASADEM).select("elevation")
    stats = gee.image_to_stats(img, regions_fc, band="elevation", scale=scale, reducer="mean")
    rows = gee.fc_to_dicts(stats)
    df = pd.DataFrame(rows)
    if "mean" in df.columns:
        df = df.rename(columns={"mean": "elevation_m"})
    return df


def fetch_landcover_fractions(
    regions_fc: ee.FeatureCollection,
    scale: int = 10,
) -> pd.DataFrame:
    """Calculate built-up, tree, and water fraction per region from ESA WorldCover.

    ESA WorldCover classes:
    50 = Built-up
    10 = Tree cover
    80 = Permanent water bodies
    """
    wc = ee.Image(ESA_WORLDCOVER).select("Map")

    built = wc.eq(50).rename("built_up")
    tree = wc.eq(10).rename("tree_cover")
    water = wc.eq(80).rename("water")

    fractions = ee.Image([built, tree, water]).float()

    stats = fractions.reduceRegions(
        collection=regions_fc,
        reducer=ee.Reducer.mean(),
        scale=scale,
        crs="EPSG:4326",
    )
    rows = gee.fc_to_dicts(stats)
    df = pd.DataFrame(rows)
    return df


def extract_covariates_for_regions(
    regions_gdf: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Extract all spatial covariates for a set of regions.

    Returns DataFrame with columns:
    name, elevation_m, built_up_fraction, tree_cover_fraction, water_fraction,
    centroid_lat, centroid_lon
    """
    gee.init_gee()
    regions_fc = gee.gdf_to_feature_collection(regions_gdf)

    df_elev = fetch_elevation(regions_fc, scale=30)
    df_lc = fetch_landcover_fractions(regions_fc, scale=10)

    # Centroids
    centroids = regions_gdf.to_crs("EPSG:4326").geometry.centroid
    df_cent = pd.DataFrame({
        "name": regions_gdf["name"],
        "centroid_lat": centroids.y,
        "centroid_lon": centroids.x,
    })

    df = df_elev.merge(df_lc, on="name", how="outer")
    df = df.merge(df_cent, on="name", how="outer")
    return df

"""Google Earth Engine helpers."""
from __future__ import annotations

import math
from numbers import Real
from typing import Any

import ee
import geopandas as gpd
import pandas as pd


# Earth Engine's noncommercial "Restricted Mode" (entered once the free compute
# quota is exceeded) caps concurrent compute requests to a very low number.
# geedim's defaults (max_requests=32, auto num_threads) burst past that ceiling,
# so multi-tile downloads die mid-stream with "Too Many Requests: Exceeded Earth
# Engine concurrency limit" -- greenspace_coverage's 84-tile export failed
# reproducibly at ~17 tiles (Lima native, 2026-07-22). Single-tile layers
# (pm25/alan/NO2/wildfire) survive because they issue one request. Serializing to
# one in-flight request keeps multi-tile exports under the ceiling -- the exact
# concurrency the single-tile layers already prove Restricted Mode serves. These
# must be forwarded to every geemap.download_ee_image call: num_threads is an
# explicit geemap param and max_requests rides **kwargs into geedim.download.
EE_DOWNLOAD_NUM_THREADS = 1
EE_DOWNLOAD_MAX_REQUESTS = 1


def init_gee(project: str = "exposome-api") -> None:
    """Initialise Earth Engine with the given project."""
    try:
        ee.Initialize(project=project)
    except Exception:
        # Fallback: try without explicit project (uses default credentials)
        ee.Initialize()


def gdf_to_feature_collection(gdf: gpd.GeoDataFrame) -> ee.FeatureCollection:
    """Convert a GeoDataFrame to an EE FeatureCollection."""
    # Use GeoJSON dicts as intermediate
    features = []
    for _, row in gdf.iterrows():
        geom = row.geometry.__geo_interface__
        # JSON has no NaN literal. Mixed administrative sources (e.g. AMBA
        # partidos + CABA comunas) legitimately leave some source columns
        # empty; never serialize those values into an Earth Engine request.
        props = {}
        for key, value in row.items():
            if key == "geometry" or value is None:
                continue
            if isinstance(value, Real) and not math.isfinite(value):
                continue
            try:
                if bool(pd.isna(value)):
                    continue
            except (TypeError, ValueError):
                # Arrays/lists are valid EE properties; their missing-value
                # handling is delegated to Earth Engine.
                pass
            props[key] = value
        features.append(ee.Feature(geom, props))
    return ee.FeatureCollection(features)


def image_to_stats(
    image: ee.Image,
    regions: ee.FeatureCollection,
    band: str,
    scale: int,
    reducer: str = "mean",
) -> ee.FeatureCollection:
    """Run zonal stats of *image* over *regions*.

    reducer: one of "mean", "median", "stdDev", "min", "max", "sum".
    """
    red = getattr(ee.Reducer, reducer)()
    stats = image.select(band).reduceRegions(
        collection=regions,
        reducer=red,
        scale=scale,
        crs="EPSG:4326",
        tileScale=4,
    )
    return stats


def fc_to_dicts(fc: ee.FeatureCollection) -> list[dict[str, Any]]:
    """Download an EE FeatureCollection to a list of plain dicts."""
    info = fc.getInfo()
    rows = []
    for feat in info.get("features", []):
        props = feat.get("properties", {})
        props["geometry"] = feat.get("geometry")
        rows.append(props)
    return rows

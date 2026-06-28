"""Google Earth Engine helpers."""
from __future__ import annotations

from typing import Any

import ee
import geopandas as gpd


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
        props = {k: v for k, v in row.items() if k != "geometry" and v is not None}
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

    reducer: one of "mean", "median", "stdDev", "min", "max".
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

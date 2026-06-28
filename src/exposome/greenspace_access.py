"""Greenspace accessibility exposome layer from OpenStreetMap.

Produces commune-level indicators of green-space accessibility:
- area and percentage of mapped green space (parks, gardens, etc.)
- number of distinct green-space polygons
- straight-line distance to the nearest green space
- green area and polygon count within 300 m, 500 m and 1000 m buffers

All geometric operations are performed in the configured metric CRS to avoid
warnings and inaccuracies from using a geographic CRS.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import osmnx as ox
import pandas as pd

from . import boundaries, config


def _download_osm_green(
    region: str,
    tags: dict[str, list[str]],
    max_retries: int = 2,
) -> gpd.GeoDataFrame:
    """Download OSM green-area features, with a short retry loop."""
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            gdf = ox.features_from_place(region, tags=tags)
            return gdf
        except Exception as err:  # noqa: BLE001
            last_err = err
            if attempt < max_retries:
                ox.utils.log(f"OSM download attempt {attempt + 1} failed, retrying...")
    raise ConnectionError(
        f"Failed to download OSM green areas after {max_retries + 1} attempts"
    ) from last_err


def fetch_green_areas(
    cfg: dict[str, Any],
    cache_path: Path | None = None,
) -> gpd.GeoDataFrame:
    """Fetch green-area polygons from OSM or load a cached GeoJSON."""
    if cache_path and cache_path.exists():
        gdf = gpd.read_file(cache_path)
        if len(gdf) > 0:
            return gdf

    ox.settings.requests_timeout = 300
    tags = cfg["greenspace"]["access"]["osm_tags"]
    gdf = _download_osm_green(cfg["region_query"], tags)

    # Keep only polygonal geometries
    gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy().reset_index(drop=True)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

    # Repair invalid geometries
    gdf["geometry"] = gdf.geometry.buffer(0)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

    # Keep a small set of useful columns
    keep_cols = ["geometry", "name", "leisure", "landuse"]
    available = [c for c in keep_cols if c in gdf.columns]
    gdf = gdf[available].copy()

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        gdf_wgs = gdf.to_crs(cfg["crs"]["geographic"]) if gdf.crs else gdf
        gdf_wgs.to_file(cache_path, driver="GeoJSON")

    return gdf


def compute_green_coverage(
    communes: gpd.GeoDataFrame,
    green_areas: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """Compute green area, percentage and count per commune."""
    metric_crs = communes.crs
    green_metric = green_areas.to_crs(metric_crs)

    # Deduplicate overlapping green polygons
    green_union = green_metric.geometry.union_all().buffer(0)

    result = communes[["name", "area_km2", "geometry"]].copy()
    result["green_osm_km2"] = (
        result.geometry.intersection(green_union).area / 1e6
    )
    result["green_osm_pct"] = (
        result["green_osm_km2"] / result["area_km2"] * 100
    )

    # Count green polygons whose representative point falls inside each commune
    pts = green_metric.copy()
    pts["geometry"] = pts.geometry.representative_point()
    joined = gpd.sjoin(
        pts[["geometry"]],
        result[["name", "geometry"]],
        how="inner",
        predicate="within",
    )
    counts = joined.groupby("name").size().rename("green_osm_n")
    result = result.merge(counts, on="name", how="left")
    result["green_osm_n"] = result["green_osm_n"].fillna(0).astype(int)

    return result


def compute_access_metrics(
    communes: gpd.GeoDataFrame,
    green_areas: gpd.GeoDataFrame,
    buffers_m: list[int],
) -> gpd.GeoDataFrame:
    """Compute distance and buffer-based accessibility metrics per commune."""
    metric_crs = communes.crs
    green_metric = green_areas.to_crs(metric_crs)

    # Representative points of green areas for distance calculations
    green_pts = green_metric.copy()
    green_pts["geometry"] = green_pts.geometry.representative_point()

    # Distance from commune centroid to nearest green point
    result = communes[["name", "geometry"]].copy()
    centroids = result.copy()
    centroids["geometry"] = centroids.geometry.centroid

    nearest = gpd.sjoin_nearest(
        centroids,
        green_pts[["geometry"]],
        how="left",
        distance_col="dist_to_nearest_park_m",
    )
    nearest = nearest.groupby("name")["dist_to_nearest_park_m"].min().reset_index()
    result = result.merge(nearest, on="name", how="left")

    # Buffer-based metrics: approximate by including whole green polygons whose
    # representative point lies inside the commune buffer. This is much faster
    # than exact polygon clipping and is consistent across communes.
    for buf in buffers_m:
        buffered = result[["name", "geometry"]].copy()
        buffered["geometry"] = buffered.geometry.buffer(buf)

        # Count green points inside buffer
        joined_count = gpd.sjoin(
            green_pts,
            buffered,
            how="inner",
            predicate="within",
        )
        name_col = "name" if "name" in joined_count.columns else "name_right"
        count_by_commune = (
            joined_count.groupby(name_col)
            .size()
            .reset_index(name=f"green_count_within_{buf}m")
            .rename(columns={name_col: "name"})
        )

        # Sum area of green polygons whose representative point is inside buffer
        joined_area = gpd.sjoin(
            green_metric[["geometry"]],
            buffered,
            how="inner",
            predicate="within",
        )
        name_col = "name" if "name" in joined_area.columns else "name_right"
        area_by_commune = (
            (joined_area.geometry.area.groupby(joined_area[name_col]).sum() / 1e6)
            .reset_index(name=f"green_area_within_{buf}m_km2")
            .rename(columns={name_col: "name"})
        )

        result = result.merge(count_by_commune, on="name", how="left")
        result = result.merge(area_by_commune, on="name", how="left")
        result[f"green_count_within_{buf}m"] = (
            result[f"green_count_within_{buf}m"].fillna(0).astype(int)
        )
        result[f"green_area_within_{buf}m_km2"] = (
            result[f"green_area_within_{buf}m_km2"].fillna(0)
        )

    return result


def build_greenspace_access_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> tuple[Path, Path]:
    """Build the greenspace accessibility layer and write CSV + GeoJSON."""
    cfg = config.load_config(city)
    cache_dir = Path(cache_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"Building greenspace access layer for {city}")

    # Load or fetch commune boundaries and reproject to metric CRS
    cache_path = cache_dir / f"{city}_communes.geojson"
    communes = boundaries.get_communes(cfg, cache_path=cache_path)
    metric_crs = cfg["crs"]["metric"]
    communes_metric = communes.to_crs(metric_crs)

    # Fetch OSM green areas
    green_cache = cache_dir / f"{city}_greenspace_osm.geojson"
    print("Fetching green areas from OpenStreetMap...")
    green_areas = fetch_green_areas(cfg, cache_path=green_cache)
    print(f"  {len(green_areas)} green-area polygons")

    # Compute coverage and access metrics
    print("Computing green coverage per commune...")
    coverage = compute_green_coverage(communes_metric, green_areas)

    buffers_m = cfg["greenspace"]["access"]["buffers_m"]
    print(f"Computing accessibility metrics (buffers {buffers_m} m)...")
    access = compute_access_metrics(communes_metric, green_areas, buffers_m)

    # Merge coverage and access
    result = coverage.merge(
        access[["name", "dist_to_nearest_park_m"] +
              [f"green_area_within_{b}m_km2" for b in buffers_m] +
              [f"green_count_within_{b}m" for b in buffers_m]],
        on="name",
        how="left",
    )

    # Round and cast
    result["green_osm_km2"] = result["green_osm_km2"].round(3)
    result["green_osm_pct"] = result["green_osm_pct"].round(2)
    # Sentinel value for communes with no OSM green areas (documented in metadata)
    result["dist_to_nearest_park_m"] = result["dist_to_nearest_park_m"].fillna(99999).round(0).astype(int)
    for b in buffers_m:
        result[f"green_area_within_{b}m_km2"] = result[f"green_area_within_{b}m_km2"].round(3)
        result[f"green_count_within_{b}m"] = result[f"green_count_within_{b}m"].astype(int)

    # Validate output
    expected = cfg["expected_communes"]
    if len(result) != expected:
        raise ValueError(f"Expected {expected} communes, got {len(result)}")
    if result["name"].duplicated().any():
        dupes = result.loc[result["name"].duplicated(), "name"].tolist()
        raise ValueError(f"Duplicate commune names: {dupes}")
    numeric_cols = [c for c in result.columns if c not in ("name", "geometry")]
    if result[numeric_cols].isna().any().any():
        missing = result[numeric_cols].columns[result[numeric_cols].isna().any()].tolist()
        raise ValueError(f"Missing values in output columns: {missing}")

    # Convert back to geographic CRS for output
    result_geo = result.to_crs(cfg["crs"]["geographic"])

    # Output file names
    base_name = f"{city}_greenspace_access"
    csv_path = out_dir / f"{base_name}.csv"
    geojson_path = out_dir / f"{base_name}.geojson"

    # CSV without geometry
    result.drop(columns="geometry").to_csv(csv_path, index=False)
    result_geo.to_file(geojson_path, driver="GeoJSON")

    # Metadata
    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "n_communes": int(len(result)),
        "n_green_polygons": int(len(green_areas)),
        "buffers_m": buffers_m,
        "buffer_area_method": "whole_polygon_by_repr_point",
        "source": "OpenStreetMap",
        "outputs": [csv_path.name, geojson_path.name],
    }
    (out_dir / f"{base_name}_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )

    print(f"Wrote {csv_path.name}: {len(result)} rows x {result.drop(columns='geometry').shape[1]} columns")
    print(f"Wrote {geojson_path.name}")

    return csv_path, geojson_path

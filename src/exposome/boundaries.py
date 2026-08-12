"""Download and cache administrative boundaries from OpenStreetMap."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import osmnx as ox
from shapely.geometry import Point


def get_communes(cfg: dict[str, Any], cache_path: Path | None = None) -> gpd.GeoDataFrame:
    """Fetch communes (admin_level=8) for the configured region from OSM.

    Falls back to existing processed GeoJSONs in data/processed/ if available,
    to avoid slow re-downloads.

    Returns a GeoDataFrame with columns: name, geometry, area_km2.
    Validates the expected commune count.
    """
    expected = int(cfg.get("expected_units", cfg.get("expected_communes", 0)))
    if cache_path and cache_path.exists():
        gdf = gpd.read_file(cache_path)
        if len(gdf) == expected and "name" in gdf.columns:
            if "area_km2" not in gdf.columns:
                metric = gdf.to_crs(cfg["crs"]["metric"])
                gdf["area_km2"] = metric.geometry.area / 1e6
            return gdf

    spatial_cfg = cfg.get("spatial_units")
    if isinstance(spatial_cfg, dict):
        from .spatial import normalize_spatial_units

        source = Path(spatial_cfg["path"])
        read_options = {}
        if spatial_cfg.get("layer"):
            read_options["layer"] = spatial_cfg["layer"]
        raw = gpd.read_file(source, **read_options)
        units = normalize_spatial_units(
            raw,
            id_column=spatial_cfg["id_column"],
            name_column=spatial_cfg.get("name_column"),
            expected_units=spatial_cfg.get("expected_units"),
            geographic_crs=cfg["crs"]["geographic"],
            metric_crs=cfg["crs"]["metric"],
            source_path=source,
        )
        units["name"] = units["spatial_name"].astype(str)
        if units["name"].duplicated().any():
            units["name"] = units["spatial_id"].astype(str)
        out = units[
            ["spatial_id", "spatial_name", "name", "geometry", "area_km2"]
        ].copy()
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            out.to_file(cache_path, driver="GeoJSON")
        return out

    # Try existing processed outputs first (fast path)
    repo_root = Path(__file__).resolve().parents[2]
    processed = repo_root / "data" / "processed"
    for candidate in [
        "socioeconomic_exposome_rm_santiago.geojson",
        "climate_heat_exposome_rm_santiago.geojson",
        "air_quality_exposome_rm_santiago.geojson",
    ]:
        p = processed / candidate
        if p.exists():
            gdf = gpd.read_file(p)
            if "name" in gdf.columns and len(gdf) == expected:
                gdf = gdf[["name", "geometry"]].copy()
                metric = gdf.to_crs(cfg["crs"]["metric"])
                gdf["area_km2"] = metric.geometry.area / 1e6
                gdf = gdf[["name", "geometry", "area_km2"]].reset_index(drop=True)
                if cache_path:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    gdf.to_file(cache_path, driver="GeoJSON")
                return gdf

    # Download region boundary
    region = ox.geocode_to_gdf(cfg["region_query"])
    bounds = region.total_bounds  # (lon_min, lat_min, lon_max, lat_max)

    # Query admin_level=8 within the bounding box
    tags = {
        "boundary": "administrative",
        "admin_level": str(cfg.get("admin_level", 8)),
    }
    gdf = ox.features_from_bbox(bbox=bounds, tags=tags)

    # Keep only polygons/multipolygons whose centroid is inside the region polygon
    region_geom = region.union_all()
    gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
    gdf["centroid"] = gdf.geometry.centroid
    mask = gdf.centroid.within(region_geom)
    gdf = gdf[mask].copy()

    # Normalise name
    gdf["name"] = gdf.get("name", gdf.get("name:es", "")).astype(str).str.strip()
    gdf = gdf[gdf["name"].notna() & (gdf["name"] != "")].copy()
    # Drop province/region names that leak through
    drop_names = {cfg["region_query"], "Chile", "Santiago Province", "Talagante Province",
                  "Melipilla Province", "Chacabuco Province", "Cordillera Province", "Maipo Province"}
    gdf = gdf[~gdf["name"].isin(drop_names)].copy()
    gdf = gdf.drop_duplicates("name")

    # Reproject to metric CRS for area
    metric = gdf.to_crs(cfg["crs"]["metric"])
    gdf["area_km2"] = metric.geometry.area / 1e6

    # Keep only what we need and validate
    gdf = gdf[["name", "geometry", "area_km2"]].reset_index(drop=True)
    n_expected = expected
    if len(gdf) != n_expected:
        raise ValueError(
            f"Expected {n_expected} communes, got {len(gdf)}. "
            f"Names: {sorted(gdf['name'].tolist())}"
        )

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(cache_path, driver="GeoJSON")

    return gdf

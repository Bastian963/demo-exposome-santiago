"""Healthcare access exposome layer from OpenStreetMap.

Produces commune-level indicators of healthcare accessibility:
- counts of health facilities, hospitals/clinics and pharmacies
- density of facilities per km²
- intra-communal Euclidean distance (mean / median / p90) to the nearest
  health facility and to the nearest hospital/clinic

Distances are computed on a regular grid inside each commune using the
configured metric CRS.  This is a straight-line (Euclidean) approximation;
it does not account for the street network or topography.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
from shapely.geometry import Point

from . import boundaries, config


def _download_osm_tag(
    region: str,
    tag_key: str,
    values: list[str],
    max_retries: int = 2,
) -> gpd.GeoDataFrame:
    """Download OSM features for a single tag key, with a short retry loop."""
    tags = {tag_key: values}
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            gdf = ox.features_from_place(region, tags=tags)
            return gdf
        except Exception as err:  # noqa: BLE001
            last_err = err
            if attempt < max_retries:
                ox.utils.log(f"OSM download attempt {attempt + 1} failed for {tag_key}, retrying...")
    raise ConnectionError(
        f"Failed to download OSM tag '{tag_key}' after {max_retries + 1} attempts"
    ) from last_err


def fetch_healthcare_osm(
    cfg: dict[str, Any],
    cache_path: Path | None = None,
) -> gpd.GeoDataFrame:
    """Download healthcare amenities from OSM or load a cached GeoJSON.

    The cache stores the raw OSM response with minimal columns so it can be
    re-classified on load.

    Downloads each tag key separately to keep individual Overpass queries small
    and robust against transient failures.
    """
    if cache_path and cache_path.exists():
        gdf = gpd.read_file(cache_path)
        if len(gdf) > 0:
            return gdf

    region = cfg["region_query"]
    tags = cfg["healthcare"]["osm_tags"]

    # Increase timeout for large region queries.
    ox.settings.requests_timeout = 300

    pieces: list[gpd.GeoDataFrame] = []
    for tag_key, values in tags.items():
        print(f"  Downloading OSM tag '{tag_key}'...")
        gdf_tag = _download_osm_tag(region, tag_key, values)
        if len(gdf_tag) == 0:
            continue
        # Preserve OSM element/id so duplicates across tag keys can be dropped.
        gdf_tag = gdf_tag.reset_index()
        pieces.append(gdf_tag)

    if not pieces:
        gdf = gpd.GeoDataFrame(
            {"geometry": []}, crs=cfg["crs"]["geographic"], index=[]
        )
    else:
        gdf = gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), crs=pieces[0].crs)
        dup_cols = [c for c in ("element", "id") if c in gdf.columns]
        if dup_cols:
            gdf = gdf.drop_duplicates(subset=dup_cols, keep="first")

    gdf = gdf[gdf.geometry.notna()].copy().reset_index(drop=True)

    # Keep only the columns needed for classification / reporting.
    keep_cols = ["geometry", "name", "amenity", "healthcare"]
    available = [c for c in keep_cols if c in gdf.columns]
    gdf = gdf[available].copy()

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        gdf_wgs = gdf.to_crs(cfg["crs"]["geographic"]) if gdf.crs else gdf
        gdf_wgs.to_file(cache_path, driver="GeoJSON")

    return gdf


def classify_facilities(
    gdf: gpd.GeoDataFrame,
    cfg: dict[str, Any],
) -> gpd.GeoDataFrame:
    """Normalize OSM tags and convert geometries to representative points.

    Adds boolean columns ``is_<category>`` for every category defined in the
    config.  Polygon/line geometries are collapsed to a representative point
    in the metric CRS to avoid geodetic centroid issues, then converted back
    to the geographic CRS.
    """
    gdf = gdf.copy()

    # Convert to representative point using metric CRS.
    metric_crs = cfg["crs"]["metric"]
    gdf_metric = gdf.to_crs(metric_crs)
    gdf_metric["geometry"] = gdf_metric.geometry.representative_point()
    gdf = gdf_metric.to_crs(cfg["crs"]["geographic"]).reset_index(drop=True)

    for cat_name, rules in cfg["healthcare"]["categories"].items():
        mask = pd.Series(False, index=gdf.index)
        for rule in rules:
            tag = rule["tag"]
            values = rule["values"]
            if tag in gdf.columns:
                mask |= gdf[tag].isin(values)
        gdf[f"is_{cat_name}"] = mask

    return gdf


def compute_counts(
    gdf_health: gpd.GeoDataFrame,
    gdf_communes: gpd.GeoDataFrame,
    cfg: dict[str, Any],
) -> pd.DataFrame:
    """Count facilities per commune using a metric-CRS spatial join."""
    metric_crs = cfg["crs"]["metric"]

    communes_metric = (
        gdf_communes.to_crs(metric_crs)[["name", "geometry"]]
        .rename(columns={"name": "commune_name"})
    )
    pts_metric = gdf_health.to_crs(metric_crs)

    joined = gpd.sjoin(pts_metric, communes_metric, how="inner", predicate="within")

    counts = joined.groupby("commune_name").agg(
        n_total=("geometry", "size"),
        n_hospital=("is_hospital", "sum"),
        n_pharmacy=("is_pharmacy", "sum"),
    ).reset_index().rename(columns={"commune_name": "name"})

    counts[["n_total", "n_hospital", "n_pharmacy"]] = (
        counts[["n_total", "n_hospital", "n_pharmacy"]].fillna(0).astype(int)
    )
    return counts


def _build_access_grid_for_row(
    row: pd.Series,
    spacing_m: int,
    crs: str,
) -> gpd.GeoDataFrame:
    """Create a regular point grid clipped to one commune polygon."""
    minx, miny, maxx, maxy = row.geometry.bounds
    xs = np.arange(minx, maxx + spacing_m, spacing_m)
    ys = np.arange(miny, maxy + spacing_m, spacing_m)
    pts = [Point(x, y) for x in xs for y in ys]

    grid = gpd.GeoDataFrame(
        {"name": [row["name"]] * len(pts)},
        geometry=pts,
        crs=crs,
    )
    grid = grid[grid.within(row.geometry)].copy()

    if grid.empty:
        grid = gpd.GeoDataFrame(
            {"name": [row["name"]]},
            geometry=[row.geometry.representative_point()],
            crs=crs,
        )
    return grid


def build_access_grid(
    gdf_communes: gpd.GeoDataFrame,
    spacing_m: int,
    metric_crs: str,
) -> gpd.GeoDataFrame:
    """Build a regular intra-communal grid in the metric CRS."""
    gdf_metric = gdf_communes.to_crs(metric_crs)
    pieces = [
        _build_access_grid_for_row(row, spacing_m, metric_crs)
        for _, row in gdf_metric.iterrows()
    ]
    grid = gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), crs=metric_crs)
    return grid


def _nearest_distances_sjoin(
    grid: gpd.GeoDataFrame,
    facilities: gpd.GeoDataFrame,
    distance_col: str,
) -> gpd.GeoDataFrame:
    """Straight-line nearest distance via GeoPandas sjoin_nearest."""
    return gpd.sjoin_nearest(
        grid,
        facilities[["geometry"]],
        how="left",
        distance_col=distance_col,
    )


def _nearest_distances_ckdtree(
    grid: gpd.GeoDataFrame,
    facilities: gpd.GeoDataFrame,
    distance_col: str,
) -> gpd.GeoDataFrame:
    """Straight-line nearest distance via scipy.spatial.cKDTree."""
    from scipy.spatial import cKDTree

    tree = cKDTree(np.vstack([facilities.geometry.x, facilities.geometry.y]).T)
    grid_coords = np.vstack([grid.geometry.x, grid.geometry.y]).T
    dists, _ = tree.query(grid_coords, k=1)

    out = grid.copy()
    out[distance_col] = dists
    return out


def nearest_distance_summary(
    grid: gpd.GeoDataFrame,
    facilities: gpd.GeoDataFrame,
    distance_col: str,
    prefix: str,
    *,
    include_count: bool = True,
    use_ckdtree: bool = False,
) -> pd.DataFrame:
    """Return mean/median/p90 nearest distance per commune.

    Parameters
    ----------
    grid : GeoDataFrame
        Grid points in a metric CRS, with a ``name`` column.
    facilities : GeoDataFrame
        Facility points in the same metric CRS.
    distance_col : str
        Name of the temporary distance column.
    prefix : str
        Prefix used for the output columns, e.g. ``nearest_health`` produces
        ``mean_nearest_health_m``, ``median_nearest_health_m``,
        ``p90_nearest_health_m``.
    include_count : bool, optional
        If True, include ``n_access_grid`` (number of grid points per commune).
    use_ckdtree : bool, optional
        Use ``scipy.spatial.cKDTree`` instead of ``gpd.sjoin_nearest``.
    """
    if facilities.empty:
        out = grid.groupby("name").size().rename("n_access_grid").reset_index()
        for col in [f"mean_{prefix}_m", f"median_{prefix}_m", f"p90_{prefix}_m"]:
            out[col] = np.nan
        return out

    if use_ckdtree:
        joined = _nearest_distances_ckdtree(grid, facilities, distance_col)
    else:
        joined = _nearest_distances_sjoin(grid, facilities, distance_col)

    agg_spec: dict[str, Any] = {
        f"mean_{prefix}_m": (distance_col, "mean"),
        f"median_{prefix}_m": (distance_col, "median"),
        f"p90_{prefix}_m": (distance_col, lambda x: x.quantile(0.90)),
    }
    if include_count:
        agg_spec["n_access_grid"] = (distance_col, "size")

    return joined.groupby("name").agg(**agg_spec).reset_index()


def build_healthcare_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    *,
    use_ckdtree: bool = False,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Run the full healthcare access pipeline.

    Returns
    -------
    df : pd.DataFrame
        Table with commune-level healthcare access metrics.
    gdf : gpd.GeoDataFrame
        Same table with geometry attached (geographic CRS).
    """
    cfg = config.load_config(city)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metric_crs = cfg["crs"]["metric"]
    geo_crs = cfg["crs"]["geographic"]
    grid_spacing = int(cfg["healthcare"]["grid_spacing_m"])
    output_base = cfg["healthcare"]["output_base"]

    # 1. Boundaries
    communes_cache = cache_dir / f"{city}_communes.geojson"
    gdf_communes = boundaries.get_communes(cfg, cache_path=communes_cache)

    # 2. Fetch + classify facilities
    osm_cache = cache_dir / f"{city}_healthcare_osm.geojson"
    gdf_health_raw = fetch_healthcare_osm(cfg, cache_path=osm_cache)
    gdf_health = classify_facilities(gdf_health_raw, cfg)

    # 3. Counts and density
    counts = compute_counts(gdf_health, gdf_communes, cfg)
    gdf_result = gdf_communes[["name", "area_km2", "geometry"]].merge(
        counts, on="name", how="left"
    )
    gdf_result[["n_total", "n_hospital", "n_pharmacy"]] = (
        gdf_result[["n_total", "n_hospital", "n_pharmacy"]].fillna(0).astype(int)
    )
    gdf_result["density_per_km2"] = gdf_result["n_total"] / gdf_result["area_km2"]

    # 4. Intra-communal access grid
    access_grid = build_access_grid(gdf_communes, grid_spacing, metric_crs)

    # 5. Nearest distances (metric CRS)
    facilities_metric = gdf_health.to_crs(metric_crs)
    all_facilities = facilities_metric[facilities_metric["is_all_health"]].copy()
    hospital_facilities = facilities_metric[facilities_metric["is_hospital"]].copy()

    dist_health = nearest_distance_summary(
        access_grid,
        all_facilities,
        distance_col="nearest_health_m",
        prefix="nearest_health",
        include_count=True,
        use_ckdtree=use_ckdtree,
    )
    dist_hospital = nearest_distance_summary(
        access_grid,
        hospital_facilities,
        distance_col="nearest_hospital_m",
        prefix="nearest_hospital",
        include_count=False,
        use_ckdtree=use_ckdtree,
    )

    gdf_result = gdf_result.merge(dist_health, on="name", how="left")
    gdf_result = gdf_result.merge(dist_hospital, on="name", how="left")

    # 6. Formatting
    gdf_result["density_per_km2"] = gdf_result["density_per_km2"].round(4)
    gdf_result["area_km2"] = gdf_result["area_km2"].round(2)
    gdf_result["n_access_grid"] = gdf_result["n_access_grid"].fillna(0).astype(int)

    distance_cols = [
        "mean_nearest_health_m",
        "median_nearest_health_m",
        "p90_nearest_health_m",
        "mean_nearest_hospital_m",
        "median_nearest_hospital_m",
        "p90_nearest_hospital_m",
    ]
    for col in distance_cols:
        gdf_result[col] = gdf_result[col].round(0).astype("Int64")

    # Reorder columns to match build_master_exposome.py expectations
    output_cols = [
        "name",
        "area_km2",
        "n_total",
        "n_hospital",
        "n_pharmacy",
        "density_per_km2",
        "n_access_grid",
        "mean_nearest_health_m",
        "median_nearest_health_m",
        "p90_nearest_health_m",
        "mean_nearest_hospital_m",
        "median_nearest_hospital_m",
        "p90_nearest_hospital_m",
    ]
    gdf_result = gdf_result[output_cols + ["geometry"]]

    # 7. Validation
    n_expected = cfg["expected_communes"]
    if len(gdf_result) != n_expected:
        raise ValueError(
            f"Expected {n_expected} communes, got {len(gdf_result)}. "
            f"Names: {sorted(gdf_result['name'].tolist())}"
        )
    if gdf_result["name"].duplicated().any():
        dupes = gdf_result.loc[gdf_result["name"].duplicated(), "name"].tolist()
        raise ValueError(f"Duplicate commune names: {dupes}")
    required = [c for c in output_cols if c != "area_km2"]
    if gdf_result[required].isna().any().any():
        missing = gdf_result[required].columns[gdf_result[required].isna().any()].tolist()
        raise ValueError(f"Missing values in required columns: {missing}")

    # 8. Separate tabular and geographic outputs
    df = gdf_result[output_cols].copy()
    gdf_out = gpd.GeoDataFrame(
        gdf_result[output_cols + ["geometry"]],
        geometry="geometry",
        crs=geo_crs,
    )

    # 9. Write outputs
    csv_path = out_dir / f"{output_base}.csv"
    geojson_path = out_dir / f"{output_base}.geojson"
    metadata_path = out_dir / f"{output_base}_metadata.json"

    df.to_csv(csv_path, index=False)
    gdf_out.to_file(geojson_path, driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "source": "OpenStreetMap via osmnx",
        "method": "Euclidean nearest-facility distance on intra-communal grid",
        "grid_spacing_m": grid_spacing,
        "metric_crs": metric_crs,
        "osm_tags": cfg["healthcare"]["osm_tags"],
        "categories": cfg["healthcare"]["categories"],
        "n_facilities_total": int(gdf_health["is_all_health"].sum()),
        "n_facilities_hospital": int(gdf_health["is_hospital"].sum()),
        "n_facilities_pharmacy": int(gdf_health["is_pharmacy"].sum()),
        "n_grid_points": int(len(access_grid)),
        "distance_metric": "euclidean_straight_line",
        "columns": output_cols,
        "n_rows": int(len(df)),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(f"Wrote {csv_path.name} ({len(df)} rows x {df.shape[1]} cols)")
    print(f"Wrote {geojson_path.name}")
    print(f"Wrote {metadata_path.name}")

    return df, gdf_out

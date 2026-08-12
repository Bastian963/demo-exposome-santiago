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
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import osmnx as ox
import pandas as pd
from tqdm import tqdm

from . import boundaries, config
from .osm_fetch import (
    GREEN_TAG_MAX_TILE_SPAN_DEG,
    _deduplicate_osm_features,
    call_with_overpass_fallback,
    fetch_features_from_bbox_tiled,
    fetch_features_from_local_extract,
    tile_grid_size_for_bbox,
)

_BETWEEN_REGIONS_S = 8  # respect Overpass rate limit (2 slots), same pacing as food_environment.py


def _download_osm_green(
    region: str,
    tags: dict[str, list[str]],
    *,
    bbox: tuple[float, float, float, float] | None = None,
    tile_cache_dir: Path | None = None,
    attempts: int = 1,
    attempt_timeout_s: float | None = 300.0,
) -> gpd.GeoDataFrame:
    """Download OSM green-area features, with endpoint fallback + backoff."""
    try:
        if bbox is not None:
            return fetch_features_from_bbox_tiled(
                bbox,
                tags,
                label=region,
                grid_size=tile_grid_size_for_bbox(bbox, GREEN_TAG_MAX_TILE_SPAN_DEG),
                checkpoint_dir=tile_cache_dir,
                attempts=attempts,
                attempt_timeout_s=attempt_timeout_s,
                log=tqdm.write,
            )
        return call_with_overpass_fallback(
            lambda: ox.features_from_place(region, tags=tags),
            label=region,
            attempts=attempts,
            attempt_timeout_s=attempt_timeout_s,
            log=tqdm.write,
        )
    except ConnectionError as err:
        raise ConnectionError(f"Failed to download OSM green areas for {region}") from err


def _normalize_regions(region_query: str | list[str]) -> list[str]:
    """Coerce a single place name or a list of localities into a list."""
    if isinstance(region_query, str):
        return [region_query]
    return list(region_query)


def _region_slug(region: str) -> str:
    """Filesystem-safe per-locality cache key (strips accents/punctuation)."""
    value = unicodedata.normalize("NFD", region)
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower())
    return value.strip("_") or "region"


def _normalise_unit_name(value: str) -> str:
    """Normalise an administrative name for region-to-reference matching."""
    return _region_slug(value).replace("_", " ")


def _unit_geometry_for_region(
    region: str,
    units: gpd.GeoDataFrame | None,
) -> Any | None:
    """Resolve a configured place label to its authoritative study polygon."""
    if units is None or units.empty:
        return None
    locality = region.split(",", 1)[0]
    candidates = [_normalise_unit_name(locality)]
    for prefix in ("cercado de ", "partido de ", "comuna de ", "distrito de "):
        if candidates[0].startswith(prefix):
            candidates.append(candidates[0][len(prefix):])

    lookup = {
        _normalise_unit_name(str(row["name"])): row.geometry
        for _, row in units.iterrows()
    }
    for candidate in candidates:
        if candidate in lookup:
            return lookup[candidate]
    return None


def _green_cache_frame(frame: gpd.GeoDataFrame, geographic_crs: str) -> gpd.GeoDataFrame:
    """Keep stable identifiers and only fields used by the green layer."""
    if frame.empty:
        return gpd.GeoDataFrame({"geometry": []}, crs=geographic_crs)
    result = frame.to_crs(geographic_crs) if frame.crs else frame.set_crs(geographic_crs)
    keep = [
        column
        for column in ("element", "id", "name", "leisure", "landuse", "geometry")
        if column in result.columns
    ]
    return result[keep].copy()


def fetch_green_areas(
    cfg: dict[str, Any],
    cache_path: Path | None = None,
) -> gpd.GeoDataFrame:
    """Fetch green-area polygons from OSM or load a cached GeoJSON.

    ``region_query`` may be a single place name (Santiago) or a list of
    localities (AMBA's 41 partidos/CABA). A single combined Overpass query
    over dozens of localities is what emptied out the AMBA cache: querying
    all of them at once times out and, since nothing was cached until the
    very end, the retry loses every locality's data. Multi-locality regions
    are instead downloaded one locality at a time with its own cache file, so
    a failure partway through keeps everything already fetched and a re-run
    resumes only the missing localities. Large authoritative polygons are
    additionally split into query tiles, each checkpointed independently.
    This matters for rural units such as Bogota's Usme and Sumapaz, where one
    locality contains 16--64 Overpass tiles.
    """
    if cache_path and cache_path.exists():
        gdf = gpd.read_file(cache_path)
        if len(gdf) > 0:
            return gdf

    access_cfg = cfg["greenspace"]["access"]
    ox.settings.requests_timeout = int(access_cfg.get("requests_timeout_s", 180))
    attempts = int(access_cfg.get("overpass_attempts", 1))
    attempt_timeout_s = float(access_cfg.get("attempt_timeout_s", 300))
    tags = access_cfg["osm_tags"]

    # A frozen regional extract replaces the whole Overpass tiling path: no
    # network, no rate limit, no per-tile checkpoints. Measured 2026-08-10 on
    # cataluna_comarques: 1.786 tiles / 69 h over Overpass vs 99 s here, with
    # 100% of the features Overpass returned inside the region also present.
    # See data/raw/geofabrik/README.md and docs/osm_local_extract.md.
    extract = access_cfg.get("osm_extract")
    if extract:
        gdf = fetch_features_from_local_extract(
            extract, tags, label=f"greenspace_access[{cfg.get('name', '?')}]", log=print
        )
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            gdf.to_file(cache_path, driver="GeoJSON")
        return gdf

    regions = _normalize_regions(cfg["region_query"])
    geo_crs = cfg["crs"]["geographic"]
    units = None
    if isinstance(cfg.get("spatial_units"), dict):
        units = boundaries.get_communes(cfg).to_crs(geo_crs)

    locality_dir = cache_path.parent / f"{cache_path.stem}_by_region" if cache_path else None
    if locality_dir:
        locality_dir.mkdir(parents=True, exist_ok=True)

    pieces: list[gpd.GeoDataFrame] = []
    failed: list[str] = []
    pending: list[tuple[int, str, Path | None]] = []
    for i, region in enumerate(regions):
        locality_cache = (
            locality_dir / f"{_region_slug(region)}.geojson"
            if locality_dir
            else None
        )
        if locality_cache is None or not locality_cache.exists():
            pending.append((i, region, locality_cache))
            continue
        piece = gpd.read_file(locality_cache)
        if len(piece) > 0:
            pieces.append(piece)

    pending_names = [region for _, region, _ in pending]
    tqdm.write(
        f"  OSM region checkpoints: {len(regions) - len(pending)}/{len(regions)}; "
        f"pending: {pending_names or 'none'}"
    )
    progress = tqdm(
        total=len(regions),
        initial=len(regions) - len(pending),
        desc="greenspace_access OSM regions",
        unit="region",
    )
    try:
        for i, region, locality_cache in pending:
            progress.set_postfix_str(region.split(",", 1)[0])
            tqdm.write(f"  [{region}] downloading from OSM …")
            unit_geometry = _unit_geometry_for_region(region, units)
            query_bbox = tuple(unit_geometry.bounds) if unit_geometry is not None else None
            tile_cache_dir = (
                locality_cache.with_name(f"{locality_cache.stem}_tiles")
                if locality_cache is not None and query_bbox is not None
                else None
            )
            try:
                piece = _download_osm_green(
                    region,
                    tags,
                    bbox=query_bbox,
                    tile_cache_dir=tile_cache_dir,
                    attempts=attempts,
                    attempt_timeout_s=attempt_timeout_s,
                )
            except ConnectionError as err:
                failed.append(region)
                tqdm.write(f"  [{region}] FAILED after retries: {err}")
                progress.update(1)
                continue
            if unit_geometry is not None and not piece.empty:
                piece = piece.to_crs(geo_crs) if piece.crs else piece.set_crs(geo_crs)
                piece = piece[piece.geometry.intersects(unit_geometry)].copy()
            if locality_cache is not None:
                piece_out = _green_cache_frame(piece, geo_crs)
                piece_out.to_file(locality_cache, driver="GeoJSON")
            # Only pace real Overpass calls, not cache hits, and never after
            # the last region.
            if i < len(regions) - 1:
                time.sleep(_BETWEEN_REGIONS_S)
            if len(piece) > 0:
                pieces.append(piece)
            progress.update(1)
    finally:
        progress.close()

    if failed:
        raise ConnectionError(
            f"Failed to download OSM green areas for {len(failed)} of {len(regions)} "
            f"region(s): {failed}. Already-fetched regions are cached under "
            f"{locality_dir}; re-run with --resume to retry only the missing ones."
        )

    gdf = (
        gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), crs=pieces[0].crs)
        if pieces
        else gpd.GeoDataFrame({"geometry": []}, crs=geo_crs)
    )
    gdf = _deduplicate_osm_features(gdf)

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

    has_spatial_id = "spatial_id" in communes.columns and "spatial_name" in communes.columns
    base_cols = (["spatial_id", "spatial_name"] if has_spatial_id else []) + ["name", "area_km2", "geometry"]
    result = communes[base_cols].copy()
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


def _write_access_figure(gdf: "gpd.GeoDataFrame", out_path: Path) -> None:
    """Write a 2-panel diagnostic map: OSM green % and distance to nearest park."""
    import matplotlib.pyplot as plt

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    plots = [
        ("green_osm_pct", "Cobertura OSM de areas verdes (%)", "Greens", "%"),
        ("dist_to_nearest_park_m", "Distancia al parque mas cercano (m)", "RdYlGn_r", "metros"),
    ]
    for ax, (column, title, cmap, label) in zip(axes, plots, strict=True):
        gdf.plot(
            column=column,
            ax=ax,
            cmap=cmap,
            legend=True,
            legend_kwds={"label": label, "shrink": 0.65},
            edgecolor="white",
            linewidth=0.3,
        )
        ax.set_title(title, fontsize=12)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _write_access_metadata(
    path: Path,
    *,
    city: str,
    n_communes: int,
    expected_units: int | None = None,
    geographic_unit: str = "spatial_unit",
    n_green_polygons: int,
    buffers_m: list[int],
    outputs: list[str],
    methodology_doc: str,
    figure: str,
) -> None:
    """Write enriched JSON metadata for the greenspace access layer."""
    buf_cols = {
        f"green_area_within_{b}m_km2": {
            "unit": "km²",
            "description": f"Total area of OSM green polygons whose representative point lies within {b} m of the commune boundary",
        }
        for b in buffers_m
    }
    buf_cols.update({
        f"green_count_within_{b}m": {
            "unit": "count",
            "description": f"Number of OSM green polygons whose representative point lies within {b} m of the commune boundary",
        }
        for b in buffers_m
    })
    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "geographic_unit": geographic_unit,
        "expected_communes": expected_units if expected_units is not None else n_communes,
        "expected_units": expected_units if expected_units is not None else n_communes,
        "n_communes": n_communes,
        "n_green_polygons": n_green_polygons,
        "source": {
            "provider": "OpenStreetMap",
            "tags": "leisure=park/garden/nature_reserve/playground/recreation_ground; landuse=grass/forest/meadow/village_green/recreation_ground",
            "cache_file": f"cache/{city}_greenspace_osm.geojson",
        },
        "buffers_m": buffers_m,
        "buffer_area_method": "whole_polygon_by_repr_point",
        "distance_method": "straight-line from commune centroid to nearest green polygon representative point",
        "columns": {
            "name": {"unit": "spatial-unit name", "description": "Configured spatial-unit label"},
            "area_km2": {"unit": "km²", "description": "Spatial-unit area in square kilometres"},
            "green_osm_km2": {"unit": "km²", "description": "Area of OSM-mapped green space within the commune (polygon intersection, deduplicated)"},
            "green_osm_pct": {"unit": "percent [0,100]", "description": "100 * green_osm_km2 / area_km2"},
            "green_osm_n": {"unit": "count", "description": "Number of distinct OSM green polygons whose representative point falls inside the commune"},
            "dist_to_nearest_park_m": {"unit": "metres", "description": "Straight-line distance from commune centroid to nearest green polygon representative point; 99999 when no green area is found"},
            **buf_cols,
        },
        "limitations": [
            "OSM mapping is heterogeneous across communes; sub-mapping bias documented in greenspace_cv validation layer.",
            "Distances are straight-line from commune centroid, not population-weighted or road-network based.",
            "Buffer metrics count whole polygons by representative point, not exact area clipped to buffer — may over- or under-count at boundaries.",
            "dist_to_nearest_park_m=99999 is a sentinel for communes with no OSM green area, not a measured distance.",
        ],
        "methodology_doc": methodology_doc,
        "diagnostic_figure": figure,
        "outputs": outputs,
    }
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


def build_greenspace_access_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    figures_dir: Path = Path("figures"),
) -> tuple[Path, Path]:
    """Build the greenspace accessibility layer and write CSV + GeoJSON."""
    cfg = config.load_config(city)
    cache_dir = Path(cache_dir)
    out_dir = Path(out_dir)
    figures_dir = Path(figures_dir)
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
    numeric_cols = [c for c in result.columns if c not in ("name", "geometry", "spatial_id", "spatial_name")]
    if result[numeric_cols].isna().any().any():
        missing = result[numeric_cols].columns[result[numeric_cols].isna().any()].tolist()
        raise ValueError(f"Missing values in output columns: {missing}")

    # Convert back to geographic CRS for output
    result_geo = result.to_crs(cfg["crs"]["geographic"])

    # Output file names
    base_name = f"{city}_greenspace_access"
    csv_path = out_dir / f"{base_name}.csv"
    geojson_path = out_dir / f"{base_name}.geojson"
    metadata_path = out_dir / f"{base_name}_metadata.json"
    figure_path = figures_dir / f"greenspace_access_{city}_2panel.png"

    # CSV without geometry
    result.drop(columns="geometry").to_csv(csv_path, index=False)
    result_geo.to_file(geojson_path, driver="GeoJSON")

    _write_access_figure(result_geo, figure_path)
    _write_access_metadata(
        metadata_path,
        city=city,
        n_communes=int(len(result)),
        expected_units=int(cfg.get("expected_units", cfg.get("expected_communes", len(result)))),
        geographic_unit=str(cfg.get("spatial_unit_type", "spatial_unit")),
        n_green_polygons=int(len(green_areas)),
        buffers_m=buffers_m,
        outputs=[csv_path.name, geojson_path.name, metadata_path.name],
        methodology_doc="docs/greenspace_access_methodology.md",
        figure=figure_path.as_posix(),
    )

    print(f"Wrote {csv_path.name}: {len(result)} rows x {result.drop(columns='geometry').shape[1]} columns")
    print(f"Wrote {geojson_path.name}")
    print(f"Wrote {metadata_path.name}")
    print(f"Wrote {figure_path.name}")

    return csv_path, geojson_path

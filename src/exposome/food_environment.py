"""Food environment exposome layer from OpenStreetMap.

Measures commune-level retail food environment quality:
  - Healthy outlets: supermarkets, greengrocers, marketplaces (ferias)
  - Unhealthy outlets: fast food, convenience stores (almacenes/minimarkets)

Headline metric is the CDC modified Retail Food Environment Index (mRFEI):
    mRFEI = healthy / (healthy + unhealthy) × 100
Plus a food-swamp ratio and access (distance to nearest supermarket).

Evidence base: the food environment shapes diet, which drives obesity, diabetes
and hypertension — three of the 14 modifiable dementia risk factors in the
Lancet Commission 2024. Neighborhood food resources predict cognitive health
behaviours ("Cognability"; Finlay et al., Soc Sci Med 2026).

OSM coverage in the RM (current cache snapshot, 2024-2025):
  - supermarket: 596 (well-mapped; covers Lider, Jumbo, Unimarc, Santa Isabel,
    Tottus, Cugat, mayorista networks).
  - greengrocer: 0 (NOT mapped in OSM Chile; queried with `shop=greengrocer`
    and Overpass returned empty).
  - marketplace: 0 (under-mapped; ~160 ferias in OSM vs ~400+ real ferias
    libres in the RM, which are mobile/temporary by nature).
  - fast_food: 0 (NOT mapped in OSM Chile; queried with `amenity=fast_food`
    and Overpass returned empty despite the obvious abundance of these
    outlets on the ground).
  - convenience: 0 (NOT mapped in OSM Chile; queried with `shop=convenience`
    and Overpass returned empty even though almacenes/minimarkets are
    pervasive in every commune).

This is a structural OSM coverage gap, not a pipeline bug. The Overpass
queries use the standard tags from the CDC mRFEI classification; the issue
is that mappers in Chile have not systematically tagged food/amenity
categories. As a result:

  - `food_n_unhealthy` is 0 in every commune.
  - `food_mrfei` is degenerate (100 in 51/52 communes, 0 in Alhué only).
  - `food_swamp_ratio` is 0 in every commune.
  - `food_index` reduces to a composite of (healthy_density, mean_dist_super,
    near-constant mrfei) — i.e. essentially "supermarket density + access".

The supermarket signal is real and informative for the food-desert pathway
(see CDC mRFEI literature; USDA Food Access Research Atlas). The unhealthy
half of the index is structurally missing and must be flagged as a known
limitation. See `data/processed/santiago_food_environment_metadata.json`
under `coverage_gap` for the remediation plan and downstream caveats.
"""
from __future__ import annotations

import json
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from .study_grid import build_study_access_grid, intersect_grid_with_units
from shapely.geometry import Point
from tqdm import tqdm

try:
    import osmnx as ox
except ImportError as e:
    raise ImportError("osmnx is required: conda install -c conda-forge osmnx") from e

try:
    from . import boundaries, config as _config
    from .osm_fetch import (
        POINT_TAG_MAX_TILE_SPAN_DEG,
        fetch_features_from_bbox_tiled,
        fetch_features_from_local_extract,
        tile_grid_size_for_bbox,
    )
except ImportError:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    import exposome.boundaries as boundaries  # type: ignore[no-redef]
    import exposome.config as _config  # type: ignore[no-redef]
    from exposome.osm_fetch import POINT_TAG_MAX_TILE_SPAN_DEG  # type: ignore[no-redef]
    from exposome.osm_fetch import fetch_features_from_bbox_tiled  # type: ignore[no-redef]
    from exposome.osm_fetch import fetch_features_from_local_extract  # type: ignore[no-redef]
    from exposome.osm_fetch import tile_grid_size_for_bbox  # type: ignore[no-redef]

_GRID_SPACING_M = 1000
_NO_SUPERMARKET_DIST_M = 50_000   # sentinel for communes with no supermarket
_DEDUP_RADIUS_M = 25              # retail outlets within 25 m = same place
_BETWEEN_QUERIES_S = 8           # respect Overpass rate limit (2 slots)

# CDC mRFEI classification
_CATEGORIES = {
    "supermarket": {"shop": "supermarket"},
    "greengrocer": {"shop": "greengrocer"},
    "marketplace": {"amenity": "marketplace"},
    "fast_food": {"amenity": "fast_food"},
    "convenience": {"shop": "convenience"},
}
_HEALTHY = ["supermarket", "greengrocer", "marketplace"]
_UNHEALTHY = ["fast_food", "convenience"]


# ---------------------------------------------------------------------------
# Data acquisition
# ---------------------------------------------------------------------------

def _fetch_region_features(
    bbox: tuple[float, float, float, float],
    tags: dict,
    label: str,
    extract: str | Path | None = None,
) -> gpd.GeoDataFrame:
    """Download OSM features within a bbox, with endpoint fallback + backoff.

    When the study declares a frozen regional extract, that file is read
    instead and no request leaves the machine. Each category is read on its own
    pass: this layer only ever uses feature geometry (see
    ``_geometry_only_cache_frame``), so unlike healthcare there is no
    cross-tag semantics to preserve by reading everything at once.

    Uses the study's bbox rather than its (possibly very detailed) union
    polygon: Overpass's `poly:` filter cost scales with vertex count, and a
    55-unit AMBA union (~20k vertices) made some tag queries hang for 90+
    minutes even though the same tag over a plain bbox returns in seconds.
    Extra candidates outside the true union are harmless -- the caller's
    per-unit spatial join (_count_within) already discards anything that
    doesn't fall inside a real commune/partido polygon.

    A query that *succeeds* with zero rows (a tag genuinely unmapped in this
    region's OSM data -- see the module docstring) is not retried and is not
    an error. Only a query that *raises* after every endpoint/attempt is
    exhausted raises ``ConnectionError`` -- previously this case silently
    returned an empty GeoDataFrame indistinguishable from a real zero,
    corrupting mRFEI with fabricated zero-counts instead of failing the layer.

    A single untiled query was fine for a city/comuna bbox but fails outright
    for a whole-province AOI (confirmed 2026-08-03 on San Juan: a trivial
    ~100 km2 Overpass query against the same province succeeded instantly,
    so a whole-bbox query failing was area size, not endpoint availability).
    ``fetch_features_from_bbox_tiled`` already implements the same
    empty-vs-connectivity-failure distinction per tile.
    """
    if extract:
        return fetch_features_from_local_extract(
            extract, tags, label=label, log=tqdm.write
        )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return fetch_features_from_bbox_tiled(
                bbox,
                tags,
                label=label,
                grid_size=tile_grid_size_for_bbox(bbox, POINT_TAG_MAX_TILE_SPAN_DEG),
                log=print,
            )
        except ConnectionError as err:
            raise ConnectionError(f"Failed to download OSM category '{label}'") from err


def _to_points(gdf: gpd.GeoDataFrame, metric_crs: str) -> gpd.GeoDataFrame:
    """Convert any geometry to representative point in metric CRS."""
    if gdf.empty or len(gdf) == 0:
        return gpd.GeoDataFrame({"geometry": []}, crs=metric_crs)
    gdf_m = gdf.to_crs(metric_crs).copy()
    gdf_m["geometry"] = gdf_m.geometry.representative_point()
    return gdf_m[["geometry"]]


def _geometry_only_cache_frame(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return the minimal, GeoJSON-safe representation needed on resume.

    Raw OSM responses can contain tag names that Fiona cannot serialize as
    field names (for example ``currency:MXN`` in CDMX).  The food environment
    pipeline only uses feature geometry after download, so retaining arbitrary
    OSM tag columns makes the cache both larger and less portable without
    affecting any computed metric.
    """
    if gdf.empty or len(gdf) == 0:
        return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")
    gdf_wgs = gdf.to_crs("EPSG:4326") if gdf.crs else gdf.set_crs("EPSG:4326")
    return gdf_wgs[["geometry"]].copy()


def _deduplicate_by_cluster(gdf: gpd.GeoDataFrame, radius_m: float) -> gpd.GeoDataFrame:
    """Cluster features within radius_m; return one point per cluster."""
    if gdf.empty or len(gdf) == 0:
        return gdf
    pts = np.vstack([gdf.geometry.x, gdf.geometry.y]).T
    tree = cKDTree(pts)
    visited: set[int] = set()
    centers: list[tuple[float, float]] = []
    for i in range(len(pts)):
        if i not in visited:
            neighbors = tree.query_ball_point(pts[i], radius_m)
            visited.update(neighbors)
            cl = pts[neighbors]
            centers.append((cl[:, 0].mean(), cl[:, 1].mean()))
    return gpd.GeoDataFrame(
        {"geometry": [Point(x, y) for x, y in centers]}, crs=gdf.crs
    )


# ---------------------------------------------------------------------------
# Distance grid (same pattern as public_transport.py)
# ---------------------------------------------------------------------------

def _build_commune_grid(row: pd.Series, spacing_m: int, crs: str) -> gpd.GeoDataFrame:
    minx, miny, maxx, maxy = row.geometry.bounds
    xs = np.arange(minx, maxx + spacing_m, spacing_m)
    ys = np.arange(miny, maxy + spacing_m, spacing_m)
    pts = [Point(x, y) for x in xs for y in ys]
    grid = gpd.GeoDataFrame({"name": [row["name"]] * len(pts)}, geometry=pts, crs=crs)
    grid = grid[grid.within(row.geometry)].copy()
    if grid.empty:
        grid = gpd.GeoDataFrame(
            {"name": [row["name"]]},
            geometry=[row.geometry.representative_point()], crs=crs,
        )
    return grid


def _build_grid(
    communes_metric: gpd.GeoDataFrame,
    spacing_m: int = _GRID_SPACING_M,
    metric_crs: str | None = None,
) -> gpd.GeoDataFrame:
    metric_crs = metric_crs or str(communes_metric.crs)
    cells = build_study_access_grid(communes_metric, spacing_m=spacing_m, metric_crs=metric_crs)
    links = intersect_grid_with_units(cells, communes_metric, name_column="name")
    samples = cells[["cell_id", "sample_point"]].rename(columns={"sample_point": "geometry"}).set_geometry("geometry")
    return gpd.GeoDataFrame(links.drop(columns="geometry").merge(samples, on="cell_id"), geometry="geometry", crs=metric_crs)


def _nearest_dist(grid: gpd.GeoDataFrame, facilities: gpd.GeoDataFrame,
                  col: str, fallback: float) -> gpd.GeoDataFrame:
    out = grid.copy()
    if facilities.empty or len(facilities) == 0:
        out[col] = fallback
        return out
    tree = cKDTree(np.vstack([facilities.geometry.x, facilities.geometry.y]).T)
    coords = np.vstack([grid.geometry.x, grid.geometry.y]).T
    dists, _ = tree.query(coords, k=1)
    out[col] = dists
    return out


def _count_within(pts: gpd.GeoDataFrame, communes_metric: gpd.GeoDataFrame) -> pd.Series:
    if pts.empty or len(pts) == 0:
        return pd.Series(0, index=communes_metric["name"])
    joined = gpd.sjoin(pts[["geometry"]], communes_metric[["name", "geometry"]],
                       how="inner", predicate="within")
    return joined.groupby("name").size().reindex(communes_metric["name"], fill_value=0)


# ---------------------------------------------------------------------------
# Composite index
# ---------------------------------------------------------------------------

def _compute_food_index(df: pd.DataFrame) -> pd.Series:
    """Z-score composite food environment index (0–100). Higher = healthier.

    Metrics: food_mrfei (+), food_healthy_density (+),
             food_mean_dist_supermarket_m (–).
    """
    positive = ["food_mrfei", "food_healthy_density"]
    negative = ["food_mean_dist_supermarket_m"]
    oriented = pd.DataFrame(index=df.index)
    for col in positive:
        x = df[col].astype(float)
        std = x.std(ddof=0)
        oriented[col] = (x - x.mean()) / std if std > 0 else 0.0
    for col in negative:
        x = df[col].astype(float)
        std = x.std(ddof=0)
        oriented[col] = -((x - x.mean()) / std) if std > 0 else 0.0
    composite = oriented.mean(axis=1).clip(-3, 3)
    cmin, cmax = composite.min(), composite.max()
    if cmax == cmin:
        return pd.Series(50.0, index=df.index)
    return ((composite - cmin) / (cmax - cmin) * 100).round(1)


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_food_environment_layer(
    city: str = "santiago",
    out_dir: Path = Path("data/processed"),
    cache_dir: Path = Path("cache"),
    resume: bool = True,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Build the food environment layer and write CSV/GeoJSON/metadata."""
    out_dir = Path(out_dir)
    cache_dir = Path(cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    cfg = _config.load_config(city)
    metric_crs = cfg["crs"]["metric"]
    expected = int(cfg.get("expected_units", cfg.get("expected_communes", 52)))
    food_cfg = cfg.get("food_environment", {})
    grid_spacing_m = int(food_cfg.get("grid_spacing_m", _GRID_SPACING_M))
    dedupe_radius_m = float(food_cfg.get("dedupe_radius_m", _DEDUP_RADIUS_M))
    no_supermarket_dist_m = float(
        food_cfg.get("no_supermarket_dist_m", _NO_SUPERMARKET_DIST_M)
    )
    osm_extract = food_cfg.get("osm_extract")
    ox.settings.requests_timeout = 300
    ox.settings.log_console = False

    # --- 1. Boundaries ---
    communes_cache = cache_dir / f"{city}_communes.geojson"
    gdf_communes = boundaries.get_communes(cfg, cache_path=communes_cache)
    has_spatial_id = "spatial_id" in gdf_communes.columns and "spatial_name" in gdf_communes.columns
    boundary_cols = (["spatial_id", "spatial_name", "name"] if has_spatial_id else ["name"]) + ["geometry"]
    communes_metric = gdf_communes[boundary_cols].to_crs(metric_crs)
    if len(communes_metric) != expected:
        raise ValueError(f"Expected {expected} spatial units, got {len(communes_metric)}")

    bbox_4326 = tuple(gdf_communes.to_crs("EPSG:4326").total_bounds)  # (west, south, east, north)

    # --- 2. Download each category (cached) ---
    cat_points: dict[str, gpd.GeoDataFrame] = {}
    categories = list(_CATEGORIES.items())
    for i, (cat, tags) in enumerate(tqdm(categories, desc=f"food_environment [{city}]", unit="category")):
        cache_f = cache_dir / f"{city}_food_{cat}.geojson"
        if resume and cache_f.exists():
            tqdm.write(f"  [{cat}] loading from cache …")
            gdf_raw = gpd.read_file(cache_f)
        else:
            tqdm.write(f"  [{cat}] downloading from OSM …")
            gdf_raw = _fetch_region_features(bbox_4326, tags, cat, extract=osm_extract)
            if len(gdf_raw) > 0:
                _geometry_only_cache_frame(gdf_raw).to_file(cache_f, driver="GeoJSON")
            # The pause only exists to respect Overpass's 2-slot rate limit;
            # reading a local file has no such budget.
            if i < len(categories) - 1 and not osm_extract:
                time.sleep(_BETWEEN_QUERIES_S)
        pts = _to_points(gdf_raw, metric_crs)
        deduped = _deduplicate_by_cluster(pts, dedupe_radius_m)
        cat_points[cat] = deduped
        tqdm.write(f"    → {len(gdf_raw)} raw → {len(deduped)} unique")

    # --- 3. Count per commune ---
    print("  Counting outlets per commune …")
    counts = {cat: _count_within(pts, communes_metric) for cat, pts in cat_points.items()}

    # --- 4. Distance to nearest supermarket (food desert access) ---
    print("  Building 1 km grid and computing supermarket access …")
    grid = _build_grid(communes_metric, grid_spacing_m, metric_crs)
    grid = _nearest_dist(grid, cat_points["supermarket"], "dist_super_m",
                         fallback=no_supermarket_dist_m)
    dist_super = grid.groupby("name")["dist_super_m"].agg(
        food_mean_dist_supermarket_m="mean",
    ).reset_index()

    # --- 5. Assemble table ---
    areas_km2 = communes_metric.set_index("name")["geometry"].area / 1e6
    df = pd.DataFrame({"name": communes_metric["name"].values}).set_index("name")

    df["food_n_supermarket"] = counts["supermarket"].values
    df["food_n_greengrocer"] = counts["greengrocer"].values
    df["food_n_marketplace"] = counts["marketplace"].values
    df["food_n_fastfood"] = counts["fast_food"].values
    df["food_n_convenience"] = counts["convenience"].values

    df["food_n_healthy"] = sum(counts[c] for c in _HEALTHY).values
    df["food_n_unhealthy"] = sum(counts[c] for c in _UNHEALTHY).values

    df["food_healthy_density"] = (df["food_n_healthy"] / areas_km2).round(3)
    df["food_unhealthy_density"] = (df["food_n_unhealthy"] / areas_km2).round(3)

    total = df["food_n_healthy"] + df["food_n_unhealthy"]
    df["food_mrfei"] = np.where(
        total > 0, (df["food_n_healthy"] / total * 100), 0.0
    ).round(1)
    df["food_swamp_ratio"] = (
        df["food_n_unhealthy"] / df["food_n_healthy"].clip(lower=1)
    ).round(3)

    df = df.join(dist_super.set_index("name"))
    df["food_mean_dist_supermarket_m"] = df["food_mean_dist_supermarket_m"].round(1)

    df = df.reset_index()
    df["food_index"] = _compute_food_index(df)

    if has_spatial_id:
        df = df.merge(
            pd.DataFrame(communes_metric[["spatial_id", "spatial_name", "name"]]),
            on="name",
            how="left",
        )

    ordered_cols = (["spatial_id", "spatial_name"] if has_spatial_id else []) + [
        "name",
        "food_n_supermarket", "food_n_greengrocer", "food_n_marketplace",
        "food_n_fastfood", "food_n_convenience",
        "food_n_healthy", "food_n_unhealthy",
        "food_healthy_density", "food_unhealthy_density",
        "food_mrfei", "food_swamp_ratio",
        "food_mean_dist_supermarket_m", "food_index",
    ]
    df = df[ordered_cols].sort_values("name").reset_index(drop=True)

    # --- 6. GeoDataFrame ---
    gdf_out = gdf_communes[["name", "geometry"]].merge(df, on="name", how="left")
    gdf_out = gpd.GeoDataFrame(gdf_out, geometry="geometry", crs=gdf_communes.crs)
    gdf_out = gdf_out.sort_values("name").reset_index(drop=True)

    # --- 7. Write outputs ---
    csv_out = out_dir / f"{city}_food_environment.csv"
    geojson_out = out_dir / f"{city}_food_environment.geojson"
    meta_out = out_dir / f"{city}_food_environment_metadata.json"

    df.to_csv(csv_out, index=False)
    gdf_out.to_file(geojson_out, driver="GeoJSON")

    top5 = df.nlargest(5, "food_index")[["name", "food_index"]].values.tolist()
    bot5 = df.nsmallest(5, "food_index")[["name", "food_index"]].values.tolist()

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "source": "OpenStreetMap via osmnx",
        "classification_cdc_mrfei": {
            "healthy": "shop=supermarket, shop=greengrocer, amenity=marketplace",
            "unhealthy": "amenity=fast_food, shop=convenience",
        },
        "deduplication_radius_m": dedupe_radius_m,
        "grid_spacing_m": grid_spacing_m,
        "crs_metric": metric_crs,
        "method": (
            "Food outlets downloaded per category for the configured study area via osmnx "
            f"features_from_polygon (cached). Deduplicated at {dedupe_radius_m:g} m. mRFEI = "
            "healthy / (healthy + unhealthy) × 100 per spatial unit. food_swamp_ratio "
            "= unhealthy / max(healthy, 1). food_index = z-scored composite of "
            "mrfei (+), healthy_density (+), mean_dist_supermarket (–); 0–100."
        ),
        "evidence": (
            "Food environment shapes diet → obesity/diabetes/hypertension, three "
            "of the 14 modifiable dementia risk factors (Livingston et al., Lancet "
            "2024). Neighborhood food resources predict cognitive health behaviours "
            "(Finlay et al., Soc Sci Med 2026, 'Cognability')."
        ),
        "known_limitation": (
            "Ferias libres (street markets) are under-mapped in OSM (~160 vs ~400+ "
            "real in the RM; they are mobile/temporary). This BIASES food_mrfei "
            "DOWNWARD in popular communes with strong feria traditions. The fixed "
            "categories (supermarkets, fast food, convenience) dominate and are well "
            "mapped, so the index remains valid; food_n_marketplace is reported "
            "separately for transparency."
        ),
        "n_communes": len(df),
        "n_spatial_units": len(df),
        "totals": {
            "supermarket": int(df["food_n_supermarket"].sum()),
            "greengrocer": int(df["food_n_greengrocer"].sum()),
            "marketplace": int(df["food_n_marketplace"].sum()),
            "fast_food": int(df["food_n_fastfood"].sum()),
            "convenience": int(df["food_n_convenience"].sum()),
        },
        "top5_healthiest": top5,
        "bot5_worst": bot5,
        "columns": ordered_cols,
    }
    meta_out.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(f"\nWrote {csv_out.name}: {len(df)} communes")
    print(f"Wrote {geojson_out.name}")
    print(f"Wrote {meta_out.name}")
    print(f"\n  Totals — super: {int(df['food_n_supermarket'].sum())}, "
          f"fast food: {int(df['food_n_fastfood'].sum())}, "
          f"convenience: {int(df['food_n_convenience'].sum())}")
    print(f"\nHealthiest: {[r[0] for r in top5]}")
    print(f"Worst: {[r[0] for r in bot5]}")

    return df, gdf_out


if __name__ == "__main__":
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    build_food_environment_layer()

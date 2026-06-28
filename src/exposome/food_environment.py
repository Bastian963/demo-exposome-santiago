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

OSM coverage in the RM was verified adequate: supermarket=879, greengrocer=320,
marketplace=160, fast_food=2266, convenience=3351. Ferias libres are
under-mapped (160 vs ~400+ real), documented as a known bias in metadata.
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
from shapely.geometry import Point

try:
    import osmnx as ox
except ImportError as e:
    raise ImportError("osmnx is required: conda install -c conda-forge osmnx") from e

try:
    from . import boundaries, config as _config
except ImportError:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    import exposome.boundaries as boundaries  # type: ignore[no-redef]
    import exposome.config as _config  # type: ignore[no-redef]

_EXPECTED_COMMUNES = 52
_CRS_METRIC = "EPSG:32719"
_GRID_SPACING_M = 1000
_NO_SUPERMARKET_DIST_M = 50_000   # sentinel for communes with no supermarket
_DEDUP_RADIUS_M = 25              # retail outlets within 25 m = same place
_RETRY_ATTEMPTS = 3
_RETRY_SLEEP_S = 15
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

def _fetch_region_features(poly_4326, tags: dict, label: str) -> gpd.GeoDataFrame:
    """Download OSM features within polygon, with retry + backoff."""
    last_exc: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                gdf = ox.features_from_polygon(poly_4326, tags=tags)
            if gdf is not None and len(gdf) > 0:
                return gdf.reset_index()
            return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")
        except Exception as exc:
            last_exc = exc
            if attempt < _RETRY_ATTEMPTS - 1:
                print(f"  [{label}] retry {attempt + 1}/{_RETRY_ATTEMPTS - 1}: {type(exc).__name__}")
                time.sleep(_RETRY_SLEEP_S)
    print(f"  [{label}] FAILED after {_RETRY_ATTEMPTS} attempts: {last_exc!r}")
    return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")


def _to_points(gdf: gpd.GeoDataFrame, metric_crs: str) -> gpd.GeoDataFrame:
    """Convert any geometry to representative point in metric CRS."""
    if gdf.empty or len(gdf) == 0:
        return gpd.GeoDataFrame({"geometry": []}, crs=metric_crs)
    gdf_m = gdf.to_crs(metric_crs).copy()
    gdf_m["geometry"] = gdf_m.geometry.representative_point()
    return gdf_m[["geometry"]]


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


def _build_grid(communes_metric: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    pieces = [_build_commune_grid(row, _GRID_SPACING_M, _CRS_METRIC)
              for _, row in communes_metric.iterrows()]
    return gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), crs=_CRS_METRIC)


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
    ox.settings.requests_timeout = 300
    ox.settings.log_console = False

    # --- 1. Boundaries ---
    communes_cache = cache_dir / f"{city}_communes.geojson"
    gdf_communes = boundaries.get_communes(cfg, cache_path=communes_cache)
    communes_metric = gdf_communes[["name", "geometry"]].to_crs(_CRS_METRIC)
    if len(communes_metric) != _EXPECTED_COMMUNES:
        raise ValueError(f"Expected {_EXPECTED_COMMUNES} communes, got {len(communes_metric)}")

    poly_4326 = gdf_communes.to_crs("EPSG:4326").union_all()

    # --- 2. Download each category (cached) ---
    cat_points: dict[str, gpd.GeoDataFrame] = {}
    for i, (cat, tags) in enumerate(_CATEGORIES.items()):
        cache_f = cache_dir / f"{city}_food_{cat}.geojson"
        if resume and cache_f.exists():
            print(f"  [{cat}] loading from cache …")
            gdf_raw = gpd.read_file(cache_f)
        else:
            print(f"  [{cat}] downloading from OSM …")
            gdf_raw = _fetch_region_features(poly_4326, tags, cat)
            if len(gdf_raw) > 0:
                gdf_raw.to_crs("EPSG:4326").to_file(cache_f, driver="GeoJSON")
            if i < len(_CATEGORIES) - 1:
                time.sleep(_BETWEEN_QUERIES_S)
        pts = _to_points(gdf_raw, _CRS_METRIC)
        deduped = _deduplicate_by_cluster(pts, _DEDUP_RADIUS_M)
        cat_points[cat] = deduped
        print(f"    → {len(gdf_raw)} raw → {len(deduped)} unique")

    # --- 3. Count per commune ---
    print("  Counting outlets per commune …")
    counts = {cat: _count_within(pts, communes_metric) for cat, pts in cat_points.items()}

    # --- 4. Distance to nearest supermarket (food desert access) ---
    print("  Building 1 km grid and computing supermarket access …")
    grid = _build_grid(communes_metric)
    grid = _nearest_dist(grid, cat_points["supermarket"], "dist_super_m",
                         fallback=_NO_SUPERMARKET_DIST_M)
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

    ordered_cols = [
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
        "deduplication_radius_m": _DEDUP_RADIUS_M,
        "grid_spacing_m": _GRID_SPACING_M,
        "crs_metric": _CRS_METRIC,
        "method": (
            "Food outlets downloaded per category for the RM via osmnx "
            "features_from_polygon (cached). Deduplicated at 25 m. mRFEI = "
            "healthy / (healthy + unhealthy) × 100 per commune. food_swamp_ratio "
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

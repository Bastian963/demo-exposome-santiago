"""Public transport accessibility exposome layer from OpenStreetMap.

Measures commune-level access to public transit infrastructure:
  - Bus stops (RED/Transantiago: highway=bus_stop)
  - Metro de Santiago stations (Lines 1-7, filtered to Metro S.A. only)
  - EFE/MetroTren rail stations (separate informative column)

Distances computed on a 1 km grid (Euclidean), following healthcare.py pattern.
Coverage metrics (% area within threshold) proxy population-level access.

Evidence: mobility constraints limit social participation and healthcare access
in older adults, increasing social isolation — a Lancet 2024 dementia risk factor.
(Musselwhite et al., Ageing Soc 2015; Lord et al., J Transp Geogr 2011)
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
_METRO_NO_DATA_DIST_M = 50_000   # sentinel for communes with no metro access
_RETRY_ATTEMPTS = 3
_RETRY_SLEEP_S = 10

# OSM download tags (broad; filtering happens in Python after download)
_OSM_TAGS_BUS = {"highway": "bus_stop"}
_OSM_TAGS_METRO = {"railway": ["station", "halt", "subway_entrance"]}

# Coverage distance thresholds (metres)
_BUS_COVER_300 = 300    # WHO ideal: walkable to bus in < 5 min
_BUS_COVER_500 = 500    # MINVU / OMS standard
_METRO_COVER_1000 = 1000  # ~15 min walk to metro


# ---------------------------------------------------------------------------
# Metro feature filtering and deduplication
# ---------------------------------------------------------------------------

def _filter_metro_features(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Split raw OSM metro download into Metro S.A. features and EFE/other rail.

    Returns (metro_sa, efe_rail):
        metro_sa  — subway_entrance nodes + Metro S.A. station nodes (for distance calc)
        efe_rail  — EFE / MetroTren / other railway stations (informative only)
    """
    if gdf.empty or len(gdf) == 0:
        empty = gpd.GeoDataFrame({"geometry": []}, crs=gdf.crs if gdf.crs else "EPSG:4326")
        return empty, empty

    railway = gdf.get("railway", pd.Series("", index=gdf.index)).fillna("")
    station = gdf.get("station", pd.Series("", index=gdf.index)).fillna("")
    operator = gdf.get("operator", pd.Series("", index=gdf.index)).fillna("")

    is_subway_entrance = railway == "subway_entrance"
    is_metro_station = (railway == "station") & (
        (station == "subway") | operator.str.contains("Metro S.A.", case=False, na=False)
    )
    is_metro_sa = is_subway_entrance | is_metro_station

    is_other_rail = railway.isin(["station", "halt"]) & ~is_metro_station

    metro_sa = gdf[is_metro_sa].copy().reset_index(drop=True)
    efe_rail = gdf[is_other_rail].copy().reset_index(drop=True)
    return metro_sa, efe_rail


def _deduplicate_by_cluster(gdf: gpd.GeoDataFrame, radius_m: float) -> gpd.GeoDataFrame:
    """Cluster features within radius_m and return one representative point per cluster.

    Uses cKDTree with a greedy nearest-neighbor pass. Representative point is
    the mean centroid of the cluster in the metric CRS.
    """
    if gdf.empty or len(gdf) == 0:
        return gdf

    pts = np.vstack([gdf.geometry.x, gdf.geometry.y]).T
    tree = cKDTree(pts)
    visited: set[int] = set()
    cluster_centers: list[tuple[float, float]] = []

    for i in range(len(pts)):
        if i not in visited:
            neighbors = tree.query_ball_point(pts[i], radius_m)
            visited.update(neighbors)
            cluster_pts = pts[neighbors]
            cluster_centers.append((cluster_pts[:, 0].mean(), cluster_pts[:, 1].mean()))

    deduped = gpd.GeoDataFrame(
        {"geometry": [Point(x, y) for x, y in cluster_centers]},
        crs=gdf.crs,
    )
    return deduped


# ---------------------------------------------------------------------------
# Data acquisition
# ---------------------------------------------------------------------------

def _fetch_region_features(region_query: str, tags: dict, label: str) -> gpd.GeoDataFrame:
    """Download OSM features for the entire region (one Overpass query)."""
    last_exc: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                gdf = ox.features_from_place(region_query, tags=tags)
            if gdf is not None and len(gdf) > 0:
                return gdf.reset_index()
            return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")
        except Exception as exc:
            last_exc = exc
            if attempt < _RETRY_ATTEMPTS - 1:
                print(f"  [{label}] retry {attempt + 1}/{_RETRY_ATTEMPTS - 1}: {exc!r}")
                time.sleep(_RETRY_SLEEP_S)
    print(f"  [{label}] failed after {_RETRY_ATTEMPTS} attempts: {last_exc!r}")
    return gpd.GeoDataFrame({"geometry": []}, crs="EPSG:4326")


def _to_points(gdf: gpd.GeoDataFrame, metric_crs: str) -> gpd.GeoDataFrame:
    """Convert any geometry to representative point in metric CRS."""
    if gdf.empty or len(gdf) == 0:
        return gdf
    gdf_m = gdf.to_crs(metric_crs).copy()
    gdf_m["geometry"] = gdf_m.geometry.representative_point()
    return gdf_m


# ---------------------------------------------------------------------------
# Distance grid (same pattern as healthcare.py)
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
            geometry=[row.geometry.representative_point()],
            crs=crs,
        )
    return grid


def _build_grid(communes_metric: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    pieces = [_build_commune_grid(row, _GRID_SPACING_M, _CRS_METRIC)
              for _, row in communes_metric.iterrows()]
    return gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), crs=_CRS_METRIC)


def _nearest_dist(grid: gpd.GeoDataFrame, facilities_metric: gpd.GeoDataFrame,
                  col: str, fallback: float) -> gpd.GeoDataFrame:
    """Nearest-facility Euclidean distance via cKDTree; fallback when no facilities."""
    out = grid.copy()
    if facilities_metric.empty or len(facilities_metric) == 0:
        out[col] = fallback
        return out
    tree = cKDTree(np.vstack([facilities_metric.geometry.x,
                               facilities_metric.geometry.y]).T)
    coords = np.vstack([grid.geometry.x, grid.geometry.y]).T
    dists, _ = tree.query(coords, k=1)
    out[col] = dists
    return out


# ---------------------------------------------------------------------------
# Per-commune aggregation
# ---------------------------------------------------------------------------

def _count_within(pts_metric: gpd.GeoDataFrame,
                  communes_metric: gpd.GeoDataFrame) -> pd.Series:
    """Count points within each commune; returns Series indexed by commune name."""
    if pts_metric.empty or len(pts_metric) == 0:
        return pd.Series(0, index=communes_metric["name"])
    joined = gpd.sjoin(
        pts_metric[["geometry"]],
        communes_metric[["name", "geometry"]],
        how="inner", predicate="within",
    )
    counts = joined.groupby("name").size()
    return counts.reindex(communes_metric["name"], fill_value=0)


# ---------------------------------------------------------------------------
# Composite index
# ---------------------------------------------------------------------------

def _compute_transit_index(df: pd.DataFrame) -> pd.Series:
    """Z-score composite transit accessibility index (0–100).

    Metrics:
        transit_bus_density (+), transit_metro_density (+),
        transit_mean_dist_bus_m (–), transit_bus_coverage_500m (+).
    """
    positive = ["transit_bus_density", "transit_metro_density",
                "transit_bus_coverage_500m"]
    negative = ["transit_mean_dist_bus_m"]

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

def build_public_transport_layer(
    city: str = "santiago",
    out_dir: Path = Path("data/processed"),
    cache_dir: Path = Path("cache"),
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Build the public transport accessibility layer and write CSV/GeoJSON/metadata."""
    out_dir = Path(out_dir)
    cache_dir = Path(cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    cfg = _config.load_config(city)
    region_query = cfg["region_query"]

    ox.settings.requests_timeout = 300
    ox.settings.log_console = False

    # --- 1. Boundaries ---
    communes_cache = cache_dir / f"{city}_communes.geojson"
    gdf_communes = boundaries.get_communes(cfg, cache_path=communes_cache)
    communes_metric = gdf_communes[["name", "geometry"]].to_crs(_CRS_METRIC)

    if len(communes_metric) != _EXPECTED_COMMUNES:
        raise ValueError(f"Expected {_EXPECTED_COMMUNES} communes, got {len(communes_metric)}")

    # --- 2. Download OSM data ---
    bus_cache = cache_dir / f"{city}_transit_bus_stops.geojson"
    metro_raw_cache = cache_dir / f"{city}_transit_metro.geojson"

    if bus_cache.exists():
        print("  Bus stops: loading from cache …")
        gdf_bus_raw = gpd.read_file(bus_cache)
    else:
        print("  Bus stops: downloading from OSM …")
        gdf_bus_raw = _fetch_region_features(region_query, _OSM_TAGS_BUS, "bus")
        if len(gdf_bus_raw) > 0:
            gdf_bus_raw.to_crs("EPSG:4326").to_file(bus_cache, driver="GeoJSON")
        print(f"    → {len(gdf_bus_raw)} raw bus stops")

    if metro_raw_cache.exists():
        print("  Metro (raw): loading from cache …")
        gdf_metro_raw = gpd.read_file(metro_raw_cache)
    else:
        print("  Metro: downloading from OSM …")
        gdf_metro_raw = _fetch_region_features(region_query, _OSM_TAGS_METRO, "metro")
        if len(gdf_metro_raw) > 0:
            gdf_metro_raw.to_crs("EPSG:4326").to_file(metro_raw_cache, driver="GeoJSON")
        print(f"    → {len(gdf_metro_raw)} raw metro features")

    # --- 3. Filter and deduplicate ---
    # Convert to metric CRS for accurate distance-based operations
    bus_pts_all = _to_points(gdf_bus_raw, _CRS_METRIC)
    gdf_metro_metric_raw = _to_points(gdf_metro_raw, _CRS_METRIC)

    metro_sa_pts, efe_pts = _filter_metro_features(gdf_metro_metric_raw)

    # Deduplicated counts
    bus_deduped = _deduplicate_by_cluster(bus_pts_all, radius_m=30)
    metro_deduped = _deduplicate_by_cluster(metro_sa_pts, radius_m=150)
    efe_deduped = _deduplicate_by_cluster(efe_pts, radius_m=150)

    print(f"  Bus stops: {len(gdf_bus_raw)} raw → {len(bus_deduped)} unique (30m cluster)")
    print(f"  Metro S.A.: {len(gdf_metro_raw)} raw → {len(metro_sa_pts)} filtered → {len(metro_deduped)} unique stations (150m cluster)")
    print(f"  EFE/rail: {len(efe_deduped)} unique stations")

    # For distance computation: use all filtered features (more spatial coverage)
    metro_dist_pts = metro_sa_pts  # all entrances + stations for distance calc

    # --- 4. Count facilities per commune ---
    print("  Counting facilities per commune …")
    n_bus = _count_within(bus_deduped, communes_metric)
    n_metro = _count_within(metro_deduped, communes_metric)
    n_rail = _count_within(efe_deduped, communes_metric)

    # --- 5. Distance grid ---
    print("  Building 1 km grid and computing distances …")
    grid = _build_grid(communes_metric)
    grid = _nearest_dist(grid, bus_pts_all, "dist_bus_m", fallback=_METRO_NO_DATA_DIST_M)
    grid = _nearest_dist(grid, metro_dist_pts, "dist_metro_m", fallback=_METRO_NO_DATA_DIST_M)

    # Aggregate distance statistics per commune
    def _agg_dist(g: gpd.GeoDataFrame, dcol: str) -> pd.DataFrame:
        return g.groupby("name")[dcol].agg(
            **{
                f"mean_{dcol}": "mean",
                f"p90_{dcol}": lambda x: x.quantile(0.90),
                f"cover_{dcol}_300": lambda x: (x <= _BUS_COVER_300).mean() if dcol == "dist_bus_m" else None,
                f"cover_{dcol}_500": lambda x: (x <= _BUS_COVER_500).mean() if dcol == "dist_bus_m" else None,
                f"cover_{dcol}_1000": lambda x: (x <= _METRO_COVER_1000).mean() if dcol == "dist_metro_m" else None,
            }
        ).reset_index()

    dist_bus_agg = grid.groupby("name")["dist_bus_m"].agg(
        transit_mean_dist_bus_m="mean",
        transit_p90_dist_bus_m=lambda x: x.quantile(0.90),
        transit_bus_coverage_300m=lambda x: (x <= _BUS_COVER_300).mean(),
        transit_bus_coverage_500m=lambda x: (x <= _BUS_COVER_500).mean(),
    ).reset_index()

    dist_metro_agg = grid.groupby("name")["dist_metro_m"].agg(
        transit_mean_dist_metro_m="mean",
        transit_metro_coverage_1000m=lambda x: (x <= _METRO_COVER_1000).mean(),
    ).reset_index()

    # --- 6. Assemble per-commune table ---
    areas_km2 = communes_metric.set_index("name")["geometry"].area / 1e6

    df = pd.DataFrame({"name": communes_metric["name"].values}).set_index("name")
    df["transit_n_bus_stops"] = n_bus.values
    df["transit_n_metro_stations"] = n_metro.values
    df["transit_n_rail_stations"] = n_rail.values
    df["transit_bus_density"] = (df["transit_n_bus_stops"] / areas_km2).round(3)
    df["transit_metro_density"] = (df["transit_n_metro_stations"] / areas_km2).round(3)
    df["transit_has_metro"] = (df["transit_n_metro_stations"] > 0).astype(int)

    df = df.join(dist_bus_agg.set_index("name")).join(dist_metro_agg.set_index("name"))

    # Communes with no metro: sentinel distance
    no_metro = df["transit_n_metro_stations"] == 0
    df.loc[no_metro, "transit_mean_dist_metro_m"] = float(_METRO_NO_DATA_DIST_M)
    df.loc[no_metro, "transit_metro_coverage_1000m"] = 0.0

    df = df.reset_index()

    # --- 7. Composite index ---
    df["transit_index"] = _compute_transit_index(df)

    # Round
    pct_cols = ["transit_bus_coverage_300m", "transit_bus_coverage_500m",
                "transit_metro_coverage_1000m"]
    for col in pct_cols:
        df[col] = df[col].round(3)
    for col in [c for c in df.columns if df[c].dtype == float and c not in pct_cols]:
        df[col] = df[col].round(1)

    ordered_cols = [
        "name",
        "transit_n_bus_stops",
        "transit_n_metro_stations",
        "transit_n_rail_stations",
        "transit_bus_density",
        "transit_metro_density",
        "transit_mean_dist_bus_m",
        "transit_p90_dist_bus_m",
        "transit_bus_coverage_300m",
        "transit_bus_coverage_500m",
        "transit_mean_dist_metro_m",
        "transit_metro_coverage_1000m",
        "transit_has_metro",
        "transit_index",
    ]
    df = df[ordered_cols].sort_values("name").reset_index(drop=True)

    # --- 8. GeoDataFrame ---
    gdf_out = gdf_communes[["name", "geometry"]].merge(df, on="name", how="left")
    gdf_out = gpd.GeoDataFrame(gdf_out, geometry="geometry", crs=gdf_communes.crs)
    gdf_out = gdf_out.sort_values("name").reset_index(drop=True)

    # --- 9. Write outputs ---
    csv_out = out_dir / f"{city}_public_transport.csv"
    geojson_out = out_dir / f"{city}_public_transport.geojson"
    meta_out = out_dir / f"{city}_public_transport_metadata.json"

    df.to_csv(csv_out, index=False)
    gdf_out.to_file(geojson_out, driver="GeoJSON")

    top5 = df.nlargest(5, "transit_index")[["name", "transit_index"]].values.tolist()
    bot5 = df.nsmallest(5, "transit_index")[["name", "transit_index"]].values.tolist()

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "source": "OpenStreetMap via osmnx",
        "osm_tags": {
            "bus_stop": "highway=bus_stop",
            "metro": "railway=[station,halt,subway_entrance] — filtered post-download to Metro S.A. only",
            "rail": "railway=station/halt — EFE/MetroTren (informative only, not in index)",
        },
        "deduplication": {
            "bus_cluster_radius_m": 30,
            "metro_cluster_radius_m": 150,
        },
        "coverage_thresholds_m": {
            "bus_300m": _BUS_COVER_300,
            "bus_500m": _BUS_COVER_500,
            "metro_1000m": _METRO_COVER_1000,
        },
        "grid_spacing_m": _GRID_SPACING_M,
        "crs_metric": _CRS_METRIC,
        "method": (
            "Bus stops and metro features downloaded for the entire region via "
            "osmnx features_from_place. Metro features filtered to Metro S.A. only "
            "(subway_entrance nodes + station nodes with station=subway or operator=Metro S.A.). "
            f"Bus stops deduplicated at {30}m; metro stations at {150}m. "
            "Distance metrics computed on 1 km grid. transit_index = z-scored composite "
            "of bus_density (+), metro_density (+), bus_coverage_500m (+), "
            "mean_dist_bus_m (–); rescaled 0–100."
        ),
        "evidence": (
            "Mobility constraints limit social participation and healthcare access "
            "in older adults, increasing social isolation — a Lancet 2024 modifiable "
            "dementia risk factor. (Musselwhite et al., Ageing Soc 2015; "
            "Lord et al., J Transp Geogr 2011)"
        ),
        "n_communes": len(df),
        "n_communes_with_metro": int(df["transit_has_metro"].sum()),
        "n_bus_stops_deduplicated": int(len(bus_deduped)),
        "n_metro_stations_deduplicated": int(len(metro_deduped)),
        "n_rail_stations_efe": int(len(efe_deduped)),
        "top5_most_accessible": top5,
        "bot5_least_accessible": bot5,
        "columns": ordered_cols,
    }
    meta_out.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(f"\nWrote {csv_out.name}: {len(df)} communes")
    print(f"Wrote {geojson_out.name}")
    print(f"Wrote {meta_out.name}")
    print(f"\n  Communes with metro: {int(df['transit_has_metro'].sum())}/52")
    print(f"  Unique bus stops: {len(bus_deduped)}")
    print(f"  Unique metro stations (Metro S.A.): {len(metro_deduped)}")
    print(f"\nTop accessible: {[r[0] for r in top5]}")
    print(f"Least accessible: {[r[0] for r in bot5]}")

    return df, gdf_out


if __name__ == "__main__":
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    build_public_transport_layer()

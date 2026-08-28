"""Social-cognitive infrastructure exposome layer from OpenStreetMap.

This layer is an ecological proxy for opportunities for social participation,
cognitive stimulation, and community activity. It does not measure individual
loneliness, social isolation, cognition, or dementia risk.

The raw inventory keeps a broad social/recreation view for audit, while the
curated inventory that feeds the master table is intentionally more
civic-cultural: it downweights recreational overcounting by excluding private
access, pitches, and swimming pools from the curated signal. Distances are
computed on a 1 km grid, matching the public transport and healthcare
accessibility pattern used elsewhere in this repo.
"""
from __future__ import annotations

import json
import os
import time
import warnings
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
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


DEFAULT_CATEGORY_ORDER = [
    "library",
    "cultural",
    "community",
    "senior",
    "sports",
    "public_space",
]
DEFAULT_CIVIC_CATEGORIES = ["library", "cultural", "community", "senior"]
DEFAULT_CURATED_ACCESS_EXCLUDE = ["private", "customers", "no", "permit"]
DEFAULT_CURATED_SPORTS_LEISURE = ["sports_centre", "stadium", "fitness_centre"]
DEFAULT_CURATED_PUBLIC_SPACE = {
    "leisure": ["recreation_ground", "park", "garden", "dog_park", "playground"],
    "landuse": ["village_green", "recreation_ground"],
    "place": ["square"],
}
SOCIAL_INDEX_WEIGHTS = {
    "civic": 0.45,
    "access": 0.35,
    "recreation": 0.20,
}

_RETRY_ATTEMPTS = 3
_RETRY_SLEEP_S = 10


def _empty_gdf(crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=crs)


def _iter_tag_clauses(tags: dict[str, Any], bbox: dict[str, float]) -> list[str]:
    south = float(bbox["lat_min"])
    west = float(bbox["lon_min"])
    north = float(bbox["lat_max"])
    east = float(bbox["lon_max"])
    bbox_text = f"({south},{west},{north},{east})"

    clauses: list[str] = []
    for key, raw_values in tags.items():
        if raw_values is True:
            clauses.append(f'nwr["{key}"]{bbox_text};')
            continue
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        for value in values:
            clauses.append(f'nwr["{key}"="{value}"]{bbox_text};')
    return clauses


def _fetch_overpass_centers(
    tags: dict[str, Any],
    bbox: dict[str, float],
    overpass_urls: list[str],
    timeout_s: int,
) -> gpd.GeoDataFrame:
    """Fetch OSM elements as point centers with tags using direct Overpass QL."""
    clauses = _iter_tag_clauses(tags, bbox)
    last_exc: Exception | None = None
    all_rows: list[dict[str, Any]] = []

    for clause in clauses:
        query = f"[out:json][timeout:{timeout_s}];\n{clause}\nout center tags;"
        clause_rows: list[dict[str, Any]] | None = None

        for url in overpass_urls:
            endpoint = f"{url.rstrip('/')}/interpreter"
            for attempt in range(_RETRY_ATTEMPTS):
                try:
                    response = requests.post(
                        endpoint,
                        data={"data": query},
                        headers={"User-Agent": "BrainLatExposome/0.1 (research; local pipeline)"},
                        timeout=timeout_s + 15,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    rows: list[dict[str, Any]] = []
                    for element in payload.get("elements", []):
                        if "lat" in element and "lon" in element:
                            lat = element["lat"]
                            lon = element["lon"]
                        else:
                            center = element.get("center") or {}
                            lat = center.get("lat")
                            lon = center.get("lon")
                        if lat is None or lon is None:
                            continue

                        rows.append(
                            {
                                "osm_type": element.get("type"),
                                "osmid": element.get("id"),
                                **element.get("tags", {}),
                                "geometry": Point(float(lon), float(lat)),
                            }
                        )
                    clause_rows = rows
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < _RETRY_ATTEMPTS - 1:
                        print(
                            f"  Direct Overpass retry {attempt + 1}/{_RETRY_ATTEMPTS - 1} "
                            f"via {url}: {exc!r}"
                        )
                        time.sleep(_RETRY_SLEEP_S)
            if clause_rows is not None:
                break
            print(f"  Direct Overpass endpoint failed for clause {clause!r}: {url}")

        if clause_rows is None:
            print(f"  Direct Overpass clause failed after {len(overpass_urls)} endpoint(s): {clause!r}")
        else:
            all_rows.extend(clause_rows)
            time.sleep(0.2)

    if not all_rows:
        print(f"  Direct Overpass download returned no rows: {last_exc!r}")
        return _empty_gdf()

    gdf = gpd.GeoDataFrame(all_rows, geometry="geometry", crs="EPSG:4326")
    if {"osm_type", "osmid"}.issubset(gdf.columns):
        gdf = gdf.drop_duplicates(["osm_type", "osmid"]).reset_index(drop=True)
    return gdf


def _fetch_region_features(
    region_query: str,
    tags: dict[str, Any],
    overpass_urls: list[str],
    bbox: dict[str, float] | None = None,
    timeout_s: int = 120,
) -> gpd.GeoDataFrame:
    """Download OSM features for the configured region."""
    if bbox:
        return _fetch_overpass_centers(tags, bbox, overpass_urls, timeout_s)

    last_exc: Exception | None = None
    original_url = ox.settings.overpass_url
    env_url = os.environ.get("OSMNX_OVERPASS_URL")
    urls = [env_url, *overpass_urls] if env_url else list(overpass_urls)
    urls = list(dict.fromkeys([url.rstrip("/") for url in urls if url]))

    for url in urls:
        ox.settings.overpass_url = url
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    if bbox:
                        bbox_tuple = (
                            float(bbox["lon_min"]),
                            float(bbox["lat_min"]),
                            float(bbox["lon_max"]),
                            float(bbox["lat_max"]),
                        )
                        gdf = ox.features_from_bbox(bbox=bbox_tuple, tags=tags)
                    else:
                        gdf = ox.features_from_place(region_query, tags=tags)
                ox.settings.overpass_url = original_url
                if gdf is None or len(gdf) == 0:
                    return _empty_gdf()
                return gdf.reset_index()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < _RETRY_ATTEMPTS - 1:
                    print(
                        f"  OSM retry {attempt + 1}/{_RETRY_ATTEMPTS - 1} "
                        f"via {url}: {exc!r}"
                    )
                    time.sleep(_RETRY_SLEEP_S)
        print(f"  OSM endpoint failed: {url}")

    ox.settings.overpass_url = original_url
    print(f"  OSM download failed after trying {len(urls)} endpoint(s): {last_exc!r}")
    return _empty_gdf()


def _merge_feature_frames(frames: list[gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    non_empty = [gdf for gdf in frames if gdf is not None and len(gdf) > 0]
    if not non_empty:
        return _empty_gdf()
    normalized = []
    for gdf in non_empty:
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        normalized.append(gdf.to_crs("EPSG:4326"))
    merged = gpd.GeoDataFrame(pd.concat(normalized, ignore_index=True), crs="EPSG:4326")
    return merged


def _load_or_fetch_group(
    city: str,
    group_name: str,
    tags: dict[str, Any],
    cfg: dict[str, Any],
    cache_dir: Path,
    overpass_urls: list[str],
    timeout_s: int,
) -> gpd.GeoDataFrame:
    cache_path = cache_dir / f"{city}_social_infrastructure_osm_{group_name}.geojson"
    if cache_path.exists():
        print(f"  {group_name}: loading OSM cache ...")
        return gpd.read_file(cache_path)

    print(f"  {group_name}: downloading from OSM ...")
    gdf = _fetch_region_features(
        cfg["region_query"],
        tags,
        overpass_urls,
        bbox=cfg.get("bbox"),
        timeout_s=timeout_s,
    )
    if len(gdf) > 0:
        gdf.to_crs(cfg["crs"]["geographic"]).to_file(cache_path, driver="GeoJSON")
    print(f"    -> {len(gdf)} raw features")
    return gdf


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip().lower() for v in value if str(v).strip()]
    if isinstance(value, tuple | set):
        return [str(v).strip().lower() for v in value if str(v).strip()]
    if pd.isna(value):
        return []
    return [part.strip().lower() for part in str(value).split(";") if part.strip()]


def _rule_matches(row: pd.Series, rule: dict[str, Any]) -> bool:
    key = str(rule["tag"])
    values = {str(v).strip().lower() for v in rule.get("values", [])}
    if key not in row.index:
        return False
    row_values = set(_as_list(row.get(key)))
    if not row_values:
        return False
    return bool(row_values & values)


def _feature_categories(row: pd.Series, categories: dict[str, list[dict[str, Any]]]) -> list[str]:
    matched: list[str] = []
    for category, rules in categories.items():
        if any(_rule_matches(row, rule) for rule in rules):
            matched.append(category)
    return matched


def _classify_features(
    raw: gpd.GeoDataFrame,
    categories: dict[str, list[dict[str, Any]]],
) -> gpd.GeoDataFrame:
    """Keep only OSM features matching at least one configured category."""
    if raw.empty or len(raw) == 0:
        return _empty_gdf(raw.crs or "EPSG:4326")

    gdf = raw.copy()
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    if gdf.empty:
        return _empty_gdf(raw.crs or "EPSG:4326")

    gdf["social_categories"] = gdf.apply(_feature_categories, axis=1, categories=categories)
    gdf = gdf[gdf["social_categories"].map(bool)].copy().reset_index(drop=True)
    return gdf


def _to_points(gdf: gpd.GeoDataFrame, metric_crs: str) -> gpd.GeoDataFrame:
    """Convert all geometries to representative points in a metric CRS."""
    if gdf.empty or len(gdf) == 0:
        return _empty_gdf(metric_crs)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    out = gdf.to_crs(metric_crs).copy()
    out["geometry"] = out.geometry.representative_point()
    return gpd.GeoDataFrame(out, geometry="geometry", crs=metric_crs)


def _deduplicate_by_cluster(gdf: gpd.GeoDataFrame, radius_m: float) -> gpd.GeoDataFrame:
    """Cluster nearby points and return one representative point per cluster."""
    if gdf.empty or len(gdf) == 0:
        return _empty_gdf(str(gdf.crs) if gdf.crs else "EPSG:4326")

    pts = np.vstack([gdf.geometry.x, gdf.geometry.y]).T
    tree = cKDTree(pts)
    visited: set[int] = set()
    centers: list[Point] = []

    for i in range(len(pts)):
        if i in visited:
            continue
        neighbors = tree.query_ball_point(pts[i], radius_m)
        visited.update(neighbors)
        cluster_pts = pts[neighbors]
        centers.append(Point(cluster_pts[:, 0].mean(), cluster_pts[:, 1].mean()))

    return gpd.GeoDataFrame({"geometry": centers}, geometry="geometry", crs=gdf.crs)


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


def _build_grid(communes_metric: gpd.GeoDataFrame, spacing_m: int, crs: str) -> gpd.GeoDataFrame:
    pieces = [_build_commune_grid(row, spacing_m, crs) for _, row in communes_metric.iterrows()]
    return gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), crs=crs)


def _nearest_distances(
    grid: gpd.GeoDataFrame,
    points_metric: gpd.GeoDataFrame,
    no_data_dist_m: float,
) -> pd.Series:
    if points_metric.empty or len(points_metric) == 0:
        return pd.Series(no_data_dist_m, index=grid.index, dtype=float)
    tree = cKDTree(np.vstack([points_metric.geometry.x, points_metric.geometry.y]).T)
    coords = np.vstack([grid.geometry.x, grid.geometry.y]).T
    dists, _ = tree.query(coords, k=1)
    return pd.Series(dists, index=grid.index, dtype=float).clip(upper=no_data_dist_m)


def _count_within(points_metric: gpd.GeoDataFrame, communes_metric: gpd.GeoDataFrame) -> pd.Series:
    if points_metric.empty or len(points_metric) == 0:
        return pd.Series(0, index=communes_metric["name"], dtype=int)
    joined = gpd.sjoin(
        points_metric[["geometry"]],
        communes_metric[["name", "geometry"]],
        how="inner",
        predicate="within",
    )
    counts = joined.groupby("name").size()
    return counts.reindex(communes_metric["name"], fill_value=0).astype(int)


def _load_population(city: str, out_dir: Path) -> pd.Series:
    """Load commune population from existing processed layers."""
    candidates = [
        (out_dir / f"{city}_demography.csv", "pop_total"),
        (out_dir / f"{city}_exposome_master.csv", "demo_pop_total"),
        (out_dir / "socioeconomic_exposome_rm_santiago.csv", "poblacion"),
    ]
    for path, col in candidates:
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if {"name", col}.issubset(df.columns):
            return df.set_index("name")[col].astype(float)
    raise FileNotFoundError(
        "Could not find population data. Run scripts/run_demography.py or "
        "scripts/build_master_exposome.py first."
    )


def _zscore(values: pd.Series, positive: bool = True) -> pd.Series:
    x = values.astype(float)
    std = x.std(ddof=0)
    if std == 0 or np.isnan(std):
        z = pd.Series(0.0, index=x.index)
    else:
        z = (x - x.mean()) / std
    return z if positive else -z


def _rescale_0_100(values: pd.Series) -> pd.Series:
    x = values.astype(float)
    xmin = x.min()
    xmax = x.max()
    if np.isnan(xmin) or np.isnan(xmax) or xmax == xmin:
        return pd.Series(50.0, index=x.index)
    return (x - xmin) / (xmax - xmin) * 100


def _winsorize_upper(values: pd.Series, quantile: float = 0.90) -> pd.Series:
    upper = values.quantile(quantile)
    return values.clip(upper=upper)


def _access_tokens(value: Any) -> set[str]:
    return set(_as_list(value))


def _normalize_access_rule_value(value: Any) -> str:
    if value is False:
        return "no"
    if value is True:
        return "yes"
    return str(value).strip().lower()


def _has_any_access_token(tokens: set[str], values: set[str]) -> bool:
    return bool(tokens & values)


def _build_curated_categories(raw_categories: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    curated = deepcopy(raw_categories)
    curated["sports"] = [
        {
            "tag": "leisure",
            "values": DEFAULT_CURATED_SPORTS_LEISURE,
        }
    ]
    curated["public_space"] = [
        {"tag": tag, "values": values}
        for tag, values in DEFAULT_CURATED_PUBLIC_SPACE.items()
    ]
    return curated


def _validate_output(df: pd.DataFrame, expected_communes: int) -> None:
    if len(df) != expected_communes:
        raise ValueError(f"Expected {expected_communes} communes, got {len(df)}")
    if df["name"].duplicated().any():
        dupes = df.loc[df["name"].duplicated(), "name"].tolist()
        raise ValueError(f"Duplicate commune names: {dupes}")
    if df.isna().any().any():
        missing = df.columns[df.isna().any()].tolist()
        raise ValueError(f"Missing values in social infrastructure output: {missing}")
    if not df["social_index"].between(0, 100).all():
        raise ValueError("social_index must be bounded between 0 and 100")


def build_social_infrastructure_layer(
    city: str = "santiago",
    out_dir: Path = Path("data/processed"),
    cache_dir: Path = Path("cache"),
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Build commune-level social-cognitive infrastructure metrics."""
    cfg = _config.load_config(city)
    social_cfg = cfg["social_infrastructure"]
    out_dir = Path(out_dir)
    cache_dir = Path(cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    metric_crs = cfg["crs"]["metric"]
    geographic_crs = cfg["crs"]["geographic"]
    expected_communes = int(cfg["expected_communes"])
    grid_spacing_m = int(social_cfg.get("grid_spacing_m", 1000))
    coverage_m = [int(v) for v in social_cfg.get("coverage_m", [500, 1000])]
    no_data_dist_m = float(social_cfg.get("no_data_dist_m", 99999))
    dedupe_radius_m = float(social_cfg.get("dedupe_radius_m", 50))
    category_order = social_cfg.get("category_order", DEFAULT_CATEGORY_ORDER)
    civic_categories = social_cfg.get("civic_categories", DEFAULT_CIVIC_CATEGORIES)
    overpass_urls = social_cfg.get("overpass_urls", [ox.settings.overpass_url])
    requests_timeout_s = int(social_cfg.get("requests_timeout_s", 120))
    curated_access_exclude = {
        _normalize_access_rule_value(v)
        for v in social_cfg.get("curated_access_exclude", DEFAULT_CURATED_ACCESS_EXCLUDE)
        if _normalize_access_rule_value(v)
    }
    curated_categories = _build_curated_categories(social_cfg["categories"])

    print(f"Building social infrastructure layer for {city}")

    ox.settings.requests_timeout = requests_timeout_s
    ox.settings.log_console = False

    communes_cache = cache_dir / f"{city}_communes.geojson"
    communes = boundaries.get_communes(cfg, cache_path=communes_cache)
    communes_metric = communes[["name", "geometry"]].to_crs(metric_crs)
    areas_km2 = communes_metric.set_index("name").geometry.area / 1e6
    population = _load_population(city, out_dir).reindex(communes_metric["name"])
    if population.isna().any():
        missing = population.index[population.isna()].tolist()
        raise ValueError(f"Population data missing communes: {missing}")

    raw_cache = cache_dir / f"{city}_social_infrastructure_osm_raw.geojson"
    if raw_cache.exists():
        print("  Social POIs: loading combined OSM cache ...")
        raw = gpd.read_file(raw_cache)
    else:
        tag_groups = social_cfg.get("osm_tag_groups") or {"all": social_cfg["osm_tags"]}
        frames: list[gpd.GeoDataFrame] = []

        if social_cfg.get("reuse_greenspace_cache", True):
            green_cache = cache_dir / f"{city}_greenspace_osm.geojson"
            if green_cache.exists():
                print("  public_space: reusing greenspace OSM cache ...")
                frames.append(gpd.read_file(green_cache))

        for group_name, tags in tag_groups.items():
            frames.append(
                _load_or_fetch_group(
                    city=city,
                    group_name=group_name,
                    tags=tags,
                    cfg=cfg,
                    cache_dir=cache_dir,
                    overpass_urls=overpass_urls,
                    timeout_s=requests_timeout_s,
                )
            )

        raw = _merge_feature_frames(frames)
        if len(raw) > 0:
            raw.to_crs(geographic_crs).to_file(raw_cache, driver="GeoJSON")
    if len(raw) == 0:
        raise RuntimeError("No social infrastructure features returned from OSM.")

    classified_raw = _classify_features(raw, social_cfg["categories"])
    if len(classified_raw) == 0:
        raise RuntimeError("OSM returned features, but none matched configured categories.")

    points_raw = _to_points(classified_raw, metric_crs)
    region_union = communes_metric.geometry.union_all()
    points_raw = points_raw[points_raw.within(region_union)].copy()
    if len(points_raw) == 0:
        raise RuntimeError("No classified social infrastructure points fall inside the commune boundaries.")

    points_raw["access_tokens"] = points_raw.get("access", pd.Series(index=points_raw.index)).apply(_access_tokens)
    points_raw["curated_access_allowed"] = ~points_raw["access_tokens"].apply(
        lambda tokens: _has_any_access_token(tokens, curated_access_exclude)
    )

    raw_all_points = _deduplicate_by_cluster(points_raw.copy(), dedupe_radius_m)
    curated_points = points_raw[points_raw["curated_access_allowed"]].copy()
    curated_points["social_categories_curated"] = curated_points.apply(
        _feature_categories,
        axis=1,
        categories=curated_categories,
    )
    curated_points = curated_points[curated_points["social_categories_curated"].map(bool)].copy()
    curated_all_points = _deduplicate_by_cluster(curated_points.copy(), dedupe_radius_m)

    print(
        f"  Social POIs: {len(raw)} raw -> {len(classified_raw)} raw-classified -> "
        f"{len(raw_all_points)} unique raw -> {len(curated_all_points)} unique curated"
    )

    df = pd.DataFrame({"name": communes_metric["name"].values}).set_index("name")
    df["social_n_total_raw"] = _count_within(raw_all_points, communes_metric).values
    df["social_n_total"] = _count_within(curated_all_points, communes_metric).values

    raw_category_counts: dict[str, int] = {}
    curated_category_counts: dict[str, int] = {}
    for category in category_order:
        raw_mask = points_raw["social_categories"].apply(lambda cats: category in cats)
        raw_category_points = _deduplicate_by_cluster(points_raw[raw_mask].copy(), dedupe_radius_m)
        raw_col = f"social_n_{category}_raw"
        if category in {"sports", "public_space"}:
            df[raw_col] = _count_within(raw_category_points, communes_metric).values
        raw_category_counts[category] = int(len(raw_category_points))

        curated_mask = curated_points["social_categories_curated"].apply(lambda cats: category in cats)
        curated_category_points = _deduplicate_by_cluster(curated_points[curated_mask].copy(), dedupe_radius_m)
        curated_col = f"social_n_{category}"
        df[curated_col] = _count_within(curated_category_points, communes_metric).values
        curated_category_counts[category] = int(len(curated_category_points))

    private_customer_points = points_raw[
        points_raw["access_tokens"].apply(lambda tokens: _has_any_access_token(tokens, {"private", "customers"}))
    ].copy()
    private_customer_dedup = _deduplicate_by_cluster(private_customer_points, dedupe_radius_m)
    df["social_private_or_customer_excluded_n"] = _count_within(
        private_customer_dedup, communes_metric
    ).values

    excluded_counts_features = {
        value: int(points_raw["access_tokens"].apply(lambda tokens, v=value: v in tokens).sum())
        for value in sorted(curated_access_exclude)
    }
    excluded_counts_unique = {
        value: int(
            len(
                _deduplicate_by_cluster(
                    points_raw[
                        points_raw["access_tokens"].apply(lambda tokens, v=value: v in tokens)
                    ].copy(),
                    dedupe_radius_m,
                )
            )
        )
        for value in sorted(curated_access_exclude)
    }

    category_cols = [f"social_n_{category}" for category in category_order]
    civic_cols = [f"social_n_{category}" for category in civic_categories]
    df["social_category_diversity"] = (df[category_cols] > 0).sum(axis=1).astype(int)
    df["social_civic_diversity"] = (df[civic_cols] > 0).sum(axis=1).astype(int)
    df["social_density_per_km2"] = df["social_n_total"] / areas_km2
    df["social_points_per_10k_raw"] = np.where(
        population > 0,
        df["social_n_total_raw"] / population * 10_000,
        0.0,
    )
    df["social_points_per_10k"] = np.where(
        population > 0,
        df["social_n_total"] / population * 10_000,
        0.0,
    )
    df["social_civic_points_per_10k"] = np.where(
        population > 0,
        df[civic_cols].sum(axis=1) / population * 10_000,
        0.0,
    )
    df["social_recreation_points_per_10k"] = np.where(
        population > 0,
        (df["social_n_sports"] + df["social_n_public_space"]) / population * 10_000,
        0.0,
    )

    print("  Building access grid and computing nearest distances ...")
    grid = _build_grid(communes_metric, grid_spacing_m, metric_crs)
    grid["dist_social_m"] = _nearest_distances(grid, curated_all_points, no_data_dist_m)
    distance_agg = grid.groupby("name")["dist_social_m"].agg(
        social_mean_nearest_m="mean",
        social_median_nearest_m="median",
        social_p90_nearest_m=lambda x: x.quantile(0.90),
        social_n_access_grid="size",
    )
    for threshold in coverage_m:
        distance_agg[f"social_coverage_{threshold}m"] = (
            grid.groupby("name")["dist_social_m"].apply(lambda x, t=threshold: (x <= t).mean())
        )

    df = df.join(distance_agg)

    civic_signal = pd.DataFrame(
        {
            "civic_points": _zscore(np.log1p(df["social_civic_points_per_10k"])),
            "civic_diversity": _zscore(df["social_civic_diversity"]),
        },
        index=df.index,
    ).mean(axis=1)
    access_signal = pd.DataFrame(
        {
            "coverage": _zscore(df["social_coverage_1000m"]),
            "distance": _zscore(df["social_mean_nearest_m"], positive=False),
        },
        index=df.index,
    ).mean(axis=1)
    recreation_winsorized = _winsorize_upper(df["social_recreation_points_per_10k"], quantile=0.90)
    recreation_signal = _zscore(np.log1p(recreation_winsorized))

    df["social_civic_index"] = _rescale_0_100(civic_signal)
    df["social_access_index"] = _rescale_0_100(access_signal)
    df["social_recreation_index"] = _rescale_0_100(recreation_signal)
    df["social_index"] = (
        SOCIAL_INDEX_WEIGHTS["civic"] * df["social_civic_index"]
        + SOCIAL_INDEX_WEIGHTS["access"] * df["social_access_index"]
        + SOCIAL_INDEX_WEIGHTS["recreation"] * df["social_recreation_index"]
    )

    int_cols = [
        "social_n_total",
        "social_n_total_raw",
        "social_n_sports_raw",
        "social_n_public_space_raw",
        "social_private_or_customer_excluded_n",
        *category_cols,
        "social_category_diversity",
        "social_civic_diversity",
        "social_n_access_grid",
    ]
    for col in int_cols:
        df[col] = df[col].fillna(0).astype(int)
    for col in [c for c in df.columns if c not in int_cols]:
        df[col] = df[col].fillna(0).astype(float)

    round_1 = ["social_mean_nearest_m", "social_median_nearest_m", "social_p90_nearest_m"]
    for col in round_1:
        df[col] = df[col].round(1)
    for col in [
        "social_density_per_km2",
        "social_points_per_10k",
        "social_points_per_10k_raw",
        "social_civic_points_per_10k",
        "social_recreation_points_per_10k",
    ]:
        df[col] = df[col].round(3)
    for threshold in coverage_m:
        df[f"social_coverage_{threshold}m"] = df[f"social_coverage_{threshold}m"].round(3)
    for col in ["social_civic_index", "social_access_index", "social_recreation_index", "social_index"]:
        df[col] = df[col].round(1)

    ordered_cols = [
        "name",
        "social_n_total",
        "social_n_total_raw",
        *category_cols,
        "social_n_sports_raw",
        "social_n_public_space_raw",
        "social_private_or_customer_excluded_n",
        "social_category_diversity",
        "social_civic_diversity",
        "social_density_per_km2",
        "social_points_per_10k",
        "social_points_per_10k_raw",
        "social_civic_points_per_10k",
        "social_recreation_points_per_10k",
        "social_mean_nearest_m",
        "social_median_nearest_m",
        "social_p90_nearest_m",
        "social_coverage_500m",
        "social_coverage_1000m",
        "social_n_access_grid",
        "social_civic_index",
        "social_access_index",
        "social_recreation_index",
        "social_index",
    ]
    df = df.reset_index()[ordered_cols].sort_values("name").reset_index(drop=True)
    _validate_output(df, expected_communes)

    gdf_out = communes[["name", "geometry"]].merge(df, on="name", how="right", validate="one_to_one")
    gdf_out = gpd.GeoDataFrame(gdf_out, geometry="geometry", crs=communes.crs)
    gdf_out = gdf_out.sort_values("name").reset_index(drop=True)

    base_name = f"{city}_social_infrastructure"
    csv_out = out_dir / f"{base_name}.csv"
    geojson_out = out_dir / f"{base_name}.geojson"
    meta_out = out_dir / f"{base_name}_metadata.json"
    low_access_out = out_dir / f"{base_name}_low_access.csv"

    df.to_csv(csv_out, index=False)
    gdf_out.to_file(geojson_out, driver="GeoJSON")
    df.nsmallest(10, "social_index").to_csv(low_access_out, index=False)

    top5 = df.nlargest(5, "social_index")[["name", "social_index"]].values.tolist()
    bot5 = df.nsmallest(5, "social_index")[["name", "social_index"]].values.tolist()

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "source": "OpenStreetMap via direct Overpass queries plus existing greenspace OSM cache",
        "osm_tags": social_cfg["osm_tags"],
        "raw_categories": social_cfg["categories"],
        "curated_categories": curated_categories,
        "raw_category_counts_deduplicated": raw_category_counts,
        "curated_category_counts_deduplicated": curated_category_counts,
        "deduplication_radius_m": dedupe_radius_m,
        "grid_spacing_m": grid_spacing_m,
        "coverage_thresholds_m": coverage_m,
        "no_data_distance_cap_m": no_data_dist_m,
        "crs_metric": metric_crs,
        "curation": {
            "access_excluded_values": sorted(curated_access_exclude),
            "sports_leisure_kept_for_curated_signal": DEFAULT_CURATED_SPORTS_LEISURE,
            "sports_leisure_excluded_from_curated_signal": ["pitch", "swimming_pool"],
            "public_space_rules": DEFAULT_CURATED_PUBLIC_SPACE,
            "civic_categories": civic_categories,
            "access_excluded_feature_counts": excluded_counts_features,
            "access_excluded_unique_point_counts": excluded_counts_unique,
        },
        "method": (
            "OSM social infrastructure points were downloaded as a broad raw "
            "inventory, then a curated civic-cultural inventory was derived by "
            "excluding access-restricted features and by narrowing sports/public-"
            "space membership for the master-facing signal. Distance and coverage "
            "metrics were computed on a 1 km grid using the curated inventory. "
            "social_index = 0.45 * social_civic_index + 0.35 * social_access_index "
            "+ 0.20 * social_recreation_index."
        ),
        "warning": (
            "Ecological proxy for social participation opportunity and cognitive "
            "stimulation; not a direct measure of loneliness, social isolation, "
            "cognition, dementia, or individual service use."
        ),
        "index_formula": {
            "social_civic_points_per_10k": (
                "(library + cultural + community + senior) / population * 10000"
            ),
            "social_recreation_points_per_10k": (
                "(sports + public_space) / population * 10000"
            ),
            "social_civic_diversity": (
                "count of non-zero civic categories among library, cultural, community, senior"
            ),
            "social_civic_index": (
                "mean(z(log1p(social_civic_points_per_10k)), z(social_civic_diversity)), rescaled 0-100"
            ),
            "social_access_index": (
                "mean(z(social_coverage_1000m), -z(social_mean_nearest_m)), rescaled 0-100"
            ),
            "social_recreation_index": (
                "z(log1p(winsorized social_recreation_points_per_10k at p90)), rescaled 0-100"
            ),
            "social_index": (
                "0.45 * social_civic_index + 0.35 * social_access_index + 0.20 * social_recreation_index"
            ),
        },
        "brain_health_relevance": {
            "social_isolation": "Social isolation is a modifiable dementia risk factor.",
            "cognitive_stimulation": (
                "Libraries, cultural venues, and community spaces are plausible "
                "neighborhood opportunities for cognitive and social engagement."
            ),
            "physical_activity": (
                "Sports and public recreation facilities may support activity and "
                "social participation."
            ),
        },
        "n_communes": len(df),
        "n_raw_osm_features": int(len(raw)),
        "n_raw_classified_osm_features": int(len(classified_raw)),
        "n_unique_social_points_raw": int(len(raw_all_points)),
        "n_unique_social_points_curated": int(len(curated_all_points)),
        "top5_most_accessible": top5,
        "bot5_least_accessible": bot5,
        "columns": ordered_cols,
        "outputs": [csv_out.name, geojson_out.name, meta_out.name, low_access_out.name],
    }
    meta_out.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(f"\nWrote {csv_out.name}: {len(df)} communes")
    print(f"Wrote {geojson_out.name}")
    print(f"Wrote {meta_out.name}")
    print(f"Wrote {low_access_out.name}")
    print(f"Top social-cognitive access: {[r[0] for r in top5]}")
    print(f"Least social-cognitive access: {[r[0] for r in bot5]}")

    return df, gdf_out


if __name__ == "__main__":
    build_social_infrastructure_layer()

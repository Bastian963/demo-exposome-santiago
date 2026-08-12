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
from tqdm import tqdm

from . import boundaries, config
from . import healthcare_network as network
from . import healthcare_official as official
from .osm_fetch import (
    POINT_TAG_MAX_TILE_SPAN_DEG,
    call_with_overpass_fallback,
    fetch_features_from_bbox_tiled,
    fetch_features_from_local_extract,
    tile_grid_size_for_bbox,
)
from .study_grid import build_study_access_grid, intersect_grid_with_units


def _download_osm_tag(
    region: str | list[str],
    tag_key: str,
    values: list[str],
    *,
    bbox: tuple[float, float, float, float] | None = None,
) -> gpd.GeoDataFrame:
    """Download OSM features for a single tag key, with endpoint fallback + backoff."""
    tags = {tag_key: values}
    try:
        if bbox is not None:
            return fetch_features_from_bbox_tiled(
                bbox,
                tags,
                label=tag_key,
                # A fixed grid_size=2 (4 tiles) was fine for city/comuna-scale
                # bboxes but each tile stayed ~2.7x Overpass's own max query
                # area for a whole-province AOI like San Juan, so every tile
                # failed outright (confirmed 2026-08-03: a trivial ~100 km2
                # Overpass query against the same province succeeded
                # instantly, so this was tile size, not endpoint
                # availability). Size the grid to the bbox instead.
                grid_size=tile_grid_size_for_bbox(bbox, POINT_TAG_MAX_TILE_SPAN_DEG),
                log=tqdm.write,
            )
        return call_with_overpass_fallback(
            lambda: ox.features_from_place(region, tags=tags),
            label=tag_key,
            log=tqdm.write,
        )
    except ConnectionError as err:
        raise ConnectionError(f"Failed to download OSM tag '{tag_key}'") from err


def fetch_healthcare_osm(
    cfg: dict[str, Any],
    cache_path: Path | None = None,
) -> gpd.GeoDataFrame:
    """Download healthcare amenities from OSM or load a cached GeoJSON.

    The cache stores the raw OSM response with minimal columns so it can be
    re-classified on load.

    Downloads each tag key separately to keep individual Overpass queries small
    and robust against transient failures. Each tag's result is checkpointed
    to its own cache file immediately after download (not just once at the
    end), so interrupting a multi-tag run only loses the tag in flight; a
    re-run with the same ``cache_path`` skips every tag already fetched.
    """
    if cache_path and cache_path.exists():
        gdf = gpd.read_file(cache_path)
        if len(gdf) > 0:
            return gdf

    region = cfg["region_query"]
    tags = cfg["healthcare"]["osm_tags"]
    geo_crs = cfg["crs"]["geographic"]

    # Modern studies already ship authoritative administrative polygons.
    # Query their compact AOI bbox (split into four Overpass requests) rather
    # than geocoding a list of 20/50/96 place names for every tag.  Results
    # are filtered back to the exact union below, so bbox-only candidates do
    # not affect counts or nearest-distance metrics.
    study_geometry = None
    study_bbox = None
    if isinstance(cfg.get("spatial_units"), dict):
        units = boundaries.get_communes(cfg).to_crs(geo_crs)
        study_geometry = units.geometry.union_all()
        study_bbox = tuple(study_geometry.bounds)

    # Increase timeout for large region queries.
    ox.settings.requests_timeout = 300

    pieces: list[gpd.GeoDataFrame] = []

    # A frozen regional extract replaces the per-tag Overpass downloads. It is
    # read ONCE with every tag key at once, not per key: Overpass hands
    # back all of a feature's tags whichever key matched it, while the extract
    # materializes only the keys asked for. Querying key by key would leave a
    # facility tagged amenity=hospital + healthcare=clinic with one of the two
    # columns empty, and the (element, id) dedup below would then keep whichever
    # copy came first -- silently moving it between categories.
    # See data/raw/geofabrik/README.md and docs/osm_local_extract.md.
    extract = cfg["healthcare"].get("osm_extract")
    if extract:
        gdf_extract = fetch_features_from_local_extract(
            extract, tags, label=f"healthcare[{cfg.get('name', '?')}]", log=tqdm.write
        )
        if len(gdf_extract) > 0:
            gdf_extract = (
                gdf_extract.to_crs(geo_crs) if gdf_extract.crs else gdf_extract.set_crs(geo_crs)
            )
            if study_geometry is not None:
                gdf_extract = gdf_extract[
                    gdf_extract.geometry.intersects(study_geometry)
                ].copy()
            pieces.append(gdf_extract)

    tag_items = [] if extract else list(tags.items())
    for tag_key, values in tqdm(tag_items, desc="healthcare OSM tags", unit="tag"):
        tag_cache = (
            cache_path.with_name(f"{cache_path.stem}_{tag_key}{cache_path.suffix}")
            if cache_path
            else None
        )
        if tag_cache and tag_cache.exists():
            tqdm.write(f"  [{tag_key}] loading from cache …")
            gdf_tag = gpd.read_file(tag_cache)
        else:
            tqdm.write(f"  [{tag_key}] downloading from OSM …")
            gdf_tag = _download_osm_tag(region, tag_key, values, bbox=study_bbox)
            if len(gdf_tag) > 0:
                if study_geometry is not None:
                    gdf_tag = gdf_tag.to_crs(geo_crs) if gdf_tag.crs else gdf_tag.set_crs(geo_crs)
                    gdf_tag = gdf_tag[gdf_tag.geometry.intersects(study_geometry)].copy()
                if not isinstance(gdf_tag.index, pd.RangeIndex):
                    gdf_tag = gdf_tag.reset_index()
            if tag_cache:
                tag_cache.parent.mkdir(parents=True, exist_ok=True)
                gdf_wgs_tag = (
                    gdf_tag.to_crs(geo_crs) if len(gdf_tag) > 0 and gdf_tag.crs else gdf_tag
                )
                if len(gdf_wgs_tag) > 0:
                    safe_columns = [
                        column
                        for column in ("element", "id", "name", "amenity", "healthcare", "geometry")
                        if column in gdf_wgs_tag.columns
                    ]
                    gdf_wgs_tag[safe_columns].to_file(tag_cache, driver="GeoJSON")
        if len(gdf_tag) == 0:
            continue
        # element/id (preserved via reset_index() before caching, above) let
        # duplicates across tag keys be dropped below.
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

    # ``is_all_health`` captures every facility matched by the configured OSM
    # tags, even if it does not belong to one of the named categories (e.g.
    # dentists, laboratories). This keeps ``n_total`` comparable to the broad
    # OSM query.
    all_health_mask = pd.Series(False, index=gdf.index)
    for tag_key, values in cfg["healthcare"]["osm_tags"].items():
        if tag_key in gdf.columns:
            all_health_mask |= gdf[tag_key].isin(values)
    gdf["is_all_health"] = all_health_mask

    # OSM facilities are neutral with respect to the public/private sector
    # split, which only comes from the official DEIS registry.
    gdf["is_public"] = False
    gdf["is_private"] = False

    return gdf


def _mark_as_osm_only(gdf: gpd.GeoDataFrame, cfg: dict[str, Any]) -> gpd.GeoDataFrame:
    """Return a copy of ``gdf`` carrying the full OSM-only column contract.

    ``compute_counts`` aggregates over ``is_<category>_public``/``is_<category>_private``
    for every configured category, so those columns must exist even when no
    official registry contributed a sector split. Both callers that end up with
    OSM points alone -- the ``use_official`` is False path and the empty-official
    early return in :func:`conflate_sources` -- go through here, so the two
    cannot drift apart again.
    """
    gdf = gdf.copy()
    gdf["source"] = "osm"
    gdf["official_type"] = ""
    gdf["is_public"] = False
    gdf["is_private"] = False
    for category in cfg["healthcare"]["categories"]:
        gdf[f"is_{category}_public"] = False
        gdf[f"is_{category}_private"] = False
    return gdf


def _normalise_name(name: Any) -> str:
    """Lowercase and strip a name for fuzzy comparison."""
    if name is None:
        return ""
    return str(name).lower().strip()


def _name_similarity(a: str, b: str) -> float:
    """Return a 0-1 fuzzy similarity score between two names."""
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio()


def conflate_sources(
    gdf_official: gpd.GeoDataFrame,
    gdf_osm: gpd.GeoDataFrame,
    cfg: dict[str, Any],
) -> gpd.GeoDataFrame:
    """Merge official and OSM facility points, removing OSM duplicates.

    An OSM point is considered a duplicate of an official point when:

    - it is within ``strict_buffer_m`` of the official point, OR
    - it is within ``buffer_m`` AND the normalised names match with a ratio
      >= ``name_match_threshold``.

    The official record is kept in both cases. OSM points that do not match
    any official point are retained as complementary coverage (e.g. pharmacies
    and informal/private facilities absent from the official registry).
    """
    metric_crs = cfg["crs"]["metric"]
    conflation_cfg = cfg["healthcare"]["official_source"]["conflation"]
    buffer_m = conflation_cfg["buffer_m"]
    strict_buffer_m = conflation_cfg.get("strict_buffer_m", buffer_m / 3)
    name_threshold = conflation_cfg.get("name_match_threshold", 0.5)

    if gdf_official.empty:
        # No official record survived the study filters, so this is the OSM-only
        # contract -- including the per-category sector columns compute_counts
        # aggregates over. Omitting them used to surface much later as a
        # KeyError on a dozen `is_*_public`/`is_*_private` labels.
        return _mark_as_osm_only(gdf_osm, cfg)

    if gdf_osm.empty:
        gdf_official["source"] = "deis"
        gdf_official["official_type"] = gdf_official.get("official_type", "")
        return gdf_official.copy()

    official_metric = gdf_official.to_crs(metric_crs).copy().reset_index(drop=True)
    osm_metric = gdf_osm.to_crs(metric_crs).copy().reset_index(drop=True)

    from scipy.spatial import cKDTree

    official_coords = np.vstack([official_metric.geometry.x, official_metric.geometry.y]).T
    tree = cKDTree(official_coords)
    osm_coords = np.vstack([osm_metric.geometry.x, osm_metric.geometry.y]).T
    dists, idx_official = tree.query(osm_coords, k=1)

    # Pre-compute normalised names.
    official_names = official_metric["name"].apply(_normalise_name).values
    osm_names = osm_metric["name"].apply(_normalise_name).values

    # Determine matches.
    within_buffer = dists <= buffer_m
    within_strict = dists <= strict_buffer_m
    name_match = np.array([
        _name_similarity(osm_names[i], official_names[idx_official[i]]) >= name_threshold
        for i in range(len(osm_metric))
    ])

    # A match requires either very close proximity or proximity + name similarity.
    is_match = within_strict | (within_buffer & name_match)

    # OSM points that did not match any official point are kept.
    osm_metric = osm_metric[~is_match].copy()

    # Mark official points that have at least one matching OSM point nearby.
    matched_official_idx = idx_official[is_match]
    has_osm_match = np.zeros(len(official_metric), dtype=bool)
    if len(matched_official_idx) > 0:
        has_osm_match[matched_official_idx] = True
    official_metric["source"] = np.where(has_osm_match, "both", "deis")

    # Normalise OSM columns to the same schema.
    osm_metric["official_type"] = ""
    osm_metric["source"] = "osm"
    osm_metric["commune"] = ""

    # Ensure all boolean category columns exist on both sides.
    all_cats = list(cfg["healthcare"]["categories"].keys())
    for col in [f"is_{c}" for c in all_cats]:
        if col not in official_metric.columns:
            official_metric[col] = False
        if col not in osm_metric.columns:
            osm_metric[col] = False

    # Add sector-split category columns (DEIS only; OSM points remain neutral).
    for cat in all_cats:
        pub_col = f"is_{cat}_public"
        pri_col = f"is_{cat}_private"
        official_metric[pub_col] = official_metric[f"is_{cat}"] & official_metric["is_public"]
        official_metric[pri_col] = official_metric[f"is_{cat}"] & official_metric["is_private"]
        osm_metric[pub_col] = False
        osm_metric[pri_col] = False

    common_cols = [
        "name",
        "commune",
        "official_type",
        "source",
        "is_public",
        "is_private",
        *[f"is_{c}" for c in all_cats],
        *[f"is_{c}_public" for c in all_cats],
        *[f"is_{c}_private" for c in all_cats],
        "geometry",
    ]
    official_metric = official_metric[common_cols].copy()
    osm_metric = osm_metric[common_cols].copy()

    combined = gpd.GeoDataFrame(
        pd.concat([official_metric, osm_metric], ignore_index=True),
        crs=metric_crs,
    )
    return combined.to_crs(cfg["crs"]["geographic"]).reset_index(drop=True)


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

    # Aggregate base category counts and split each DEIS-derived category
    # into public / private sectors. Pharmacies are OSM-only and therefore
    # stay without a sector split.
    base_counts = {"n_total": ("geometry", "size")}

    categories = [
        "hospital",
        "clinic",
        "primary_care",
        "laboratory",
        "dental",
        "mental_health",
    ]
    for cat in categories:
        base_counts[f"n_{cat}"] = (f"is_{cat}", "sum")
        base_counts[f"n_{cat}_public"] = (
            f"is_{cat}_public",
            "sum",
        )
        base_counts[f"n_{cat}_private"] = (
            f"is_{cat}_private",
            "sum",
        )

    base_counts["n_pharmacy"] = ("is_pharmacy", "sum")
    base_counts["n_public_total"] = ("is_public", "sum")
    base_counts["n_private_total"] = ("is_private", "sum")

    counts = joined.groupby("commune_name").agg(**base_counts).reset_index().rename(
        columns={"commune_name": "name"}
    )

    int_cols = [c for c in counts.columns if c != "name"]
    counts[int_cols] = counts[int_cols].fillna(0).astype(int)
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
    """Build one AOI-aligned access grid and link it by area intersection."""
    units = gdf_communes.to_crs(metric_crs)
    cells = build_study_access_grid(units, spacing_m=spacing_m, metric_crs=metric_crs)
    links = intersect_grid_with_units(cells, units, name_column="name")
    samples = cells[["cell_id", "sample_point", "geometry"]].rename(
        columns={"sample_point": "geometry", "geometry": "cell_geometry"}
    ).set_geometry("geometry")
    out = links.drop(columns="geometry").merge(samples, on="cell_id", how="left")
    out = gpd.GeoDataFrame(out, geometry="geometry", crs=metric_crs)
    out["area_weight_m2"] = out["intersection_area_m2"]
    return out


def _write_healthcare_detail_grid(
    access_grid: gpd.GeoDataFrame,
    facilities: gpd.GeoDataFrame,
    *,
    spacing_m: int,
    destination: Path,
    use_ckdtree: bool,
) -> Path:
    """Write the actual stable nearest-facility grid for browser detail."""
    from shapely.geometry import mapping

    cells = access_grid.sort_values("cell_id").drop_duplicates("cell_id").copy()
    cells = gpd.GeoDataFrame(cells, geometry="geometry", crs=access_grid.crs)
    if use_ckdtree:
        values = _nearest_distances_ckdtree(cells, facilities, "value")
    else:
        values = _nearest_distances_sjoin(cells, facilities, "value")
    # A legacy/partially materialized access grid can carry an old ``value``
    # attribute.  GeoPandas then appends the new nearest-distance column with
    # the same label, and ``itertuples().value`` becomes a Series instead of a
    # scalar.  The distance just calculated is the rightmost one; retain it
    # explicitly so browser detail is always based on the current facilities.
    if values.columns.duplicated().any():
        duplicate_value_columns = [
            index for index, column in enumerate(values.columns) if column == "value"
        ]
        if len(duplicate_value_columns) > 1:
            current_value = values.iloc[:, duplicate_value_columns[-1]].copy()
            values = values.loc[:, ~values.columns.duplicated(keep="first")].copy()
            values["value"] = current_value
    cells = values.set_geometry("cell_geometry", crs=access_grid.crs).to_crs("EPSG:4326")
    features = [
        {
            "type": "Feature",
            "properties": {"value": round(float(row.value), 3), "pixel_id": str(row.cell_id)},
            "geometry": mapping(row.cell_geometry),
        }
        for row in cells.itertuples()
        if row.cell_geometry is not None and not row.cell_geometry.is_empty
    ]
    payload = {
        "type": "FeatureCollection",
        "exposome": "healthcare",
        "column": "mean_nearest_health_m",
        "source": "OSM/official healthcare inventory; nearest Euclidean facility distance",
        "analysis_resolution_m": spacing_m,
        "grid_alignment": "study_aoi_metric_grid",
        "is_synthetic": False,
        "n_features": len(features),
        "features": features,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return destination


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

    rows: list[dict[str, Any]] = []
    for name, group in joined.groupby("name"):
        weights = group.get("area_weight_m2", pd.Series(1.0, index=group.index))
        # Spatial joins legitimately retain duplicate index labels (for
        # instance, a boundary cell or equidistant facility). Selecting a
        # quantile back with ``.loc[index_label]`` can therefore return a
        # Series, not one distance. Work positionally after the stable sort.
        ordered = group.assign(_area_weight=weights.to_numpy()).sort_values(
            distance_col, kind="stable"
        )
        ordered_weights = ordered["_area_weight"]
        cumulative = ordered_weights.cumsum() / ordered_weights.sum()

        def quantile(q: float) -> float:
            position = int(np.flatnonzero(cumulative.to_numpy() >= q)[0])
            return float(ordered.iloc[position][distance_col])
        record: dict[str, Any] = {
            "name": name,
            f"mean_{prefix}_m": float(np.average(group[distance_col], weights=weights)),
            f"median_{prefix}_m": quantile(0.5),
            f"p90_{prefix}_m": quantile(0.9),
        }
        if include_count:
            record["n_access_grid"] = int(group["cell_id"].nunique())
        rows.append(record)
    return pd.DataFrame(rows)


def build_healthcare_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    *,
    use_official: bool = True,
    refresh_official: bool = False,
    use_network: bool = False,
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
    official_cfg = cfg["healthcare"].get("official_source", {})
    network_cfg = cfg["healthcare"].get("network", {})
    use_official = use_official and official_cfg.get("enabled", False)
    use_network = use_network or network_cfg.get("enabled", False)

    # 1. Boundaries
    communes_cache = cache_dir / f"{city}_communes.geojson"
    gdf_communes = boundaries.get_communes(cfg, cache_path=communes_cache)

    # 2. Fetch + classify OSM facilities
    osm_cache = cache_dir / f"{city}_healthcare_osm.geojson"
    gdf_health_raw = fetch_healthcare_osm(cfg, cache_path=osm_cache)
    gdf_health_osm = classify_facilities(gdf_health_raw, cfg)

    # 3. Optionally load official (DEIS) facilities and conflate with OSM.
    if use_official:
        print("Loading official DEIS facilities...")
        gdf_health_official = official.prepare_official_facilities(
            cfg, cache_dir, refresh=refresh_official
        )
        gdf_health = conflate_sources(gdf_health_official, gdf_health_osm, cfg)
    else:
        gdf_health = _mark_as_osm_only(gdf_health_osm, cfg)

    # 4. Counts and density
    counts = compute_counts(gdf_health, gdf_communes, cfg)
    gdf_result = gdf_communes[["name", "area_km2", "geometry"]].merge(
        counts, on="name", how="left"
    )
    int_cols = [
        "n_total", "n_hospital", "n_clinic", "n_primary_care", "n_pharmacy",
        "n_laboratory", "n_dental", "n_mental_health",
        "n_hospital_public", "n_hospital_private",
        "n_clinic_public", "n_clinic_private",
        "n_primary_care_public", "n_primary_care_private",
        "n_laboratory_public", "n_laboratory_private",
        "n_dental_public", "n_dental_private",
        "n_mental_health_public", "n_mental_health_private",
        "n_public_total", "n_private_total",
    ]
    gdf_result[int_cols] = gdf_result[int_cols].fillna(0).astype(int)
    gdf_result["density_per_km2"] = gdf_result["n_total"] / gdf_result["area_km2"]

    # 5. Intra-communal access grid
    access_grid = build_access_grid(gdf_communes, grid_spacing, metric_crs)

    # 6. Nearest distances (metric CRS)
    facilities_metric = gdf_health.to_crs(metric_crs)
    all_facilities = facilities_metric[facilities_metric["is_all_health"]].copy()
    hospital_facilities = facilities_metric[facilities_metric["is_hospital"]].copy()
    primary_care_facilities = facilities_metric[facilities_metric["is_primary_care"]].copy()

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
    dist_primary_care = nearest_distance_summary(
        access_grid,
        primary_care_facilities,
        distance_col="nearest_primary_care_m",
        prefix="nearest_primary_care",
        include_count=False,
        use_ckdtree=use_ckdtree,
    )

    detail_grid_path = _write_healthcare_detail_grid(
        access_grid,
        all_facilities,
        spacing_m=grid_spacing,
        destination=out_dir / "subcomuna" / "healthcare.geojson",
        use_ckdtree=use_ckdtree,
    )

    gdf_result = gdf_result.merge(dist_health, on="name", how="left")
    gdf_result = gdf_result.merge(dist_hospital, on="name", how="left")
    gdf_result = gdf_result.merge(dist_primary_care, on="name", how="left")

    # 6b. Optional street-network distances (more realistic, slower).
    network_distance_cols: list[str] = []
    if use_network:
        print("Computing street-network distances...")
        graph_cache = Path(network_cfg.get("graph_cache", f"cache/{city}_walk_graph.graphml"))
        graph = network.fetch_street_graph(
            cfg["region_query"],
            graph_cache,
            network_type=network_cfg.get("network_type", "walk"),
            to_crs=metric_crs,
        )

        max_snap = network_cfg.get("max_snap_distance_m", 500.0)
        dist_health_network = network.network_distance_summary(
            access_grid,
            all_facilities,
            graph,
            cfg,
            prefix="nearest_health_network",
            max_snap_distance_m=max_snap,
        )
        dist_hospital_network = network.network_distance_summary(
            access_grid,
            hospital_facilities,
            graph,
            cfg,
            prefix="nearest_hospital_network",
            max_snap_distance_m=max_snap,
        )
        dist_primary_care_network = network.network_distance_summary(
            access_grid,
            primary_care_facilities,
            graph,
            cfg,
            prefix="nearest_primary_care_network",
            max_snap_distance_m=max_snap,
        )

        gdf_result = gdf_result.merge(dist_health_network, on="name", how="left")
        gdf_result = gdf_result.merge(dist_hospital_network, on="name", how="left")
        gdf_result = gdf_result.merge(dist_primary_care_network, on="name", how="left")

        # Fallback to Euclidean distance where the street network does not
        # provide a reliable value (e.g. rural communes with sparse roads or
        # a whole commune snapping to the same road node).
        fallback_pairs = [
            ("mean_nearest_health_network_m", "mean_nearest_health_m"),
            ("median_nearest_health_network_m", "median_nearest_health_m"),
            ("p90_nearest_health_network_m", "p90_nearest_health_m"),
            ("mean_nearest_hospital_network_m", "mean_nearest_hospital_m"),
            ("median_nearest_hospital_network_m", "median_nearest_hospital_m"),
            ("p90_nearest_hospital_network_m", "p90_nearest_hospital_m"),
            ("mean_nearest_primary_care_network_m", "mean_nearest_primary_care_m"),
            ("median_nearest_primary_care_network_m", "median_nearest_primary_care_m"),
            ("p90_nearest_primary_care_network_m", "p90_nearest_primary_care_m"),
        ]
        for net_col, euc_col in fallback_pairs:
            gdf_result[net_col] = gdf_result[net_col].fillna(gdf_result[euc_col])
            # Replace an implausible zero summary for a whole commune with the
            # Euclidean equivalent (likely a snapping artefact).
            zero_mask = gdf_result[net_col] == 0
            gdf_result.loc[zero_mask, net_col] = gdf_result.loc[zero_mask, euc_col]

        network_distance_cols = [
            "mean_nearest_health_network_m",
            "median_nearest_health_network_m",
            "p90_nearest_health_network_m",
            "mean_nearest_hospital_network_m",
            "median_nearest_hospital_network_m",
            "p90_nearest_hospital_network_m",
            "mean_nearest_primary_care_network_m",
            "median_nearest_primary_care_network_m",
            "p90_nearest_primary_care_network_m",
        ]

    # 7. Formatting
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
        "mean_nearest_primary_care_m",
        "median_nearest_primary_care_m",
        "p90_nearest_primary_care_m",
        *network_distance_cols,
    ]
    for col in distance_cols:
        gdf_result[col] = gdf_result[col].round(0).astype("Int64")

    # Reorder columns to match build_master_exposome.py expectations
    output_cols = [
        "name",
        "area_km2",
        "n_total",
        "n_public_total",
        "n_private_total",
        "n_hospital",
        "n_hospital_public",
        "n_hospital_private",
        "n_clinic",
        "n_clinic_public",
        "n_clinic_private",
        "n_primary_care",
        "n_primary_care_public",
        "n_primary_care_private",
        "n_pharmacy",
        "n_laboratory",
        "n_laboratory_public",
        "n_laboratory_private",
        "n_dental",
        "n_dental_public",
        "n_dental_private",
        "n_mental_health",
        "n_mental_health_public",
        "n_mental_health_private",
        "density_per_km2",
        "n_access_grid",
        "mean_nearest_health_m",
        "median_nearest_health_m",
        "p90_nearest_health_m",
        "mean_nearest_hospital_m",
        "median_nearest_hospital_m",
        "p90_nearest_hospital_m",
        "mean_nearest_primary_care_m",
        "median_nearest_primary_care_m",
        "p90_nearest_primary_care_m",
        *network_distance_cols,
    ]
    gdf_result = gdf_result[output_cols + ["geometry"]]

    # 8. Validation
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

    # 9. Separate tabular and geographic outputs
    df = gdf_result[output_cols].copy()
    gdf_out = gpd.GeoDataFrame(
        gdf_result[output_cols + ["geometry"]],
        geometry="geometry",
        crs=geo_crs,
    )

    # 10. Write outputs
    csv_path = out_dir / f"{output_base}.csv"
    geojson_path = out_dir / f"{output_base}.geojson"
    metadata_path = out_dir / f"{output_base}_metadata.json"

    df.to_csv(csv_path, index=False)
    gdf_out.to_file(geojson_path, driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "source": "OpenStreetMap via osmnx + MINSAL/DEIS official registry" if use_official else "OpenStreetMap via osmnx",
        "method": "Euclidean nearest-facility distance on intra-communal grid",
        "grid_spacing_m": grid_spacing,
        "metric_crs": metric_crs,
        "use_official_source": use_official,
        "osm_tags": cfg["healthcare"]["osm_tags"],
        "categories": cfg["healthcare"]["categories"],
        "official_type_mapping": official_cfg.get("type_mapping", {}) if use_official else {},
        "n_facilities_total": int(gdf_health["is_all_health"].sum()),
        "n_facilities_public_total": int(gdf_health["is_public"].sum()),
        "n_facilities_private_total": int(gdf_health["is_private"].sum()),
        "n_facilities_hospital": int(gdf_health["is_hospital"].sum()),
        "n_facilities_hospital_public": int(gdf_health["is_hospital_public"].sum()),
        "n_facilities_hospital_private": int(gdf_health["is_hospital_private"].sum()),
        "n_facilities_clinic": int(gdf_health["is_clinic"].sum()),
        "n_facilities_clinic_public": int(gdf_health["is_clinic_public"].sum()),
        "n_facilities_clinic_private": int(gdf_health["is_clinic_private"].sum()),
        "n_facilities_primary_care": int(gdf_health["is_primary_care"].sum()),
        "n_facilities_primary_care_public": int(gdf_health["is_primary_care_public"].sum()),
        "n_facilities_primary_care_private": int(gdf_health["is_primary_care_private"].sum()),
        "n_facilities_pharmacy": int(gdf_health["is_pharmacy"].sum()),
        "n_facilities_laboratory": int(gdf_health["is_laboratory"].sum()),
        "n_facilities_laboratory_public": int(gdf_health["is_laboratory_public"].sum()),
        "n_facilities_laboratory_private": int(gdf_health["is_laboratory_private"].sum()),
        "n_facilities_dental": int(gdf_health["is_dental"].sum()),
        "n_facilities_dental_public": int(gdf_health["is_dental_public"].sum()),
        "n_facilities_dental_private": int(gdf_health["is_dental_private"].sum()),
        "n_facilities_mental_health": int(gdf_health["is_mental_health"].sum()),
        "n_facilities_mental_health_public": int(gdf_health["is_mental_health_public"].sum()),
        "n_facilities_mental_health_private": int(gdf_health["is_mental_health_private"].sum()),
        "n_facilities_osm": int((gdf_health["source"] == "osm").sum()),
        "n_facilities_official": int((gdf_health["source"].isin(["deis", "both"])).sum()),
        "n_grid_points": int(len(access_grid)),
        "distance_metric": (
            "street_network_shortest_path"
            if use_network
            else "euclidean_straight_line"
        ),
        "use_network": use_network,
        "network_type": network_cfg.get("network_type", "walk") if use_network else None,
        "columns": output_cols,
        "n_rows": int(len(df)),
        "detail_grid": {
            "path": detail_grid_path.relative_to(out_dir).as_posix(),
            "grid_alignment": "study_aoi_metric_grid",
            "is_synthetic": False,
            "value_column": "mean_nearest_health_m",
        },
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(f"Wrote {csv_path.name} ({len(df)} rows x {df.shape[1]} cols)")
    print(f"Wrote {geojson_path.name}")
    print(f"Wrote {metadata_path.name}")
    print(f"Wrote {detail_grid_path.relative_to(out_dir)}")

    return df, gdf_out

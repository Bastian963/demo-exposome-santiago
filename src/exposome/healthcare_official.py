"""Official healthcare facility inventory for Chile (MINSAL/DEIS).

This module downloads and normalises the "Establecimientos de Salud Vigentes"
dataset published by DEIS on datos.gob.cl, and prepares it for conflation with
OpenStreetMap data.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point


def _discover_csv_url(ckan_package_url: str, timeout: int = 30) -> str:
    """Query CKAN package_show and return the most recent CSV resource URL."""
    response = requests.get(ckan_package_url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise ValueError(f"CKAN API call failed: {payload}")

    resources = payload["result"].get("resources", [])
    csv_candidates = [
        r for r in resources
        if str(r.get("format", "")).lower() == "csv"
        and str(r.get("url", "")).lower().endswith(".csv")
    ]
    if not csv_candidates:
        raise ValueError("No CSV resource found in CKAN package")

    # Prefer the most recently modified resource.
    csv_candidates.sort(
        key=lambda r: r.get("last_modified", r.get("created", "")),
        reverse=True,
    )
    return str(csv_candidates[0]["url"])


def _download_file(url: str, dest: Path, timeout: int = 120) -> None:
    """Download a file to ``dest`` using streaming requests."""
    response = requests.get(url, timeout=timeout, stream=True)
    response.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def fetch_deis_csv(
    cfg: dict[str, Any],
    cache_path: Path,
    *,
    refresh: bool = False,
) -> Path:
    """Download the DEIS CSV or return a cached copy.

    First tries the CKAN API to discover the latest resource URL; falls back
    to the explicit ``csv_url`` in the config if discovery fails.
    """
    if cache_path.exists() and not refresh:
        return cache_path

    official_cfg = cfg["healthcare"]["official_source"]
    ckan_url = official_cfg.get("ckan_package_url")
    fallback_url = official_cfg["csv_url"]

    url = fallback_url
    if ckan_url:
        try:
            url = _discover_csv_url(ckan_url)
            print(f"  Discovered DEIS CSV via CKAN: {url}")
        except Exception as err:  # noqa: BLE001
            print(f"  CKAN discovery failed ({err}), using fallback URL")

    print(f"  Downloading DEIS CSV...")
    _download_file(url, cache_path)
    print(f"  Cached DEIS CSV at {cache_path}")
    return cache_path


def load_deis_facilities(
    csv_path: Path,
    cfg: dict[str, Any],
) -> gpd.GeoDataFrame:
    """Load, filter and classify DEIS facilities from a local CSV.

    Returns a GeoDataFrame with the same schema expected by
    ``src.exposome.healthcare``:

    - ``name`` : official establishment name
    - ``commune`` : commune name
    - ``official_type`` : original DEIS facility type
    - ``is_hospital``, ``is_clinic``, ``is_primary_care`` : boolean categories
    - ``is_all_health`` : True if the facility matched any configured category
    - ``source`` : ``"deis"``
    - ``geometry`` : representative Point in the configured geographic CRS
    """
    official_cfg = cfg["healthcare"]["official_source"]
    col_cfg = official_cfg["columns"]
    geo_crs = cfg["crs"]["geographic"]

    df = pd.read_csv(csv_path, sep=official_cfg.get("csv_sep", ";"), low_memory=False)

    # Column normalisation.
    name_col = col_cfg["name"]
    type_col = col_cfg["type"]
    region_col = col_cfg["region"]
    commune_col = col_cfg["commune"]
    lat_col = col_cfg["lat"]
    lon_col = col_cfg["lon"]
    status_col = col_cfg["status"]

    # Ensure coordinate columns are numeric.
    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")

    # Filters.
    region_filter = official_cfg["region_filter"]
    status_contains = official_cfg.get("status_contains", "Vigente")

    mask_region = df[region_col].astype(str).str.contains(region_filter, case=False, na=False)
    mask_status = df[status_col].astype(str).str.contains(status_contains, case=False, na=False)
    mask_coords = df[lat_col].notna() & df[lon_col].notna()

    df = df[mask_region & mask_status & mask_coords].copy()

    # Bounding-box filter to discard obvious coordinate errors.
    bbox = cfg.get("bbox", {})
    if all(k in bbox for k in ("lat_min", "lat_max", "lon_min", "lon_max")):
        df = df[
            (df[lat_col] >= bbox["lat_min"])
            & (df[lat_col] <= bbox["lat_max"])
            & (df[lon_col] >= bbox["lon_min"])
            & (df[lon_col] <= bbox["lon_max"])
        ].copy()

    # Build geometry.
    geometry = [Point(lon, lat) for lon, lat in zip(df[lon_col], df[lat_col])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs=geo_crs)

    # Classify. Normalise whitespace in the raw type so config values do not
    # need to match stray spaces (e.g. "  (COSAM)" in the DEIS CSV).
    type_mapping = official_cfg["type_mapping"]
    gdf["official_type"] = (
        gdf[type_col]
        .astype(str)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    category_masks: dict[str, pd.Series] = {}
    for cat_name, values in type_mapping.items():
        import re
        values_norm = [re.sub(r"\s+", " ", str(v)).strip() for v in values]
        category_masks[cat_name] = gdf["official_type"].isin(values_norm)

    for cat_name, mask in category_masks.items():
        gdf[f"is_{cat_name}"] = mask

    # Every DEIS establishment that passes the region/status/coordinate filters
    # is a health facility, so ``is_all_health`` is True for the whole set.
    # Named categories (hospital, clinic, primary_care) are subsets.
    gdf["is_all_health"] = True

    # Normalise output schema.
    gdf["name"] = gdf[name_col].astype(str)
    gdf["commune"] = gdf[commune_col].astype(str)
    gdf["source"] = "deis"

    out_cols = ["name", "commune", "official_type", "source"]
    out_cols += [f"is_{cat}" for cat in type_mapping.keys()]
    out_cols += ["is_all_health", "geometry"]

    return gdf[out_cols].copy().reset_index(drop=True)


def prepare_official_facilities(
    cfg: dict[str, Any],
    cache_dir: Path,
    *,
    refresh: bool = False,
) -> gpd.GeoDataFrame:
    """Download (if needed) and load the official DEIS facilities."""
    cache_path = Path(cache_dir) / "establecimientos_deis.csv"
    csv_path = fetch_deis_csv(cfg, cache_path, refresh=refresh)
    return load_deis_facilities(csv_path, cfg)

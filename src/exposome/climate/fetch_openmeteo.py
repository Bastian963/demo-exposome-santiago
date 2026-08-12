"""Fetch historical climate data from Open-Meteo API.

Alternative to GEE ERA5-Land for rapid bulk downloads.
Uses commune centroids as sampling points.

To reduce Open-Meteo API load, the module fetches the entire requested
year range in a single call per commune and caches the full range locally.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests
from tqdm import tqdm

from .. import boundaries, config

OPENMETEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "apparent_temperature_max",
    "precipitation_sum",
]


def _call_openmeteo(
    lat: float,
    lon: float,
    start: str,
    end: str,
    daily_vars: list[str] | None = None,
    max_retries: int = 8,
) -> dict[str, Any]:
    """Make a single Open-Meteo API call with retries and rate-limit handling."""
    daily_vars = daily_vars or DAILY_VARIABLES
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": ",".join(daily_vars),
        "timezone": "auto",
    }

    last_exception: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(OPENMETEO_ARCHIVE_URL, params=params, timeout=180)
            if resp.status_code == 429:
                wait = 2 ** attempt + 5
                print(f"    Rate limited (429). Retry {attempt + 1}/{max_retries} after {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            last_exception = e
            wait = 2 ** attempt + 5
            print(f"    Request error: {e}. Retry {attempt + 1}/{max_retries} after {wait}s...")
            time.sleep(wait)

    raise last_exception or RuntimeError("Open-Meteo request failed after retries")


def _parse_daily(data: dict[str, Any], name: str, daily_vars: list[str]) -> pd.DataFrame:
    """Parse Open-Meteo daily response into a tidy DataFrame."""
    daily = data.get("daily", {})
    dates = daily.get("time", [])

    rows = [{"name": name, "date": d} for d in dates]
    for var in daily_vars:
        values = daily.get(var, [])
        for i, row in enumerate(rows):
            if i < len(values):
                row[var] = values[i]

    return pd.DataFrame(rows)


def fetch_openmeteo_for_commune(
    name: str,
    lat: float,
    lon: float,
    year: int,
    daily_vars: list[str] | None = None,
) -> pd.DataFrame:
    """Fetch one year of daily data for a commune centroid (back-compat wrapper)."""
    daily_vars = daily_vars or DAILY_VARIABLES
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    data = _call_openmeteo(lat, lon, start, end, daily_vars=daily_vars)
    return _parse_daily(data, name, daily_vars)


def fetch_openmeteo_years(
    city: str = "santiago",
    years: list[int] | None = None,
    daily_vars: list[str] | None = None,
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> pd.DataFrame:
    """Fetch Open-Meteo historical data for all communes and years.

    Uses commune centroids as representative points. Fetches the entire
    requested year range in one API call per commune to minimize request
    volume and avoid Open-Meteo rate limits.
    """
    cfg = config.load_config(city)
    years = years or cfg.get("climate", {}).get("years", list(range(2015, 2025)))
    daily_vars = daily_vars or DAILY_VARIABLES

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load boundaries and get centroids
    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)
    gdf_metric = gdf_comm.to_crs(cfg["crs"]["metric"])
    centroids_metric = gdf_metric.geometry.centroid
    gdf_cent = gpd.GeoDataFrame(
        {"name": gdf_metric["name"]},
        geometry=centroids_metric,
        crs=cfg["crs"]["metric"],
    ).to_crs("EPSG:4326")
    gdf_wgs = gdf_comm[["name"]].copy()
    gdf_wgs["centroid_lat"] = gdf_cent.geometry.y.values
    gdf_wgs["centroid_lon"] = gdf_cent.geometry.x.values

    start_date = f"{min(years)}-01-01"
    end_date = f"{max(years)}-12-31"

    print(f"Fetching Open-Meteo for {len(gdf_wgs)} communes, {min(years)}-{max(years)}")

    all_dfs = []
    progress = tqdm(list(gdf_wgs.iterrows()), desc=f"climate_openmeteo [{city}]", unit="commune")
    for _, row in progress:
        name = row["name"]
        lat = row["centroid_lat"]
        lon = row["centroid_lon"]
        progress.set_postfix_str(name)

        safe_name = name.replace(" ", "_")
        range_cache = cache_dir / f"openmeteo_{safe_name}_{min(years)}_{max(years)}.csv"

        if range_cache.exists():
            df_comm = pd.read_csv(range_cache)
        else:
            try:
                data = _call_openmeteo(lat, lon, start_date, end_date, daily_vars=daily_vars)
                df_comm = _parse_daily(data, name, daily_vars)
                df_comm.to_csv(range_cache, index=False)
                time.sleep(3.0)  # polite pause between communes
            except Exception as e:
                tqdm.write(f"  ERROR {name}: {e}")
                continue

        df_comm["date"] = pd.to_datetime(df_comm["date"])
        df_comm["year"] = df_comm["date"].dt.year
        df_comm = df_comm[df_comm["year"].isin(years)].copy()
        df_comm = df_comm.drop(columns=["year"])
        all_dfs.append(df_comm)

    if not all_dfs:
        raise ValueError("No data fetched")

    df = pd.concat(all_dfs, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["name", "date"]).reset_index(drop=True)

    out_path = out_dir / f"{city}_climate_openmeteo_daily_{min(years)}_{max(years)}.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved: {out_path} ({len(df)} rows)")
    return df

"""Fetch ERA5-Land daily data via Google Earth Engine.

Server-side batch extraction, processing month-by-month to stay under
GEE's 5000-element getInfo() limit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import pandas as pd

from .. import boundaries, config, gee

ERA5LAND_DAILY = "ECMWF/ERA5_LAND/DAILY_AGGR"

DEFAULT_BANDS = [
    "temperature_2m",
    "temperature_2m_min",
    "temperature_2m_max",
    "dewpoint_temperature_2m",
    "total_precipitation_sum",
]

# Map GEE band names to output CSV column names for consistency with Open-Meteo.
BAND_NAME_MAP = {
    "temperature_2m": "temperature_2m_mean",
}


def _kelvin_to_celsius(k: float) -> float:
    return k - 273.15


def _parse_features(info: dict[str, Any], band: str) -> list[dict[str, Any]]:
    rows = []
    for feat in info.get("features", []):
        props = feat.get("properties", {})
        row = {
            "name": props.get("name"),
            "date": props.get("date"),
            band: props.get("mean"),
        }
        rows.append(row)
    return rows


def fetch_era5land_month_server_side(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    year: int,
    month: int,
    band: str,
    scale: int = 9_000,
) -> pd.DataFrame:
    """Fetch one band for one month."""
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1}-01-01"
    else:
        end = f"{year}-{month + 1:02d}-01"

    col = (
        ee.ImageCollection(ERA5LAND_DAILY)
        .filterDate(start, end)
        .select(band)
    )

    def extract(img: ee.Image) -> ee.FeatureCollection:
        date_str = img.date().format("YYYY-MM-dd")
        stats = img.reduceRegions(
            collection=regions_fc,
            reducer=ee.Reducer.mean(),
            scale=scale,
            crs="EPSG:4326",
            tileScale=4,
        )
        return stats.map(lambda f: f.set("date", date_str))

    flattened = col.map(extract).flatten()
    info = flattened.getInfo()
    rows = _parse_features(info, band)

    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError(f"No data for {year}-{month:02d} {band}")

    if "temperature" in band:
        df[band] = df[band].apply(lambda x: _kelvin_to_celsius(x) if pd.notna(x) else x)
    if "precipitation" in band:
        df[band] = df[band] * 1000.0

    return df


def fetch_era5land_year(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    year: int,
    bands: list[str] | None = None,
    scale: int = 9_000,
    cache_path: Path | None = None,
) -> pd.DataFrame:
    """Fetch one year, month by month, merging bands."""
    bands = bands or DEFAULT_BANDS

    if cache_path and cache_path.exists():
        return pd.read_csv(cache_path)

    all_months = []
    for month in range(1, 13):
        month_dfs = []
        for band in bands:
            try:
                df_band = fetch_era5land_month_server_side(cfg, regions_fc, year, month, band, scale=scale)
                month_dfs.append(df_band)
            except Exception as e:
                print(f"    {year}-{month:02d} {band}: ERROR {e}")
                continue

        if not month_dfs:
            continue

        df_month = month_dfs[0]
        for df_band in month_dfs[1:]:
            df_month = df_month.merge(df_band, on=["name", "date"], how="outer")

        all_months.append(df_month)
        print(f"  {year}-{month:02d}: {len(df_month)} rows")

    df_year = pd.concat(all_months, ignore_index=True)
    df_year = df_year.sort_values(["name", "date"]).reset_index(drop=True)

    # Rename GEE bands to consistent output column names.
    df_year = df_year.rename(columns=BAND_NAME_MAP)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df_year.to_csv(cache_path, index=False)

    return df_year


def fetch_era5land_years(
    city: str = "santiago",
    years: list[int] | None = None,
    bands: list[str] | None = None,
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> pd.DataFrame:
    """Fetch ERA5-Land for multiple years."""
    cfg = config.load_config(city)
    gee.init_gee()

    years = years or cfg.get("climate", {}).get("years", list(range(2015, 2025)))
    bands = bands or DEFAULT_BANDS
    scale = cfg.get("climate", {}).get("collections", {}).get("era5land_daily", {}).get("scale_meters", 9_000)

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)
    regions_fc = gee.gdf_to_feature_collection(gdf_comm)

    print(f"Fetching ERA5-Land for {city}: {min(years)}-{max(years)}, bands={bands}")

    all_years = []
    for year in years:
        year_cache = cache_dir / f"{city}_era5land_{year}.csv"
        try:
            df_year = fetch_era5land_year(cfg, regions_fc, year, bands=bands, scale=scale, cache_path=year_cache)
            all_years.append(df_year)
        except Exception as e:
            print(f"  {year}: ERROR {e}")

    if not all_years:
        raise ValueError("No data fetched for any year")

    df = pd.concat(all_years, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["name", "date"]).reset_index(drop=True)

    out_path = out_dir / f"{city}_climate_era5land_daily_{min(years)}_{max(years)}.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved combined: {out_path} ({len(df)} rows)")
    return df

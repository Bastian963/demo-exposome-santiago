"""Fetch MODIS LST (day and night) from GEE for thermal characterization.

Used for:
- Urban Heat Island detection
- Spatial thermal heterogeneity within communes/zip codes
- Covariate for downscaling model
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import pandas as pd

from .. import config, gee

MODIS_TERRA = "MODIS/061/MOD11A1"
MODIS_AQUA = "MODIS/061/MYD11A1"
LST_DAY_BAND = "LST_Day_1km"
LST_NIGHT_BAND = "LST_Night_1km"
QC_DAY_BAND = "QC_Day"
QC_NIGHT_BAND = "QC_Night"

# MODIS LST scale factor: 0.02, offset: 0
# Temperature in Kelvin = DN * 0.02
# Convert to Celsius by subtracting 273.15
LST_SCALE = 0.02
LST_OFFSET_K = 273.15


def _kelvin_dn_to_celsius(k: float) -> float:
    return k * LST_SCALE - LST_OFFSET_K


def mask_lst_quality(img: ee.Image, qc_band: str, max_error: int = 1) -> ee.Image:
    """Mask MODIS LST pixels based on QC flags.

    QC bits:
    - 0-1: LST produced, other quality
      0 = good quality, 1 = other quality, 2 = TBD, 3 = no produced
    We keep 0 and 1 (max_error=1) or 0-2 (max_error=2).
    """
    qa = img.select(qc_band)
    mask = qa.bitwiseAnd(3).lte(max_error)
    return img.updateMask(mask)


def _lst_to_celsius(img: ee.Image, band: str) -> ee.Image:
    """Apply MODIS LST scaling and convert Kelvin to Celsius."""
    return img.select(band).multiply(LST_SCALE).subtract(LST_OFFSET_K)


def _fetch_single_collection_stats(
    collection_id: str,
    regions_fc: ee.FeatureCollection,
    start: str,
    end: str,
    day_night: str,
    scale: int,
    max_error: int,
) -> pd.DataFrame:
    """Fetch LST stats from a single MODIS collection (Terra or Aqua)."""
    cols = []
    for band, qc in [
        (LST_DAY_BAND, QC_DAY_BAND),
        (LST_NIGHT_BAND, QC_NIGHT_BAND),
    ]:
        if day_night == "day" and band != LST_DAY_BAND:
            continue
        if day_night == "night" and band != LST_NIGHT_BAND:
            continue

        col = (
            ee.ImageCollection(collection_id)
            .filterDate(start, end)
            .select([band, qc])
            .map(lambda img: mask_lst_quality(img, qc, max_error=max_error))
            .map(lambda img: _lst_to_celsius(img, band))
        )

        # Mean composite
        mean_img = col.mean().rename(f"{band}_mean_c")
        # Max composite
        max_img = col.max().rename(f"{band}_max_c")
        # 95th percentile composite (for night UHI extremes)
        p95_img = col.reduce(ee.Reducer.percentile([95])).rename(f"{band}_p95_c")

        stats_mean = gee.image_to_stats(mean_img, regions_fc, band=f"{band}_mean_c", scale=scale, reducer="mean")
        stats_max = gee.image_to_stats(max_img, regions_fc, band=f"{band}_max_c", scale=scale, reducer="mean")
        stats_p95 = gee.image_to_stats(p95_img, regions_fc, band=f"{band}_p95_c", scale=scale, reducer="mean")

        df_mean = pd.DataFrame(gee.fc_to_dicts(stats_mean))[["name", "mean"]].rename(columns={"mean": f"{band}_mean_c"})
        df_max = pd.DataFrame(gee.fc_to_dicts(stats_max))[["name", "mean"]].rename(columns={"mean": f"{band}_max_c"})
        df_p95 = pd.DataFrame(gee.fc_to_dicts(stats_p95))[["name", "mean"]].rename(columns={"mean": f"{band}_p95_c"})

        df = df_mean.merge(df_max, on="name", how="outer").merge(df_p95, on="name", how="outer")
        cols.append(df)

    if not cols:
        raise ValueError(f"No bands selected for day_night={day_night}")

    out = cols[0]
    for df in cols[1:]:
        out = out.merge(df, on="name", how="outer")
    return out


def fetch_modis_lst(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    start: str,
    end: str,
    day_night: str = "both",
    scale: int = 1_000,
    max_error: int = 1,
    use_aqua: bool = True,
) -> pd.DataFrame:
    """Fetch mean/max/p95 MODIS LST for a period.

    Parameters
    ----------
    cfg : dict
        City config (kept for API consistency; not used directly).
    regions_fc : ee.FeatureCollection
        Regions for zonal stats.
    start, end : str
        ISO dates.
    day_night : str
        "day", "night", or "both".
    scale : int
        Zonal stats scale in meters.
    max_error : int
        Maximum QC error to keep (0=best, 1=good, 2=TBD).
    use_aqua : bool
        If True, average Terra and Aqua composites.

    Returns
    -------
    pd.DataFrame
        Columns: name, lst_day_mean_c, lst_day_max_c, lst_day_p95_c,
        lst_night_mean_c, lst_night_max_c, lst_night_p95_c.
    """
    df_terra = _fetch_single_collection_stats(
        MODIS_TERRA, regions_fc, start, end, day_night, scale, max_error
    )

    if not use_aqua:
        return df_terra

    df_aqua = _fetch_single_collection_stats(
        MODIS_AQUA, regions_fc, start, end, day_night, scale, max_error
    )

    # Merge and average Terra + Aqua
    merged = df_terra.merge(df_aqua, on="name", how="outer", suffixes=("_terra", "_aqua"))
    value_cols = [c for c in merged.columns if c.endswith("_terra")]
    for col in value_cols:
        base = col.replace("_terra", "")
        aqua_col = f"{base}_aqua"
        if aqua_col in merged.columns:
            merged[base] = merged[[col, aqua_col]].mean(axis=1, skipna=True)
        else:
            merged[base] = merged[col]

    final_cols = ["name"] + [c.replace("_terra", "") for c in value_cols]
    return merged[final_cols].copy()


def fetch_modis_lst_annual_and_summer(
    city: str = "santiago",
    years: list[int] | None = None,
    scale: int = 1_000,
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> pd.DataFrame:
    """Fetch annual and summer MODIS LST summaries for each year.

    Summer is defined as Dec-Feb (Southern Hemisphere).
    """
    cfg = config.load_config(city)
    gee.init_gee()

    years = years or cfg.get("climate", {}).get("years", list(range(2015, 2025)))

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    from .. import boundaries

    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)
    regions_fc = gee.gdf_to_feature_collection(gdf_comm)

    print(f"Fetching MODIS LST for {city}: {min(years)}-{max(years)}")

    all_rows = []
    for year in years:
        cache_path = cache_dir / f"{city}_modis_lst_{year}.csv"
        if cache_path.exists():
            df_year = pd.read_csv(cache_path)
            all_rows.append(df_year)
            continue

        # Annual: Jan-Dec
        annual_start = f"{year}-01-01"
        annual_end = f"{year + 1}-01-01"
        df_annual = fetch_modis_lst(cfg, regions_fc, annual_start, annual_end, scale=scale)
        df_annual["year"] = year
        df_annual["season"] = "annual"

        # Summer: Dec(year-1) - Feb(year)
        summer_start = f"{year - 1}-12-01"
        summer_end = f"{year}-03-01"
        df_summer = fetch_modis_lst(cfg, regions_fc, summer_start, summer_end, scale=scale)
        df_summer["year"] = year
        df_summer["season"] = "summer"

        df_year = pd.concat([df_annual, df_summer], ignore_index=True)
        df_year.to_csv(cache_path, index=False)
        all_rows.append(df_year)
        print(f"  {year}: {len(df_year)} rows")

    df = pd.concat(all_rows, ignore_index=True)
    df = df.sort_values(["name", "year", "season"]).reset_index(drop=True)

    out_path = out_dir / f"{city}_climate_modis_lst_{min(years)}_{max(years)}.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved: {out_path} ({len(df)} rows)")
    return df

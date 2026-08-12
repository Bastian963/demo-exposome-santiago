"""Fetch ERA5-Land daily data via Google Earth Engine.

Server-side batch extraction, processing in sub-month date windows to stay
under GEE's 5000-element collection-query abort.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ee
import pandas as pd
from tqdm import tqdm

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
        coordinates = feat.get("geometry", {}).get("coordinates", [None, None])
        lon, lat = coordinates[:2] if len(coordinates) >= 2 else (None, None)
        row = {
            "lon": lon,
            "lat": lat,
            "date": props.get("date"),
            # ``Image.sample`` keeps the selected band's own property name.
            # The old parser looked only for ``mean`` (the property emitted by
            # reducers), silently writing an all-NaN annual cache even though
            # GEE had returned every pixel/date successfully.
            band: props.get(band, props.get("mean")),
        }
        if lon is not None and lat is not None:
            row["pixel_id"] = f"{float(lon):.6f}:{float(lat):.6f}"
        rows.append(row)
    return rows


def _cache_has_required_values(
    frame: pd.DataFrame,
    bands: list[str],
) -> bool:
    """Return whether an ERA5 annual cache is complete enough to resume."""
    required = {"pixel_id", "lon", "lat", "date"}
    output_bands = [BAND_NAME_MAP.get(band, band) for band in bands]
    if frame.empty or not required.issubset(frame.columns):
        return False
    if any(column not in frame.columns for column in output_bands):
        return False
    if frame[output_bands].isna().any().any():
        return False
    dates = pd.to_datetime(frame["date"], errors="coerce")
    return set(range(1, 13)).issubset(set(dates.dt.month.dropna().astype(int)))


def _quarantine_invalid_cache(cache_path: Path) -> Path:
    """Move an invalid cache aside instead of deleting it."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = cache_path.with_name(f"{cache_path.stem}.invalid_{stamp}{cache_path.suffix}")
    counter = 2
    while target.exists():
        target = cache_path.with_name(
            f"{cache_path.stem}.invalid_{stamp}_{counter}{cache_path.suffix}"
        )
        counter += 1
    cache_path.replace(target)
    return target


def _complete_cached_months(frame: pd.DataFrame, bands: list[str], year: int) -> set[int]:
    """Return months whose partial cache has every day, band and pixel value."""
    required = {"pixel_id", "date", *bands}
    if frame.empty or not required.issubset(frame.columns):
        return set()
    dates = pd.to_datetime(frame["date"], errors="coerce")
    completed: set[int] = set()
    for month in range(1, 13):
        rows = frame[(dates.dt.year == year) & (dates.dt.month == month)]
        expected_days = set(range(1, calendar.monthrange(year, month)[1] + 1))
        if rows.empty or set(pd.to_datetime(rows["date"]).dt.day) != expected_days:
            continue
        if rows[list(bands)].isna().any().any():
            continue
        counts = rows.groupby("date")["pixel_id"].nunique()
        if counts.empty or counts.nunique() != 1:
            continue
        completed.add(month)
    return completed


def _month_date_windows(year: int, month: int, max_days: int = 11) -> list[tuple[str, str]]:
    """Split a month into ``filterDate`` windows of at most ``max_days`` days.

    Ends are exclusive.  A full 31-day month sampled over the AOI bounding box
    accumulates enough elements to trip GEE's 5000-element collection-query
    abort; 11-day windows give three calls per month, each far below it.
    """
    n_days = calendar.monthrange(year, month)[1]
    windows = []
    for day0 in range(1, n_days + 1, max_days):
        day_end = min(day0 + max_days - 1, n_days)
        start = f"{year}-{month:02d}-{day0:02d}"
        if day_end == n_days:
            end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"
        else:
            end = f"{year}-{month:02d}-{day_end + 1:02d}"
        windows.append((start, end))
    return windows


def era5land_max_days_for_aoi(
    aoi_metric_bounds: tuple[float, float, float, float],
    scale: int = 11_132,
    budget: int = 4000,
    default_max_days: int = 11,
) -> int:
    """Pick a per-month window size that keeps ``days * pixels`` under GEE's abort.

    ``_month_date_windows``'s 11-day default was tuned for a single
    city/comuna bbox. A whole-province AOI (San Juan: ~440x490 km, ~1,580
    ERA5-Land pixels at 11,132 m) blows past the 5000-element abort even at
    11 days (11 * 1,580 ~= 17,000); a smaller city bbox stays comfortably
    under 5000 even at the 11-day default, so this never shrinks it further
    than that proven value -- only larger AOIs get a smaller window.
    """
    west, south, east, north = aoi_metric_bounds
    width_m = max(east - west, scale)
    height_m = max(north - south, scale)
    n_pixels = (width_m / scale) * (height_m / scale)
    return max(1, min(default_max_days, int(budget // n_pixels)))


def fetch_era5land_month_server_side(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    year: int,
    month: int,
    band: str,
    scale: int = 11_132,
    max_days: int = 11,
) -> pd.DataFrame:
    """Fetch native ERA5-Land pixel samples for one band/month.

    ``regions_fc`` is retained as the public parameter name for callers, but
    it is now an AOI feature collection.  Sampling uses the image projection,
    never ``reduceRegions`` over administrative units.

    ``max_days`` must shrink for AOIs whose bbox covers enough pixels that
    even an 11-day window trips GEE's 5000-element abort (a whole province
    like San Juan, unlike a single city/comuna bbox) -- see
    :func:`era5land_max_days_for_aoi`.
    """

    def extract(img: ee.Image) -> ee.FeatureCollection:
        date_str = img.date().format("YYYY-MM-dd")
        stats = img.sample(
            # Sample the AOI bounds, not only pixels whose centre falls inside
            # the dissolved boundary.  The later polygon intersection needs
            # the full edge-pixel ring so tiny boundary units are not missed.
            region=regions_fc.geometry().bounds(),
            scale=scale,
            projection=img.projection(),
            geometries=True,
            tileScale=4,
        )
        return stats.map(lambda f: f.set("date", date_str))

    rows: list[dict[str, Any]] = []
    for start, end in _month_date_windows(year, month, max_days=max_days):
        col = (
            ee.ImageCollection(ERA5LAND_DAILY)
            .filterDate(start, end)
            .select(band)
        )
        flattened = col.map(extract).flatten()
        rows.extend(_parse_features(flattened.getInfo(), band))

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
    scale: int = 11_132,
    cache_path: Path | None = None,
    max_days: int = 11,
) -> pd.DataFrame:
    """Fetch one year, month by month, merging bands."""
    bands = bands or DEFAULT_BANDS

    if cache_path and cache_path.exists():
        cached = pd.read_csv(cache_path)
        if _cache_has_required_values(cached, bands):
            return cached
        quarantined = _quarantine_invalid_cache(cache_path)
        tqdm.write(
            f"  [{year}] invalid ERA5-Land cache moved to {quarantined.name}; refetching"
        )

    partial_path = (
        cache_path.with_name(f"{cache_path.stem}.partial{cache_path.suffix}")
        if cache_path
        else None
    )
    partial = pd.DataFrame()
    if partial_path and partial_path.is_file():
        try:
            partial = pd.read_csv(partial_path)
        except (OSError, pd.errors.EmptyDataError):
            partial = pd.DataFrame()
    completed_months = _complete_cached_months(partial, bands, year)
    if completed_months:
        tqdm.write(
            f"  [{year}] resuming ERA5-Land cache; months already saved: "
            + ", ".join(f"{month:02d}" for month in sorted(completed_months))
        )

    for month in tqdm(range(1, 13), desc=f"era5land {year}", unit="month", leave=False):
        if month in completed_months:
            continue
        month_dfs = []
        for band in bands:
            try:
                df_band = fetch_era5land_month_server_side(
                    cfg, regions_fc, year, month, band, scale=scale, max_days=max_days
                )
                month_dfs.append(df_band)
            except Exception as e:
                tqdm.write(f"    {year}-{month:02d} {band}: ERROR {e}")
                continue

        if not month_dfs:
            continue

        df_month = month_dfs[0]
        for df_band in month_dfs[1:]:
            df_month = df_month.merge(df_band, on=["pixel_id", "lon", "lat", "date"], how="outer")

        partial = pd.concat([partial, df_month], ignore_index=True)
        partial = partial.drop_duplicates(["pixel_id", "date"], keep="last")
        if partial_path:
            partial_path.parent.mkdir(parents=True, exist_ok=True)
            partial.to_csv(partial_path, index=False)
        tqdm.write(f"  {year}-{month:02d}: {len(df_month)} rows")

    if partial.empty:
        raise ValueError(f"No ERA5-Land monthly data fetched for {year}")
    df_year = partial.copy()
    df_year = df_year.sort_values(["pixel_id", "date"]).reset_index(drop=True)

    # Rename GEE bands to consistent output column names.
    df_year = df_year.rename(columns=BAND_NAME_MAP)

    if not _cache_has_required_values(df_year, bands):
        raise ValueError(
            f"ERA5-Land {year} result is incomplete or contains missing band values; "
            "the invalid year was not cached"
        )

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df_year.to_csv(cache_path, index=False)
        if partial_path and partial_path.exists():
            partial_path.unlink()

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
    scale = cfg.get("climate", {}).get("collections", {}).get("era5land_daily", {}).get("scale_meters", 11_132)

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)
    # Dissolve before sampling: a changed administrative partition cannot
    # change the selected pixels or their values.
    aoi = gdf_comm[["geometry"]].dissolve().reset_index(drop=True)
    regions_fc = gee.gdf_to_feature_collection(aoi)

    metric_crs = cfg.get("crs", {}).get("metric")
    aoi_metric_bounds = tuple(aoi.to_crs(metric_crs).total_bounds) if metric_crs else None
    max_days = (
        era5land_max_days_for_aoi(aoi_metric_bounds, scale=scale)
        if aoi_metric_bounds is not None
        else 11
    )
    if max_days < 11:
        print(
            f"AOI bbox is large enough at {scale} m scale to need "
            f"max_days={max_days} per GEE query (default 11) to stay under "
            "the 5000-element collection-query abort."
        )

    print(f"Fetching ERA5-Land for {city}: {min(years)}-{max(years)}, bands={bands}")

    all_years = []
    for year in tqdm(years, desc=f"era5land [{city}]", unit="year"):
        year_cache = cache_dir / f"{city}_era5land_grid_{year}.csv"
        if year_cache.exists():
            tqdm.write(f"  [{year}] loading from cache …")
        else:
            tqdm.write(f"  [{year}] fetching from GEE …")
        try:
            df_year = fetch_era5land_year(
                cfg, regions_fc, year, bands=bands, scale=scale, cache_path=year_cache, max_days=max_days
            )
            all_years.append(df_year)
        except Exception as e:
            tqdm.write(f"  {year}: ERROR {e}")

    if not all_years:
        raise ValueError("No data fetched for any year")

    df = pd.concat(all_years, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["pixel_id", "date"]).reset_index(drop=True)

    out_path = out_dir / f"{city}_climate_era5land_grid_daily_{min(years)}_{max(years)}.csv"
    df.to_csv(out_path, index=False)
    print(f"Saved combined: {out_path} ({len(df)} rows)")
    return df


def ensure_era5land_daily(
    city: str,
    *,
    year: int,
    cache_dir: Path,
) -> Path:
    """Ensure the native ERA5-Land pixel-day cache required by heat exists.

    A normal Study run invokes the importable heat builder directly, rather
    than the old two-command wrapper.  Keeping this gate here means a first
    run fetches its missing provider cache, while a resumed run leaves a
    complete year untouched.  The caller is responsible for invoking this
    only in an approved data-collection execution.
    """
    cache_dir = Path(cache_dir)
    cache_path = cache_dir / f"{city}_era5land_grid_{year}.csv"
    if cache_path.is_file():
        try:
            cached = pd.read_csv(cache_path)
        except (OSError, pd.errors.EmptyDataError):
            cached = pd.DataFrame()
        if _cache_has_required_values(cached, DEFAULT_BANDS):
            return cache_path

    fetch_era5land_years(
        city=city,
        years=[year],
        cache_dir=cache_dir,
        # This combined convenience export is auxiliary operation state; the
        # per-year cache above remains the input consumed by the heat builder.
        out_dir=cache_dir,
    )
    if not cache_path.is_file():
        raise FileNotFoundError(f"ERA5-Land cache was not created: {cache_path}")
    return cache_path

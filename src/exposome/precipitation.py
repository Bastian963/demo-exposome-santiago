"""Daily precipitation exposome layer via CHIRPS and Google Earth Engine.

The layer summarizes commune-level rainfall exposure for the Santiago urban
exposome. It is designed as an exposure table that can later be joined to
brain-health, cognitive, biomarker, or neuroimaging outcomes; it does not claim
causality or model any brain outcome directly.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import numpy as np
import pandas as pd

from . import boundaries, config, gee


DEFAULT_CHIRPS_COLLECTION = "UCSB-CHG/CHIRPS/DAILY"
DEFAULT_PRECIP_BAND = "precipitation"

OUTPUT_COLUMNS = [
    "name",
    "area_km2",
    "precip_annual_mean_mm",
    "precip_annual_sd_mm",
    "precip_annual_cv",
    "precip_wet_days",
    "precip_wet_day_pct",
    "precip_heavy_days_10mm",
    "precip_very_heavy_days_20mm",
    "precip_rx1day_mm",
    "precip_rx5day_mm",
    "precip_cdd_days",
    "precip_cwd_days",
    "precip_intensity_wet_day_mm",
    "precip_winter_mean_mm",
    "precip_summer_mean_mm",
    "precip_latest_year_mm",
    "precip_latest_anomaly_mm",
    "precip_latest_anomaly_pct",
    "precip_extremes_index",
    "precip_n_years",
    "precip_n_days",
]


def _parse_features(info: dict[str, Any], out_col: str) -> list[dict[str, Any]]:
    rows = []
    for feat in info.get("features", []):
        props = feat.get("properties", {})
        rows.append(
            {
                "name": props.get("name"),
                "date": props.get("date"),
                out_col: props.get("mean"),
            }
        )
    return rows


def fetch_chirps_month_server_side(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    year: int,
    month: int,
    scale: int | None = None,
) -> pd.DataFrame:
    """Fetch one month of CHIRPS daily precipitation for all communes."""
    pr_cfg = cfg.get("precipitation", {})
    col_cfg = pr_cfg.get("collection", {})
    collection_id = col_cfg.get("id", DEFAULT_CHIRPS_COLLECTION)
    band = col_cfg.get("band", DEFAULT_PRECIP_BAND)
    scale = scale or int(col_cfg.get("scale_meters", 5_566))

    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1}-01-01"
    else:
        end = f"{year}-{month + 1:02d}-01"

    collection = ee.ImageCollection(collection_id).filterDate(start, end).select(band)

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

    info = collection.map(extract).flatten().getInfo()
    df = pd.DataFrame(_parse_features(info, "precipitation_mm"))
    if df.empty:
        raise ValueError(f"No CHIRPS precipitation data for {year}-{month:02d}")
    return df


def fetch_chirps_period_server_side(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    start: str,
    end: str,
    scale: int | None = None,
) -> pd.DataFrame:
    """Fetch a date range of CHIRPS daily precipitation for all communes."""
    pr_cfg = cfg.get("precipitation", {})
    col_cfg = pr_cfg.get("collection", {})
    collection_id = col_cfg.get("id", DEFAULT_CHIRPS_COLLECTION)
    band = col_cfg.get("band", DEFAULT_PRECIP_BAND)
    scale = scale or int(col_cfg.get("scale_meters", 5_566))

    collection = ee.ImageCollection(collection_id).filterDate(start, end).select(band)

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

    info = collection.map(extract).flatten().getInfo()
    df = pd.DataFrame(_parse_features(info, "precipitation_mm"))
    if df.empty:
        raise ValueError(f"No CHIRPS precipitation data for {start} to {end}")
    return df


def fetch_chirps_year(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    year: int,
    scale: int | None = None,
    cache_path: Path | None = None,
) -> pd.DataFrame:
    """Fetch one year of daily CHIRPS data, month by month."""
    if cache_path and cache_path.exists():
        df_cached = pd.read_csv(cache_path)
        df_cached["date"] = pd.to_datetime(df_cached["date"])
        return df_cached

    periods = [
        (f"{year}-01-01", f"{year}-04-01", "Q1"),
        (f"{year}-04-01", f"{year}-07-01", "Q2"),
        (f"{year}-07-01", f"{year}-10-01", "Q3"),
        (f"{year}-10-01", f"{year + 1}-01-01", "Q4"),
    ]

    period_dfs = []
    for start, end, label in periods:
        df_period = fetch_chirps_period_server_side(
            cfg, regions_fc, start, end, scale=scale
        )
        period_dfs.append(df_period)
        print(f"  {year}-{label}: {len(df_period)} rows")

    df_year = pd.concat(period_dfs, ignore_index=True)
    df_year["date"] = pd.to_datetime(df_year["date"])
    df_year = df_year.sort_values(["name", "date"]).reset_index(drop=True)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df_year.to_csv(cache_path, index=False)

    return df_year


def fetch_chirps_daily_years(
    city: str = "santiago",
    years: list[int] | None = None,
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> pd.DataFrame:
    """Fetch daily CHIRPS precipitation for configured years and communes."""
    cfg = config.load_config(city)
    gee.init_gee()

    pr_cfg = cfg.get("precipitation", {})
    years = years or pr_cfg.get("years") or cfg.get("climate", {}).get("years")
    if not years:
        raise ValueError("No precipitation years configured")
    years = [int(year) for year in years]

    collection_cfg = pr_cfg.get("collection", {})
    scale = int(collection_cfg.get("scale_meters", 5_566))

    cache_dir = Path(cache_dir)
    out_dir = Path(out_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)
    regions_fc = gee.gdf_to_feature_collection(gdf_comm)

    print(
        f"Fetching CHIRPS precipitation for {city}: "
        f"{min(years)}-{max(years)}"
    )

    all_years = []
    for year in years:
        year_cache = cache_dir / f"{city}_precipitation_chirps_{year}.csv"
        df_year = fetch_chirps_year(
            cfg, regions_fc, year, scale=scale, cache_path=year_cache
        )
        all_years.append(df_year)

    df = pd.concat(all_years, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["name", "date"]).reset_index(drop=True)

    daily_out = out_dir / (
        f"{city}_precipitation_chirps_daily_{min(years)}_{max(years)}.csv"
    )
    df.to_csv(daily_out, index=False)
    print(f"Saved daily precipitation: {daily_out} ({len(df)} rows)")
    return df


def calculate_precipitation_metrics(
    df_daily: pd.DataFrame,
    date_col: str = "date",
    precip_col: str = "precipitation_mm",
    group_col: str = "name",
    wet_day_threshold_mm: float = 1.0,
    heavy_day_threshold_mm: float = 10.0,
    very_heavy_day_threshold_mm: float = 20.0,
    latest_year: int | None = None,
) -> pd.DataFrame:
    """Calculate commune-level chronic and latest-year rainfall metrics."""
    required = {date_col, precip_col, group_col}
    missing = sorted(required - set(df_daily.columns))
    if missing:
        raise ValueError(f"Missing precipitation input columns: {missing}")

    df = df_daily[[group_col, date_col, precip_col]].copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df[precip_col] = pd.to_numeric(df[precip_col], errors="coerce")
    if df[precip_col].isna().any():
        raise ValueError(f"{precip_col} contains missing or non-numeric values")

    df["year"] = df[date_col].dt.year
    df["month"] = df[date_col].dt.month
    if latest_year is None:
        latest_year = int(df["year"].max())

    rows = []
    for name, gdf in df.groupby(group_col, sort=True):
        metrics = _metrics_for_group(
            gdf.sort_values(date_col),
            date_col=date_col,
            precip_col=precip_col,
            wet_day_threshold_mm=wet_day_threshold_mm,
            heavy_day_threshold_mm=heavy_day_threshold_mm,
            very_heavy_day_threshold_mm=very_heavy_day_threshold_mm,
            latest_year=latest_year,
        )
        metrics[group_col] = name
        rows.append(metrics)

    out = pd.DataFrame(rows)
    if out.empty:
        raise ValueError("No precipitation metrics could be calculated")

    out["precip_extremes_index"] = _extremes_index(out)
    ordered = [group_col, *[c for c in out.columns if c != group_col]]
    return out[ordered].copy()


def _metrics_for_group(
    gdf: pd.DataFrame,
    date_col: str,
    precip_col: str,
    wet_day_threshold_mm: float,
    heavy_day_threshold_mm: float,
    very_heavy_day_threshold_mm: float,
    latest_year: int,
) -> dict[str, float | int]:
    annual_rows = []
    for year, ydf in gdf.groupby("year", sort=True):
        precip = ydf[precip_col].astype(float)
        wet = precip >= wet_day_threshold_mm
        annual_rows.append(
            {
                "year": int(year),
                "annual_total": float(precip.sum()),
                "n_days": int(len(ydf)),
                "wet_days": int(wet.sum()),
                "wet_day_pct": float(wet.mean() * 100.0),
                "heavy_days": int((precip >= heavy_day_threshold_mm).sum()),
                "very_heavy_days": int(
                    (precip >= very_heavy_day_threshold_mm).sum()
                ),
                "rx1day": float(precip.max()),
                "rx5day": float(precip.rolling(5, min_periods=1).sum().max()),
                "cdd": _max_consecutive(~wet),
                "cwd": _max_consecutive(wet),
            }
        )

    annual = pd.DataFrame(annual_rows).sort_values("year")
    annual_mean = float(annual["annual_total"].mean())
    annual_sd = float(annual["annual_total"].std(ddof=0))
    annual_cv = annual_sd / annual_mean if annual_mean > 0 else 0.0

    seasonal_rows = []
    for year, ydf in gdf.groupby("year", sort=True):
        seasonal_rows.append(
            {
                "year": int(year),
                "winter": float(
                    ydf.loc[ydf["month"].isin([6, 7, 8]), precip_col].sum()
                ),
                "summer": float(
                    ydf.loc[ydf["month"].isin([12, 1, 2]), precip_col].sum()
                ),
            }
        )
    seasonal = pd.DataFrame(seasonal_rows).set_index("year")

    if latest_year in annual["year"].to_numpy():
        latest_total = float(
            annual.loc[annual["year"] == latest_year, "annual_total"].iloc[0]
        )
    else:
        latest_total = float(annual["annual_total"].iloc[-1])
        latest_year = int(annual["year"].iloc[-1])

    baseline = annual.loc[annual["year"] < latest_year, "annual_total"]
    baseline_mean = float(baseline.mean()) if len(baseline) else annual_mean
    latest_anomaly_mm = latest_total - baseline_mean
    latest_anomaly_pct = (
        latest_anomaly_mm / baseline_mean * 100.0 if baseline_mean > 0 else 0.0
    )

    wet_days_mean = float(annual["wet_days"].mean())
    intensity = annual["annual_total"] / annual["wet_days"].replace(0, np.nan)
    intensity_mean = float(intensity.fillna(0.0).mean())

    return {
        "precip_annual_mean_mm": annual_mean,
        "precip_annual_sd_mm": annual_sd,
        "precip_annual_cv": annual_cv,
        "precip_wet_days": wet_days_mean,
        "precip_wet_day_pct": float(annual["wet_day_pct"].mean()),
        "precip_heavy_days_10mm": float(annual["heavy_days"].mean()),
        "precip_very_heavy_days_20mm": float(annual["very_heavy_days"].mean()),
        "precip_rx1day_mm": float(annual["rx1day"].mean()),
        "precip_rx5day_mm": float(annual["rx5day"].mean()),
        "precip_cdd_days": float(annual["cdd"].mean()),
        "precip_cwd_days": float(annual["cwd"].mean()),
        "precip_intensity_wet_day_mm": intensity_mean,
        "precip_winter_mean_mm": float(seasonal["winter"].mean()),
        "precip_summer_mean_mm": float(seasonal["summer"].mean()),
        "precip_latest_year_mm": latest_total,
        "precip_latest_anomaly_mm": latest_anomaly_mm,
        "precip_latest_anomaly_pct": latest_anomaly_pct,
        "precip_n_years": int(annual["year"].nunique()),
        "precip_n_days": int(annual["n_days"].sum()),
    }


def _max_consecutive(mask: pd.Series) -> int:
    if mask.empty:
        return 0
    values = mask.astype(bool).to_numpy()
    best = 0
    current = 0
    for value in values:
        if value:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return int(best)


def _rank_percentile(values: pd.Series) -> pd.Series:
    if len(values) <= 1:
        return pd.Series(50.0, index=values.index)
    ranks = values.rank(method="average")
    return (ranks - 1) / (len(values) - 1) * 100.0


def _extremes_index(df: pd.DataFrame) -> pd.Series:
    components = pd.DataFrame(
        {
            "heavy": _rank_percentile(df["precip_heavy_days_10mm"]),
            "rx5day": _rank_percentile(df["precip_rx5day_mm"]),
            "dry_spell": _rank_percentile(df["precip_cdd_days"]),
            "latest_anomaly": _rank_percentile(
                df["precip_latest_anomaly_pct"].abs()
            ),
        },
        index=df.index,
    )
    return components.mean(axis=1)


def _validate_precipitation_output(df: pd.DataFrame, expected_communes: int) -> None:
    if len(df) != expected_communes:
        raise ValueError(f"Expected {expected_communes} rows, got {len(df)}")
    if df["name"].duplicated().any():
        dupes = df.loc[df["name"].duplicated(), "name"].tolist()
        raise ValueError(f"Duplicate commune names: {dupes}")
    missing_cols = [col for col in OUTPUT_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing precipitation output columns: {missing_cols}")
    if df[OUTPUT_COLUMNS].isna().any().any():
        missing = df[OUTPUT_COLUMNS].columns[
            df[OUTPUT_COLUMNS].isna().any()
        ].tolist()
        raise ValueError(f"Missing values in precipitation output: {missing}")
    if not df["precip_extremes_index"].between(0, 100).all():
        raise ValueError("precip_extremes_index must be bounded between 0 and 100")


def build_precipitation_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Build the CHIRPS precipitation exposome layer and write outputs."""
    cfg = config.load_config(city)
    pr_cfg = cfg.get("precipitation", {})
    years = [int(year) for year in pr_cfg.get("years", [])]
    if not years:
        raise ValueError("No precipitation years configured")

    thresholds = pr_cfg.get("thresholds", {})
    wet_day_mm = float(thresholds.get("wet_day_mm", 1.0))
    heavy_day_mm = float(thresholds.get("heavy_day_mm", 10.0))
    very_heavy_day_mm = float(thresholds.get("very_heavy_day_mm", 20.0))

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    df_daily = fetch_chirps_daily_years(
        city=city, years=years, cache_dir=cache_dir, out_dir=out_dir
    )
    missing_daily_values = int(df_daily["precipitation_mm"].isna().sum())
    if missing_daily_values:
        raise ValueError(
            "CHIRPS daily precipitation has missing values; "
            f"cannot build a strict layer ({missing_daily_values} missing)"
        )

    metrics = calculate_precipitation_metrics(
        df_daily,
        wet_day_threshold_mm=wet_day_mm,
        heavy_day_threshold_mm=heavy_day_mm,
        very_heavy_day_threshold_mm=very_heavy_day_mm,
        latest_year=max(years),
    )

    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)
    df = gdf_comm[["name", "area_km2"]].merge(
        metrics, on="name", how="left", validate="one_to_one"
    )

    int_cols = ["precip_n_years", "precip_n_days"]
    for col in df.columns:
        if col not in {"name", *int_cols}:
            if pd.api.types.is_numeric_dtype(df[col]):
                df[col] = df[col].round(4)
    for col in int_cols:
        df[col] = df[col].astype(int)

    df = df[OUTPUT_COLUMNS].copy()
    _validate_precipitation_output(df, int(cfg["expected_communes"]))

    gdf = gdf_comm[["name", "geometry"]].merge(
        df, on="name", how="right", validate="one_to_one"
    )
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    base_name = f"{city}_precipitation_chirps_{min(years)}_{max(years)}"
    csv_path = out_dir / f"{base_name}.csv"
    geojson_path = out_dir / f"{base_name}.geojson"
    json_path = out_dir / f"{base_name}.json"

    df.to_csv(csv_path, index=False)
    gdf.to_file(geojson_path, driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "years": years,
        "latest_year": max(years),
        "method": (
            "CHIRPS daily precipitation, commune area means via Google Earth "
            "Engine, summarized into chronic rainfall, heavy-rain, dry-spell, "
            "seasonal, and latest-year anomaly metrics."
        ),
        "interpretation": (
            "Exploratory exposome monitoring layer for later linkage with "
            "brain-health, cognitive, biomarker, or neuroimaging outcomes; "
            "not a causal brain-outcome model."
        ),
        "thresholds_mm": {
            "wet_day": wet_day_mm,
            "heavy_day": heavy_day_mm,
            "very_heavy_day": very_heavy_day_mm,
        },
        "sources": {
            "chirps": {
                "provider": "UCSB Climate Hazards Center",
                "collection": pr_cfg.get("collection", {}).get(
                    "id", DEFAULT_CHIRPS_COLLECTION
                ),
                "band": pr_cfg.get("collection", {}).get(
                    "band", DEFAULT_PRECIP_BAND
                ),
                "scale_meters": pr_cfg.get("collection", {}).get(
                    "scale_meters", 5_566
                ),
                "earth_engine_catalog": (
                    "https://developers.google.com/earth-engine/datasets/"
                    "catalog/UCSB-CHG_CHIRPS_DAILY"
                ),
            },
            "brain_health_context": {
                "weather_woes": "https://www.mdpi.com/1660-4601/17/23/9011"
            },
        },
        "columns": df.columns.tolist(),
        "outputs": [
            csv_path.name,
            geojson_path.name,
            json_path.name,
            f"{city}_precipitation_chirps_daily_{min(years)}_{max(years)}.csv",
        ],
    }
    json_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(
        f"Wrote {csv_path.name} / {geojson_path.name} "
        f"({len(df)} rows x {df.shape[1]} cols)"
    )
    return df, gdf

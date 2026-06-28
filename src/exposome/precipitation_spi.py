"""Precipitation drought indices (SPI) and anomaly-monitoring layer.

Complements the existing CHIRPS-based precipitation module
(:mod:`exposome.precipitation`) by adding:

- **SPI** (Standardized Precipitation Index) at 3-, 6-, and 12-month scales,
  computed on the 2015-2024 CHIRPS daily series already cached locally.
- **Drought frequency metrics** per commune: share of months in moderate/severe
  drought, longest consecutive drought episode.
- **Precipitation trend** over the decade (linear slope in mm/decade).
- **Near-real-time anomaly** (``--monitor`` mode): fetches the last 90 days from
  Open-Meteo and compares to the CHIRPS historical baseline, printing a per-commune
  status table without writing any output files.

All computation uses only locally cached data + Open-Meteo (no API key).  The SPI
algorithm follows McKee et al. (1993): monthly aggregation → Gamma CDF fit per
calendar month → standard-normal transform via the probability-weighted mixed
distribution to handle the zero-inflation typical of arid climates.

Brain-health rationale
----------------------
- **Drought exposure** (drought_months_pct, drought_max_duration) → chronic
  psychological stress, water insecurity, neuroinflammation.
- **Drying trend** (precip_trend_mm_per_decade) → cumulative climate-change
  exposure, food/water system pressure.
- **Current anomaly** → acute stressor monitoring, enables prospective tracking.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from scipy import stats

from . import boundaries, config

CHIRPS_DAILY_FILE = "santiago_precipitation_chirps_daily_2015_2024.csv"
OPENMETEO_URL = "https://archive-api.open-meteo.com/v1/archive"

# SPI thresholds (McKee et al. 1993)
_SPI_MODERATE = -1.0   # moderate drought
_SPI_SEVERE = -2.0     # severe drought


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
def load_chirps_daily(data_dir: Path) -> pd.DataFrame:
    """Load the cached CHIRPS daily precipitation series.

    Returns a DataFrame with columns ``[name, date, precipitation_mm]``,
    where ``date`` is a proper datetime and the index is reset.
    """
    path = Path(data_dir) / CHIRPS_DAILY_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"CHIRPS daily data not found: {path}\n"
            "Run scripts/run_precipitation.py first to generate it."
        )
    df = pd.read_csv(path, parse_dates=["date"])
    df["precipitation_mm"] = pd.to_numeric(df["precipitation_mm"], errors="coerce").fillna(0.0)
    return df.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# SPI computation
# --------------------------------------------------------------------------- #
def _monthly_totals(daily: pd.DataFrame) -> pd.DataFrame:
    """Aggregate CHIRPS daily data to monthly totals per commune."""
    daily = daily.copy()
    daily["year_month"] = daily["date"].dt.to_period("M")
    monthly = (
        daily.groupby(["name", "year_month"])["precipitation_mm"]
        .sum()
        .reset_index()
    )
    monthly["date"] = monthly["year_month"].dt.to_timestamp()
    return monthly.drop(columns="year_month")


def _spi_for_commune(monthly_series: pd.Series, scale: int) -> pd.Series:
    """Compute SPI at ``scale`` months for a single commune's monthly series.

    ``monthly_series`` must have a DatetimeIndex sorted in ascending order.
    Returns a Series of SPI values (NaN for the first ``scale-1`` months).

    Algorithm (McKee et al. 1993):
      1. Compute rolling ``scale``-month precipitation totals.
      2. For each calendar month (1–12), fit a Gamma distribution to the
         non-zero values from the historical record.
      3. Apply the mixed CDF: P(X=0) + (1 − P(X=0)) × Gamma_CDF(x).
      4. Transform to N(0,1) via the inverse-normal CDF.
    """
    rolling = monthly_series.rolling(scale).sum()
    spi = pd.Series(np.nan, index=rolling.index, dtype=float)

    for cal_month in range(1, 13):
        mask = rolling.index.month == cal_month
        vals = rolling[mask].dropna().values

        if len(vals) < 4:
            continue

        n_zero = (vals == 0).sum()
        p0 = n_zero / len(vals)
        nonzero = vals[vals > 0]

        if len(nonzero) < 3:
            # Not enough non-zero values to fit Gamma → skip month
            continue

        try:
            a, _, b = stats.gamma.fit(nonzero, floc=0)
        except Exception:
            continue

        for idx in rolling.index[mask]:
            x = rolling[idx]
            if pd.isna(x):
                continue
            if x == 0:
                cdf = p0
            else:
                cdf = p0 + (1.0 - p0) * stats.gamma.cdf(x, a, loc=0, scale=b)
            cdf = float(np.clip(cdf, 1e-6, 1.0 - 1e-6))
            spi[idx] = stats.norm.ppf(cdf)

    return spi


def compute_spi_all_communes(
    monthly: pd.DataFrame, scale: int
) -> pd.DataFrame:
    """Compute SPI-``scale`` for every commune.

    Parameters
    ----------
    monthly:
        Output of :func:`_monthly_totals` with columns
        ``[name, date, precipitation_mm]``.
    scale:
        Accumulation period in months (3, 6, or 12).

    Returns
    -------
    DataFrame with columns ``[name, date, spi_<scale>]``.
    """
    records = []
    for commune, grp in monthly.groupby("name"):
        grp = grp.set_index("date").sort_index()
        spi_s = _spi_for_commune(grp["precipitation_mm"], scale)
        for dt, val in spi_s.items():
            records.append({"name": commune, "date": dt, f"spi_{scale}": val})
    return pd.DataFrame(records)


# --------------------------------------------------------------------------- #
# Drought metrics per commune
# --------------------------------------------------------------------------- #
def compute_drought_metrics(
    spi3: pd.DataFrame, annual_mm: pd.DataFrame
) -> pd.DataFrame:
    """Derive per-commune drought summary metrics from the SPI-3 series.

    Parameters
    ----------
    spi3:
        Wide DataFrame with columns ``[name, date, spi_3]`` (output of
        :func:`compute_spi_all_communes` with scale=3).
    annual_mm:
        DataFrame with columns ``[name, year, precip_annual_mm]`` (annual
        totals per commune from CHIRPS daily data).

    Returns
    -------
    DataFrame indexed by ``name`` with drought summary columns.
    """
    rows = []
    for commune, grp in spi3.groupby("name"):
        grp = grp.dropna(subset=["spi_3"]).sort_values("date")
        s = grp["spi_3"].values

        if len(s) == 0:
            continue

        # Drought frequency
        moderate = (s < _SPI_MODERATE).mean() * 100
        severe = (s < _SPI_SEVERE).mean() * 100

        # Longest consecutive drought episode (SPI-3 < -1)
        in_drought = s < _SPI_MODERATE
        max_dur = 0
        cur = 0
        for v in in_drought:
            cur = cur + 1 if v else 0
            max_dur = max(max_dur, cur)

        # Precipitation trend (mm/decade) from annual totals
        ann = annual_mm[annual_mm["name"] == commune].sort_values("year")
        if len(ann) >= 3:
            slope, _ = np.polyfit(ann["year"].values, ann["precip_annual_mm"].values, 1)
            trend_per_decade = round(float(slope * 10), 2)
        else:
            trend_per_decade = np.nan

        rows.append(
            {
                "name": commune,
                "drought_months_pct": round(moderate, 2),
                "drought_severe_months_pct": round(severe, 2),
                "drought_max_duration_months": int(max_dur),
                "precip_trend_mm_per_decade": trend_per_decade,
            }
        )
    return pd.DataFrame(rows)


def _annual_totals(daily: pd.DataFrame) -> pd.DataFrame:
    """Aggregate CHIRPS daily data to annual totals per commune."""
    daily = daily.copy()
    daily["year"] = daily["date"].dt.year
    ann = (
        daily.groupby(["name", "year"])["precipitation_mm"]
        .sum()
        .reset_index()
        .rename(columns={"precipitation_mm": "precip_annual_mm"})
    )
    return ann


# --------------------------------------------------------------------------- #
# Near-real-time anomaly (monitoring mode)
# --------------------------------------------------------------------------- #
def _fetch_openmeteo_recent(
    lat: float, lon: float, start: str, end: str, max_retries: int = 5
) -> list[float]:
    """Fetch daily precipitation_sum from Open-Meteo archive for a single point."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start,
        "end_date": end,
        "daily": "precipitation_sum",
        "timezone": "auto",
    }
    for attempt in range(max_retries):
        try:
            resp = requests.get(OPENMETEO_URL, params=params, timeout=60)
            if resp.status_code == 429:
                time.sleep(2 ** attempt + 3)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data.get("daily", {}).get("precipitation_sum", [])
        except Exception:
            if attempt == max_retries - 1:
                return []
            time.sleep(2 ** attempt)
    return []


def fetch_recent_anomaly(
    daily_chirps: pd.DataFrame,
    gdf_communes: gpd.GeoDataFrame,
    days: int = 90,
) -> pd.DataFrame:
    """Compare the last ``days`` days of Open-Meteo precipitation to the CHIRPS baseline.

    For each commune, fetches recent daily data from Open-Meteo using the
    commune centroid (WGS84), then computes the anomaly relative to the same
    calendar period's historical mean from CHIRPS.

    Returns a DataFrame with columns ``[name, recent_mm, baseline_mm,
    precip_anomaly_90d_pct]``.
    """
    today = date.today()
    end_date = today.strftime("%Y-%m-%d")
    start_date = (today - pd.Timedelta(days=days)).strftime("%Y-%m-%d")

    # Build historical baseline: mean for the same calendar-day window across years
    period_start_md = (today - pd.Timedelta(days=days)).strftime("%m-%d")
    period_end_md = today.strftime("%m-%d")
    daily_chirps = daily_chirps.copy()
    daily_chirps["md"] = daily_chirps["date"].dt.strftime("%m-%d")

    # Compute centroids: project to metric CRS first, then back to WGS84 for API calls
    centroids = gdf_communes[["name", "geometry"]].copy()
    centroids_metric = centroids.to_crs("EPSG:32719")
    centroids_metric = centroids_metric.copy()
    centroids_metric["geometry"] = centroids_metric.geometry.centroid
    centroids_wgs = centroids_metric.to_crs("EPSG:4326")
    centroids = centroids[["name"]].copy()
    centroids["lon"] = centroids_wgs.geometry.x.values
    centroids["lat"] = centroids_wgs.geometry.y.values

    results = []
    print(f"  [monitor] Fetching {days}-day precipitation from Open-Meteo "
          f"({start_date} → {end_date})...")

    for _, row in centroids.iterrows():
        name = row["name"]
        vals = _fetch_openmeteo_recent(row["lat"], row["lon"], start_date, end_date)
        recent_mm = float(np.nansum(vals)) if vals else np.nan

        # Historical baseline: sum of same calendar period across CHIRPS years
        hist = daily_chirps[daily_chirps["name"] == name]
        if period_start_md <= period_end_md:
            hist_period = hist[
                (hist["md"] >= period_start_md) & (hist["md"] <= period_end_md)
            ]
        else:
            hist_period = hist[
                (hist["md"] >= period_start_md) | (hist["md"] <= period_end_md)
            ]
        # Per-year sum then average across years
        hist_period = hist_period.copy()
        hist_period["year"] = hist_period["date"].dt.year
        annual_sums = hist_period.groupby("year")["precipitation_mm"].sum()
        baseline_mm = float(annual_sums.mean()) if len(annual_sums) > 0 else np.nan

        if not np.isnan(recent_mm) and baseline_mm and baseline_mm > 0:
            anomaly_pct = round((recent_mm - baseline_mm) / baseline_mm * 100, 1)
        else:
            anomaly_pct = np.nan

        results.append(
            {
                "name": name,
                "recent_mm": round(recent_mm, 1) if not np.isnan(recent_mm) else np.nan,
                "baseline_mm": round(baseline_mm, 1) if not np.isnan(baseline_mm) else np.nan,
                "precip_anomaly_90d_pct": anomaly_pct,
            }
        )
        time.sleep(0.15)  # gentle rate limiting

    return pd.DataFrame(results)


def _print_history_report(annual_df: pd.DataFrame, spi12_df: pd.DataFrame) -> None:
    """Print two historical-summary tables using the cached CHIRPS + SPI data.

    Table 1: one row per year — regional mean precipitation, anomaly %, and how
    many communes had SPI-12 < -1 at year-end.
    Table 2: top-10 communes with the most drought months over the full period.
    """
    # --- Tabla 1: resumen regional por año ---
    mean_by_year = annual_df.groupby("year")["precip_annual_mm"].mean()
    baseline = mean_by_year.mean()

    # End-of-year SPI-12: last non-NaN value in December (or last month) per commune/year
    spi12_df = spi12_df.copy()
    spi12_df["date"] = pd.to_datetime(spi12_df["date"])
    spi12_df["year"] = spi12_df["date"].dt.year
    spi12_eoy = (
        spi12_df.dropna(subset=["spi_12"])
        .sort_values("date")
        .groupby(["name", "year"])
        .last()
        .reset_index()[["name", "year", "spi_12"]]
    )

    print(f"\n{'── Precipitación Histórica RM 2015-2024 ─':─<72}")
    print(f"{'Año':>5}  {'Media RM (mm)':>14}  {'Anomalía%':>10}  "
          f"{'Comunas sequía':>15}  {'Peor comuna':}")
    print("─" * 72)

    for year in sorted(mean_by_year.index):
        mm = mean_by_year[year]
        anom = (mm - baseline) / baseline * 100
        year_spi = spi12_eoy[spi12_eoy["year"] == year]
        drought_n = (year_spi["spi_12"] < -1.0).sum()
        total_n = len(year_spi)
        if not year_spi.empty and drought_n > 0:
            worst_row = year_spi.loc[year_spi["spi_12"].idxmin()]
            worst = f"{worst_row['name']} ({worst_row['spi_12']:+.2f})"
        else:
            worst = "—"
        flag = "🔴" if anom < -20 else ("🟡" if anom < -5 else "🟢")
        print(f"{flag} {year:>4}  {mm:>14.1f}  {anom:>+9.1f}%  "
              f"{drought_n:>6}/{total_n:<7}  {worst}")

    print("─" * 72)
    print(f"  Baseline (media 2015-2024): {baseline:.1f} mm/año")

    # --- Tabla 2: ranking de comunas más afectadas históricamente ---
    drought_months = (
        spi12_df[spi12_df["spi_12"] < -1.0]
        .groupby("name")
        .size()
        .rename("meses_sequia")
        .reset_index()
        .sort_values("meses_sequia", ascending=False)
        .head(10)
    )
    worst_year = (
        spi12_eoy.loc[spi12_eoy.groupby("name")["spi_12"].idxmin()]
        [["name", "year", "spi_12"]]
        .rename(columns={"year": "peor_año", "spi_12": "spi_min"})
    )
    ranking = drought_months.merge(worst_year, on="name", how="left")

    print(f"\n{'── Top 10 comunas con más sequía histórica (SPI-12 < -1) ─':─<72}")
    print(f"  {'Comuna':<22}  {'Meses sequía':>12}  {'Peor año':>9}  {'SPI mínimo':>11}")
    print("  " + "─" * 58)
    for _, r in ranking.iterrows():
        peor = f"{int(r['peor_año'])}" if not pd.isna(r.get("peor_año")) else "n/a"
        spi_min = f"{r['spi_min']:+.2f}" if not pd.isna(r.get("spi_min")) else "n/a"
        print(f"  {r['name']:<22}  {int(r['meses_sequia']):>12}  {peor:>9}  {spi_min:>11}")
    print("  " + "─" * 58)
    print("  SPI-12 < -1.0 = sequía moderada a severa (McKee et al. 1993)")


def _print_monitor_report(anomaly_df: pd.DataFrame, spi_latest: pd.DataFrame) -> None:
    """Print a coloured anomaly-monitoring table to stdout."""
    merged = anomaly_df.merge(spi_latest, on="name", how="left")
    merged = merged.sort_values("precip_anomaly_90d_pct")

    print(
        f"\n{'── Precipitation Monitor ── ' + datetime.now().strftime('%Y-%m-%d %H:%M'):─<72}"
    )
    print(f"{'Comuna':<22}{'SPI-12 latest':>14}{'Baseline 90d':>14}"
          f"{'Recent 90d':>12}{'Anomalía %':>12}")
    print("─" * 72)

    for _, r in merged.iterrows():
        spi = f"{r['spi_12_latest']:+.2f}" if not pd.isna(r.get("spi_12_latest")) else "  n/a"
        base = f"{r['baseline_mm']:.1f}" if not pd.isna(r["baseline_mm"]) else "n/a"
        rec = f"{r['recent_mm']:.1f}" if not pd.isna(r["recent_mm"]) else "n/a"
        anom = r["precip_anomaly_90d_pct"]
        flag = "🔴" if anom < -40 else ("🟡" if anom < -10 else "🟢") if not pd.isna(anom) else "  "
        anom_str = f"{anom:+.1f}%" if not pd.isna(anom) else "n/a"
        print(f"{flag} {r['name']:<20}{spi:>14}{base:>14}{rec:>12}{anom_str:>12}")

    print("─" * 72)
    print("SPI-12: drought if < −1.0 | anomaly: recent 90d vs 2015-2024 same period")


# --------------------------------------------------------------------------- #
# Layer builder
# --------------------------------------------------------------------------- #
def build_precipitation_spi_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    monitor: bool = False,
    history: bool = False,
) -> pd.DataFrame | None:
    """Build the SPI + drought metrics exposome layer.

    When ``monitor=True``, fetches recent precipitation from Open-Meteo,
    prints a per-commune anomaly report, and returns ``None`` without writing
    any files.

    When ``history=True``, prints year-by-year historical summaries from the
    cached CHIRPS data and returns ``None`` without writing any files or making
    API calls.

    Otherwise, writes the canonical CSV + GeoJSON + metadata.
    """
    cfg = config.load_config(city)
    cache_dir = Path(cache_dir)
    data_dir = Path(out_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    print(f"Building precipitation SPI layer for {city}...")

    # 1. Load cached CHIRPS daily data.
    daily = load_chirps_daily(data_dir)
    n_communes = daily["name"].nunique()
    n_days = daily["date"].nunique()
    print(f"  Loaded CHIRPS daily: {n_communes} communes × {n_days} days")

    # 2. Monthly aggregation and annual totals.
    monthly = _monthly_totals(daily)
    annual = _annual_totals(daily)

    # 3. Compute SPI at three scales — use parquet cache keyed to the source
    #    file's mtime so the cache is invalidated when CHIRPS data is refreshed.
    chirps_mtime = (data_dir / CHIRPS_DAILY_FILE).stat().st_mtime
    spi_cache = cache_dir / f"spi_monthly_{city}.parquet"
    if spi_cache.exists() and spi_cache.stat().st_mtime >= chirps_mtime:
        print("  Loading SPI from cache...")
        spi_all = pd.read_parquet(spi_cache)
        spi3_df = spi_all[["name", "date", "spi_3"]].dropna(subset=["spi_3"])
        spi6_df = spi_all[["name", "date", "spi_6"]].dropna(subset=["spi_6"])
        spi12_df = spi_all[["name", "date", "spi_12"]].dropna(subset=["spi_12"])
    else:
        print("  Computing SPI-3, SPI-6, SPI-12...")
        spi3_df = compute_spi_all_communes(monthly, 3)
        spi6_df = compute_spi_all_communes(monthly, 6)
        spi12_df = compute_spi_all_communes(monthly, 12)
        spi_all = (
            spi3_df
            .merge(spi6_df, on=["name", "date"], how="outer")
            .merge(spi12_df, on=["name", "date"], how="outer")
        )
        cache_dir.mkdir(parents=True, exist_ok=True)
        spi_all.to_parquet(spi_cache, index=False)
        print(f"  SPI cached → {spi_cache.name}")

    # 4a. History mode: print annual summaries and return early (no API calls).
    if history:
        _print_history_report(annual, spi12_df)
        return None

    # 4b. Drought metrics from SPI-3 and annual totals.
    metrics = compute_drought_metrics(spi3_df, annual)

    # 5. SPI-12 latest value (most recent non-NaN per commune).
    spi12_latest = (
        spi12_df.dropna(subset=["spi_12"])
        .sort_values("date")
        .groupby("name")
        .last()[["spi_12"]]
        .reset_index()
        .rename(columns={"spi_12": "spi_12_latest"})
    )
    spi12_latest["spi_12_latest"] = spi12_latest["spi_12_latest"].round(3)

    # 6. Boundaries for geometry.
    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)

    # 7. Monitoring mode: fetch recent data, print report, return early.
    if monitor:
        anomaly_df = fetch_recent_anomaly(daily, gdf_comm)
        _print_monitor_report(anomaly_df, spi12_latest)
        return None

    # 8. SPI series summaries per commune (mean over full period).
    def _spi_summary(spi_df: pd.DataFrame, col: str) -> pd.DataFrame:
        return (
            spi_df.dropna(subset=[col])
            .groupby("name")[col]
            .agg(mean="mean", std="std")
            .reset_index()
            .rename(columns={"mean": f"{col}_mean", "std": f"{col}_std"})
            .assign(
                **{
                    f"{col}_mean": lambda d: d[f"{col}_mean"].round(3),
                    f"{col}_std": lambda d: d[f"{col}_std"].round(3),
                }
            )
        )

    s3 = _spi_summary(spi3_df, "spi_3")
    s6 = _spi_summary(spi6_df, "spi_6")
    s12 = _spi_summary(spi12_df, "spi_12")

    # 9. Merge everything onto the commune name base.
    df = (
        gdf_comm[["name", "area_km2"]].copy()
        .merge(metrics, on="name", how="left")
        .merge(spi12_latest, on="name", how="left")
        .merge(s3[["name", "spi_3_mean", "spi_3_std"]], on="name", how="left")
        .merge(s6[["name", "spi_6_mean"]], on="name", how="left")
        .merge(s12[["name", "spi_12_mean"]], on="name", how="left")
    )
    df["area_km2"] = df["area_km2"].round(2)

    col_order = [
        "name", "area_km2",
        "drought_months_pct", "drought_severe_months_pct",
        "drought_max_duration_months",
        "precip_trend_mm_per_decade",
        "spi_12_latest",
        "spi_3_mean", "spi_3_std",
        "spi_6_mean",
        "spi_12_mean",
    ]
    df = df[[c for c in col_order if c in df.columns]].copy()

    # 10. Validate.
    n_expected = cfg["expected_communes"]
    if len(df) != n_expected:
        raise ValueError(f"Expected {n_expected} rows, got {len(df)}")
    if df["name"].duplicated().any():
        raise ValueError("Duplicate commune names")
    core = ["drought_months_pct", "drought_severe_months_pct",
            "drought_max_duration_months", "precip_trend_mm_per_decade",
            "spi_12_latest"]
    missing_core = [c for c in core if df[c].isna().any()]
    if missing_core:
        raise ValueError(f"Missing values in core SPI columns: {missing_core}")

    # 11. Write outputs.
    base_name = "santiago_precipitation_spi"
    df.to_csv(data_dir / f"{base_name}.csv", index=False)

    gdf = gdf_comm[["name", "geometry"]].merge(df, on="name", how="right")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])
    gdf.to_file(data_dir / f"{base_name}.geojson", driver="GeoJSON")

    date_range = f"{int(annual['year'].min())}–{int(annual['year'].max())}"
    metadata: dict[str, Any] = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "n_rows": int(len(df)),
        "columns": df.columns.tolist(),
        "source": {
            "name": "CHIRPS daily precipitation",
            "file": CHIRPS_DAILY_FILE,
            "period": date_range,
            "n_communes": int(n_communes),
            "n_days": int(n_days),
        },
        "spi_algorithm": {
            "method": "McKee et al. (1993)",
            "distribution": "Gamma (scipy.stats.gamma, MLE fit, floc=0)",
            "zero_handling": "mixed probability mass at zero + Gamma CDF",
            "scales": [3, 6, 12],
            "thresholds": {
                "moderate_drought": _SPI_MODERATE,
                "severe_drought": _SPI_SEVERE,
            },
            "note": (
                "Reference period = evaluation period (2015-2024). "
                "Drought metrics reflect within-period variability. "
                "The Chilean mega-drought (2010-present) means SPI values "
                "are computed relative to an already-dry baseline."
            ),
        },
        "columns_description": {
            "drought_months_pct": "% of months where SPI-3 < -1 (moderate drought)",
            "drought_severe_months_pct": "% of months where SPI-3 < -2 (severe drought)",
            "drought_max_duration_months": "Longest consecutive months in moderate drought",
            "precip_trend_mm_per_decade": "Linear trend in annual precipitation (mm/decade)",
            "spi_12_latest": f"SPI-12 for the most recent month in record ({date_range})",
            "spi_3_mean": "Mean SPI-3 over the full record (≈ 0 by construction)",
            "spi_3_std": "SD of SPI-3 — higher = more precipitation variability",
            "spi_6_mean": "Mean SPI-6 over the full record",
            "spi_12_mean": "Mean SPI-12 over the full record",
        },
        "brain_health_relevance": {
            "drought_exposure": "Chronic water stress → psychological stress, neuroinflammation",
            "drying_trend": "Long-term climate change exposure trajectory",
            "spi_variability": "Unpredictable precipitation → food/water system disruption",
        },
        "outputs": [f"{base_name}.csv", f"{base_name}.geojson"],
    }
    (data_dir / f"{base_name}_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )

    print(f"Wrote {base_name}.csv / .geojson ({len(df)} rows × {df.shape[1]} cols)")
    d_range = f"{df['drought_months_pct'].min():.1f}–{df['drought_months_pct'].max():.1f}"
    t_range = f"{df['precip_trend_mm_per_decade'].min():.1f}–{df['precip_trend_mm_per_decade'].max():.1f}"
    print(f"  Drought frequency range: {d_range}% of months in moderate drought")
    print(f"  Precipitation trend range: {t_range} mm/decade")
    return df

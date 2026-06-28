"""Calculate derived climate metrics from daily temperature series.

Input: daily time series (long format) per commune or zip code.
Output: annual/seasonal summary metrics per unit.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def calculate_climate_metrics(
    df_daily: pd.DataFrame,
    date_col: str = "date",
    tmax_col: str = "temperature_2m_max",
    tmin_col: str = "temperature_2m_min",
    tmean_col: str = "temperature_2m",
    group_col: str = "name",
    thresholds: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Compute full suite of climate exposure metrics.

    Parameters
    ----------
    df_daily : pd.DataFrame
        Long-format daily data.
    thresholds : dict | None
        Config thresholds (hot_day_c, tropical_night_c, etc.)

    Returns
    -------
    pd.DataFrame
        One row per group with metrics as columns.
    """
    df = df_daily.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df["year"] = df[date_col].dt.year
    df["month"] = df[date_col].dt.month

    # Southern Hemisphere seasons
    df["season"] = df["month"].map({
        12: "summer", 1: "summer", 2: "summer",
        3: "autumn", 4: "autumn", 5: "autumn",
        6: "winter", 7: "winter", 8: "winter",
        9: "spring", 10: "spring", 11: "spring",
    })

    results = []
    for grp, gdf in df.groupby(group_col):
        metrics = _metrics_for_group(gdf, date_col, tmax_col, tmin_col, tmean_col, thresholds)
        metrics[group_col] = grp
        results.append(metrics)

    return pd.DataFrame(results)


def _metrics_for_group(
    gdf: pd.DataFrame,
    date_col: str,
    tmax_col: str,
    tmin_col: str,
    tmean_col: str,
    thresholds: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute all metrics for a single group."""
    thresholds = thresholds or {}
    metrics: dict[str, Any] = {}

    tmax = gdf[tmax_col]
    tmin = gdf[tmin_col]
    tmean = gdf[tmean_col]

    # Thresholds
    hot_day_th = thresholds.get("hot_day_c", 30)
    very_hot_day_th = thresholds.get("very_hot_day_c", 35)
    tropical_night_th = thresholds.get("tropical_night_c", 20)
    frost_th = thresholds.get("frost_day_c", 0)
    hw_pctl = thresholds.get("heat_wave_percentile", 0.90)
    cs_pctl = thresholds.get("cold_spell_percentile", 0.10)
    hw_min = thresholds.get("heat_wave_min_days", 2)
    cs_min = thresholds.get("cold_spell_min_days", 2)
    cdd_base = thresholds.get("cdd_base_c", 18)
    hdd_base = thresholds.get("hdd_base_c", 10)

    # --- Magnitude ---
    metrics["tmean_annual"] = tmean.mean()
    metrics["tmax_mean_annual"] = tmax.mean()
    metrics["tmin_mean_annual"] = tmin.mean()

    for season in ["summer", "winter", "autumn", "spring"]:
        mask = gdf["season"] == season
        if mask.sum() > 0:
            metrics[f"tmean_{season}"] = tmean[mask].mean()
            metrics[f"tmax_mean_{season}"] = tmax[mask].mean()
            metrics[f"tmin_mean_{season}"] = tmin[mask].mean()

    # --- Extremes ---
    metrics["hot_days_30c"] = (tmax >= hot_day_th).sum()
    metrics["hot_days_35c"] = (tmax >= very_hot_day_th).sum()
    metrics["tropical_nights_20c"] = (tmin >= tropical_night_th).sum()
    metrics["frost_days"] = (tmin <= frost_th).sum()

    # Percentiles for heat waves / cold spells (local to group)
    p90_tmax = tmax.quantile(hw_pctl)
    p10_tmin = tmin.quantile(cs_pctl)

    metrics["heat_wave_days"] = _count_consecutive_above(tmax, p90_tmax, min_len=hw_min)
    metrics["cold_spell_days"] = _count_consecutive_below(tmin, p10_tmin, min_len=cs_min)

    # --- Variability ---
    dtr = tmax - tmin
    metrics["dtr_mean"] = dtr.mean()
    metrics["dtr_p95"] = dtr.quantile(0.95)

    monthly_mean = gdf.groupby(gdf[date_col].dt.to_period("M"))[tmean_col].mean()
    metrics["temp_monthly_sd"] = monthly_mean.std()

    metrics["seasonal_amplitude"] = metrics.get("tmean_summer", np.nan) - metrics.get("tmean_winter", np.nan)

    # --- Cumulative load ---
    metrics[f"cdd_{cdd_base}"] = ((tmean - cdd_base).clip(lower=0)).sum()
    metrics[f"hdd_{hdd_base}"] = ((hdd_base - tmean).clip(lower=0)).sum()

    # Excess heat degree days above P90 of tmean
    p90_tmean = tmean.quantile(0.90)
    metrics["ehdd"] = ((tmean - p90_tmean).clip(lower=0)).sum()

    # --- Additional ---
    metrics["tmax_p95"] = tmax.quantile(0.95)
    metrics["tmin_p05"] = tmin.quantile(0.05)

    return metrics


def _count_consecutive_above(series: pd.Series, threshold: float, min_len: int = 2) -> int:
    """Count days belonging to consecutive runs above threshold."""
    above = series > threshold
    if not above.any():
        return 0
    # Identify run starts
    runs = (above != above.shift()).cumsum()
    run_lengths = above.groupby(runs).sum()
    return int(run_lengths[run_lengths >= min_len].sum())


def _count_consecutive_below(series: pd.Series, threshold: float, min_len: int = 2) -> int:
    """Count days belonging to consecutive runs below threshold."""
    below = series < threshold
    if not below.any():
        return 0
    runs = (below != below.shift()).cumsum()
    run_lengths = below.groupby(runs).sum()
    return int(run_lengths[run_lengths >= min_len].sum())


def calculate_apparent_temperature(
    t: pd.Series,
    rh: pd.Series,
    wind: pd.Series,
) -> pd.Series:
    """Calculate apparent temperature using Steadman formula.

    Reference: Steadman, R.G. (1984). A universal scale of apparent temperature.
    """
    # Simplified formula combining heat index and wind chill
    # For warm conditions (t > 20C): use heat index approximation
    # For cool conditions: use wind chill
    # Full implementation would use pythermalcomfort
    try:
        from pythermalcomfort.models import at
        return pd.Series([at(ta=ta, rh=rhi, v=wi) for ta, rhi, wi in zip(t, rh, wind)], index=t.index)
    except ImportError:
        raise ImportError("pythermalcomfort required for apparent temperature")

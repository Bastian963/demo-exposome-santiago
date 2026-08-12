"""Time-series trend analysis (Mann-Kendall + Sen's slope) for the
multi-year exposome indicators that already have yearly caches.

Variables analyzed (4):
- tmax_mean_annual_c   — climate (from ERA5-Land daily cache)
- precip_annual_mm     — climate (from CHIRPS daily cache)
- hot_days_30c         — climate (count of days with tmax>30 from ERA5-Land)
- fire_burned_pct      — wildfire (from MCD64A1 + FIRMS annual cache)

The PM2.5 series per commune-per-year is **not** in the cache (the
master uses a multi-year window); it is documented in the README
as a known limitation.

For each commune and each variable, we compute:
- Sen's slope [units/year]
- Mann-Kendall S statistic
- Two-sided p-value (variance with tie correction)
- Trend class: significant_increasing (p<0.05, slope>0),
  significant_decreasing (p<0.05, slope<0), no_trend.

Outputs
-------
1. `data/processed/time_series_trends.csv` (52 x 4 = 208 rows)
   Columns: name, variable, sen_slope_per_year, p_value,
   trend_class, n_years.
2. `figures/time_series_trends.png` (4-panel: slopes per commune
   for the 4 variables, sorted by slope value).
3. `data/processed/time_series_trends_summary.json` with
   per-variable counts of significant trends.

Usage
-----
    python scripts/time_series_trends.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm

REPO_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = REPO_ROOT / "cache"
DATA_DIR = REPO_ROOT / "data" / "processed"
FIGURES_DIR = REPO_ROOT / "figures"

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "font.family": "STIXGeneral",
        "mathtext.fontset": "stix",
        "axes.titlesize": 10.5,
        "axes.labelsize": 9.5,
    }
)

YEAR_MIN = 2015
YEAR_MAX = 2024
ALPHA = 0.05


def _mann_kendall(x: np.ndarray) -> tuple[float, float]:
    """Two-sided Mann-Kendall test with tie correction.

    Returns (S, p_value). Reference: Helsel & Hirsch (2002).
    """
    n = len(x)
    s = 0
    for i in range(n - 1):
        diffs = x[i + 1:] - x[i]
        s += np.sum(np.sign(diffs))
    # Variance with tie correction.
    unique, counts = np.unique(x, return_counts=True)
    tie_term = np.sum(counts * (counts - 1) * (2 * counts + 5))
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if var_s <= 0:
        return float(s), 1.0
    if s > 0:
        z = (s - 1) / np.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / np.sqrt(var_s)
    else:
        z = 0.0
    p = 2.0 * (1.0 - norm.cdf(abs(z)))
    return float(s), float(p)


def _sens_slope(x: np.ndarray) -> float:
    """Theil-Sen slope estimator: median of pairwise slopes."""
    n = len(x)
    slopes = []
    for i in range(n):
        for j in range(i + 1, n):
            slopes.append((x[j] - x[i]) / (j - i))
    return float(np.median(slopes)) if slopes else 0.0


def _load_era5_annual() -> pd.DataFrame:
    """Compute annual tmax and hot_days_30c per commune from ERA5-Land daily."""
    rows: list[dict] = []
    for year in range(YEAR_MIN, YEAR_MAX + 1):
        path = CACHE_DIR / f"santiago_era5land_{year}.csv"
        if not path.exists():
            print(f"  skip ERA5 {year}: cache missing")
            continue
        df = pd.read_csv(path, parse_dates=["date"])
        annual = df.groupby("name").agg(
            tmax_mean=("temperature_2m_max", "mean"),
            hot_days=("temperature_2m_max",
                      lambda s: int((s > 30.0).sum())),
            precip_sum=("total_precipitation_sum", "sum"),
        ).reset_index()
        annual["year"] = year
        rows.append(annual)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def _load_chirps_annual() -> pd.DataFrame:
    """Compute annual precip sum per commune from CHIRPS daily."""
    rows: list[dict] = []
    for year in range(YEAR_MIN, YEAR_MAX + 1):
        path = CACHE_DIR / f"santiago_precipitation_chirps_{year}.csv"
        if not path.exists():
            print(f"  skip CHIRPS {year}: cache missing")
            continue
        df = pd.read_csv(path, parse_dates=["date"])
        annual = df.groupby("name")["precipitation_mm"].sum().reset_index()
        annual.columns = ["name", "precip_sum"]
        annual["year"] = year
        rows.append(annual)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


def _load_wildfire_annual() -> pd.DataFrame:
    """Wildfire annual metrics per commune from MCD64A1 + FIRMS cache."""
    path = CACHE_DIR / "santiago_wildfire_annual_2015_2024.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _per_commune_trends(
    series_df: pd.DataFrame, year_col: str, value_col: str,
) -> pd.DataFrame:
    """Apply Mann-Kendall + Sen's slope per commune."""
    rows: list[dict] = []
    for name, sub in series_df.groupby("name"):
        sub = sub.sort_values(year_col)
        x = sub[value_col].to_numpy(dtype=float)
        if np.isnan(x).any():
            x = pd.Series(x).interpolate().to_numpy()
        if len(x) < 5 or np.std(x) == 0:
            rows.append({
                "name": name, "n_years": int(len(x)),
                "sen_slope_per_year": 0.0, "p_value": 1.0,
                "trend_class": "no_trend",
            })
            continue
        s, p = _mann_kendall(x)
        slope = _sens_slope(x)
        if p < ALPHA:
            cls = "significant_increasing" if slope > 0 \
                else "significant_decreasing"
        else:
            cls = "no_trend"
        rows.append({
            "name": name, "n_years": int(len(x)),
            "sen_slope_per_year": round(slope, 6),
            "p_value": round(p, 4),
            "trend_class": cls,
        })
    return pd.DataFrame(rows)


def _plot_trends(trends: pd.DataFrame, out: Path) -> None:
    variables = sorted(trends["variable"].unique())
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    fig.suptitle(
        "Time-series trends por comuna — Mann-Kendall + Sen's slope 2015-2024\n"
        "Slopes positivos = aumento; negativos = descenso; "
        "marcador = p<0.05 significativo",
        fontsize=11,
    )
    nice_labels = {
        "tmax_mean_annual_c": "Tmax medio annual (C/yr)",
        "precip_annual_mm": "Precipitacion annual (mm/yr)",
        "hot_days_30c": "Dias calidos >30C (dias/yr)",
        "fire_detections": "Wildfire FIRMS detections (n/yr)",
    }
    for ax, var in zip(axes.ravel(), variables):
        sub = trends[trends["variable"] == var].copy()
        sub = sub.sort_values("sen_slope_per_year")
        colors = np.where(
            (sub["p_value"] < ALPHA) & (sub["sen_slope_per_year"] > 0),
            "#d7191c",
            np.where(
                (sub["p_value"] < ALPHA) & (sub["sen_slope_per_year"] < 0),
                "#2c7bb6", "#cccccc",
            ),
        )
        ax.barh(sub["name"], sub["sen_slope_per_year"],
                color=colors, edgecolor="white", linewidth=0.3)
        ax.axvline(0, color="#333", lw=0.6)
        ax.set_xlabel(nice_labels.get(var, var), fontsize=9)
        n_sig = int((sub["p_value"] < ALPHA).sum())
        ax.set_title(
            f"{var}  (n_sig = {n_sig}/{len(sub)})",
            fontsize=10,
        )
        ax.tick_params(axis="y", labelsize=5.5)
        ax.grid(axis="x", alpha=0.3)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    all_trends: list[pd.DataFrame] = []

    # Variable 1: tmax_mean_annual_c (from ERA5-Land daily)
    era5 = _load_era5_annual()
    if not era5.empty:
        tr = _per_commune_trends(era5, "year", "tmax_mean")
        tr["variable"] = "tmax_mean_annual_c"
        all_trends.append(tr)
        print(f"  tmax_mean_annual_c: {len(tr)} communes")

    # Variable 2: hot_days_30c (from ERA5-Land daily)
    if not era5.empty:
        tr = _per_commune_trends(era5, "year", "hot_days")
        tr["variable"] = "hot_days_30c"
        all_trends.append(tr)
        print(f"  hot_days_30c: {len(tr)} communes")

    # Variable 3: precip_annual_mm (from CHIRPS daily)
    chirps = _load_chirps_annual()
    if not chirps.empty:
        tr = _per_commune_trends(chirps, "year", "precip_sum")
        tr["variable"] = "precip_annual_mm"
        all_trends.append(tr)
        print(f"  precip_annual_mm: {len(tr)} communes")

    # Variable 4: fire_detections (FIRMS active-fire counts per year).
    # burned_km2 is too sparse (mostly 0); detections is more continuous.
    fire = _load_wildfire_annual()
    if not fire.empty and "detections" in fire.columns:
        tr = _per_commune_trends(fire, "year", "detections")
        tr["variable"] = "fire_detections"
        all_trends.append(tr)
        print(f"  fire_detections: {len(tr)} communes")

    if not all_trends:
        print("ERROR: no time series could be loaded")
        return

    trends = pd.concat(all_trends, ignore_index=True)
    cols = ["name", "variable", "n_years", "sen_slope_per_year",
            "p_value", "trend_class"]
    trends = trends[cols]
    out_csv = DATA_DIR / "time_series_trends.csv"
    trends.to_csv(out_csv, index=False)
    print(f"Wrote: {out_csv} ({len(trends)} rows)")

    _plot_trends(trends, FIGURES_DIR / "time_series_trends.png")

    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "method": (
            "Mann-Kendall test (two-sided, with tie correction) + "
            "Theil-Sen slope estimator. Trends with p < 0.05 classified "
            "as significant."
        ),
        "year_range": [YEAR_MIN, YEAR_MAX],
        "alpha": ALPHA,
        "per_variable": {},
    }
    for var in trends["variable"].unique():
        sub = trends[trends["variable"] == var]
        n_sig_inc = int(((sub["p_value"] < ALPHA) &
                          (sub["sen_slope_per_year"] > 0)).sum())
        n_sig_dec = int(((sub["p_value"] < ALPHA) &
                          (sub["sen_slope_per_year"] < 0)).sum())
        n_no = int((sub["p_value"] >= ALPHA).sum())
        summary["per_variable"][var] = {
            "n_communes": int(len(sub)),
            "n_significant_increasing": n_sig_inc,
            "n_significant_decreasing": n_sig_dec,
            "n_no_trend": n_no,
            "median_slope": round(float(sub["sen_slope_per_year"].median()), 6),
            "median_p_value": round(float(sub["p_value"].median()), 4),
        }
    summary_path = DATA_DIR / "time_series_trends_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Wrote: {summary_path}")


if __name__ == "__main__":
    sys.exit(main())

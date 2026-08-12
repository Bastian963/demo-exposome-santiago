"""Compare the two climate_heat layer outputs (Open-Meteo vs ERA5-Land).

Both CSVs share the same 12 metric columns plus the indices. This script
joins them commune-by-commune, computes the per-commune delta and a
summary of bias and dispersion for each metric, and writes:

- ``data/processed/climate_heat_source_comparison_by_commune.csv``:
  per-commune side-by-side values and deltas.
- ``data/processed/climate_heat_source_comparison_summary.csv``:
  per-metric bias, RMSE, mean absolute difference.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np
import pandas as pd  # noqa: E402
import typer  # noqa: E402

app = typer.Typer(help="Compare Open-Meteo vs ERA5-Land climate_heat outputs.")


METRIC_COLS = [
    "tmean_annual_c",
    "tmax_mean_annual_c",
    "summer_tmax_mean_c",
    "tmax_p95_c",
    "tmax_abs_c",
    "apparent_tmax_mean_c",
    "hot_days_30c",
    "hot_days_35c",
    "apparent_hot_days_35c",
    "tropical_nights_20c",
    "precip_annual_mm",
    "heat_exposure_index",
    "urban_heat_anomaly_c",
]


@app.command()
def run(
    openmeteo_csv: Path = typer.Option(
        Path("data/processed/santiago_climate_heat_exposome_rm_santiago.csv"),
        help="Open-Meteo layer CSV (canonical)",
    ),
    era5land_csv: Path = typer.Option(
        Path("data/processed/santiago_climate_heat_era5land_2024.csv"),
        help="ERA5-Land layer CSV (comparator)",
    ),
    out_by_commune: Path = typer.Option(
        Path("data/processed/climate_heat_source_comparison_by_commune.csv"),
        help="Per-commune side-by-side CSV",
    ),
    out_summary: Path = typer.Option(
        Path("data/processed/climate_heat_source_comparison_summary.csv"),
        help="Per-metric summary CSV",
    ),
) -> None:
    """Generate the Open-Meteo vs ERA5-Land comparison tables."""
    om = pd.read_csv(openmeteo_csv)
    er = pd.read_csv(era5land_csv)
    if "name" not in om.columns or "name" not in er.columns:
        raise ValueError("Both CSVs must contain a 'name' column.")
    common_cols = [c for c in METRIC_COLS if c in om.columns and c in er.columns]
    if len(common_cols) < len(METRIC_COLS):
        missing = set(METRIC_COLS) - set(common_cols)
        print(f"  Note: {len(missing)} metrics missing from one source: {missing}")

    om_s = om[["name"] + common_cols].rename(
        columns={c: f"{c}_openmeteo" for c in common_cols}
    )
    er_s = er[["name"] + common_cols].rename(
        columns={c: f"{c}_era5land" for c in common_cols}
    )

    merged = om_s.merge(er_s, on="name", how="outer", validate="one_to_one")

    # Deltas (era5land - openmeteo) for the matching metrics.
    for c in common_cols:
        merged[f"delta_{c}"] = merged[f"{c}_era5land"] - merged[f"{c}_openmeteo"]

    merged.sort_values("name").to_csv(out_by_commune, index=False)
    print(f"Wrote {out_by_commune.name} ({len(merged)} communes, {merged.shape[1]} cols)")

    summary_rows = []
    for c in common_cols:
        a = merged[f"{c}_openmeteo"]
        b = merged[f"{c}_era5land"]
        mask = a.notna() & b.notna()
        n = int(mask.sum())
        if n == 0:
            summary_rows.append(
                {
                    "metric": c,
                    "n": 0,
                    "bias_era5_minus_om": np.nan,
                    "rmse": np.nan,
                    "mean_abs_diff": np.nan,
                    "pearson_r": np.nan,
                }
            )
            continue
        d = b[mask] - a[mask]
        rmse = float(np.sqrt(((d) ** 2).mean()))
        summary_rows.append(
            {
                "metric": c,
                "n": n,
                "bias_era5_minus_om": round(float(d.mean()), 4),
                "rmse": round(rmse, 4),
                "mean_abs_diff": round(float(d.abs().mean()), 4),
                "pearson_r": round(float(np.corrcoef(a[mask], b[mask])[0, 1]), 4)
                if a[mask].std() > 0 and b[mask].std() > 0
                else np.nan,
            }
        )

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(out_summary, index=False)
    print(f"Wrote {out_summary.name} ({len(summary)} metrics)")
    print()
    print("Bias (ERA5 - Open-Meteo) per metric:")
    for r in summary_rows:
        print(f"  {r['metric']:>30s}: bias={r['bias_era5_minus_om']:+.3f}  "
              f"rmse={r['rmse']:.3f}  r={r['pearson_r']}")


if __name__ == "__main__":
    app()

"""Build the per-year precipitation series consumed by the webapp year slider.

Reads the CHIRPS daily archive already on disk
(``data/processed/santiago_precipitation_chirps_daily_2015_2024.csv``) and
summarises it per commune and year with the same per-year logic that feeds
the chronic metrics of the canonical layer
(``exposome.precipitation.calculate_annual_precipitation_table``).

Output (wide, 52 communes):

- ``data/processed/santiago_precipitation_by_year.csv`` with columns
  ``precip_annual_mm_<Y>``, ``precip_cdd_days_<Y>``,
  ``precip_heavy_days_10mm_<Y>`` for 2015-2024.
- ``..._by_year_metadata.json``

Run from the repo root:

    .conda/envs/exposome/bin/python scripts/run_precipitation_annual.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import pandas as pd  # noqa: E402
import typer  # noqa: E402

from exposome import config as _config  # noqa: E402
from exposome.precipitation import calculate_annual_precipitation_table  # noqa: E402

app = typer.Typer(help="Per-year CHIRPS precipitation series (2015-2024).")

# annual-table column -> webapp column stem (matches the canonical layer's
# chronic metric names so the slider's "Prom" stop stays interpretable).
SERIES_COLS = {
    "annual_total": "precip_annual_mm",
    "cdd": "precip_cdd_days",
    "heavy_days": "precip_heavy_days_10mm",
}


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name"),
    daily_csv: Path = typer.Option(
        Path("data/processed/santiago_precipitation_chirps_daily_2015_2024.csv"),
        help="CHIRPS daily archive (commune-level)",
    ),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
) -> None:
    """Summarise the CHIRPS daily archive into a wide per-year table."""
    cfg = _config.load_config(city)
    if not daily_csv.exists():
        raise FileNotFoundError(
            f"{daily_csv} not found. Run scripts/run_precipitation.py first."
        )
    df_daily = pd.read_csv(daily_csv)
    annual = calculate_annual_precipitation_table(df_daily)
    years = sorted(annual["year"].unique().tolist())

    wide = None
    for src_col, stem in SERIES_COLS.items():
        piv = annual.pivot(index="name", columns="year", values=src_col)
        piv.columns = [f"{stem}_{y}" for y in piv.columns]
        wide = piv if wide is None else wide.join(piv)
    wide = wide.round(2).reset_index().sort_values("name").reset_index(drop=True)

    expected = cfg.get("expected_communes", 52)
    if len(wide) != expected:
        raise ValueError(f"Expected {expected} communes, got {len(wide)}")
    value_cols = [c for c in wide.columns if c != "name"]
    if wide[value_cols].isna().any().any():
        bad = wide.columns[wide.isna().any()].tolist()
        raise ValueError(f"NaN values in per-year precipitation series: {bad}")

    # Sanity: the mean of the per-year annual totals must reproduce the
    # canonical chronic metric.
    canonical = pd.read_csv(
        Path("data/processed") / f"{city}_precipitation_chirps_2015_2024.csv"
    )
    annual_cols = [f"precip_annual_mm_{y}" for y in years]
    chk = wide[["name"]].copy()
    chk["mean_of_years"] = wide[annual_cols].mean(axis=1)
    chk = chk.merge(canonical[["name", "precip_annual_mean_mm"]], on="name")
    max_diff = (chk["mean_of_years"] - chk["precip_annual_mean_mm"]).abs().max()
    print(f"Sanity vs canonical precip_annual_mean_mm: max |diff| = {max_diff:.3f} mm")
    if max_diff > 0.5:
        raise RuntimeError("Per-year means diverge from the canonical chronic metric")

    csv_path = out_dir / f"{city}_precipitation_by_year.csv"
    wide.to_csv(csv_path, index=False)

    meta = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "layer": "precipitation_by_year",
        "years": years,
        "columns_per_year": list(SERIES_COLS.values()),
        "n_rows": int(len(wide)),
        "n_cols": int(len(wide.columns)),
        "source": "CHIRPS v2 daily (GEE), commune-aggregated archive on disk",
        "method": (
            "Per-commune, per-year summaries via "
            "exposome.precipitation.calculate_annual_precipitation_table: "
            "annual total (mm), max consecutive dry days (wet-day threshold "
            "1 mm) and days with >=10 mm. The canonical layer's chronic "
            "metrics are the multi-year means of these values."
        ),
        "consumers": [
            "scripts/build_master_exposome.py",
            "webapp year slider (palette.json year_columns)",
        ],
    }
    meta_path = out_dir / f"{city}_precipitation_by_year_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"Wrote {csv_path.name} ({len(wide)} rows x {len(wide.columns)} cols)")
    print(f"  Metadata: {meta_path.name}")


if __name__ == "__main__":
    app()

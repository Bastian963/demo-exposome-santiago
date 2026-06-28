"""CLI entrypoint for climate metrics calculation."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer

from exposome.climate.metrics import calculate_climate_metrics
from exposome import config
import pandas as pd

app = typer.Typer(help="Calculate climate exposure metrics.")


@app.command()
def metrics(
    city: str = typer.Option("santiago", help="City config name"),
    daily_csv: Path = typer.Option(Path("data/processed/santiago_climate_era5land_daily_2024_2024.csv"), help="Daily climate CSV"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
) -> None:
    """Compute derived climate metrics from daily time series."""
    cfg = config.load_config(city)
    df_daily = pd.read_csv(daily_csv)

    thresholds = cfg.get("climate", {}).get("thresholds", {})
    df_metrics = calculate_climate_metrics(
        df_daily,
        date_col="date",
        tmax_col="temperature_2m_max",
        tmin_col="temperature_2m_min",
        tmean_col="temperature_2m_mean",
        group_col="name",
        thresholds=thresholds,
    )

    out_path = out_dir / f"{city}_climate_metrics_annual.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_metrics.to_csv(out_path, index=False)
    print(f"Saved metrics: {out_path} ({len(df_metrics)} rows x {df_metrics.shape[1]} cols)")


if __name__ == "__main__":
    app()

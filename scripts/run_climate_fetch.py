"""CLI entrypoint for climate historical fetch."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer

from exposome.climate.fetch_era5land import fetch_era5land_years

app = typer.Typer(help="Run climate data extraction from GEE.")


@app.command()
def fetch(
    city: str = typer.Option("santiago", help="City config name"),
    years: list[int] | None = typer.Option(None, help="Years to fetch (default from config)"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Combined-output directory"),
) -> None:
    """Fetch ERA5-Land daily data for selected or all configured years."""
    year_list = years if years else None
    df = fetch_era5land_years(
        city=city,
        years=year_list,
        cache_dir=cache_dir,
        out_dir=out_dir,
    )
    print(f"Fetched {len(df)} rows total")


if __name__ == "__main__":
    app()

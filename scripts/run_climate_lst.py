"""CLI entrypoint for MODIS LST extraction."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer

from exposome.climate.fetch_modis_lst import fetch_modis_lst_annual_and_summer

app = typer.Typer(help="Fetch MODIS Land Surface Temperature summaries.")


@app.command()
def fetch(
    city: str = typer.Option("santiago", help="City config name"),
    years: list[int] | None = typer.Option(None, help="Years to fetch (default from config)"),
    scale: int = typer.Option(1_000, help="Zonal stats scale in meters"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
) -> None:
    """Fetch annual and summer MODIS LST summaries for all communes."""
    year_list = years if years else None
    df = fetch_modis_lst_annual_and_summer(
        city=city,
        years=year_list,
        scale=scale,
        cache_dir=cache_dir,
    )
    print(f"Fetched {len(df)} rows total")


if __name__ == "__main__":
    app()

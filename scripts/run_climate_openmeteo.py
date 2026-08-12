"""CLI entrypoint for Open-Meteo climate fetch."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer

from exposome.climate.fetch_openmeteo import fetch_openmeteo_years

app = typer.Typer(help="Fetch historical climate from Open-Meteo API.")


@app.command()
def fetch(
    city: str = typer.Option("santiago", help="City config name"),
    years: list[int] | None = typer.Option(None, help="Years to fetch (default from config)"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
) -> None:
    """Fetch daily climate data via Open-Meteo for all configured years."""
    year_list = years if years else None
    df = fetch_openmeteo_years(city=city, years=year_list, cache_dir=cache_dir)
    print(f"Fetched {len(df)} rows total")


if __name__ == "__main__":
    app()

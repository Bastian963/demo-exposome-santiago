"""CLI entrypoint for the precipitation SPI and drought-monitoring layer.

Usage
-----
Normal (writes CSV + GeoJSON + metadata):
    python scripts/run_precipitation_spi.py

Monitoring mode (prints near-real-time anomaly table, no files written):
    python scripts/run_precipitation_spi.py --monitor
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.precipitation_spi import build_precipitation_spi_layer  # noqa: E402

app = typer.Typer(help="Precipitation SPI indices and drought-monitoring layer.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
    monitor: bool = typer.Option(
        False,
        "--monitor",
        help=(
            "Monitoring mode: fetch the last 90 days from Open-Meteo, "
            "compare to the CHIRPS baseline, and print a per-commune "
            "anomaly table. Does NOT write any output files."
        ),
    ),
    history: bool = typer.Option(
        False,
        "--history",
        help=(
            "Historical mode: print year-by-year precipitation summary "
            "(2015-2024) and ranking of most drought-affected communes. "
            "Uses only local cached data — no API calls. Does NOT write files."
        ),
    ),
) -> None:
    """Build SPI drought indices from CHIRPS data, or run live anomaly monitoring."""
    build_precipitation_spi_layer(
        city=city,
        cache_dir=cache_dir,
        out_dir=out_dir,
        monitor=monitor,
        history=history,
    )


if __name__ == "__main__":
    app()

"""CLI entrypoint for the wind exposure layer (ERA5 10-m wind)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.wind import build_wind_layer  # noqa: E402

app = typer.Typer(help="Wind exposure layer (ERA5 10-m wind).")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
) -> None:
    """Build the wind exposure layer and export commune-level zonal stats."""
    build_wind_layer(city=city, cache_dir=cache_dir, out_dir=out_dir)


if __name__ == "__main__":
    app()

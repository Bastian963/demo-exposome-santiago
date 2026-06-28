"""CLI entrypoint for the chronic PM2.5 (ACAG) exposome layer."""
from __future__ import annotations

import sys
from pathlib import Path

# Add repo/src to path so `exposome` is importable without install
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.pm25 import build_pm25_layer  # noqa: E402

app = typer.Typer(help="Run exposome layers from the command line.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name (matches config/cities/<city>.yaml)"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
) -> None:
    """Fetch chronic surface PM2.5 (ACAG) and export commune-level zonal stats."""
    build_pm25_layer(city=city, cache_dir=cache_dir, out_dir=out_dir)


if __name__ == "__main__":
    app()

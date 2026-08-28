"""CLI entrypoint for the demography (Census 2017) layer."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.demography import build_demography_layer  # noqa: E402

app = typer.Typer(help="Run demography exposome layer from the command line.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City name used for output filenames"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
) -> None:
    """Download Chile Censo 2017 data and export commune-level population."""
    build_demography_layer(city=city, cache_dir=cache_dir, out_dir=out_dir)


if __name__ == "__main__":
    app()

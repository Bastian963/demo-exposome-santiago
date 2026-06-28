"""CLI entrypoint for the public transport accessibility exposome layer."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.public_transport import build_public_transport_layer  # noqa: E402

app = typer.Typer(help="Build public transport accessibility metrics from OSM.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory for OSM downloads"),
) -> None:
    """Compute commune-level public transit access indices from OSM bus/metro data."""
    build_public_transport_layer(city=city, out_dir=out_dir, cache_dir=cache_dir)


if __name__ == "__main__":
    app()

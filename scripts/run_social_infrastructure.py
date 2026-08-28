"""CLI entrypoint for the social-cognitive infrastructure exposome layer."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.social_infrastructure import build_social_infrastructure_layer  # noqa: E402

app = typer.Typer(help="Build social-cognitive infrastructure metrics from OSM.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory for OSM downloads"),
) -> None:
    """Compute commune-level social infrastructure accessibility from OSM POIs."""
    build_social_infrastructure_layer(city=city, out_dir=out_dir, cache_dir=cache_dir)


if __name__ == "__main__":
    app()

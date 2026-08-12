"""CLI entrypoint for the walkability / built-environment exposome layer."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.walkability import build_walkability_layer  # noqa: E402

app = typer.Typer(help="Build pedestrian walkability metrics from OSM street networks.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
    cache_dir: Path = typer.Option(Path("cache"), help="Boundary/cache directory"),
    resume: bool = typer.Option(True, help="Skip communes already in output CSV (walk_n_nodes > 0)"),
) -> None:
    """Compute commune-level walkability indices from OSM walk network."""
    build_walkability_layer(city=city, out_dir=out_dir, resume=resume, cache_dir=cache_dir)


if __name__ == "__main__":
    app()

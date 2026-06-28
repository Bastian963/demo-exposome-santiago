"""CLI entrypoint for the food environment exposome layer."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.food_environment import build_food_environment_layer  # noqa: E402

app = typer.Typer(help="Build retail food environment metrics (CDC mRFEI) from OSM.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory for OSM downloads"),
    resume: bool = typer.Option(True, help="Use cached category downloads if present"),
) -> None:
    """Compute commune-level food environment indices (mRFEI, food swamp) from OSM."""
    build_food_environment_layer(city=city, out_dir=out_dir, cache_dir=cache_dir, resume=resume)


if __name__ == "__main__":
    app()

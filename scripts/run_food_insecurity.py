"""CLI entrypoint for the food insecurity exposome layer (CASEN SAE)."""
from __future__ import annotations

import sys
from pathlib import Path

# Add repo/src to path so `exposome` is importable without install
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.food_insecurity import build_food_insecurity_layer  # noqa: E402

app = typer.Typer(help="Run exposome layers from the command line.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name (matches config/cities/<city>.yaml)"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
) -> None:
    """Build the commune-level food insecurity layer (CASEN 2020 & 2022 SAE)."""
    build_food_insecurity_layer(city=city, cache_dir=cache_dir, out_dir=out_dir)


if __name__ == "__main__":
    app()

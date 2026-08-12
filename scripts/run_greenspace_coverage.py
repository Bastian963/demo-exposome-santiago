"""CLI entrypoint for the satellite greenspace coverage layer."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.greenspace_satellite import build_greenspace_coverage_layer  # noqa: E402

app = typer.Typer(help="Run satellite greenspace coverage layer from the command line.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name (matches config/cities/<city>.yaml)"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
    figures_dir: Path = typer.Option(Path("figures"), help="Directory for diagnostic figures"),
) -> None:
    """Fetch Landsat-8/9 data and export commune-level greenness metrics."""
    build_greenspace_coverage_layer(city=city, cache_dir=cache_dir, out_dir=out_dir, figures_dir=figures_dir)


if __name__ == "__main__":
    app()

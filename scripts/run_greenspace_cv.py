"""CLI entrypoint for the high-resolution greenspace CV layer."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.greenspace_cv import build_greenspace_cv_layer  # noqa: E402

app = typer.Typer(help="Run high-resolution greenspace CV layer from the command line.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name (matches config/cities/<city>.yaml)"),
    method: str = typer.Option("exg", help="CV method: 'exg' (fast CPU) or 'sam' (slow GPU, not implemented yet)"),
    samples_per_commune: int = typer.Option(5, help="Number of random samples per commune"),
    seed: int = typer.Option(42, help="Random seed for reproducible sampling"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
) -> None:
    """Fetch aerial imagery and detect vegetation to validate OSM green coverage."""
    build_greenspace_cv_layer(
        city=city,
        method=method,
        samples_per_commune=samples_per_commune,
        cache_dir=cache_dir,
        out_dir=out_dir,
        seed=seed,
    )


if __name__ == "__main__":
    app()

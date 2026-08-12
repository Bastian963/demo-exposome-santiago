"""CLI entrypoint for the poverty SAE exposome layer (MDSF official estimates)."""
from __future__ import annotations

import sys
from pathlib import Path

# Add repo/src to path so `exposome` is importable without install
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.pobreza_sae import build_pobreza_sae_layer  # noqa: E402

app = typer.Typer(help="Run exposome layers from the command line.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name (matches config/cities/<city>.yaml)"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
) -> None:
    """Build the commune-level poverty SAE layer (MDSF 2017-2024)."""
    build_pobreza_sae_layer(city=city, cache_dir=cache_dir, out_dir=out_dir)


if __name__ == "__main__":
    app()

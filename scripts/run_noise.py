"""CLI entrypoint for the traffic noise exposome layer (MMA 2023)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.noise import build_noise_layer  # noqa: E402

app = typer.Typer(help="Build the Mapa de Ruido Gran Santiago Urbano 2023 layer.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
) -> None:
    """Export commune-level traffic noise exposure from the MMA 2023 map."""
    build_noise_layer(city=city, out_dir=out_dir)


if __name__ == "__main__":
    app()

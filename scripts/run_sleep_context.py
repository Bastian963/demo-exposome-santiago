"""CLI entrypoint for the sleep-circadian context layer."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.sleep_context import build_sleep_context_layer  # noqa: E402

app = typer.Typer(help="Run sleep-circadian context exposome layer from the command line.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name (matches config/cities/<city>.yaml)"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
) -> None:
    """Build an environmental sleep-circadian context index by commune."""
    build_sleep_context_layer(city=city, out_dir=out_dir)


if __name__ == "__main__":
    app()

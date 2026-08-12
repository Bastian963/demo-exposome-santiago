"""CLI entrypoint for the Argentina SAT community-safety layer."""
from __future__ import annotations

import sys
from pathlib import Path

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.community_safety import build_community_safety_layer  # noqa: E402

app = typer.Typer(help="Build AMBA registered property-crime context metrics.")


@app.command()
def run(
    city: str = typer.Option("buenos_aires_amba", help="Study id"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Layer output directory"),
    cache_dir: Path = typer.Option(Path("cache"), help="Unused; kept for runner compatibility"),
) -> None:
    build_community_safety_layer(city=city, out_dir=out_dir, cache_dir=cache_dir)


if __name__ == "__main__":
    app()

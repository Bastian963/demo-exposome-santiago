"""CLI entrypoint for internal Argentina SAT outcome comparators."""
from __future__ import annotations

import sys
from pathlib import Path

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.argentina_outcomes import build_argentina_outcome_comparator  # noqa: E402

app = typer.Typer(help="Build internal AMBA SAT mortality comparators.")


@app.command()
def run(
    outcome: str = typer.Option(..., help="suicide_mortality or road_traffic_mortality"),
    city: str = typer.Option("buenos_aires_amba", help="Study id"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Comparator output directory"),
    cache_dir: Path = typer.Option(Path("cache"), help="Unused; kept for runner compatibility"),
) -> None:
    build_argentina_outcome_comparator(outcome, city=city, out_dir=out_dir, cache_dir=cache_dir)  # type: ignore[arg-type]


if __name__ == "__main__":
    app()

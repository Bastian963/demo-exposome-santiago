"""Build native ERA5-Land heat metrics for one study.

The builder creates or resumes its per-year native-pixel cache when missing.
The cache contains ERA5-Land pixel centres, never commune summaries.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.climate.build_layer import build_climate_heat_layer  # noqa: E402

app = typer.Typer(help="Build the cache-first ERA5-Land climate_heat layer.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name"),
    year: int = typer.Option(2024, help="Reference year"),
    cache_dir: Path = typer.Option(Path("cache"), help="Native ERA5 cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
    out_base: str | None = typer.Option(None, "--out-base", help="Output basename"),
) -> None:
    """Aggregate physical ERA5-Land pixel metrics by area intersection."""
    build_climate_heat_layer(
        city=city,
        cache_dir=cache_dir,
        out_dir=out_dir,
        source="era5land",
        year=year,
        fallback_to_representative_point=False,
        base_name=out_base or f"{city}_climate_heat_era5land_{year}",
    )


if __name__ == "__main__":
    app()

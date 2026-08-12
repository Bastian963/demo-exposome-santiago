"""CLI to build the heavy metals (RETC) exposome layer.

Downloads annual RETC air-emission CSV/XLSX files from datosretc.mma.gob.cl,
filters to the Región Metropolitana, classifies heavy metal contaminants
(Pb, Mn, As, Cd, Hg), aggregates by commune, and writes:

  data/processed/<city>_heavy_metals_retc_<start>_<end>.{csv,geojson,json}

The canonical source is a verified immutable snapshot under ``data/raw``.
For one migration window this legacy wrapper can read pre-existing originals
from ``cache/``; it never downloads new provider files into the cache.

Usage
-----
  python scripts/run_heavy_metals.py
  python scripts/run_heavy_metals.py --start-year 2018 --end-year 2022
  python scripts/run_heavy_metals.py --city santiago --out-dir data/processed
"""
from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(add_completion=False)

REPO_ROOT = Path(__file__).resolve().parents[1]


@app.command()
def main(
    city: str = typer.Option("santiago", help="City name matching config/cities/<city>.yaml"),
    start_year: int = typer.Option(2015, help="First year in the chronic-exposure window"),
    end_year: int = typer.Option(2022, help="Last year in the chronic-exposure window (inclusive)"),
    cache_dir: Path = typer.Option(REPO_ROOT / "cache", help="Legacy cache fallback root"),
    raw_dir: Path = typer.Option(
        REPO_ROOT / "data" / "raw" / "mma" / "retc-air-point-sources" / "ckan-2026-06",
        help="Verified immutable RETC source snapshot",
    ),
    legacy_cache_fallback: bool = typer.Option(
        True,
        "--legacy-cache-fallback/--no-legacy-cache-fallback",
        help="Temporary compatibility path when the raw snapshot is not migrated yet",
    ),
    out_dir: Path = typer.Option(REPO_ROOT / "data" / "processed", help="Output directory"),
) -> None:
    import sys

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from exposome.heavy_metals import build_heavy_metals_layer

    years = list(range(start_year, end_year + 1))
    typer.echo(f"Building heavy metals layer for {city} ({start_year}–{end_year})…")
    if legacy_cache_fallback and not (raw_dir / "source_manifest.json").is_file():
        typer.echo(
            "DEPRECATION: using original RETC files from cache/. Run "
            "scripts/migrations/migrate_retc_raw.py; this fallback will be removed.",
            err=True,
        )
    df, _ = build_heavy_metals_layer(
        city=city,
        cache_dir=cache_dir,
        out_dir=out_dir,
        years=years,
        raw_dir=raw_dir,
        allow_legacy_cache=legacy_cache_fallback,
    )
    typer.echo(f"Done — {len(df)} communes, output in {out_dir}")


if __name__ == "__main__":
    app()

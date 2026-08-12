#!/usr/bin/env python3
"""CLI entrypoint for the AMBA SNIC community-violence exposome."""
from __future__ import annotations

import sys
from pathlib import Path

import typer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.community_violence import build_community_violence_layer  # noqa: E402


app = typer.Typer(help=__doc__)


@app.command()
def main(
    city: str = "buenos_aires_amba",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> None:
    build_community_violence_layer(city=city, cache_dir=cache_dir, out_dir=out_dir)


if __name__ == "__main__":
    app()

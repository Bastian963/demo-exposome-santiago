#!/usr/bin/env python3
"""Run the quality gate for AMBA outcome/exposome associations."""
from pathlib import Path
import sys

import typer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.argentina_associations import build_argentina_associations  # noqa: E402

app = typer.Typer(help=__doc__)


@app.command()
def main(
    city: str = "buenos_aires_amba",
    processed_dir: Path | None = None,
    covariates_path: Path | None = None,
) -> None:
    path = build_argentina_associations(
        city=city, processed_dir=processed_dir, covariates_path=covariates_path
    )
    typer.echo(path)


if __name__ == "__main__":
    app()

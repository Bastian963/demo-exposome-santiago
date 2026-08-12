"""Prepare a manual-labeling package for greenspace validation."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.greenspace_validation import prepare_validation_package  # noqa: E402

app = typer.Typer(help="Export candidate scenes and empty label templates for greenspace validation.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name."),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory."),
    processed_dir: Path = typer.Option(Path("data/processed"), help="Processed outputs directory."),
    validation_dir: Path = typer.Option(Path("data/validation"), help="Validation working directory."),
    include_showcase: bool = typer.Option(True, help="Include curated showcase scenes."),
) -> None:
    paths = prepare_validation_package(
        city=city,
        cache_dir=cache_dir,
        processed_dir=processed_dir,
        validation_dir=validation_dir,
        include_showcase=include_showcase,
    )
    print(f"Wrote {paths.sites_csv}")
    print(f"Wrote {paths.second_pass_csv}")
    print(f"Wrote {paths.batches_csv}")
    print(f"Wrote images to {paths.images_dir}")
    print(f"Wrote label templates to {paths.labels_dir}")
    print(f"Wrote contact sheet to {paths.contact_sheet_pdf}")


if __name__ == "__main__":
    app()

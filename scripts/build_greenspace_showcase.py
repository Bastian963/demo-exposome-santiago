"""CLI entrypoint for the greenspace CV showcase PDF."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.greenspace_showcase import build_showcase_pdf  # noqa: E402

app = typer.Typer(help="Build the greenspace CV vs OSM showcase PDF.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name."),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory."),
    out_pdf: Path | None = typer.Option(None, help="Output PDF path."),
    out_csv: Path | None = typer.Option(None, help="Output CSV path."),
    figures_subdir: Path | None = typer.Option(None, help="Directory for per-location PNG pages."),
) -> None:
    """Generate a presentation PDF and per-location figures."""
    df = build_showcase_pdf(
        city=city,
        cache_dir=cache_dir,
        out_pdf=out_pdf,
        out_csv=out_csv,
        figures_subdir=figures_subdir,
    )
    print(f"Wrote showcase for {city}: {len(df)} locations")


if __name__ == "__main__":
    app()

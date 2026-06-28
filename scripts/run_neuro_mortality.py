"""CLI entrypoint for the DEIS neuro-sanitary mortality comparator."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.neuro_mortality import build_neuro_mortality_layer  # noqa: E402

app = typer.Typer(help="Build commune-level neuro-sanitary mortality comparator tables.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name (matches config/cities/<city>.yaml)"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
    refresh: bool = typer.Option(False, help="Refresh the mortality source download when a URL is configured"),
    allow_crude_only: bool = typer.Option(
        False,
        help="Allow building only crude rates when the source lacks age information",
    ),
) -> None:
    """Build the neuro-sanitary mortality comparator from DEIS exports."""
    build_neuro_mortality_layer(
        city=city,
        cache_dir=cache_dir,
        out_dir=out_dir,
        refresh=refresh,
        allow_crude_only=allow_crude_only,
    )


if __name__ == "__main__":
    app()

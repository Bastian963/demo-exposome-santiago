"""CLI entrypoint for the healthcare access layer."""
from __future__ import annotations

import sys
from pathlib import Path

# Add repo/src to path so `exposome` is importable without install
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402

from exposome.healthcare import build_healthcare_layer  # noqa: E402

app = typer.Typer(help="Run healthcare access exposome layer from the command line.")


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name (matches config/cities/<city>.yaml)"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
    use_official: bool = typer.Option(
        True,
        "--use-official/--no-official",
        help="Combine MINSAL/DEIS official registry with OSM (default: True)",
    ),
    refresh_official: bool = typer.Option(
        False,
        "--refresh-official",
        help="Force re-download of the official DEIS CSV",
    ),
    use_network: bool = typer.Option(
        False,
        "--use-network",
        help="Compute street-network distances (slower, more realistic)",
    ),
    use_ckdtree: bool = typer.Option(
        False, help="Use scipy.spatial.cKDTree for nearest-distance queries (faster for large grids)"
    ),
) -> None:
    """Fetch healthcare facilities and export commune-level access metrics."""
    build_healthcare_layer(
        city=city,
        cache_dir=cache_dir,
        out_dir=out_dir,
        use_official=use_official,
        refresh_official=refresh_official,
        use_network=use_network,
        use_ckdtree=use_ckdtree,
    )


if __name__ == "__main__":
    app()

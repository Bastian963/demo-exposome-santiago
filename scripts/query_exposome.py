"""Query native exposome products at coordinates.

The command consumes coordinates, not ZIP polygons.  ZIP/address geocoding is
kept outside the exposure sampler because a postal area is not a unique point.

The sampling itself lives in :mod:`exposome.point_query` so the webapp, the
``exposome extract-points`` command and the offline tests all share one
implementation.  This file is only the CLI surface.
"""
from __future__ import annotations

import sys
from pathlib import Path

import typer

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.point_query import (  # noqa: E402
    PointQueryError,
    query_native_points,
    read_points,
    resolve_layers,
)
from exposome.studies import load_study  # noqa: E402

app = typer.Typer(help="Query native exposome products using coordinates.")


@app.command()
def query(
    study: str = typer.Option(..., "--study", help="Native study id, e.g. caba_native"),
    input: Path | None = typer.Option(None, "--input", help="CSV with id, lon and lat columns"),
    lon: float | None = typer.Option(None, "--lon"),
    lat: float | None = typer.Option(None, "--lat"),
    layers: str | None = typer.Option(None, "--layers", help="Comma-separated native layers"),
    output: Path | None = typer.Option(None, "--output"),
    id_column: str = typer.Option("id", "--id-column"),
    lon_column: str = typer.Option("lon", "--lon-column"),
    lat_column: str = typer.Option("lat", "--lat-column"),
) -> None:
    context = load_study(study)
    if not context.is_native:
        raise typer.BadParameter("--study must refer to a native study")
    try:
        query_points = read_points(input, lon, lat, id_column, lon_column, lat_column)
        selected = resolve_layers(layers, context.enabled_layers)
    except PointQueryError as error:
        raise typer.BadParameter(str(error)) from error

    result = query_native_points(context, query_points, selected)
    outside = int(result["out_of_coverage"].sum())

    destination = output or (context.paths.processed / "queries" / "native_point_queries.csv")
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(destination, index=False)
    message = f"Wrote {destination} ({len(result)} points, {len(selected)} layers)"
    if outside:
        message += f"; {outside} outside the AOI, flagged not dropped"
    typer.echo(message)


if __name__ == "__main__":
    app()

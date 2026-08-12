"""Create optional polygon summaries from native products.

This is intentionally a downstream operation.  It never replaces the native
assets and uses area-weighted raster means where a raster is available.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import typer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.native import NATIVE_LAYER_SPECS, RASTER_KINDS, load_native_aoi  # noqa: E402
from exposome.studies import load_study  # noqa: E402

app = typer.Typer(help="Aggregate native products to user-supplied polygons.")


def _raster_polygon_stats(
    path: Path, polygons: gpd.GeoDataFrame, id_column: str, prefix: str
) -> pd.DataFrame:
    import numpy as np
    import rasterio
    from rasterio.mask import mask

    rows: list[dict[str, Any]] = []
    with rasterio.open(path) as src:
        projected = polygons.to_crs(src.crs)
        for identifier, geom in zip(polygons[id_column], projected.geometry):
            values, _ = mask(src, [geom], crop=True, filled=False)
            row: dict[str, Any] = {id_column: identifier}
            for index in range(values.shape[0]):
                data = values[index].compressed()
                row[f"{prefix}_band_{index + 1}_mean"] = float(np.nanmean(data)) if len(data) else None
            rows.append(row)
    return pd.DataFrame(rows)


def _osm_polygon_stats(path: Path, layer_id: str, polygons: gpd.GeoDataFrame, id_column: str) -> pd.DataFrame:
    if layer_id == "walkability":
        features = gpd.read_file(path, layer="nodes")
    else:
        features = gpd.read_file(path, layer="features")
    if features.empty:
        return pd.DataFrame({id_column: polygons[id_column], f"{layer_id}_n_features": 0})
    joined = gpd.sjoin(features.to_crs(polygons.crs), polygons[[id_column, "geometry"]], predicate="within", how="right")
    counts = joined.groupby(id_column, dropna=False).size().rename(f"{layer_id}_n_features")
    return polygons[[id_column]].merge(counts, on=id_column, how="left").fillna({f"{layer_id}_n_features": 0})


@app.command()
def aggregate(
    study: str = typer.Option(..., "--study"),
    polygons: Path = typer.Option(..., "--polygons", help="GeoJSON/GPKG with summary units"),
    id_column: str = typer.Option(..., "--id-column"),
    layers: str | None = typer.Option(None, "--layers"),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    context = load_study(study)
    if not context.is_native:
        raise typer.BadParameter("--study must refer to a native study")
    load_native_aoi(context)
    units = gpd.read_file(polygons)
    if id_column not in units.columns:
        raise typer.BadParameter(f"Polygon input is missing {id_column!r}")
    if units.crs is None:
        raise typer.BadParameter("Polygon input must declare a CRS")
    selected = tuple(item.strip() for item in layers.split(",")) if layers else tuple(context.enabled_layers)
    result = units[[id_column]].copy()
    for layer_id in selected:
        if layer_id not in NATIVE_LAYER_SPECS:
            raise typer.BadParameter(f"Unsupported native layer: {layer_id}")
        directory = Path(context.paths.layer_processed(layer_id))
        spec = NATIVE_LAYER_SPECS[layer_id]
        if spec.kind in RASTER_KINDS:
            values = _raster_polygon_stats(
                directory / f"{layer_id}_native.tif", units, id_column, layer_id
            )
        elif spec.kind == "osm_network":
            values = _osm_polygon_stats(directory / "walkability_native.gpkg", layer_id, units, id_column)
        elif spec.kind == "osm_features":
            values = _osm_polygon_stats(directory / f"{layer_id}_native.gpkg", layer_id, units, id_column)
        else:
            raise typer.BadParameter(
                f"Layer {layer_id} requires point-level climate aggregation; use query_exposome.py first"
            )
        result = result.merge(values, on=id_column, how="left", validate="one_to_one")
    destination = output or (context.paths.processed / "derived" / "native_polygon_summary.csv")
    destination.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(destination, index=False)
    typer.echo(f"Wrote {destination} ({len(result)} polygons)")


if __name__ == "__main__":
    app()

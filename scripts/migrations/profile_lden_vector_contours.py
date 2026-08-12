#!/usr/bin/env python3
"""Profile locally clipped Lden vector contours before a web-detail decision.

This migration never downloads, edits, or republishes source data. It reads a
materialized SICA GeoPackage, clips the >=55 dB(A) Lden contours to a supplied
official boundary, and writes a compact JSON report. The report quantifies the
feature/vertex/byte budget required by Phase C of the Spain-noise plan.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import geopandas as gpd
import shapely
from shapely.ops import unary_union

from exposome.noise_spain import LDEN_LAYER, SOURCE_CRS, _band_midpoint


def _vertex_count(geometry: object) -> int:
    """Count coordinates without treating multipart outlines as a raster grid."""
    if geometry is None or geometry.is_empty:
        return 0
    if geometry.geom_type == "Polygon":
        return sum(len(ring.coords) for ring in geometry.interiors) + len(geometry.exterior.coords)
    if geometry.geom_type.startswith("Multi") or geometry.geom_type == "GeometryCollection":
        return sum(_vertex_count(item) for item in geometry.geoms)
    return len(geometry.coords) if hasattr(geometry, "coords") else 0


def profile_contours(
    source_gpkg: Path,
    boundary: Path,
    *,
    output: Path | None = None,
    source_asset_path: str | None = None,
    source_asset_sha256: str | None = None,
) -> dict[str, object]:
    """Return a serializable size/topology profile for clipped >=55 Lden contours."""
    if not source_gpkg.is_file():
        raise FileNotFoundError(source_gpkg)
    if not boundary.is_file():
        raise FileNotFoundError(boundary)

    units = gpd.read_file(boundary)
    if units.empty or units.crs is None:
        raise ValueError("Boundary must contain non-empty geometries and a CRS")
    metric_units = units.to_crs(SOURCE_CRS)
    footprint = unary_union(metric_units.geometry)
    bbox = tuple(float(value) for value in metric_units.total_bounds)

    started = perf_counter()
    raw = gpd.read_file(source_gpkg, layer=LDEN_LAYER, bbox=bbox)
    read_seconds = perf_counter() - started
    if raw.crs is None or "category" not in raw.columns:
        raise ValueError(f"{source_gpkg} lacks a CRS or the required category column")

    started = perf_counter()
    frame = raw.to_crs(SOURCE_CRS)
    frame["band_midpoint_dba"] = frame["category"].map(_band_midpoint)
    frame = frame.loc[
        frame["band_midpoint_dba"].notna()
        & frame.geometry.notna()
        & ~frame.geometry.is_empty
    ].copy()
    invalid_before_repair = int((~frame.geometry.is_valid).sum())
    if invalid_before_repair:
        frame.loc[~frame.geometry.is_valid, "geometry"] = frame.loc[
            ~frame.geometry.is_valid, "geometry"
        ].map(shapely.make_valid)
    frame["geometry"] = frame.geometry.intersection(footprint)
    frame = frame.loc[~frame.geometry.is_empty].copy()
    clip_seconds = perf_counter() - started
    if frame.empty:
        raise ValueError("No >=55 dB(A) Lden contours intersect the supplied boundary")

    frame = frame[["category", "band_midpoint_dba", "geometry"]].sort_values(
        ["band_midpoint_dba", "category"], kind="stable"
    ).reset_index(drop=True)
    bands: dict[str, dict[str, float | int]] = {}
    for midpoint, group in frame.groupby("band_midpoint_dba", sort=True):
        bands[f"{float(midpoint):g}"] = {
            "features": int(len(group)),
            "vertices": int(sum(_vertex_count(geometry) for geometry in group.geometry)),
            "raw_area_km2": float(group.geometry.area.sum() / 1_000_000),
        }

    started = perf_counter()
    geojson_bytes = len(frame.to_crs("EPSG:4326").to_json().encode("utf-8"))
    geojson_seconds = perf_counter() - started
    started = perf_counter()
    with TemporaryDirectory(prefix="gemma-lden-profile-") as temporary:
        parquet = Path(temporary) / "contours.parquet"
        frame.to_parquet(parquet, index=False)
        parquet_bytes = parquet.stat().st_size
    parquet_seconds = perf_counter() - started

    report: dict[str, object] = {
        "schema_version": 1,
        "source_gpkg_filename": source_gpkg.name,
        "source_gpkg_role": "local materialized cache; not a source of record",
        "source_gpkg_bytes": source_gpkg.stat().st_size,
        "source_asset_path": source_asset_path,
        "source_asset_sha256": source_asset_sha256,
        "boundary": str(boundary),
        "layer": LDEN_LAYER,
        "source_crs": SOURCE_CRS,
        "threshold": "Lden >=55 dB(A)",
        "bbox_metric": list(bbox),
        "features": int(len(frame)),
        "vertices": int(sum(_vertex_count(geometry) for geometry in frame.geometry)),
        "invalid_features_repaired": invalid_before_repair,
        "raw_area_km2": float(frame.geometry.area.sum() / 1_000_000),
        "bands": bands,
        "estimated_geojson_bytes": geojson_bytes,
        "geoparquet_bytes": parquet_bytes,
        "timing_seconds": {
            "read_bbox": read_seconds,
            "repair_and_clip": clip_seconds,
            "serialize_geojson": geojson_seconds,
            "serialize_geoparquet": parquet_seconds,
        },
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-gpkg", required=True, type=Path)
    parser.add_argument("--boundary", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-asset", help="Stable raw-manifest asset path, for example cataluna/barcelona.zip")
    parser.add_argument("--source-sha256", help="Stable SHA-256 of the raw-manifest asset")
    args = parser.parse_args()
    profile_contours(
        args.source_gpkg,
        args.boundary,
        output=args.output,
        source_asset_path=args.source_asset,
        source_asset_sha256=args.source_sha256,
    )
    print(args.output)


if __name__ == "__main__":
    main()

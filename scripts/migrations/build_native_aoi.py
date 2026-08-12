#!/usr/bin/env python3
"""Dissolve an aggregate study's spatial units into its native study's AOI.

A native study needs one polygon, not many: `native.py` unions whatever it
loads (`aoi_geometry`, native.py:151-153) before every Earth Engine call. The
established method -- used for santiago_native and cdmx_native, see
docs/resolution_manifest.md -- is to dissolve the aggregate study's already
validated official boundaries rather than geocode a new metropolitan limit.
Those AOIs were built ad hoc; this script exists so the next one is
reproducible and byte-identical on a re-run.

Local only: reads one GeoJSON, writes another. Never contacts a provider.

    python3 scripts/migrations/build_native_aoi.py \\
        --study pais_vasco_provincias --native-study pais_vasco_native

Holes are preserved on purpose. The Condado de Treviño is a Castilla y León
enclave inside Álava, so the Basque AOI is legitimately a polygon with a hole;
filling it would silently extend every raster over land the study does not
cover.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
from shapely import make_valid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from exposome.studies import load_study  # noqa: E402


def build(study_id: str, native_study_id: str, *, force: bool) -> Path:
    context = load_study(study_id, repo_root_path=ROOT)
    if context.is_native:
        raise SystemExit(f"{study_id} is already a native study; pass the aggregate one")

    units_path = Path(context.study.spatial_path)
    units = gpd.read_file(units_path)
    if units.crs is None:
        raise SystemExit(f"{units_path} has no CRS; refusing to guess")
    units = units.to_crs("EPSG:4326")

    # make_valid before the union: a single self-intersecting ring makes
    # union_all() return a geometry that Earth Engine rejects much later, with
    # an error that names neither the file nor the offending unit.
    units["geometry"] = units.geometry.apply(make_valid)
    dissolved = units.geometry.union_all()
    if dissolved.is_empty:
        raise SystemExit(f"Dissolve of {units_path} produced an empty geometry")

    country = context.country_code.lower()
    city = context.city
    output = ROOT / "data" / "reference" / country / city / native_study_id / "aoi.geojson"
    if output.exists() and not force:
        raise SystemExit(f"{output} already exists; pass --force to overwrite")

    unit_type = context.study.unit_type
    name = f"{city} ({len(units)} {unit_type}s, disuelto)"
    payload = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": name,
                    "source_study": study_id,
                    "n_source_polygons": len(units),
                },
                "geometry": json.loads(gpd.GeoSeries([dissolved], crs="EPSG:4326").to_json())[
                    "features"
                ][0]["geometry"],
            }
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    bounds = dissolved.bounds
    print(f"wrote {output}")
    print(f"  source     : {units_path} ({len(units)} {unit_type}s)")
    print(f"  geometry   : {dissolved.geom_type}")
    print(f"  bbox       : {', '.join(f'{v:.4f}' for v in bounds)}")
    print(f"  area (deg2): {dissolved.area:.6f}")
    print(f"  bytes      : {output.stat().st_size}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True, help="Aggregate study id")
    parser.add_argument("--native-study", required=True, help="Native study id to build the AOI for")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing aoi.geojson")
    args = parser.parse_args()
    build(args.study, args.native_study, force=args.force)


if __name__ == "__main__":
    main()

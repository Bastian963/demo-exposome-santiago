#!/usr/bin/env python3
"""Build the Sao Paulo distritos spatial reference for sao_paulo_distritos.

Mirrors scripts/migrations/build_bogota_localidades_reference.py. Sao Paulo
municipality (not the wider RMSP metro region) is divided into 96 distritos
municipais, grouped into 32 subprefeituras -- the user chose "municipio de
Sao Paulo" scope over the ~39-municipio RMSP metro, and distritos (the
finer, directly-available official layer) over subprefeituras, which are
not separately downloadable in the official service and would otherwise
require a fragile dissolve-by-code + a separate name lookup.

Source: GeoSampa (Prefeitura de Sao Paulo, Secretaria Municipal de
Desenvolvimento Urbano) publishes the official political-administrative
division via a public GeoServer WFS -- no ArcGIS REST host was found for
this city (unlike AMVA/CAR for the Colombian cities), but the WFS is
directly queryable and reachable without authentication:

    http://wfs.geosampa.prefeitura.sp.gov.br/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=geoportal:distrito_municipal&outputFormat=application/json&srsName=EPSG:4326

Fetched and verified 2026-07: 96 features, CRS reported as EPSG:4326 (no
reprojection needed), no duplicate cd_distrito_municipal, no null
geometries, total_bounds consistent with Sao Paulo municipality
(~-46.83..-46.37 lon, -24.01..-23.36 lat).

Fields: cd_distrito_municipal (2-digit district code), nm_distrito_municipal
(district name, upper-case in the source),
cd_identificador_subprefeitura (the subprefeitura code the district belongs
to -- kept as an auxiliary column for a future subprefeitura-level rollup,
not used as the join key here), qt_area_quilometro (area in km^2, per the
source's own computation -- not recomputed here).

Only one source format is accepted here: a GeoJSON or shapefile with the
native cd_distrito_municipal/nm_distrito_municipal columns (case-insensitive
match). If a downloaded file uses different column names, the script fails
fast and lists what is actually present -- fix this file rather than
guessing.

Save the downloaded file under
data/raw/br/sao_paulo/geosampa_distrito_municipal/<version>/ and pass its
path with --source.
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

import geopandas as gpd
import shapely
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = ROOT / "data" / "reference" / "br" / "sao_paulo" / "sao_paulo_distritos"

REQUIRED_FIELDS = ("cd_distrito_municipal", "nm_distrito_municipal", "cd_identificador_subprefeitura")

EXPECTED_UNITS = 96


def _checksum(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _resolve_columns(columns: list[str]) -> dict[str, str]:
    """Case-insensitive lookup of REQUIRED_FIELDS in the source's real columns."""
    by_lower = {str(c).lower(): c for c in columns}
    missing = [field for field in REQUIRED_FIELDS if field not in by_lower]
    if missing:
        raise ValueError(
            f"Source is missing expected columns {missing} (case-insensitive "
            f"match against {list(REQUIRED_FIELDS)}); actual columns: "
            f"{sorted(columns)}. Update this script to match the real file "
            "rather than guessing."
        )
    return {field: by_lower[field] for field in REQUIRED_FIELDS}


def main(source: Path, force: bool) -> None:
    output = TARGET_DIR / "spatial_units.geojson"
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --force")
    if not source.exists():
        raise FileNotFoundError(
            f"{source} not found. Fetch the GeoSampa distrito_municipal WFS "
            "layer first -- see this script's module docstring for the "
            "exact URL -- and pass its path with --source."
        )

    raw = gpd.read_file(source)
    resolved = _resolve_columns(list(raw.columns))

    result = gpd.GeoDataFrame(
        {
            "unit_id": raw[resolved["cd_distrito_municipal"]].astype(str).str.strip().str.zfill(2),
            "unit_name": raw[resolved["nm_distrito_municipal"]].astype(str).str.strip(),
            "unit_type": "distrito",
            "unit_source": "GeoSampa (Prefeitura de Sao Paulo, SMDU) distrito_municipal WFS layer",
            "subprefeitura_code": raw[resolved["cd_identificador_subprefeitura"]].astype(str).str.strip(),
            "geometry": raw.geometry,
        },
        geometry="geometry",
        crs=raw.crs or "EPSG:4326",
    )
    if str(result.crs) != "EPSG:4326":
        result = result.to_crs("EPSG:4326")

    n_units = len(result)
    if n_units != EXPECTED_UNITS:
        raise ValueError(
            f"Expected {EXPECTED_UNITS} distritos, found {n_units}. Check "
            "the source is the full Sao Paulo distrito_municipal layer, not "
            "a pre-filtered extract."
        )
    if result["unit_id"].duplicated().any():
        raise ValueError("Duplicate unit_id (cd_distrito_municipal) in Sao Paulo distritos reference")
    if result["unit_name"].duplicated().any():
        dupes = result.loc[result["unit_name"].duplicated(keep=False), "unit_name"].tolist()
        raise ValueError(f"Duplicate unit_name in Sao Paulo distritos reference: {dupes}")
    if not result.geometry.notna().all():
        raise ValueError("Null geometries in Sao Paulo distritos reference")
    invalid = ~result.geometry.is_valid
    if bool(invalid.any()):
        # make_valid() on a self-intersecting polygon can return a
        # GeometryCollection mixing the repaired Polygon with a degenerate
        # sliver (a stray LineString/Point from the intersection) -- found
        # on distrito LAJEADO in the 2026-07 source. Keep only the
        # polygonal member(s), unioned, instead of accepting a
        # GeometryCollection that would fail the pipeline's own
        # Polygon/MultiPolygon contract downstream.
        def _fix(geom):
            fixed = shapely.make_valid(geom)
            if fixed.geom_type == "GeometryCollection":
                polys = [g for g in fixed.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
                if not polys:
                    raise ValueError(f"make_valid() produced no polygonal geometry for {geom!r}")
                fixed = unary_union(polys)
            return fixed

        result.loc[invalid, "geometry"] = result.loc[invalid, "geometry"].apply(_fix)
    bad_types = set(result.geometry.type) - {"Polygon", "MultiPolygon"}
    if bad_types:
        raise ValueError(f"Non-polygonal geometry types after repair: {bad_types}")

    n_subprefeituras = result["subprefeitura_code"].nunique()
    bounds = result.total_bounds
    print(
        f"total_bounds (west,south,east,north): {bounds[0]:.4f}, {bounds[1]:.4f}, "
        f"{bounds[2]:.4f}, {bounds[3]:.4f}"
    )
    print(f"n distritos: {len(result)}, n subprefeituras (via subprefeitura_code): {n_subprefeituras}")
    print(
        "Update config/locations/br/sao_paulo.yaml's bbox with the total_bounds "
        "above (plus a small margin)."
    )

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    result.to_file(output, driver="GeoJSON")

    metadata = {
        "schema_version": 1,
        "study_id": "sao_paulo_distritos",
        "spatial_id": "unit_id (cd_distrito_municipal)",
        "source_geometry": str(source),
        "source_geometry_sha256": _checksum(source),
        "unit_count": len(result),
        "total_bounds": bounds.tolist(),
    }
    (TARGET_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (TARGET_DIR / "README.md").write_text(
        "# Sao Paulo distritos spatial reference\n\n"
        "`spatial_units.geojson` holds the 96 distritos municipais of the "
        "municipio de Sao Paulo (not the wider RMSP metro region). The "
        "authoritative source is GeoSampa (Prefeitura de Sao Paulo, SMDU)'s "
        "public GeoServer WFS -- `geoportal:distrito_municipal` -- fetched "
        "directly, no manual GUI export or third-party mirror needed (unlike "
        "Bogota/Lima, no host was unreachable while onboarding this city). "
        "See this script's module docstring for the exact query URL. "
        "`unit_id` is the source's own 2-digit cd_distrito_municipal code; "
        "`unit_name` is the source's own upper-case nm_distrito_municipal "
        "spelling, source-faithful -- same convention as the other cities' "
        "references. `subprefeitura_code` is kept as an auxiliary column "
        "(the distrito's parent subprefeitura, one of 32) for a possible "
        "future subprefeitura-level rollup study -- not used as the spatial "
        "join key here. Licensed under GeoSampa's open-data terms "
        "(Lei de Acesso a Informacao / Decreto Municipal de Dados Abertos); "
        "see https://geosampa.prefeitura.sp.gov.br for current terms.\n",
        encoding="utf-8",
    )
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to the downloaded GeoSampa distrito_municipal layer (GeoJSON or shapefile)",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(source=args.source, force=args.force)

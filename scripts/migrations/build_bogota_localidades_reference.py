#!/usr/bin/env python3
"""Build the Bogota D.C. localidades spatial reference for bogota_localidades.

Mirrors scripts/migrations/build_lima_distritos_reference.py, simpler because
Bogota D.C. is a single administrative entity (no department/province split
like Lima+Callao) -- the source layer already covers exactly the 20
localidades with no filtering needed. The authoritative source is the
Secretaria Distrital de Planeacion's (SDP) "Localidad" layer, normally served
via IDECA/UAECD Catastro Bogota's own ArcGIS REST endpoint -- but that host
(serviciosgis.catastrobogota.gov.co) and Bogota's open-data CKAN portal
(datosabiertos.bogota.gov.co) both timed out (TCP connect timeout, not DNS or
refusal -- consistent with geo-blocking outside Colombia) from every network
tried while onboarding this city, including the machine that actually ran
this script. The data used here was pulled instead from CAR Cundinamarca's
public visor, which mirrors the same SDP-sourced locality boundaries (same
LocAAdmini acuerdo values, e.g. "Acuerdo 117 de 2003" for Antonio Narino,
that SDP itself cites) and was reachable:

    https://sig.car.gov.co/arcgis/rest/services/visor/Division_Territorial/FeatureServer/5/query?where=1=1&outFields=*&returnGeometry=true&outSR=4326&f=geojson

If IDECA's own endpoint becomes reachable later, prefer it -- same data,
authoritative host:

    https://serviciosgis.catastrobogota.gov.co/arcgis/rest/services/ordenamientoterritorial/localidad/MapServer/0/query?where=1=1&outFields=*&f=geojson&outSR=4326

Fields (CAR's export; IDECA's own service reports the same fields upper-cased
as LOCCODIGO/LOCNOMBRE/LOCAADMINI/LOCAREA -- same data, different casing):
LocCodigo (2-digit locality code, "01"-"20"), LocNombre (locality name),
LocAAdmini (founding decree), LocArea. Both outSR=4326 exports already come
out as clean WGS84 with no GeoJSON "crs" member needed. There is no
independent locality-level backup for Bogota: DANE's Marco Geoestadistico
Nacional stops at municipio (Bogota D.C. = a single code, 11001) and HDX's
COD-AB Colombia Admin 3 covers rural veredas, not Bogota's urban localidades
-- sub-municipal division is SDP/IDECA's exclusive scope, CAR's visor being
the only alternate access point found for it.

Only one source format is accepted here: a GeoJSON or shapefile with the
native LocCodigo/LocNombre columns (case-insensitive match). If a downloaded
file uses different column names, the script fails fast and lists what is
actually present -- fix this file rather than guessing.

Save the downloaded file under
data/raw/co/bogota/ideca_localidades/<version>/ and pass its path with
--source.
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = ROOT / "data" / "reference" / "co" / "bogota" / "bogota_localidades"

# IDECA's own service reports these upper-cased (LOCCODIGO/LOCNOMBRE); CAR
# Cundinamarca's mirror (the one actually reachable while onboarding this
# city) reports them mixed-case (LocCodigo/LocNombre). Same fields, same
# data -- matched case-insensitively so either export works unmodified.
REQUIRED_FIELDS = ("loccodigo", "locnombre")

EXPECTED_UNITS = 20


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


def _load_native(gdf: gpd.GeoDataFrame, col_loccodigo: str, col_locnombre: str) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    gdf["loccodigo"] = gdf[col_loccodigo].astype(str).str.strip().str.zfill(2)
    gdf["unit_name_source"] = gdf[col_locnombre].astype(str).str.strip()
    return gdf[["loccodigo", "unit_name_source", "geometry"]]


def main(source: Path, force: bool) -> None:
    output = TARGET_DIR / "spatial_units.geojson"
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --force")
    if not source.exists():
        raise FileNotFoundError(
            f"{source} not found. Download the IDECA/SDP 'Localidad' layer "
            "first -- see this script's module docstring for the exact URL "
            "-- and pass its path with --source."
        )

    raw = gpd.read_file(source)
    resolved = _resolve_columns(list(raw.columns))
    normalized = _load_native(raw, resolved["loccodigo"], resolved["locnombre"])

    n_units = len(normalized)
    if n_units != EXPECTED_UNITS:
        raise ValueError(
            f"Expected {EXPECTED_UNITS} localidades, found {n_units}. Check "
            "the source is the full Bogota D.C. localidad layer, not a "
            "pre-filtered extract."
        )

    result = normalized.copy()
    result["unit_id"] = result["loccodigo"]
    result["unit_name"] = result["unit_name_source"]
    result["unit_type"] = "localidad"
    result["unit_source"] = (
        "Secretaria Distrital de Planeacion (SDP) via CAR Cundinamarca visor "
        "(IDECA/UAECD Catastro Bogota's own service was unreachable)"
    )
    result = result[
        ["unit_id", "unit_name", "unit_type", "unit_source", "loccodigo", "geometry"]
    ]
    result = gpd.GeoDataFrame(result, geometry="geometry", crs=normalized.crs or "EPSG:4326")

    if result["unit_id"].duplicated().any():
        raise ValueError("Duplicate unit_id (LOCCODIGO) in Bogota localidades reference")
    if result["unit_name"].duplicated().any():
        dupes = result.loc[result["unit_name"].duplicated(keep=False), "unit_name"].tolist()
        raise ValueError(f"Duplicate unit_name in Bogota localidades reference: {dupes}")
    if not result.geometry.notna().all():
        raise ValueError("Null geometries in Bogota localidades reference")
    invalid = ~result.geometry.is_valid
    if bool(invalid.any()):
        result.loc[invalid, "geometry"] = result.loc[invalid, "geometry"].make_valid()

    bounds = result.total_bounds
    print(
        f"total_bounds (west,south,east,north): {bounds[0]:.4f}, {bounds[1]:.4f}, "
        f"{bounds[2]:.4f}, {bounds[3]:.4f}"
    )
    print(f"n localidades: {len(result)}")
    print(
        "Update config/locations/co/bogota.yaml's bbox with the total_bounds "
        "above (plus a small margin)."
    )

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    result.to_file(output, driver="GeoJSON")

    metadata = {
        "schema_version": 1,
        "study_id": "bogota_localidades",
        "spatial_id": "unit_id (LOCCODIGO)",
        "source_geometry": str(source),
        "source_geometry_sha256": _checksum(source),
        "unit_count": len(result),
        "total_bounds": bounds.tolist(),
    }
    (TARGET_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (TARGET_DIR / "README.md").write_text(
        "# Bogota D.C. localidades spatial reference\n\n"
        "`spatial_units.geojson` holds the 20 localidades of Bogota D.C. The "
        "authoritative source is the Secretaria Distrital de Planeacion's "
        "(SDP) 'Localidad' layer, normally served via IDECA/UAECD Catastro "
        "Bogota's own ArcGIS REST endpoint -- but that host and Bogota's "
        "open-data CKAN portal both timed out from every network tried while "
        "onboarding this city, so this copy was pulled instead from CAR "
        "Cundinamarca's public visor, which mirrors the same SDP-sourced "
        "boundaries (matching LocAAdmini acuerdo values). See this script's "
        "module docstring for both URLs and the full provenance note. "
        "`unit_id` is the 2-digit LocCodigo code (Bogota's own locality "
        "identifier, \"01\"-\"20\"); `unit_name` is the source's own "
        "LocNombre spelling, source-faithful -- same convention as the "
        "Lima/CDMX/Buenos Aires references. Unlike Lima (Provincia de Lima + "
        "Callao) or CDMX's alcaldias, Bogota D.C. is a single administrative "
        "entity -- no department/province split needed. The underlying data "
        "is SDP/IDECA's, licensed CC BY 4.0 at the source; CAR's own license "
        "terms for this specific mirror were not separately confirmed.\n",
        encoding="utf-8",
    )
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to the downloaded IDECA/SDP localidad layer (GeoJSON or shapefile)",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(source=args.source, force=args.force)

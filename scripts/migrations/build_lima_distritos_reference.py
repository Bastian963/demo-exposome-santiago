#!/usr/bin/env python3
"""Build the Lima+Callao distritos spatial reference for lima_distritos.

Mirrors scripts/migrations/build_cdmx_alcaldias_reference.py: a single source
instead of a multi-source merge (contrast with
build_buenos_aires_amba_reference.py). The source is IGN/IDEP's "Limite
Distrital" layer (Infraestructura de Datos Espaciales del Peru, geometry
attributed FUENTE=INEI in the live service), which covers all of Peru at
distrito (ADM3) granularity. Filtered here to Provincia de Lima (43
distritos) + Provincia Constitucional del Callao (7 distritos) = 50.

Confirmed live against the ArcGIS REST service before writing this script:

    https://www.idep.gob.pe/geoportal/rest/services/DATOS_GEOESPACIALES/LIMITESTT/MapServer/3

Fields: UBIGEO, NOMBDEP, NOMBPROV, NOMBDIST, FUENTE. Lima's 43 distritos have
NOMBDEP=NOMBPROV="LIMA"; Callao's 7 distritos have NOMBDEP="CALLAO" (Callao is
its own department with a single province). Exportable directly as GeoJSON by
appending a query, e.g.:

    .../MapServer/3/query?where=NOMBDEP%3D%27LIMA%27+OR+NOMBDEP%3D%27CALLAO%27&outFields=*&f=geojson

If that service is awkward to pull by hand, HDX's "Peru - Subnational
Administrative Boundaries" (COD-AB, data.humdata.org/dataset/cod-ab-per,
CC BY-IGO) ships the same IGN-sourced ADM3 layer nationwide (1873 distritos)
as a GeoJSON/Shapefile/Geodatabase bundle -- filter it the same way this
script does.

Only one source format is accepted here (unlike CDMX's shapefile/KML branch):
a GeoJSON or shapefile with the native IGN/IDEP or HDX COD-AB attribute
columns. If a downloaded file uses different column names (e.g. HDX's
ADM3_ES/ADM2_ES/ADM3_PCODE), the script fails fast and lists what is actually
present -- fix this file rather than guessing.

Save the downloaded file under
data/raw/pe/lima/ign_idep_limites_distritales/<version>/ and pass its path
with --source.
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = ROOT / "data" / "reference" / "pe" / "lima" / "lima_distritos"

LIMA_PROVINCE = "LIMA"
CALLAO_DEPARTMENT = "CALLAO"
COL_UBIGEO = "UBIGEO"
COL_NOMBDEP = "NOMBDEP"
COL_NOMBPROV = "NOMBPROV"
COL_NOMBDIST = "NOMBDIST"
NATIVE_COLUMNS = {COL_UBIGEO, COL_NOMBDEP, COL_NOMBPROV, COL_NOMBDIST}

EXPECTED_LIMA = 43
EXPECTED_CALLAO = 7
EXPECTED_TOTAL = EXPECTED_LIMA + EXPECTED_CALLAO


def _checksum(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _load_native(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    gdf[COL_UBIGEO] = gdf[COL_UBIGEO].astype(str).str.zfill(6)
    gdf["unit_name_source"] = gdf[COL_NOMBDIST].astype(str).str.strip()
    return gdf[[COL_UBIGEO, COL_NOMBDEP, COL_NOMBPROV, "unit_name_source", "geometry"]]


def main(source: Path, force: bool) -> None:
    output = TARGET_DIR / "spatial_units.geojson"
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --force")
    if not source.exists():
        raise FileNotFoundError(
            f"{source} not found. Download the IGN/IDEP 'Limite Distrital' "
            "layer (or the HDX COD-AB Peru mirror) first -- see this script's "
            "module docstring for the exact URLs -- and pass its path with "
            "--source."
        )

    raw = gpd.read_file(source)
    if not NATIVE_COLUMNS.issubset(raw.columns):
        raise ValueError(
            f"Source is missing expected columns {sorted(NATIVE_COLUMNS)}; "
            f"actual columns: {sorted(raw.columns)}. Update this script to "
            "match the real file rather than guessing (e.g. HDX COD-AB uses "
            "ADM3_ES/ADM2_ES/ADM3_PCODE instead)."
        )
    normalized = _load_native(raw)

    dept_upper = normalized[COL_NOMBDEP].astype(str).str.upper().str.strip()
    prov_upper = normalized[COL_NOMBPROV].astype(str).str.upper().str.strip()
    lima_mask = (dept_upper == LIMA_PROVINCE) & (prov_upper == LIMA_PROVINCE)
    callao_mask = dept_upper == CALLAO_DEPARTMENT
    distritos = normalized[lima_mask | callao_mask].copy()

    n_lima = int(lima_mask.sum())
    n_callao = int(callao_mask.sum())
    if n_lima != EXPECTED_LIMA or n_callao != EXPECTED_CALLAO:
        raise ValueError(
            f"Expected {EXPECTED_LIMA} Lima distritos + {EXPECTED_CALLAO} "
            f"Callao distritos, found {n_lima} + {n_callao}. Check the "
            "source covers the whole country, not a pre-filtered extract, "
            "and that NOMBDEP/NOMBPROV spellings match 'LIMA'/'CALLAO'."
        )

    distritos["unit_id"] = distritos[COL_UBIGEO]
    distritos["unit_name"] = distritos["unit_name_source"]
    distritos["unit_type"] = "distrito"
    distritos["unit_source"] = "INEI (via IGN/IDEP)"
    distritos["province"] = prov_upper.where(lima_mask, "CALLAO")[distritos.index]
    result = distritos[
        ["unit_id", "unit_name", "unit_type", "unit_source", "province", COL_UBIGEO, "geometry"]
    ]
    result = result.rename(columns={COL_UBIGEO: "ubigeo"})
    result = gpd.GeoDataFrame(result, geometry="geometry", crs=normalized.crs or "EPSG:4326")

    if result["unit_id"].duplicated().any():
        raise ValueError("Duplicate unit_id (UBIGEO) in Lima distritos reference")
    if result["unit_name"].duplicated().any():
        dupes = result.loc[result["unit_name"].duplicated(keep=False), "unit_name"].tolist()
        raise ValueError(
            f"Duplicate unit_name in Lima distritos reference: {dupes}. "
            "Distrito names repeat across Peruvian regions (same risk as "
            "CDMX's Benito Juarez/Cuauhtemoc) -- if this fires, disambiguate "
            "unit_name with province before re-running."
        )
    if not result.geometry.notna().all():
        raise ValueError("Null geometries in Lima distritos reference")
    invalid = ~result.geometry.is_valid
    if bool(invalid.any()):
        result.loc[invalid, "geometry"] = result.loc[invalid, "geometry"].make_valid()

    bounds = result.total_bounds
    print(f"total_bounds (west,south,east,north): {bounds[0]:.4f}, {bounds[1]:.4f}, {bounds[2]:.4f}, {bounds[3]:.4f}")
    print(f"n distritos: {len(result)} (Lima: {n_lima}, Callao: {n_callao})")
    print("Update config/locations/pe/lima.yaml's bbox with the total_bounds above (plus a small margin).")

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    result.to_file(output, driver="GeoJSON")

    metadata = {
        "schema_version": 1,
        "study_id": "lima_distritos",
        "spatial_id": "unit_id (UBIGEO)",
        "source_geometry": str(source),
        "source_geometry_sha256": _checksum(source),
        "unit_count": len(result),
        "unit_count_lima": n_lima,
        "unit_count_callao": n_callao,
        "total_bounds": bounds.tolist(),
    }
    (TARGET_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (TARGET_DIR / "README.md").write_text(
        "# Lima + Callao distritos spatial reference\n\n"
        "`spatial_units.geojson` holds the 50 distritos of Provincia de Lima "
        "(43) and the Provincia Constitucional del Callao (7), filtered from "
        "IGN/IDEP's 'Limite Distrital' layer (Infraestructura de Datos "
        "Espaciales del Peru; geometry attributed FUENTE=INEI in the live "
        "ArcGIS REST service). `unit_id` is the 6-digit UBIGEO code "
        "(Peru's national administrative-unit identifier, equivalent role "
        "to Chile's CUT / Mexico's INEGI clave); `unit_name` is the source's "
        "own `NOMBDIST` spelling, source-faithful (not re-accented or "
        "stripped) -- same convention as the CDMX and Buenos Aires "
        "references. `province` distinguishes LIMA-province distritos from "
        "CALLAO ones for any downstream analysis that needs to split them.\n",
        encoding="utf-8",
    )
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to the downloaded IGN/IDEP or HDX COD-AB Peru distrital layer (GeoJSON or shapefile)",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(source=args.source, force=args.force)

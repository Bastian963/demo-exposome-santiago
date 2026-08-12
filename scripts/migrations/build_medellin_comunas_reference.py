#!/usr/bin/env python3
"""Build the Medellin comunas + corregimientos spatial reference for medellin_comunas.

Mirrors scripts/migrations/build_bogota_localidades_reference.py. The
authoritative source is the Departamento Administrativo de Planeacion
(DAP)'s "Comunas y Corregimientos" layer (internal feature class
LimiteComunasCorregimientos_2014, feature dataset
PLANEACION.DivisionAdministrativa), served via the city's own ArcGIS REST
endpoint:

    https://www.medellin.gov.co/servidormapas/rest/services/mapas_nacionales/VC_Limite_Politico_Admtivo/MapServer/1/query?where=nombre+IS+NOT+NULL&outFields=*&returnGeometry=true&outSR=4326&f=geojson

That host sits behind a WAF that returns a 403 Forbidden HTML page (not an
error JSON) for any request missing a browser-like Referer header -- this
applies to every programmatic client, not just curl, so a `Referer:
https://www.medellin.gov.co/` header must be set when fetching. Native CRS
is MAGNA-SIRGAS Origen-Nacional (wkid 9377); outSR=4326 reprojects to clean
WGS84 at the source, avoiding any local reprojection.

The raw layer returns 23 features: 21 real comunas/corregimientos (16
comunas, codes "01"-"16"; 5 corregimientos, codes "50"-"90") plus 2
placeholder rows with null nombre/codigo ("SN01"/"SN02", apparently
unassigned institutional enclaves) -- the `where=nombre IS NOT NULL` filter
above already drops these at query time, but this script also drops any
null/blank nombre or codigo defensively in case a differently-filtered or
future export lets them back in.

Fields: codigo (2-digit code, unique across both comunas and corregimientos),
nombre, identificacion ("Comuna 1" / "Corregimiento 50" -- descriptive
text), subtipo_comunacorregimiento (domain-coded: 1=Comuna, 2=Corregimiento),
limitemunicipioid (constant "001", Medellin's own DANE municipio code).
ArcGIS Server returns these lower-cased; the official data dictionary
(DiccionarioDatosGeograficosMapaReferencia.xlsx, sheet "DiccionarioDatos")
documents them upper-cased (CODIGO/NOMBRE/...) -- same data, different
casing, matched case-insensitively here like Bogota's LocCodigo/LocNombre
split.

License: the ArcGIS service itself carries no copyrightText. The paired
ISO19115 metadata record (Alcaldia de Medellin - DAP, uuid
5af8b936-8a61-4c41-bdd4-9cbcfba29da9) declares a CC-BY-SA-equivalent reuse
grant ("libre de compartir y/o adaptar... con atribucion... mismo
licenciamiento") -- cite DAP/Alcaldia de Medellin.

Save the downloaded file under
data/raw/co/medellin/dap_comunas_corregimientos/<version>/ and pass its
path with --source.
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = ROOT / "data" / "reference" / "co" / "medellin" / "medellin_comunas"

# The ArcGIS Server export reports these lower-cased (codigo/nombre/...);
# the official data-dictionary xlsx documents them upper-cased
# (CODIGO/NOMBRE/...) -- same fields, matched case-insensitively so either
# casing works unmodified.
REQUIRED_FIELDS = ("codigo", "nombre", "identificacion", "subtipo_comunacorregimiento")

EXPECTED_UNITS = 21


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


def _load_native(gdf: gpd.GeoDataFrame, cols: dict[str, str]) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    gdf["codigo"] = gdf[cols["codigo"]].astype(str).str.strip().str.zfill(2)
    gdf["nombre_source"] = gdf[cols["nombre"]].astype(str).str.strip()
    gdf["identificacion"] = gdf[cols["identificacion"]].astype(str).str.strip()
    gdf["subtipo_comunacorregimiento"] = (
        gdf[cols["subtipo_comunacorregimiento"]].astype(str).str.strip()
    )
    return gdf[
        ["codigo", "nombre_source", "identificacion", "subtipo_comunacorregimiento", "geometry"]
    ]


def main(source: Path, force: bool) -> None:
    output = TARGET_DIR / "spatial_units.geojson"
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --force")
    if not source.exists():
        raise FileNotFoundError(
            f"{source} not found. Download the DAP 'Comunas y Corregimientos' "
            "layer first -- see this script's module docstring for the exact "
            "URL and the required Referer header -- and pass its path with "
            "--source."
        )

    raw = gpd.read_file(source)
    resolved = _resolve_columns(list(raw.columns))
    normalized = _load_native(raw, resolved)

    # Defensive: drop any placeholder rows with null/blank nombre or codigo
    # (the 2 "SN01"/"SN02" rows seen in the raw 23-feature export) even if
    # the source file wasn't pre-filtered with where=nombre IS NOT NULL.
    blank_name = normalized["nombre_source"].isin(["", "None", "nan", "NaN"]) | normalized[
        "nombre_source"
    ].isna()
    blank_code = normalized["codigo"].isin(["", "None", "nan", "NaN"]) | normalized[
        "codigo"
    ].isna()
    dropped = int((blank_name | blank_code).sum())
    if dropped:
        print(f"Dropping {dropped} placeholder row(s) with null nombre/codigo")
    normalized = normalized.loc[~(blank_name | blank_code)].copy()

    n_units = len(normalized)
    if n_units != EXPECTED_UNITS:
        raise ValueError(
            f"Expected {EXPECTED_UNITS} comunas/corregimientos after dropping "
            f"placeholders, found {n_units}. Check the source is the full "
            "Medellin comunas+corregimientos layer, not a pre-filtered extract."
        )

    result = normalized.copy()
    result["unit_id"] = result["codigo"]
    result["unit_name"] = result["nombre_source"]
    result["unit_type"] = "comuna_corregimiento"
    result["unit_source"] = (
        "Departamento Administrativo de Planeacion (DAP), Alcaldia de Medellin "
        "-- capa 'Comunas y Corregimientos' (LimiteComunasCorregimientos_2014)"
    )
    result = result[
        [
            "unit_id",
            "unit_name",
            "unit_type",
            "unit_source",
            "codigo",
            "identificacion",
            "subtipo_comunacorregimiento",
            "geometry",
        ]
    ]
    result = gpd.GeoDataFrame(result, geometry="geometry", crs=normalized.crs or "EPSG:4326")

    if result["unit_id"].duplicated().any():
        raise ValueError("Duplicate unit_id (codigo) in Medellin comunas reference")
    if result["unit_name"].duplicated().any():
        dupes = result.loc[result["unit_name"].duplicated(keep=False), "unit_name"].tolist()
        raise ValueError(f"Duplicate unit_name in Medellin comunas reference: {dupes}")
    if not result.geometry.notna().all():
        raise ValueError("Null geometries in Medellin comunas reference")
    invalid = ~result.geometry.is_valid
    if bool(invalid.any()):
        result.loc[invalid, "geometry"] = result.loc[invalid, "geometry"].make_valid()

    bounds = result.total_bounds
    print(
        f"total_bounds (west,south,east,north): {bounds[0]:.4f}, {bounds[1]:.4f}, "
        f"{bounds[2]:.4f}, {bounds[3]:.4f}"
    )
    print(f"n comunas/corregimientos: {len(result)}")
    print(
        "Update config/locations/co/medellin.yaml's bbox with the "
        "total_bounds above (plus a small margin)."
    )

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    result.to_file(output, driver="GeoJSON")

    metadata = {
        "schema_version": 1,
        "study_id": "medellin_comunas",
        "spatial_id": "unit_id (codigo)",
        "source_geometry": str(source),
        "source_geometry_sha256": _checksum(source),
        "unit_count": len(result),
        "total_bounds": bounds.tolist(),
    }
    (TARGET_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (TARGET_DIR / "README.md").write_text(
        "# Medellin comunas + corregimientos spatial reference\n\n"
        "`spatial_units.geojson` holds the 21 comunas (16, urban, codes "
        "\"01\"-\"16\") and corregimientos (5, rural, codes \"50\"-\"90\") of "
        "the Municipio de Medellin. The authoritative source is the "
        "Departamento Administrativo de Planeacion's (DAP) 'Comunas y "
        "Corregimientos' layer (internal feature class "
        "LimiteComunasCorregimientos_2014), served via the city's own "
        "ArcGIS REST endpoint at "
        "www.medellin.gov.co/servidormapas -- see this script's module "
        "docstring for the exact query URL and the Referer header it "
        "requires (the host 403s any request without one, for any client, "
        "not just curl). The raw export returns 23 features -- 21 real "
        "units plus 2 null-name placeholder rows (apparently unassigned "
        "institutional enclaves) -- which this script drops defensively. "
        "`unit_id` is the 2-digit `codigo` (Medellin's own comuna/"
        "corregimiento code, unique across both types); `unit_name` is the "
        "source's own `nombre` spelling, source-faithful. `identificacion` "
        "(e.g. \"Comuna 1\", \"Corregimiento 50\") and "
        "`subtipo_comunacorregimiento` (domain-coded: 1=Comuna, "
        "2=Corregimiento) are kept as extra columns so urban/rural can be "
        "split later without recomputing this reference. Native CRS is "
        "MAGNA-SIRGAS Origen-Nacional (wkid 9377); the query requests "
        "outSR=4326 so this file is already clean WGS84. Licensing: the "
        "ArcGIS service itself carries no copyrightText, but the paired "
        "ISO19115 metadata record (Alcaldia de Medellin - DAP, uuid "
        "5af8b936-8a61-4c41-bdd4-9cbcfba29da9) declares a CC-BY-SA-"
        "equivalent reuse grant -- cite DAP/Alcaldia de Medellin.\n",
        encoding="utf-8",
    )
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to the downloaded DAP comunas+corregimientos layer (GeoJSON or shapefile)",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(source=args.source, force=args.force)

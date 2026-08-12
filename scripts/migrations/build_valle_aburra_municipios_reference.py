#!/usr/bin/env python3
"""Build the Valle de Aburra municipios spatial reference for valle_aburra_municipios.

Mirrors scripts/migrations/build_medellin_comunas_reference.py, at metro
scale instead of city scale: the 10 municipios that make up the Area
Metropolitana del Valle de Aburra (Medellin, Bello, Itagui, Envigado,
Sabaneta, La Estrella, Caldas, Copacabana, Girardota, Barbosa). This is a
SEPARATE study from medellin_comunas (city-only, sub-municipal), not a
derivation of it -- same relationship as buenos_aires_amba (metro) vs.
buenos_aires_comunas (CABA only): independent, parallel studies, matching
however the cohort's own residence data is grouped (588 -> 508 participants
are labelled "Valle de Aburra (Medellin)", i.e. metro-wide, not
Medellin-city-only).

The authoritative source is AMVA (Area Metropolitana del Valle de Aburra,
the metro government itself), not DANE -- DANE's own geoportal
(geoportal.dane.gov.co) did not respond from any network tried while
onboarding this city. AMVA's own ArcGIS Server responds with no auth or
special headers needed:

    https://sim.metropol.gov.co/arcgis/rest/services/Division_Politica/Division_Politica/MapServer/2/query?where=1=1&outFields=*&returnGeometry=true&outSR=4326&f=geojson

(mirrored identically at .../Limites/Limites/MapServer/2). This returns
exactly 10 features -- the full metro, no filtering needed. Native CRS is
wkid 3116; outSR=4326 reprojects to clean WGS84 at the source.

Fields: ID_MPIO (3-digit municipio code, no department prefix -- Antioquia's
DIVIPOLA department code is the constant "05" for all 10, so the full
DIVIPOLA code is "05"+ID_MPIO) and S_MUNICIPIO (name, ALL-CAPS in the
source).

License: the MapServer only carries a copyright *notice*
("(c) 2017 Area Metropolitana del Valle de Aburra") -- this is an
attribution/ownership statement, not a confirmed reuse license. AMVA's own
open-data (DKAN) portal is JS-rendered and its API did not return license
metadata for this dataset when checked. Documented here as unconfirmed,
same honesty standard as Bogota's CAR Cundinamarca mirror.

Save the downloaded file under
data/raw/co/valle_aburra/amva_municipios/<version>/ and pass its path with
--source.
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = ROOT / "data" / "reference" / "co" / "valle_aburra" / "valle_aburra_municipios"

# Antioquia's DIVIPOLA department code -- constant for all 10 Valle de
# Aburra municipios, prepended to AMVA's own 3-digit ID_MPIO to build the
# full 5-digit national municipio code.
ANTIOQUIA_DEPT_CODE = "05"

REQUIRED_FIELDS = ("id_mpio", "s_municipio")

EXPECTED_UNITS = 10


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


def _load_native(gdf: gpd.GeoDataFrame, col_id: str, col_name: str) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    gdf["divipola"] = ANTIOQUIA_DEPT_CODE + gdf[col_id].astype(str).str.strip().str.zfill(3)
    gdf["nombre_source"] = gdf[col_name].astype(str).str.strip().str.title()
    return gdf[["divipola", "nombre_source", "geometry"]]


def main(source: Path, force: bool) -> None:
    output = TARGET_DIR / "spatial_units.geojson"
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --force")
    if not source.exists():
        raise FileNotFoundError(
            f"{source} not found. Download AMVA's 'Valle de Aburra' municipios "
            "layer first -- see this script's module docstring for the exact "
            "URL -- and pass its path with --source."
        )

    raw = gpd.read_file(source)
    resolved = _resolve_columns(list(raw.columns))
    normalized = _load_native(raw, resolved["id_mpio"], resolved["s_municipio"])

    n_units = len(normalized)
    if n_units != EXPECTED_UNITS:
        raise ValueError(
            f"Expected {EXPECTED_UNITS} municipios, found {n_units}. Check "
            "the source is AMVA's full Valle de Aburra layer, not a "
            "pre-filtered extract."
        )

    result = normalized.copy()
    result["unit_id"] = result["divipola"]
    result["unit_name"] = result["nombre_source"]
    result["unit_type"] = "municipio"
    result["unit_source"] = (
        "Area Metropolitana del Valle de Aburra (AMVA) -- capa 'Division "
        "Politica' / 'Valle de Aburra' (license not separately confirmed, "
        "see this script's module docstring)"
    )
    result = result[["unit_id", "unit_name", "unit_type", "unit_source", "divipola", "geometry"]]
    result = gpd.GeoDataFrame(result, geometry="geometry", crs=normalized.crs or "EPSG:4326")

    if result["unit_id"].duplicated().any():
        raise ValueError("Duplicate unit_id (DIVIPOLA) in Valle de Aburra municipios reference")
    if result["unit_name"].duplicated().any():
        dupes = result.loc[result["unit_name"].duplicated(keep=False), "unit_name"].tolist()
        raise ValueError(f"Duplicate unit_name in Valle de Aburra municipios reference: {dupes}")
    if not result.geometry.notna().all():
        raise ValueError("Null geometries in Valle de Aburra municipios reference")
    invalid = ~result.geometry.is_valid
    if bool(invalid.any()):
        result.loc[invalid, "geometry"] = result.loc[invalid, "geometry"].make_valid()

    bounds = result.total_bounds
    print(
        f"total_bounds (west,south,east,north): {bounds[0]:.4f}, {bounds[1]:.4f}, "
        f"{bounds[2]:.4f}, {bounds[3]:.4f}"
    )
    print(f"n municipios: {len(result)}")
    print(sorted(result["unit_name"].tolist()))
    print(
        "Update config/locations/co/valle_aburra.yaml's bbox with the "
        "total_bounds above (plus a small margin)."
    )

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    result.to_file(output, driver="GeoJSON")

    metadata = {
        "schema_version": 1,
        "study_id": "valle_aburra_municipios",
        "spatial_id": "unit_id (DIVIPOLA, '05'+ID_MPIO)",
        "source_geometry": str(source),
        "source_geometry_sha256": _checksum(source),
        "unit_count": len(result),
        "total_bounds": bounds.tolist(),
    }
    (TARGET_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (TARGET_DIR / "README.md").write_text(
        "# Valle de Aburra municipios spatial reference\n\n"
        "`spatial_units.geojson` holds the 10 municipios of the Area "
        "Metropolitana del Valle de Aburra (Medellin, Bello, Itagui, "
        "Envigado, Sabaneta, La Estrella, Caldas, Copacabana, Girardota, "
        "Barbosa). This is a SEPARATE, metro-scale study from "
        "medellin_comunas (Medellin city only, sub-municipal) -- same "
        "relationship as buenos_aires_amba (metro) vs. "
        "buenos_aires_comunas (CABA only): independent studies, not one "
        "derived from the other. Chosen because the cohort's own residence "
        "data groups 508 participants under \"Valle de Aburra (Medellin)\" "
        "metro-wide, not Medellin-city-only -- see docs/multicity_status.md.\n\n"
        "The authoritative source is AMVA (Area Metropolitana del Valle de "
        "Aburra, the metro government itself), not DANE -- DANE's own "
        "geoportal did not respond from any network tried while onboarding "
        "this city. See this script's module docstring for AMVA's exact "
        "query URL. `unit_id` is the full 5-digit DIVIPOLA code "
        "(Antioquia's constant department code \"05\" + AMVA's own 3-digit "
        "ID_MPIO); `unit_name` is AMVA's own S_MUNICIPIO spelling, "
        "title-cased from the source's ALL-CAPS. Native CRS is wkid 3116; "
        "the query requests outSR=4326 so this file is already clean "
        "WGS84. Licensing: the AMVA service carries only a copyright "
        "*notice* (\"(c) 2017 Area Metropolitana del Valle de Aburra\"), "
        "not a confirmed reuse license -- AMVA's own open-data portal did "
        "not return license metadata for this dataset when checked. Same "
        "unconfirmed-license honesty standard as Bogota's CAR Cundinamarca "
        "mirror (see build_bogota_localidades_reference.py).\n",
        encoding="utf-8",
    )
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Path to the downloaded AMVA Valle de Aburra municipios layer (GeoJSON or shapefile)",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(source=args.source, force=args.force)

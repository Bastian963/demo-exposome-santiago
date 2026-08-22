#!/usr/bin/env python3
"""Build the official 34-municipality RMBH reference for BrainLat.

This migrator deliberately does not download data.  It combines two immutable
IBGE snapshots that a human has already downloaded:

* the ``qg_2021_212_categoriametrop`` WFS layer, filtered to IBGE's exact
  category ``Região Metropolitana de Belo Horizonte``; and
* IBGE's Minas Gerais municipal digital mesh (MMD).

The first source decides *membership* and the second supplies the official
municipal geometry.  This keeps the cohort scope as the legally constituted
RMBH (34 municípios), explicitly excluding the separate Colar Metropolitano.
Both source payloads and their SHA-256 hashes are recorded under
``data/raw/br/belo_horizonte/ibge_rmbh/<version>/``; this script only writes
the derived reference after every membership and geometry check passes.

Recommended manual acquisition (from the repository root):

    RAW=data/raw/br/belo_horizonte/ibge_rmbh/2021-2024
    mkdir -p "$RAW"
    curl -fL --retry 3 -o "$RAW/rmbh_membership.geojson" \
      "https://geoservicos.ibge.gov.br/geoserver/CGMAT/wfs?service=WFS&version=2.0.0&request=GetFeature&typeNames=CGMAT:qg_2021_212_categoriametrop&outputFormat=application/json&srsName=EPSG:4326&CQL_FILTER=nm_catmetrop%20%3D%20%27Regi%C3%A3o%20Metropolitana%20de%20Belo%20Horizonte%27"
    curl -fL --retry 3 -o "$RAW/MG_Municipios_2024.zip" \
      "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2024/UFs/MG/MG_Municipios_2024.zip"

    PYTHONPYCACHEPREFIX=/tmp .venv/bin/python \
      scripts/migrations/build_belo_horizonte_rmbh_reference.py \
      --membership "$RAW/rmbh_membership.geojson" \
      --municipalities "$RAW/MG_Municipios_2024.zip" \
      --version 2021-2024
"""
from __future__ import annotations

import argparse
import json
import unicodedata
from hashlib import sha256
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import shapely
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = ROOT / "data" / "reference" / "br" / "belo_horizonte" / "belo_horizonte_rmbh"
RAW_ROOT = ROOT / "data" / "raw" / "br" / "belo_horizonte" / "ibge_rmbh"

METRO_NAME = "Região Metropolitana de Belo Horizonte"
EXPECTED_UNITS = 34
MEMBERSHIP_URL = (
    "https://geoservicos.ibge.gov.br/geoserver/CGMAT/wfs?service=WFS&version=2.0.0&"
    "request=GetFeature&typeNames=CGMAT:qg_2021_212_categoriametrop&"
    "outputFormat=application/json&srsName=EPSG:4326&"
    "CQL_FILTER=nm_catmetrop%20%3D%20%27Regi%C3%A3o%20Metropolitana%20de%20Belo%20Horizonte%27"
)
MUNICIPALITIES_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_municipais/municipio_2024/UFs/MG/MG_Municipios_2024.zip"
)

_MEMBERSHIP_FIELDS = ("cd_catmetrop", "nm_catmetrop", "cd_mun", "nm_mun")
_MUNICIPALITY_FIELDS = ("cd_mun", "nm_mun")


def _checksum(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value).strip())
    return "".join(char for char in text if not unicodedata.combining(char)).casefold()


def _code(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if not text.isdigit():
        raise ValueError(f"IBGE municipality code is not numeric: {value!r}")
    return text.zfill(7)


def _resolve_columns(columns: Iterable[object], required: tuple[str, ...]) -> dict[str, object]:
    by_lower = {str(column).casefold(): column for column in columns}
    missing = [field for field in required if field not in by_lower]
    if missing:
        raise ValueError(
            f"Source is missing expected fields {missing}; actual fields: "
            f"{sorted(map(str, columns))}. Update the migrator rather than guessing."
        )
    return {field: by_lower[field] for field in required}


def _polygonal_valid(geometry):
    if geometry is None or geometry.is_empty:
        raise ValueError("Null or empty geometry in IBGE municipal mesh")
    repaired = geometry if geometry.is_valid else shapely.make_valid(geometry)
    if repaired.geom_type == "GeometryCollection":
        polygons = [part for part in repaired.geoms if part.geom_type in {"Polygon", "MultiPolygon"}]
        if not polygons:
            raise ValueError("Geometry repair produced no polygonal component")
        repaired = unary_union(polygons)
    if repaired.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"Municipal mesh has non-polygon geometry after repair: {repaired.geom_type}")
    return repaired


def build_reference(membership: gpd.GeoDataFrame, municipalities: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Return the validated official municipal geometry for the RMBH only."""
    membership_fields = _resolve_columns(membership.columns, _MEMBERSHIP_FIELDS)
    municipality_fields = _resolve_columns(municipalities.columns, _MUNICIPALITY_FIELDS)

    is_rmbh = membership[membership_fields["nm_catmetrop"]].map(_normalise) == _normalise(METRO_NAME)
    selected = membership.loc[is_rmbh].copy()
    if len(selected) != EXPECTED_UNITS:
        raise ValueError(
            f"Expected {EXPECTED_UNITS} official RMBH municipalities, found {len(selected)}. "
            "Check that the IBGE WFS snapshot is filtered to the RMBH and excludes Colar Metropolitano."
        )

    member_codes = selected[membership_fields["cd_mun"]].map(_code)
    if member_codes.duplicated().any():
        duplicates = sorted(member_codes[member_codes.duplicated(keep=False)].unique())
        raise ValueError(f"Duplicate cd_mun in official RMBH membership: {duplicates}")

    mesh = municipalities.copy()
    mesh["_cd_mun"] = mesh[municipality_fields["cd_mun"]].map(_code)
    mesh["_nm_mun"] = mesh[municipality_fields["nm_mun"]].astype(str).str.strip()
    if mesh["_cd_mun"].duplicated().any():
        raise ValueError("Duplicate CD_MUN in the IBGE municipal mesh")

    result = mesh.loc[mesh["_cd_mun"].isin(set(member_codes))].copy()
    missing = sorted(set(member_codes).difference(result["_cd_mun"]))
    if missing:
        raise ValueError(f"Official RMBH municipality codes absent from MG municipal mesh: {missing}")
    if len(result) != EXPECTED_UNITS:
        raise ValueError(f"Expected {EXPECTED_UNITS} RMBH municipal geometries, found {len(result)}")

    result["geometry"] = result.geometry.map(_polygonal_valid)
    result = gpd.GeoDataFrame(result, geometry="geometry", crs=mesh.crs or "EPSG:4674")
    if str(result.crs) != "EPSG:4326":
        result = result.to_crs("EPSG:4326")

    result["unit_id"] = result["_cd_mun"]
    result["unit_name"] = result["_nm_mun"]
    result["unit_type"] = "municipio"
    result["unit_source"] = (
        "IBGE Recortes Metropolitanos (membership) + Malha Municipal Digital MG 2024 (geometry)"
    )
    result = result[["unit_id", "unit_name", "unit_type", "unit_source", "geometry"]].sort_values("unit_id")
    if result["unit_name"].duplicated().any():
        duplicates = sorted(result.loc[result["unit_name"].duplicated(keep=False), "unit_name"].unique())
        raise ValueError(f"Duplicate municipal names in RMBH reference: {duplicates}")
    return gpd.GeoDataFrame(result, geometry="geometry", crs="EPSG:4326")


def _write_raw_manifest(
    raw_dir: Path,
    membership: Path,
    municipalities: Path,
    version: str,
) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = raw_dir / "source_manifest.json"
    manifest = {
        "schema_version": 1,
        "provider": "IBGE",
        "dataset": "rmbh_official_membership_and_municipal_mesh",
        "version": version,
        "scope": "IBGE category Região Metropolitana de Belo Horizonte only; excludes Colar Metropolitano",
        "files": [
            {
                "path": membership.name,
                "sha256": _checksum(membership),
                "source_url": MEMBERSHIP_URL,
                "role": "official metropolitan membership",
            },
            {
                "path": municipalities.name,
                "sha256": _checksum(municipalities),
                "source_url": MUNICIPALITIES_URL,
                "role": "official municipal geometry",
            },
        ],
    }
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing != manifest:
            raise FileExistsError(
                f"Refusing to replace immutable raw manifest {manifest_path}; use a new version directory."
            )
        return
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(membership_path: Path, municipalities_path: Path, version: str, force: bool) -> None:
    membership_path = membership_path.resolve()
    municipalities_path = municipalities_path.resolve()
    if not membership_path.exists() or not municipalities_path.exists():
        raise FileNotFoundError("Both manually downloaded IBGE source files must exist before migration")
    raw_dir = RAW_ROOT / version
    if membership_path.parent != raw_dir or municipalities_path.parent != raw_dir:
        raise ValueError(
            "Inputs must live together in "
            f"{raw_dir.relative_to(ROOT)} so the immutable manifest has one clear snapshot root"
        )

    output = TARGET_DIR / "spatial_units.geojson"
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --force only for an intentional rebuild")

    result = build_reference(gpd.read_file(membership_path), gpd.read_file(municipalities_path))
    _write_raw_manifest(raw_dir, membership_path, municipalities_path, version)

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    result.to_file(output, driver="GeoJSON")
    bounds = result.total_bounds.tolist()
    metadata = {
        "schema_version": 1,
        "study_id": "belo_horizonte_rmbh",
        "spatial_id": "unit_id (IBGE CD_MUN, seven digits)",
        "source_geometry": str(municipalities_path.relative_to(ROOT)),
        "source_geometry_sha256": _checksum(municipalities_path),
        "membership_source": str(membership_path.relative_to(ROOT)),
        "membership_source_sha256": _checksum(membership_path),
        "unit_count": len(result),
        "total_bounds": bounds,
        "scope": "IBGE Região Metropolitana de Belo Horizonte (RMBH), excludes Colar Metropolitano",
    }
    (TARGET_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (TARGET_DIR / "README.md").write_text(
        "# Belo Horizonte — RMBH municipal reference\n\n"
        "`spatial_units.geojson` contains exactly the 34 municipalities in the legally "
        "IBGE Região Metropolitana de Belo Horizonte (RMBH), not the separate "
        "Colar Metropolitano. Membership comes from IBGE's Recortes Metropolitanos WFS "
        "snapshot and geometry from the IBGE Minas Gerais Malha Municipal Digital 2024. "
        "`unit_id` is IBGE `CD_MUN` (seven digits); `unit_name` retains the MMD spelling. "
        "The exact downloaded files, checksums and URLs are frozen in the matching "
        "`data/raw/br/belo_horizonte/ibge_rmbh/" + version + "/source_manifest.json`.\n",
        encoding="utf-8",
    )
    print(f"RMBH municipalities: {len(result)}")
    print(f"total_bounds (west,south,east,north): {bounds[0]:.4f}, {bounds[1]:.4f}, {bounds[2]:.4f}, {bounds[3]:.4f}")
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--membership", type=Path, required=True, help="Filtered IBGE categoria metropolitana WFS GeoJSON")
    parser.add_argument("--municipalities", type=Path, required=True, help="IBGE MG municipal mesh ZIP/GeoJSON")
    parser.add_argument("--version", required=True, help="Immutable combined-source snapshot version, e.g. 2021-2024")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(args.membership, args.municipalities, args.version, args.force)

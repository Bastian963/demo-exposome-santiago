#!/usr/bin/env python3
"""Build the CDMX alcaldias spatial reference for cdmx_alcaldias.

Mirrors scripts/migrations/build_buenos_aires_amba_reference.py, but from a
single source instead of a two-source merge: INEGI's Marco Geoestadistico
municipal boundaries ("Division politica municipal, 1:250000"), filtered to
CVE_ENT "09" (Ciudad de Mexico), which gives the 16 alcaldias.

Two source formats are accepted, detected from the file's columns:

- Shapefile/GeoJSON with native attribute columns CVEGEO/CVE_ENT/CVE_MUN/
  NOMGEO (INEGI's own casing).
- KML/KMZ (the CONABIO mirror's "Google Earth" export,
  http://geoportal.conabio.gob.mx/metadatos/doc/html/mun22gw.html): geopandas
  reads KML placemarks with a free-text `description` column that embeds the
  same attributes as lower-case `<li>cve_ent: ...</li>` HTML, and each
  placemark's geometry is a GeometryCollection of a label Point plus the
  actual Polygon -- both are handled below (regex-parsed and
  Polygon-extracted respectively). Confirmed against the actual 2022 CONABIO
  KMZ: 2475 national features, CRS EPSG:4326, CDMX subset is exactly 16 rows.

Save the downloaded file under
data/raw/mx/cdmx/inegi_marco_geoestadistico/<version>/ and pass its path with
--source. If a source has neither the native columns nor a `description`
column, the script fails fast and lists what is actually present -- fix this
file rather than guessing.
"""
from __future__ import annotations

import argparse
import json
import re
from hashlib import sha256
from pathlib import Path

import geopandas as gpd
from shapely.geometry.base import BaseGeometry

ROOT = Path(__file__).resolve().parents[2]
TARGET_DIR = ROOT / "data" / "reference" / "mx" / "cdmx" / "cdmx_alcaldias"

CDMX_ENTITY_CODE = "09"
COL_CVEGEO = "CVEGEO"
COL_CVE_ENT = "CVE_ENT"
COL_CVE_MUN = "CVE_MUN"
COL_NOMGEO = "NOMGEO"
NATIVE_COLUMNS = {COL_CVEGEO, COL_CVE_ENT, COL_CVE_MUN, COL_NOMGEO}

_KML_ATTR_RE = re.compile(
    r'<span class="atr-name">(?P<key>[^<]+)</span>:</strong>\s*'
    r'<span class="atr-value">(?P<value>[^<]*)</span>'
)


def _checksum(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _parse_kml_description(description: str) -> dict[str, str]:
    return {m.group("key"): m.group("value") for m in _KML_ATTR_RE.finditer(description)}


def _largest_polygon(geometry: BaseGeometry) -> BaseGeometry:
    """INEGI's KML export packs a label Point + the boundary Polygon into one
    GeometryCollection per placemark; keep only the polygonal part."""
    if geometry.geom_type in ("Polygon", "MultiPolygon"):
        return geometry
    if geometry.geom_type == "GeometryCollection":
        polygons = [g for g in geometry.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        if len(polygons) == 1:
            return polygons[0]
        if len(polygons) > 1:
            return max(polygons, key=lambda g: g.area)
    raise ValueError(f"No polygon found in geometry of type {geometry.geom_type}")


def _load_native(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    gdf[COL_CVE_ENT] = gdf[COL_CVE_ENT].astype(str).str.zfill(2)
    gdf[COL_CVE_MUN] = gdf[COL_CVE_MUN].astype(str).str.zfill(3)
    gdf["unit_name_source"] = gdf[COL_NOMGEO].astype(str).str.strip()
    return gdf[[COL_CVE_ENT, COL_CVE_MUN, "unit_name_source", "geometry"]]


def _load_kml(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    attrs = gdf["description"].apply(_parse_kml_description)
    out = gpd.GeoDataFrame(
        {
            COL_CVE_ENT: attrs.map(lambda a: a.get("cve_ent", "")).astype(str).str.zfill(2),
            COL_CVE_MUN: attrs.map(lambda a: a.get("cve_mun", "")).astype(str).str.zfill(3),
            "unit_name_source": attrs.map(lambda a: a.get("nomgeo", "")).astype(str).str.strip(),
            "geometry": gdf.geometry.apply(_largest_polygon),
        },
        crs=gdf.crs,
    )
    return out


def main(source: Path, force: bool) -> None:
    output = TARGET_DIR / "spatial_units.geojson"
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --force")
    if not source.exists():
        raise FileNotFoundError(
            f"{source} not found. Download the INEGI Marco Geoestadistico "
            "municipal layer first (see this script's module docstring for "
            "the portal) and pass its path with --source."
        )

    raw = gpd.read_file(source)
    if NATIVE_COLUMNS.issubset(raw.columns):
        normalized = _load_native(raw)
    elif "description" in raw.columns:
        normalized = _load_kml(raw)
    else:
        raise ValueError(
            f"Source has neither native columns {sorted(NATIVE_COLUMNS)} nor a "
            f"KML `description` column; actual columns: {sorted(raw.columns)}. "
            "Update this script to match the real file rather than guessing."
        )

    alcaldias = normalized[normalized[COL_CVE_ENT] == CDMX_ENTITY_CODE].copy()
    if len(alcaldias) != 16:
        raise ValueError(
            f"Expected 16 CDMX alcaldias (CVE_ENT={CDMX_ENTITY_CODE}), found "
            f"{len(alcaldias)}. Check the source covers the whole country, "
            "not a pre-filtered state extract."
        )

    alcaldias["unit_id"] = "cdmx_" + alcaldias[COL_CVE_MUN].astype(str)
    alcaldias["unit_name"] = alcaldias["unit_name_source"]
    alcaldias["unit_type"] = "alcaldia"
    alcaldias["unit_source"] = "INEGI"
    result = alcaldias[["unit_id", "unit_name", "unit_type", "unit_source", COL_CVE_MUN, "geometry"]]
    result = result.rename(columns={COL_CVE_MUN: "cve_mun"})
    result = gpd.GeoDataFrame(result, geometry="geometry", crs=normalized.crs or "EPSG:4326")

    if result["unit_id"].duplicated().any():
        raise ValueError("Duplicate unit_id in CDMX alcaldias reference")
    if result["unit_name"].duplicated().any():
        dupes = result.loc[result["unit_name"].duplicated(keep=False), "unit_name"].tolist()
        raise ValueError(f"Duplicate unit_name in CDMX alcaldias reference: {dupes}")
    if not result.geometry.notna().all():
        raise ValueError("Null geometries in CDMX alcaldias reference")
    invalid = ~result.geometry.is_valid
    if bool(invalid.any()):
        result.loc[invalid, "geometry"] = result.loc[invalid, "geometry"].make_valid()

    bounds = result.total_bounds
    print(f"total_bounds (west,south,east,north): {bounds[0]:.4f}, {bounds[1]:.4f}, {bounds[2]:.4f}, {bounds[3]:.4f}")
    print(f"n alcaldias: {len(result)}")
    print("Update config/locations/mx/cdmx.yaml's bbox with the total_bounds above (plus a small margin).")

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    result.to_file(output, driver="GeoJSON")

    metadata = {
        "schema_version": 1,
        "study_id": "cdmx_alcaldias",
        "spatial_id": "unit_id (cdmx_<cve_mun>)",
        "source_geometry": str(source),
        "source_geometry_sha256": _checksum(source),
        "unit_count": len(result),
        "total_bounds": bounds.tolist(),
    }
    (TARGET_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (TARGET_DIR / "README.md").write_text(
        "# CDMX alcaldias spatial reference\n\n"
        "`spatial_units.geojson` holds the 16 alcaldias of Ciudad de Mexico "
        "(CVE_ENT 09), filtered from INEGI's Marco Geoestadistico municipal "
        "layer (\"Division politica municipal, 1:250000. 2022\", CONABIO "
        "mirror, CC-BY-NC 2.5 MX -- cite INEGI/CONABIO, non-commercial use). "
        "`unit_id` is `cdmx_<cve_mun>` (3-digit INEGI municipio code within "
        "the entity); `unit_name` is INEGI's own `nomgeo` spelling, "
        "source-faithful (not re-accented or stripped) -- same convention as "
        "data/reference/ar/buenos_aires_amba/buenos_aires_amba.\n",
        encoding="utf-8",
    )
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="Path to the downloaded INEGI municipal layer (shapefile, GeoJSON, or KML/KMZ)")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(source=args.source, force=args.force)

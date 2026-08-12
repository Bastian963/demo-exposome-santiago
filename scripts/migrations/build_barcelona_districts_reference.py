#!/usr/bin/env python3
"""Build Barcelona's canonical municipal-district spatial reference.

The official Barcelona district boundary must be downloaded by a human from
the Ayuntamiento's Open Data BCN portal and kept as an immutable local raw
source, for example under::

    data/raw/ajuntament-barcelona/districtes-municipals/<version>/districtes.json

This migration performs no download. It converts that source into the study
reference consumed by GEMMA, retaining source identifiers and names rather
than inventing a join key. It accepts the official ``BarcelonaCiutat_Districtes.json``
array (WKT geometry in ETRS89 / UTM zone 31N) as well as a conventional
GeoJSON feature collection. The input must represent all ten municipal
districts, not neighborhoods or the wider Barcelonès comarca.
"""
from __future__ import annotations

import argparse
import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Iterable
import sys

import geopandas as gpd
import shapely
from shapely import from_wkt
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from exposome.raw_sources import (  # noqa: E402
    SOURCE_MANIFEST_NAME,
    build_raw_source_asset,
    write_source_manifest,
)

TARGET_DIR = ROOT / "data" / "reference" / "es" / "barcelona" / "barcelona_districts_noise"
EXPECTED_UNITS = 10
# Open Data BCN's authoritative WKT layer has 11.417 m² of total pairwise
# overlap across ~102 km², caused by independently digitised shared edges.
# This permits only that negligible topology noise, never a meaningful overlap.
MAX_NUMERICAL_OVERLAP_M2 = 25.0
OFFICIAL_PORTAL = "https://opendata-ajuntament.barcelona.cat/"
RAW_PROVIDER = "ajuntament-barcelona"
RAW_DATASET = "districtes-municipals"

_ID_ALIASES = (
    "codi_districte",
    "cod_districte",
    "district_code",
    "district_id",
    "id_districte",
)
_NAME_ALIASES = (
    "nom_districte",
    "name_districte",
    "district_name",
    "district",
)
_WKT_GEOMETRY_ALIASES = (
    "geometria_etrs89",
    "geometry_wkt",
    "wkt",
)
OFFICIAL_WKT_CRS = "EPSG:25831"  # ETRS89 / UTM zone 31N, used by Open Data BCN.


def _checksum(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_column(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")


def _resolve_column(
    columns: Iterable[object],
    *,
    requested: str | None,
    aliases: tuple[str, ...],
    role: str,
) -> object:
    available = list(columns)
    by_normalised = {_normalise_column(column): column for column in available}
    if requested:
        selected = by_normalised.get(_normalise_column(requested))
        if selected is None:
            raise ValueError(
                f"District source has no requested {role} column {requested!r}; "
                f"available columns: {available}"
            )
        return selected
    matches = [by_normalised[alias] for alias in aliases if alias in by_normalised]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(
            f"District source has multiple plausible {role} columns {matches}; "
            f"pass --{role}-column explicitly."
        )
    raise ValueError(
        f"District source has no recognised {role} column; expected one of {aliases}, "
        f"available columns: {available}. Pass --{role}-column explicitly."
    )


def _polygonal_valid(geometry: object) -> object:
    fixed = shapely.make_valid(geometry)
    if fixed.geom_type == "GeometryCollection":
        polygons = [item for item in fixed.geoms if item.geom_type in {"Polygon", "MultiPolygon"}]
        if not polygons:
            raise ValueError("make_valid produced no polygonal geometry")
        fixed = unary_union(polygons)
    if fixed.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"Expected polygonal geometry after repair, got {fixed.geom_type}")
    return fixed


def _read_source(source: Path) -> gpd.GeoDataFrame:
    """Read either a GeoJSON feature collection or Open Data BCN's WKT JSON array."""
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # Preserve GeoPandas' useful error message for malformed feature collections.
        return gpd.read_file(source)

    if not isinstance(payload, list):
        return gpd.read_file(source)
    if not payload or not all(isinstance(row, dict) for row in payload):
        raise ValueError(
            "Barcelona district JSON must be a non-empty array of official district records."
        )
    geometry_column = _resolve_column(
        payload[0].keys(),
        requested=None,
        aliases=_WKT_GEOMETRY_ALIASES,
        role="WKT geometry",
    )
    geometries = []
    for index, row in enumerate(payload):
        value = row.get(geometry_column)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"District record {index} has no WKT geometry in {geometry_column!r}")
        try:
            geometries.append(from_wkt(value))
        except Exception as exc:  # GEOS errors do not share a stable public exception class.
            raise ValueError(
                f"District record {index} has invalid WKT geometry in {geometry_column!r}"
            ) from exc
    return gpd.GeoDataFrame(payload, geometry=geometries, crs=OFFICIAL_WKT_CRS)


def build_reference(
    source: Path,
    *,
    target_dir: Path = TARGET_DIR,
    id_column: str | None = None,
    name_column: str | None = None,
    source_url: str = OFFICIAL_PORTAL,
    source_version: str | None = None,
    force: bool = False,
) -> Path:
    """Validate a local official source and write the canonical 10-district reference."""
    source = source.resolve()
    output = target_dir / "spatial_units.geojson"
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass force=True")
    if not source.is_file():
        raise FileNotFoundError(
            f"{source} not found. Download the official Barcelona district geometry locally "
            f"and pass it to this migration; see {OFFICIAL_PORTAL}"
        )
    if source.suffix.casefold() not in {".geojson", ".json"}:
        raise ValueError(
            "Barcelona district input must be one JSON or GeoJSON file so its complete raw payload "
            "can be tracked by one immutable source manifest."
        )

    raw = _read_source(source)
    if raw.crs is None:
        raise ValueError(f"District source lacks CRS: {source}")
    resolved_id = _resolve_column(
        raw.columns,
        requested=id_column,
        aliases=_ID_ALIASES,
        role="id",
    )
    resolved_name = _resolve_column(
        raw.columns,
        requested=name_column,
        aliases=_NAME_ALIASES,
        role="name",
    )
    result = gpd.GeoDataFrame(
        {
            "unit_id": raw[resolved_id].astype(str).str.strip(),
            "unit_name": raw[resolved_name].astype(str).str.strip(),
            "unit_type": "distrito",
            "unit_source": "Ajuntament de Barcelona Open Data — districtes municipals",
            "geometry": raw.geometry,
        },
        geometry="geometry",
        crs=raw.crs,
    )
    if len(result) != EXPECTED_UNITS:
        raise ValueError(
            f"Expected {EXPECTED_UNITS} Barcelona municipal districts, found {len(result)}. "
            "Check that the source is the complete district layer, not neighborhoods or a filter."
        )
    if result["unit_id"].eq("").any() or result["unit_name"].eq("").any():
        raise ValueError("Barcelona district source has blank IDs or names")
    if result["unit_id"].duplicated().any():
        duplicates = result.loc[result["unit_id"].duplicated(keep=False), "unit_id"].tolist()
        raise ValueError(f"Duplicate Barcelona district IDs: {duplicates}")
    if result["unit_name"].duplicated().any():
        duplicates = result.loc[result["unit_name"].duplicated(keep=False), "unit_name"].tolist()
        raise ValueError(f"Duplicate Barcelona district names: {duplicates}")
    if not result.geometry.notna().all() or result.geometry.is_empty.any():
        raise ValueError("Barcelona district source has null or empty geometries")
    invalid = ~result.geometry.is_valid
    if invalid.any():
        result.loc[invalid, "geometry"] = result.loc[invalid, "geometry"].map(_polygonal_valid)
    bad_types = set(result.geometry.geom_type) - {"Polygon", "MultiPolygon"}
    if bad_types:
        raise ValueError(f"Barcelona district source has non-polygonal geometries: {sorted(bad_types)}")
    result = result.to_crs("EPSG:4326").sort_values("unit_id", kind="stable").reset_index(drop=True)
    metric = result.to_crs("EPSG:3035")
    raw_area_m2 = float(metric.geometry.area.sum())
    dissolved_area_m2 = float(unary_union(metric.geometry).area)
    overlap_m2 = max(0.0, raw_area_m2 - dissolved_area_m2)
    # A municipality reference must be a partition. The official raw layer
    # itself has small shared-edge slivers, so preserve a narrow documented
    # tolerance without accepting a material overlap.
    if overlap_m2 > MAX_NUMERICAL_OVERLAP_M2:
        raise ValueError(
            f"Barcelona district geometries overlap by {overlap_m2:.3f} m²; "
            f"the maximum permitted numerical tolerance is {MAX_NUMERICAL_OVERLAP_M2:.0f} m²."
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    result.to_file(output, driver="GeoJSON")
    raw_version = source_version or source.parent.name
    source_asset = build_raw_source_asset(source.parent, source, url=source_url)
    source_manifest = write_source_manifest(
        source.parent,
        provider=RAW_PROVIDER,
        dataset=RAW_DATASET,
        version=raw_version,
        license_name="Ajuntament de Barcelona Open Data terms; see source URL",
        assets=[source_asset],
    )
    try:
        source_path = source.relative_to(ROOT).as_posix()
        manifest_path = source_manifest.relative_to(ROOT).as_posix()
    except ValueError:
        # Tests and one-off staging may be outside the checkout. Their bytes
        # remain identified by SHA-256; production raw payloads belong under
        # data/raw and therefore use the portable path branch above.
        source_path = source.name
        manifest_path = SOURCE_MANIFEST_NAME
    metadata = {
        "schema_version": 1,
        "study_id": "barcelona_districts_noise",
        "spatial_id": f"unit_id ({resolved_id})",
        "spatial_name": f"unit_name ({resolved_name})",
        "source_geometry": source_path,
        "source_geometry_sha256": _checksum(source),
        "source_url": source_url,
        "source_manifest": manifest_path,
        "unit_count": len(result),
        "crs": "EPSG:4326",
        "total_bounds": result.total_bounds.tolist(),
        "district_overlap_m2": overlap_m2,
    }
    (target_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (target_dir / "README.md").write_text(
        "# Barcelona — distritos municipales\n\n"
        "`spatial_units.geojson` contiene los diez distritos municipales de Barcelona, "
        "derivados de una descarga local de la capa oficial de districtes del Ajuntament. "
        "`unit_id` y `unit_name` preservan las columnas de la fuente indicada en "
        "`metadata.json`; no se fabrican códigos ni nombres. La referencia sirve sólo "
        "para `barcelona_districts_noise`, no para barrios ni para la comarca Barcelonès.\n\n"
        f"Portal oficial: {source_url}\n",
        encoding="utf-8",
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        required=True,
        type=Path,
        help="Local official district GeoJSON or BarcelonaCiutat_Districtes.json",
    )
    parser.add_argument("--id-column", help="Official source field used as the stable district ID")
    parser.add_argument("--name-column", help="Official source field used as the district name")
    parser.add_argument("--source-url", default=OFFICIAL_PORTAL)
    parser.add_argument(
        "--source-version",
        help="Immutable local raw version; defaults to the source file's parent directory name",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    output = build_reference(
        args.source,
        id_column=args.id_column,
        name_column=args.name_column,
        source_url=args.source_url,
        source_version=args.source_version,
        force=args.force,
    )
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()

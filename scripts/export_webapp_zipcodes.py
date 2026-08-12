#!/usr/bin/env python3
"""Export local postal-code lookup data for the webapp.

The webapp never geocodes ZIP codes online. It only resolves codes from
local, reproducible reference files:

- data/raw/zipcodes/postal_code_reference.csv
  columns: zipcode, city, commune, lat, lon
- data/raw/zipcodes/zipcodes_rm.geojson
  properties: zipcode/postcode/codigo_postal plus optional commune/name,
  geometry used to derive a representative lon/lat.

If neither file exists, the exported JSON explicitly reports
``missing_reference`` so the UI can keep the manual map marker as the
honest fallback.
"""
from __future__ import annotations

import csv
import json
import unicodedata
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "zipcodes"
CSV_SOURCE = RAW_DIR / "postal_code_reference.csv"
GEOJSON_SOURCE = RAW_DIR / "zipcodes_rm.geojson"
MASTER_GEOJSON = REPO_ROOT / "webapp" / "public" / "data" / "master.geojson"
OUT_JSON = REPO_ROOT / "webapp" / "public" / "data" / "zipcodes.json"


def _slugify(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().strip()
    keep = []
    for ch in text:
        if ch.isalnum():
            keep.append(ch)
        elif ch in {" ", "-", "_"}:
            keep.append("_")
    slug = "".join(keep)
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def _load_commune_lookup() -> dict[str, dict[str, str]]:
    if not MASTER_GEOJSON.exists():
        return {}
    data = json.loads(MASTER_GEOJSON.read_text())
    lookup: dict[str, dict[str, str]] = {}
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        name = props.get("name") or ""
        slug = props.get("slug") or _slugify(name)
        if name:
            lookup[_slugify(name)] = {"commune_name": name, "commune_slug": slug}
    return lookup


def _normalize_zipcode(value: Any) -> str | None:
    raw = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(raw) != 7:
        return None
    return raw


def _record(
    zipcode: Any,
    lat: Any,
    lon: Any,
    commune: Any = "",
    city: Any = "",
    source: str = "",
    commune_lookup: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any] | None:
    code = _normalize_zipcode(zipcode)
    if not code:
        return None
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None
    commune_name = str(commune or "").strip()
    commune_slug = _slugify(commune_name)
    lookup = (commune_lookup or {}).get(commune_slug)
    if lookup:
        commune_name = lookup["commune_name"]
        commune_slug = lookup["commune_slug"]
    return {
        "zipcode": code,
        "city": str(city or "Santiago").strip() or "Santiago",
        "commune_name": commune_name,
        "commune_slug": commune_slug,
        "lat": round(lat_f, 7),
        "lon": round(lon_f, 7),
        "source": source,
    }


def _load_csv(commune_lookup: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with CSV_SOURCE.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rec = _record(
                row.get("zipcode"),
                row.get("lat"),
                row.get("lon"),
                row.get("commune"),
                row.get("city"),
                str(CSV_SOURCE.relative_to(REPO_ROOT)),
                commune_lookup,
            )
            if rec:
                records.append(rec)
    return records


def _coords_from_geometry(geometry: dict[str, Any]) -> tuple[float, float] | None:
    coords = geometry.get("coordinates")
    if not coords:
        return None
    points: list[tuple[float, float]] = []

    def visit(node: Any) -> None:
        if (
            isinstance(node, list)
            and len(node) >= 2
            and isinstance(node[0], (int, float))
            and isinstance(node[1], (int, float))
        ):
            points.append((float(node[0]), float(node[1])))
            return
        if isinstance(node, list):
            for child in node:
                visit(child)

    visit(coords)
    if not points:
        return None
    lon = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    return lon, lat


def _load_geojson(commune_lookup: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    data = json.loads(GEOJSON_SOURCE.read_text())
    records: list[dict[str, Any]] = []
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        center = _coords_from_geometry(feature.get("geometry") or {})
        if not center:
            continue
        lon, lat = center
        zipcode = (
            props.get("zipcode")
            or props.get("postcode")
            or props.get("codigo_postal")
            or props.get("cod_postal")
        )
        commune = props.get("commune") or props.get("comuna") or props.get("name")
        rec = _record(
            zipcode,
            lat,
            lon,
            commune,
            props.get("city") or "Santiago",
            str(GEOJSON_SOURCE.relative_to(REPO_ROOT)),
            commune_lookup,
        )
        if rec:
            records.append(rec)
    return records


def _dedupe(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_zip: dict[str, dict[str, Any]] = {}
    for rec in records:
        by_zip.setdefault(rec["zipcode"], rec)
    return [by_zip[k] for k in sorted(by_zip)]


def main() -> None:
    commune_lookup = _load_commune_lookup()
    if CSV_SOURCE.exists():
        records = _dedupe(_load_csv(commune_lookup))
        payload = {
            "schema_version": 1,
            "status": "ready",
            "source": str(CSV_SOURCE.relative_to(REPO_ROOT)),
            "records": records,
        }
    elif GEOJSON_SOURCE.exists():
        records = _dedupe(_load_geojson(commune_lookup))
        payload = {
            "schema_version": 1,
            "status": "ready",
            "source": str(GEOJSON_SOURCE.relative_to(REPO_ROOT)),
            "records": records,
        }
    else:
        payload = {
            "schema_version": 1,
            "status": "missing_reference",
            "source": None,
            "records": [],
            "message": (
                "No hay tabla o capa postal local para la Region Metropolitana. "
                "El perfil por codigo postal se activa cuando exista "
                "data/raw/zipcodes/postal_code_reference.csv o "
                "data/raw/zipcodes/zipcodes_rm.geojson."
            ),
        }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote {OUT_JSON.relative_to(REPO_ROOT)} ({payload['status']})")


if __name__ == "__main__":
    main()

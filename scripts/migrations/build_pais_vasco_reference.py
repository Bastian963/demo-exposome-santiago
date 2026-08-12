#!/usr/bin/env python3
"""Build the País Vasco spatial reference for pais_vasco_provincias.

Single source, no merge: the 3 NUTS3 provinces of the Basque Country
(Araba/Álava, Gipuzkoa, Bizkaia) from Eurostat GISCO's NUTS level-3
dataset, pre-filtered to NUTS_ID starting with "ES21".

Source:
- Eurostat GISCO NUTS level 3 (2024): downloaded as
  NUTS_RG_01M_2024_4326_LEVL_3.geojson (whole of Europe, ~27.6 MB) and
  filtered locally to ES21x. Eurostat/GISCO license, free reuse with
  attribution. See data/raw/gisco/nuts/2024/README.md for the exact
  download + filter steps.

Scope note: unlike santiago_communes/san_juan_departamentos, this study is
not driven by cohort residence (0 real Spain participants in the 2026-07
delivery) -- added by direct request. See
config/studies/pais_vasco_provincias.yaml for the full note.
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[2]

GISCO_NUTS3_PV = ROOT / "data" / "raw" / "gisco" / "nuts" / "2024" / "nuts3_pais_vasco.geojson"
TARGET_DIR = ROOT / "data" / "reference" / "es" / "pais_vasco" / "pais_vasco_provincias"


def _checksum(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main(force: bool) -> None:
    output = TARGET_DIR / "spatial_units.geojson"
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --force")

    gdf = gpd.read_file(GISCO_NUTS3_PV)
    if len(gdf) != 3:
        raise ValueError(f"Expected 3 País Vasco provinces, found {len(gdf)}")

    gdf["unit_id"] = gdf["NUTS_ID"].map(lambda code: f"pv_{code}")
    gdf["unit_name"] = gdf["NAME_LATN"]
    gdf["unit_type"] = "provincia"
    gdf["unit_source"] = "GISCO"
    gdf = gdf[["unit_id", "unit_name", "unit_type", "unit_source", "NUTS_ID", "NAME_LATN", "geometry"]]

    if gdf["unit_id"].duplicated().any():
        raise ValueError("Duplicate unit_id in País Vasco reference")
    if gdf["unit_name"].duplicated().any():
        dupes = gdf.loc[gdf["unit_name"].duplicated(keep=False), "unit_name"].tolist()
        raise ValueError(f"Duplicate unit_name in País Vasco reference: {dupes}")
    if not gdf.geometry.notna().all():
        raise ValueError("Null geometries in País Vasco reference")
    invalid = ~gdf.geometry.is_valid
    if bool(invalid.any()):
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].make_valid()

    bounds = gdf.total_bounds
    print(f"total_bounds (west,south,east,north): {bounds[0]:.4f}, {bounds[1]:.4f}, {bounds[2]:.4f}, {bounds[3]:.4f}")
    print(f"n provincias: {len(gdf)}")

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output, driver="GeoJSON")

    metadata = {
        "schema_version": 1,
        "study_id": "pais_vasco_provincias",
        "spatial_id": "unit_id (pv_<NUTS_ID>)",
        "source": str(GISCO_NUTS3_PV.relative_to(ROOT)),
        "source_sha256": _checksum(GISCO_NUTS3_PV),
        "unit_count": len(gdf),
        "total_bounds": bounds.tolist(),
    }
    (TARGET_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (TARGET_DIR / "README.md").write_text(
        "# País Vasco (provincias) spatial reference\n\n"
        "`spatial_units.geojson` covers the 3 NUTS3 provinces of the Basque "
        "Country (Eurostat GISCO): Araba/Álava, Gipuzkoa, Bizkaia. `unit_id` "
        "is `pv_<NUTS_ID>` (e.g. `pv_ES211`); `unit_name` is GISCO's own "
        "`NAME_LATN` spelling verbatim.\n",
        encoding="utf-8",
    )
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(force=args.force)

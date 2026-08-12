#!/usr/bin/env python3
"""Build the San Juan province spatial reference for san_juan_departamentos.

Single source, no merge (unlike buenos_aires_amba, which fuses GCBA comunas
with IGN partidos): the 19 departamentos of San Juan province from the IGN
`ign:departamento` layer, filtered by INDEC province prefix 70.

Source:
- IGN departamentos (San Juan province): downloaded via WFS from
  wms.ign.gob.ar, CQL_FILTER=in1 LIKE '70%' (in1 = 5-digit INDEC code,
  province prefix 70 = San Juan). CC-BY (IGN Argentina).
  See data/raw/ign/departamentos/v2024/README.md for the exact curl command.

Scope decision (whole province, not just Gran San Juan metro): the 2026-07
cohort delivery's 195 San Juan participants carry department-level `City`
values spanning ~13 of the 19 departments -- Gran San Juan (Capital,
Chimbas, Rawson, Rivadavia, Santa Lucía, Pocito) holds the bulk, but
Iglesia, Calingasta, Jáchal, Albardón, Angaco, Caucete and 9 de Julio are
also non-zero. A metro-only study would drop real cohort residents, so
this study covers the full province at department granularity.

Naming is source-faithful: unit_name uses IGN's own `nam` spelling verbatim
(accented). The raw cohort `City` column does not match this exactly
(observed variants: "Albardon"/"Albardón", "9 de julio"/"9 de Julio",
"Ullúm" vs IGN's "Ullum") -- that normalization belongs in whatever later
joins cohort rows to spatial_id, not in this reference file.
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[2]

IGN_DEPARTAMENTOS = ROOT / "data" / "raw" / "ign" / "departamentos" / "v2024" / "departamentos_san_juan.geojson"
TARGET_DIR = ROOT / "data" / "reference" / "ar" / "san_juan" / "san_juan_departamentos"


def _checksum(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main(force: bool) -> None:
    output = TARGET_DIR / "spatial_units.geojson"
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --force")

    gdf = gpd.read_file(IGN_DEPARTAMENTOS)
    if len(gdf) != 19:
        raise ValueError(f"Expected 19 San Juan departamentos, found {len(gdf)}")

    gdf["unit_id"] = gdf["in1"].map(lambda code: f"sj_{code}")
    gdf["unit_name"] = gdf["nam"]
    gdf["unit_type"] = "departamento"
    gdf["unit_source"] = "IGN"
    gdf = gdf[["unit_id", "unit_name", "unit_type", "unit_source", "in1", "nam", "fna", "gna", "geometry"]]

    if gdf["unit_id"].duplicated().any():
        raise ValueError("Duplicate unit_id in San Juan reference")
    if gdf["unit_name"].duplicated().any():
        dupes = gdf.loc[gdf["unit_name"].duplicated(keep=False), "unit_name"].tolist()
        raise ValueError(f"Duplicate unit_name in San Juan reference: {dupes}")
    if not gdf.geometry.notna().all():
        raise ValueError("Null geometries in San Juan reference")
    invalid = ~gdf.geometry.is_valid
    if bool(invalid.any()):
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].make_valid()

    bounds = gdf.total_bounds
    print(f"total_bounds (west,south,east,north): {bounds[0]:.4f}, {bounds[1]:.4f}, {bounds[2]:.4f}, {bounds[3]:.4f}")
    print(f"n departamentos: {len(gdf)}")

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output, driver="GeoJSON")

    metadata = {
        "schema_version": 1,
        "study_id": "san_juan_departamentos",
        "spatial_id": "unit_id (sj_<in1>)",
        "source": str(IGN_DEPARTAMENTOS.relative_to(ROOT)),
        "source_sha256": _checksum(IGN_DEPARTAMENTOS),
        "unit_count": len(gdf),
        "total_bounds": bounds.tolist(),
    }
    (TARGET_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (TARGET_DIR / "README.md").write_text(
        "# San Juan (province) spatial reference\n\n"
        "`spatial_units.geojson` covers the 19 departamentos of San Juan "
        "province (IGN `ign:departamento` layer, INDEC province prefix 70). "
        "`unit_id` is `sj_<in1>` (5-digit INDEC department code); `unit_name` "
        "is IGN's own `nam` spelling verbatim (accented, source-faithful).\n\n"
        "Known naming mismatch: the 2026-07 cohort delivery's `City` column "
        "does not match `nam` on exact string equality (observed variants: "
        "\"Albardon\"/\"Albardón\", \"9 de julio\"/\"9 de Julio\", \"Ullúm\" "
        "vs this file's \"Ullum\"). Normalize at join time, not here.\n",
        encoding="utf-8",
    )
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(force=args.force)

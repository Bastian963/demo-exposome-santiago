#!/usr/bin/env python3
"""Build the Catalunya spatial reference for cataluna_comarques.

Single source, no merge: the 43 comarques of Catalunya (42 official
comarques + Val d'Aran, treated by this source layer as an ordinary
comarca with no special case) from the ICGC `divisions_administratives`
WFS.

Source:
- ICGC comarques (Institut Cartogràfic i Geològic de Catalunya): downloaded
  via WFS from geoserveis.icgc.cat,
  typeName=divisions_administratives_wfs:divisions_administratives_comarques_5000,
  outputFormat=geojson. CC BY 4.0 (ICGC). See
  data/raw/icgc/divisions_administratives/2026/README.md for the exact
  curl command.

Scope note: unlike santiago_communes/san_juan_departamentos, this study is
not driven by cohort residence (0 real Spain participants in the 2026-07
delivery) -- added by direct request. See
config/studies/cataluna_comarques.yaml for the full note.
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[2]

ICGC_COMARQUES = ROOT / "data" / "raw" / "icgc" / "divisions_administratives" / "2026" / "comarques.geojson"
TARGET_DIR = ROOT / "data" / "reference" / "es" / "cataluna" / "cataluna_comarques"

# Douglas-Peucker tolerance in metres, applied in the local UTM CRS. See the
# rationale block in main() before changing it.
SIMPLIFY_TOLERANCE_M = 10.0


def _checksum(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def main(force: bool) -> None:
    output = TARGET_DIR / "spatial_units.geojson"
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --force")

    gdf = gpd.read_file(ICGC_COMARQUES)
    if len(gdf) != 43:
        raise ValueError(f"Expected 43 Catalunya comarques, found {len(gdf)}")

    gdf["unit_id"] = gdf["CODICOMAR"].map(lambda code: f"cat_{code}")
    gdf["unit_name"] = gdf["NOMCOMAR"]
    gdf["unit_type"] = "comarca"
    gdf["unit_source"] = "ICGC"
    gdf = gdf[["unit_id", "unit_name", "unit_type", "unit_source", "CODICOMAR", "NOMCOMAR", "geometry"]]

    if gdf["unit_id"].duplicated().any():
        raise ValueError("Duplicate unit_id in Catalunya reference")
    if gdf["unit_name"].duplicated().any():
        dupes = gdf.loc[gdf["unit_name"].duplicated(keep=False), "unit_name"].tolist()
        raise ValueError(f"Duplicate unit_name in Catalunya reference: {dupes}")
    if not gdf.geometry.notna().all():
        raise ValueError("Null geometries in Catalunya reference")
    invalid = ~gdf.geometry.is_valid
    if bool(invalid.any()):
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].make_valid()

    # ICGC ships this layer as 1:5,000 cartography: 702,080 vertices across the
    # 43 comarques (16,327 per unit, a 19 MB GeoJSON). That is two orders of
    # magnitude finer than anything the exposome layers need -- san_juan
    # runs on 2,102 vertices/unit and santiago on a 1.3 MB file -- and it
    # breaks the pipeline twice over: boundaries.get_communes copies the file
    # into every layer's cache dir (14 x 20 MB inside Dropbox, ~3 min per
    # layer of pure I/O), and a GEE reduceRegions over 700k vertices does not
    # come back.
    #
    # This is NOT a resolution downgrade in the sense the repo forbids: no
    # product raster is coarsened, and aggregation still happens at each
    # provider's native grid. It only stops carrying survey-grade boundary
    # cartography into zonal statistics. At 10 m the tolerance is 111x
    # smaller than the coarsest pixel we aggregate (1113 m ACAG PM2.5) and
    # the worst-affected comarca changes area by 0.0154% (mean 0.0026%),
    # while vertices drop to 9.4% of the original.
    #
    # simplify(preserve_topology=True) is per-geometry, so shared borders are
    # simplified independently and can leave slivers on the order of the
    # tolerance. At 10 m against comarques tens of km across that is far
    # below any exposome signal; do not raise the tolerance without
    # re-measuring the area deltas above.
    metric = gdf.estimate_utm_crs()
    geographic = gdf.crs
    gdf = gdf.to_crs(metric)
    gdf["geometry"] = gdf.geometry.simplify(SIMPLIFY_TOLERANCE_M, preserve_topology=True)
    invalid = ~gdf.geometry.is_valid
    if bool(invalid.any()):
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].make_valid()
    gdf = gdf.to_crs(geographic)
    if not gdf.geometry.notna().all():
        raise ValueError("Simplification produced null geometries")
    if len(gdf) != 43:
        raise ValueError(f"Simplification changed the unit count: {len(gdf)}")

    bounds = gdf.total_bounds
    print(f"total_bounds (west,south,east,north): {bounds[0]:.4f}, {bounds[1]:.4f}, {bounds[2]:.4f}, {bounds[3]:.4f}")
    print(f"n comarques: {len(gdf)}")

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output, driver="GeoJSON")

    metadata = {
        "schema_version": 1,
        "study_id": "cataluna_comarques",
        "spatial_id": "unit_id (cat_<CODICOMAR>)",
        "source": str(ICGC_COMARQUES.relative_to(ROOT)),
        "source_sha256": _checksum(ICGC_COMARQUES),
        "unit_count": len(gdf),
        "total_bounds": bounds.tolist(),
        "simplify_tolerance_m": SIMPLIFY_TOLERANCE_M,
        "simplify_crs": str(metric),
        "simplify_note": (
            "Douglas-Peucker in the local UTM CRS, applied to the ICGC 1:5,000 "
            "comarques so zonal statistics stop carrying survey-grade boundary "
            "cartography. No product raster is coarsened."
        ),
    }
    (TARGET_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (TARGET_DIR / "README.md").write_text(
        "# Catalunya (comarques) spatial reference\n\n"
        "`spatial_units.geojson` covers the 43 comarques of Catalunya (ICGC "
        "`divisions_administratives_comarques_5000` layer -- 42 official "
        "comarques plus Val d'Aran, which this source treats as an ordinary "
        "comarca). `unit_id` is `cat_<CODICOMAR>`; `unit_name` is ICGC's own "
        "`NOMCOMAR` spelling verbatim (accented, source-faithful).\n",
        encoding="utf-8",
    )
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(force=args.force)

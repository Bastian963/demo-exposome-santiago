#!/usr/bin/env python3
"""Build the merged CABA + AMBA spatial reference for buenos_aires_amba.

Merges the GCBA comunas (15 units, CABA) with the AMBA partidos of Buenos
Aires province (40 units, IGN departamento layer) into a single unified
spatial_units.geojson with 55 features. Also writes a `display_name` column
onto the standalone CABA reference (buenos_aires_comunas) so both studies
share the same "Comuna N · barrios" composite naming rule.

Sources:
- GCBA comunas: data/raw/ar/buenos_aires/buenos_aires_comunas/comunas.geojson
  (data.buenosaires.gob.ar/dataset/comunas, CC-BY-2.5-AR)
- IGN departamentos (Buenos Aires province partidos): downloaded via WFS
  from wms.ign.gob.ar, CQL_FILTER=in1 LIKE '06%' (in1 = 5-digit INDEC code,
  province prefix 06 = Buenos Aires). CC-BY (IGN Argentina).

Naming is source-faithful: comuna names use GCBA's own `barrios` spelling
verbatim, partido names use IGN's own `nam` spelling verbatim (both may
carry accents; both render fine in the webapp's VT323 body font).

Known limitation (v1, accepted): GCBA and IGN geometries are digitized
independently and have small overlap/gap slivers along the CABA/AMBA
boundary (Av. General Paz, Riachuelo). Zonal statistics tolerate this;
no clipping is performed.
"""
from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

GCBA_COMUNAS = ROOT / "data" / "raw" / "ar" / "buenos_aires" / "buenos_aires_comunas" / "comunas.geojson"
IGN_PARTIDOS = ROOT / "data" / "raw" / "ign" / "departamentos" / "v2024" / "departamentos_buenos_aires.geojson"

AMBA_TARGET_DIR = ROOT / "data" / "reference" / "ar" / "buenos_aires_amba" / "buenos_aires_amba"
CABA_TARGET = ROOT / "data" / "reference" / "ar" / "buenos_aires" / "buenos_aires_comunas" / "spatial_units.geojson"

# 40 AMBA partidos (INDEC "Partido" units of Buenos Aires province), matched
# by `nam` against the IGN departamento layer. Includes Gran La Plata
# (La Plata, Berisso, Ensenada) deliberately -- see plan context.
AMBA_PARTIDOS = [
    # 24 GBA partidos
    "Almirante Brown", "Avellaneda", "Berazategui", "Esteban Echeverría",
    "Ezeiza", "Florencio Varela", "General San Martín", "Hurlingham",
    "Ituzaingó", "José C. Paz", "La Matanza", "Lanús", "Lomas de Zamora",
    "Malvinas Argentinas", "Merlo", "Moreno", "Morón", "Quilmes",
    "San Fernando", "San Isidro", "San Miguel", "Tigre", "Tres de Febrero",
    "Vicente López",
    # 16 outer-ring AMBA partidos (incl. Gran La Plata)
    "Berisso", "Brandsen", "Campana", "Cañuelas", "Ensenada", "Escobar",
    "Exaltación de la Cruz", "General Las Heras", "General Rodríguez",
    "La Plata", "Luján", "Marcos Paz", "Pilar", "Presidente Perón",
    "San Vicente", "Zárate",
]


def _composite_comuna_name(comuna_num: int, barrios: str) -> str:
    parts = [b.strip() for b in barrios.split(",") if b.strip()]
    if len(parts) <= 2:
        return f"Comuna {comuna_num} · {', '.join(parts)}"
    remaining = len(parts) - 2
    return f"Comuna {comuna_num} · {parts[0]}, {parts[1]} +{remaining}"


def _checksum(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _load_comunas() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(GCBA_COMUNAS)
    if len(gdf) != 15:
        raise ValueError(f"Expected 15 GCBA comunas, found {len(gdf)}")
    gdf["display_name"] = gdf.apply(
        lambda row: _composite_comuna_name(int(row["comuna"]), str(row["barrios"])), axis=1
    )
    gdf["unit_id"] = gdf["comuna"].astype(int).map(lambda n: f"caba_comuna_{n:02d}")
    gdf["unit_name"] = gdf["display_name"]
    gdf["unit_type"] = "comuna"
    gdf["unit_source"] = "GCBA"
    return gdf[["unit_id", "unit_name", "unit_type", "unit_source", "comuna", "nombre", "barrios", "geometry"]]


def _load_partidos() -> gpd.GeoDataFrame:
    gdf = gpd.read_file(IGN_PARTIDOS)
    gdf = gdf[gdf["nam"].isin(AMBA_PARTIDOS)].copy()
    matched = set(gdf["nam"])
    missing = sorted(set(AMBA_PARTIDOS) - matched)
    if missing:
        raise ValueError(f"AMBA partidos not found in IGN layer: {missing}")
    if len(gdf) != 40:
        raise ValueError(f"Expected 40 AMBA partidos, matched {len(gdf)}")
    gdf["unit_id"] = gdf["in1"].map(lambda code: f"pba_{code}")
    # Source-faithful naming: partido names are IGN's `nam` verbatim
    # (accented -- "José C. Paz", "Lanús", "Morón"). Comuna names are GCBA's
    # `barrios` verbatim too (see _composite_comuna_name), which happens to
    # be mostly unaccented except letters like "ñ". Both render in VT323
    # (webapp/src/style.css .pixel-popup-name / .commune-name), which
    # handles accents fine -- unlike Press Start 2P (machine-chrome labels
    # only), so there is no reason to strip either source's own spelling.
    gdf["unit_name"] = gdf["nam"]
    gdf["unit_type"] = "partido"
    gdf["unit_source"] = "IGN"
    return gdf[["unit_id", "unit_name", "unit_type", "unit_source", "in1", "nam", "fna", "gna", "geometry"]]


def main(force: bool) -> None:
    output = AMBA_TARGET_DIR / "spatial_units.geojson"
    if output.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {output}; pass --force")

    comunas = _load_comunas()
    partidos = _load_partidos()
    if comunas.crs != partidos.crs:
        partidos = partidos.to_crs(comunas.crs)

    merged = pd.concat([comunas, partidos], ignore_index=True)
    merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=comunas.crs)

    if len(merged) != 55:
        raise ValueError(f"Expected 55 merged units, found {len(merged)}")
    if merged["unit_id"].duplicated().any():
        raise ValueError("Duplicate unit_id in merged reference")
    if merged["unit_name"].duplicated().any():
        dupes = merged.loc[merged["unit_name"].duplicated(keep=False), "unit_name"].tolist()
        raise ValueError(f"Duplicate unit_name in merged reference: {dupes}")
    if not merged.geometry.notna().all():
        raise ValueError("Null geometries in merged reference")
    invalid = ~merged.geometry.is_valid
    if bool(invalid.any()):
        merged.loc[invalid, "geometry"] = merged.loc[invalid, "geometry"].make_valid()

    bounds = merged.total_bounds
    print(f"total_bounds (west,south,east,north): {bounds[0]:.4f}, {bounds[1]:.4f}, {bounds[2]:.4f}, {bounds[3]:.4f}")
    print(f"n comunas: {len(comunas)}, n partidos: {len(partidos)}, total: {len(merged)}")

    AMBA_TARGET_DIR.mkdir(parents=True, exist_ok=True)
    merged.to_file(output, driver="GeoJSON")

    metadata = {
        "schema_version": 1,
        "study_id": "buenos_aires_amba",
        "spatial_id": "unit_id (caba_comuna_NN or pba_<in1>)",
        "source_comunas": str(GCBA_COMUNAS.relative_to(ROOT)),
        "source_comunas_sha256": _checksum(GCBA_COMUNAS),
        "source_partidos": str(IGN_PARTIDOS.relative_to(ROOT)),
        "source_partidos_sha256": _checksum(IGN_PARTIDOS),
        "unit_count": len(merged),
        "n_comunas": len(comunas),
        "n_partidos": len(partidos),
        "total_bounds": bounds.tolist(),
    }
    (AMBA_TARGET_DIR / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (AMBA_TARGET_DIR / "README.md").write_text(
        "# Buenos Aires AMBA spatial reference\n\n"
        "`spatial_units.geojson` merges the 15 CABA comunas (GCBA) with the "
        "40 AMBA partidos of Buenos Aires province (IGN), including Gran La "
        "Plata (La Plata, Berisso, Ensenada). `unit_id` disambiguates the two "
        "admin levels (`caba_comuna_NN` / `pba_<in1>`); `unit_name` is the "
        "display name (comunas use the \"Comuna N · barrios\" composite, "
        "partidos use IGN's own spelling). Names are source-faithful (not "
        "re-accented or stripped). Known limitation: GCBA/IGN "
        "geometries have small overlap/gap slivers along the CABA/AMBA "
        "boundary; not clipped in v1.\n",
        encoding="utf-8",
    )
    print(output.relative_to(ROOT))


def apply_caba_display_names(force: bool = False) -> None:
    """Rewrite the standalone CABA reference with the same display_name rule."""
    if not CABA_TARGET.exists():
        raise FileNotFoundError(CABA_TARGET)
    gdf = gpd.read_file(CABA_TARGET)
    if "display_name" in gdf.columns and not force:
        raise FileExistsError(f"{CABA_TARGET} already has display_name; pass --force")
    gdf["display_name"] = gdf.apply(
        lambda row: _composite_comuna_name(int(row["comuna"]), str(row["barrios"])), axis=1
    )
    gdf.to_file(CABA_TARGET, driver="GeoJSON")
    print(CABA_TARGET.relative_to(ROOT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    main(force=args.force)
    apply_caba_display_names(force=args.force)

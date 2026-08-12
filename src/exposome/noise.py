"""Traffic noise exposure layer — Mapa de Ruido Gran Santiago Urbano 2023.

Source: Ministerio del Medio Ambiente, Departamento Ruido Lumínica y Olores,
April 2024. Tabular results extracted from the published Minuta PDF.

Thresholds follow OECD guidelines:
  Ld > 65 dBA  — daytime period  (07:00–23:00)
  Ln > 55 dBA  — nighttime period (23:00–07:00)

Coverage: 35 urban communes in the Gran Santiago Urbano (GSU).
The remaining 17 peri-urban/rural RM communes are outside the modelled area
and receive 0 for all exposure columns plus noise_in_gsu_map = 0.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd

try:
    from .demography import normalize_comuna_name
except ImportError:
    # Running as a script directly (python src/exposome/noise.py)
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "src"))
    from exposome.demography import normalize_comuna_name  # type: ignore[no-redef]

# Tuple layout: (ld_pop, ld_pct, ln_pop, ln_pct)
# ld = daytime Leq > 65 dBA; ln = nighttime Leq > 55 dBA
# Population reference: INE ACON 2022; modelling year: 2023
_GSU_NOISE_RAW: dict[str, tuple[int, int, int, int]] = {
    "SANTIAGO":            (97936, 15, 114922, 17),
    "LAS CONDES":          (74295, 19,  60624, 16),
    "MAIPÚ":               (59122, 12,  73771, 14),
    "ÑUÑOA":               (55512, 16,  46794, 14),
    "LA FLORIDA":          (51837, 13,  60591, 15),
    "PUENTE ALTO":         (47833,  9,  54149, 10),
    "PROVIDENCIA":         (36977, 16,  32715, 14),
    "ESTACIÓN CENTRAL":    (32796, 15,  42805, 20),
    "VITACURA":            (25211, 24,  29357, 28),
    "MACUL":               (24943, 17,  29257, 20),
    "SAN BERNARDO":        (23799,  8,  38681, 13),
    "PUDAHUEL":            (22418, 10,  39732, 18),
    "RENCA":               (20556, 15,  35899, 26),
    "PEÑALOLÉN":           (20179,  9,  24912, 11),
    "LO BARNECHEA":        (19729, 20,  19144, 19),
    "CERRILLOS":           (18742, 21,  27300, 31),
    "QUILICURA":           (17969,  9,  28052, 14),
    "LO ESPEJO":           (16500, 20,  23884, 29),
    "CONCHALÍ":            (14799, 13,  20603, 18),
    "LA REINA":            (14225, 15,   9092, 10),
    "SAN MIGUEL":          (13137,  7,  18008, 10),
    "INDEPENDENCIA":       (13097, 10,  18307, 13),
    "RECOLETA":            (12253,  8,  15863, 10),
    "HUECHURABA":          (11865, 13,  16185, 17),
    "QUINTA NORMAL":       (11857,  9,  17234, 13),
    "SAN JOAQUÍN":         (11498, 11,  15627, 15),
    "LA GRANJA":           (11320, 10,  18587, 17),
    "LA CISTERNA":         (11156, 10,  16907, 15),
    "CERRO NAVIA":         (11073,  9,  16837, 14),
    "LA PINTANA":          ( 9951,  6,  14260,  9),
    "PEDRO AGUIRRE CERDA": ( 8226,  9,  13927, 15),
    "LO PRADO":            ( 7651,  8,  11619, 13),
    "EL BOSQUE":           ( 7034,  5,  10913,  7),
    "SAN RAMÓN":           ( 7028, 10,  10865, 15),
    "PADRE HURTADO":       ( 1313,  2,   1435,  2),
}

_EXPECTED_COMMUNES = 52
_GSU_POP_TOTAL = 6_910_822


def _noise_dataframe() -> pd.DataFrame:
    """Build a 35-row DataFrame from the hardcoded GSU table."""
    rows = []
    for raw_name, (ld_pop, ld_pct, ln_pop, ln_pct) in _GSU_NOISE_RAW.items():
        rows.append(
            {
                "name_raw": raw_name,
                "noise_ld_pop_exposed": ld_pop,
                "noise_ld_pct_exposed": float(ld_pct),
                "noise_ln_pop_exposed": ln_pop,
                "noise_ln_pct_exposed": float(ln_pct),
            }
        )
    df = pd.DataFrame(rows)
    df["name"] = normalize_comuna_name(df["name_raw"])
    return df.drop(columns="name_raw")


def _load_boundaries(out_dir: Path) -> gpd.GeoDataFrame:
    """Load commune geometries from an existing processed GeoJSON (fast path)."""
    candidates = [
        "socioeconomic_exposome_rm_santiago.geojson",
        "climate_heat_exposome_rm_santiago.geojson",
        "santiago_air_quality_satellite_2024.geojson",
        "santiago_alan_viirs_2024.geojson",
    ]
    for name in candidates:
        p = out_dir / name
        if p.exists():
            gdf = gpd.read_file(p)
            if "name" in gdf.columns and len(gdf) == _EXPECTED_COMMUNES:
                return gdf[["name", "geometry"]].copy()

    # Fallback: query OSM (requires network; avoids needing GEE)
    try:
        from . import boundaries
        from . import config as _config
    except ImportError:
        import exposome.boundaries as boundaries  # type: ignore[no-redef]
        import exposome.config as _config  # type: ignore[no-redef]

    cfg = _config.load_config("santiago")
    return boundaries.get_communes(cfg)[["name", "geometry"]]


def build_noise_layer(
    city: str = "santiago",
    out_dir: Path = Path("data/processed"),
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Build the traffic-noise exposome layer and write CSV/GeoJSON/metadata.

    Returns (df, gdf) — the plain DataFrame and the geometry-enabled version.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    noise_df = _noise_dataframe()
    boundaries_gdf = _load_boundaries(out_dir)

    # Left-merge so all 52 communes appear; unmatched get NaN → fill with 0.
    merged = boundaries_gdf.merge(noise_df, on="name", how="left")

    noise_cols = [
        "noise_ld_pop_exposed",
        "noise_ld_pct_exposed",
        "noise_ln_pop_exposed",
        "noise_ln_pct_exposed",
    ]
    merged["noise_in_gsu_map"] = merged["noise_ld_pop_exposed"].notna().astype(int)
    merged[noise_cols] = merged[noise_cols].fillna(0)
    merged["noise_ld_pop_exposed"] = merged["noise_ld_pop_exposed"].astype(int)
    merged["noise_ln_pop_exposed"] = merged["noise_ln_pop_exposed"].astype(int)
    merged["noise_combined_pct"] = (
        (merged["noise_ld_pct_exposed"] + merged["noise_ln_pct_exposed"]) / 2
    ).round(1)

    ordered_cols = [
        "name",
        "noise_ld_pop_exposed",
        "noise_ld_pct_exposed",
        "noise_ln_pop_exposed",
        "noise_ln_pct_exposed",
        "noise_combined_pct",
        "noise_in_gsu_map",
    ]
    df = merged[ordered_cols].sort_values("name").reset_index(drop=True)
    gdf = merged[ordered_cols + ["geometry"]].sort_values("name").reset_index(drop=True)
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=boundaries_gdf.crs)

    n_matched = int(df["noise_in_gsu_map"].sum())
    if n_matched != len(_GSU_NOISE_RAW):
        unmatched = set(normalize_comuna_name(pd.Series(list(_GSU_NOISE_RAW.keys())))) - set(df.loc[df["noise_in_gsu_map"] == 1, "name"])
        raise ValueError(
            f"Matched {n_matched}/{len(_GSU_NOISE_RAW)} GSU communes. "
            f"Unmatched names: {sorted(unmatched)}"
        )
    if len(df) != _EXPECTED_COMMUNES:
        raise ValueError(f"Expected {_EXPECTED_COMMUNES} communes, got {len(df)}")

    csv_out = out_dir / f"{city}_noise_mma_2023.csv"
    geojson_out = out_dir / f"{city}_noise_mma_2023.geojson"
    meta_out = out_dir / f"{city}_noise_mma_2023_metadata.json"

    df.to_csv(csv_out, index=False)
    gdf.to_file(geojson_out, driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "source": "MMA 2024 — Minuta Mapa de Ruido Gran Santiago Urbano 2023",
        "year": 2023,
        "method": (
            "Traffic noise modelling (13 590 km of road network) — "
            "vehicle count data from cameras, toll portals and Sistema RED; "
            "noise levels computed for 792 km² across 35 urban communes (GSU). "
            "Exposure counts = population in cells above OECD threshold."
        ),
        "thresholds_dba": {"day_Ld": 65, "night_Ln": 55},
        "periods": {"day": "07:00–23:00", "night": "23:00–07:00"},
        "population_reference": "INE ACON 2022",
        "n_communes_total": len(df),
        "n_communes_in_gsu_map": n_matched,
        "gsu_population_total": _GSU_POP_TOTAL,
        "columns": ordered_cols,
        "note": (
            "Communes outside the GSU urban perimeter have noise_in_gsu_map=0 "
            "and all noise exposure values set to 0 (not modelled)."
        ),
    }
    meta_out.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(
        f"Wrote {csv_out.name}: {len(df)} communes "
        f"({n_matched} in GSU map, {len(df) - n_matched} set to 0)"
    )
    print(f"Wrote {geojson_out.name}")
    print(f"Wrote {meta_out.name}")

    return df, gdf


if __name__ == "__main__":
    import sys
    from pathlib import Path as _Path

    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    build_noise_layer()

"""Export a slim master GeoJSON for the webapp.

Reads ``data/processed/santiago_exposome_master.geojson`` and writes
``webapp/public/data/master.geojson`` with:

- Geometry simplified with a small tolerance (~10m).
- A ``slug`` property added to every feature (URL-safe lowercase,
  underscores for spaces, ASCII only).
- Numeric properties rounded to 3 decimals.
- A curated set of columns (PM2.5 + cluster + ebi + lisa for v0.5).

Also exports per-year annual GeoJSONs from
``data/processed/santiago_pm25_acag_{year}.csv`` to
``webapp/public/data/annual/pm25_{year}.geojson``.

This file is loaded at startup by the webapp. Target size: < 200 KB.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd
import pandas as pd

SRC = REPO_ROOT / "data" / "processed" / "santiago_exposome_master.geojson"
DST = REPO_ROOT / "webapp" / "public" / "data" / "master.geojson"
DST.parent.mkdir(parents=True, exist_ok=True)
ANNUAL_DIR = REPO_ROOT / "webapp" / "public" / "data" / "annual"

# Annual PM2.5 sources (one CSV per year 2015-2022).
ANNUAL_SOURCES = [
    (2015, REPO_ROOT / "data" / "processed" / "santiago_pm25_acag_2015.csv"),
    (2016, REPO_ROOT / "data" / "processed" / "santiago_pm25_acag_2016.csv"),
    (2017, REPO_ROOT / "data" / "processed" / "santiago_pm25_acag_2017.csv"),
    (2018, REPO_ROOT / "data" / "processed" / "santiago_pm25_acag_2018.csv"),
    (2019, REPO_ROOT / "data" / "processed" / "santiago_pm25_acag_2019.csv"),
    (2020, REPO_ROOT / "data" / "processed" / "santiago_pm25_acag_2020.csv"),
    (2021, REPO_ROOT / "data" / "processed" / "santiago_pm25_acag_2021.csv"),
    (2022, REPO_ROOT / "data" / "processed" / "santiago_pm25_acag_2022.csv"),
]

# Columns to keep in the slim master (in addition to name, slug, geometry).
# v0.5: only what's needed for the PM2.5 choropleth + EBI + cluster + LISA.
SLIM_COLS = [
    "name",
    "pm25_mean",
    "no2_surface_ug_m3",
    "o3_mean",
    "alan_radiance_mean",
    "heat_exposure_index",
    "summer_tmax_mean_c",
    "hot_days_30c",
    "tropical_nights_20c",
    "urban_heat_anomaly_c",
    "precip_extremes_index",
    "precip_annual_mean_mm",
    "precip_cdd_days",
    "precip_heavy_days_10mm",
    "green_cover_pct_ndvi",
    "green_total_pct",
    "tree_pct",
    "canopy_cover_pct",
    "canopy_mean_height_m",
    "green_km2",
    "nse_index",
    "pobreza_pct",
    "hacinamiento_phh",
    "walk_index",
    "transit_index",
    "food_index",
    "food_healthy_density",
    "food_n_supermarket",
    "food_mean_dist_supermarket_m",
    "food_insec_2020",
    "food_insec_2022",
    "food_insec_sae_type_2022",
    "health_n_primary_care",
    "hm_index",
    "n_sources",
    "noise_combined_pct",
    "noise_in_gsu_map",
    "social_index",
    "wind_calm_pct",
    "fire_burned_pct_mean_annual",
    "pm25_std",
    "nse_quintil",
    # Per-year vintages for the webapp year slider (palette.json
    # year_columns). Heat 2024 is the un-suffixed canonical column above.
    *[
        f"{metric}_{year}"
        for metric in ("summer_tmax_mean_c", "hot_days_30c", "tropical_nights_20c")
        for year in range(2015, 2024)
    ],
    *[
        f"{stem}_{year}"
        for stem in ("precip_annual_mm", "precip_cdd_days", "precip_heavy_days_10mm")
        for year in range(2015, 2025)
    ],
    # Official MDSF poverty SAE, per-year (palette.json year_columns for
    # poverty_income / poverty_multi); CI bounds stay profile-only.
    "pobreza_ing_2017", "pobreza_ing_2020", "pobreza_ing_2022", "pobreza_ing_2024",
    "pobreza_ing_sae_type_2024",
    "pobreza_multi_2017", "pobreza_multi_2022", "pobreza_multi_2024",
    "pobreza_multi_sae_type_2024",
]


def slugify(s: str) -> str:
    """Convert 'Ñuñoa' -> 'nunoa', 'Las Condes' -> 'las_condes'."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace(" ", "_").replace("-", "_")
    out = []
    for c in s:
        if c.isalnum() or c == "_":
            out.append(c)
    return "".join(out).strip("_") or "unknown"


def round_floats(obj, decimals: int = 3) -> object:
    """Recursively round floats to N decimals in JSON-like structures."""
    if isinstance(obj, float):
        if obj != obj:  # NaN
            return None
        return round(obj, decimals)
    if isinstance(obj, dict):
        return {k: round_floats(v, decimals) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_floats(v, decimals) for v in obj]
    return obj


def _build_features(gdf: gpd.GeoDataFrame) -> list:
    """Build the simplified feature list with slug + geometry."""
    gdf = gdf.copy()
    gdf["slug"] = gdf["name"].apply(slugify)
    keep = [c for c in SLIM_COLS if c in gdf.columns] + ["slug", "geometry"]
    drop = [c for c in gdf.columns if c not in keep]
    gdf = gdf.drop(columns=drop)
    gdf = gdf.to_crs("EPSG:32719")
    gdf["geometry"] = gdf.geometry.simplify(10, preserve_topology=True)
    gdf = gdf.to_crs("EPSG:4326")
    geojson = json.loads(gdf.to_json())
    geojson = round_floats(geojson, decimals=3)
    return geojson["features"]


def _write_geojson(path: Path, features: list, extra_meta: dict | None = None) -> None:
    """Write a FeatureCollection GeoJSON with optional top-level metadata."""
    fc = {
        "type": "FeatureCollection",
        "features": features,
    }
    if extra_meta:
        fc.update(extra_meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, separators=(",", ":"))


def main() -> None:
    if not SRC.exists():
        raise FileNotFoundError(
            f"Source master not found: {SRC}. "
            "Run scripts/build_master_exposome.py first."
        )
    print(f"Reading {SRC.name}...")
    gdf = gpd.read_file(SRC)
    print(f"  {len(gdf)} features, {len(gdf.columns)} columns")

    features = _build_features(gdf)
    print(f"  Kept {len(features[0]['properties']) if features else 0} data columns + geometry")

    # Write multi-year average.
    _write_geojson(DST, features, {
        "exposome": "pm25",
        "period": "2015-2022 (annual average)",
        "n_communes": len(features),
    })
    size_kb = DST.stat().st_size / 1024
    print(f"  Wrote: {DST.relative_to(REPO_ROOT)} ({size_kb:.1f} KB)")

    # Write per-year annual GeoJSONs (PM2.5 only, same geometry).
    print("\nAnnual PM2.5 exports:")
    annual_count = 0
    for year, src in ANNUAL_SOURCES:
        if not src.exists():
            print(f"  SKIP {year}: {src.relative_to(REPO_ROOT)} not found")
            continue
        # Read annual CSV and merge with master geometry by name.
        ann = pd.read_csv(src)
        if "name" not in ann.columns:
            print(f"  SKIP {year}: no 'name' column in {src.name}")
            continue
        # Build a per-year gdf with only name + pm25_mean.
        ann_min = ann[["name"]].copy()
        # Find the PM2.5 value column (year-specific or generic).
        pm25_col = "pm25_mean" if "pm25_mean" in ann.columns else (
            [c for c in ann.columns if c.startswith("pm25_") and c != "pm25_std"] + [None]
        )[0]
        if not pm25_col or pm25_col not in ann.columns:
            print(f"  SKIP {year}: no PM2.5 column in {src.name}")
            continue
        ann_min["pm25_mean"] = ann[pm25_col]
        # Merge with master geometry (by name).
        ann_gdf = gdf[["name", "geometry"]].merge(ann_min, on="name", how="left")
        if ann_gdf["pm25_mean"].isna().any():
            n_missing = int(ann_gdf["pm25_mean"].isna().sum())
            print(f"  WARN {year}: {n_missing} communes have no PM2.5 value")
        ann_features = _build_features(ann_gdf)
        out_path = ANNUAL_DIR / f"pm25_{year}.geojson"
        _write_geojson(out_path, ann_features, {
            "exposome": "pm25",
            "period": f"{year} (annual)",
            "year": year,
            "n_communes": len(ann_features),
        })
        size_kb = out_path.stat().st_size / 1024
        print(f"  Wrote: {out_path.relative_to(REPO_ROOT)} ({size_kb:.1f} KB)")
        annual_count += 1
    print(f"\nDone. {annual_count} annual files written.")


if __name__ == "__main__":
    main()

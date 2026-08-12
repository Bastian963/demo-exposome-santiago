"""Fetch a historical (pre-mortality-window) chronic PM2.5 layer (Paso 2).

The production PM2.5 layer (config/cities/santiago.yaml `pm25:` block) covers
2015-2022, which OVERLAPS the DEIS mortality window (2018-2022) -- not a valid
"exposure before outcome" design. ACAG/van Donkelaar (GEE collection
projects/sat-io/open-datasets/GLOBAL-SATELLITE-PM25/ANNUAL) provides annual
means back to 2000, so we can build a genuine antecedent cumulative-exposure
window (2000-2017) that precedes the mortality window entirely.

This script does NOT modify the live pm25 config on disk -- it overrides the
window in an in-memory copy of the config and reuses the existing, tested
exposome.pm25 fetch functions, writing to a distinctly-named output so the
production PM2.5 layer (and anything downstream of it, e.g. the master table)
is untouched.
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402

from exposome import boundaries, config, gee  # noqa: E402
from exposome.pm25 import fetch_pm25, fetch_pop_weighted_pm25  # noqa: E402

CITY = "santiago"
CACHE_DIR = REPO_ROOT / "cache"
OUT_DIR = REPO_ROOT / "data" / "processed"

# Antecedent window: ends strictly before the mortality window starts (2018).
HIST_YEARS = list(range(2000, 2018))
HIST_START = "2000-01-01"
HIST_END = "2018-01-01"  # exclusive upper bound


def main() -> None:
    cfg = config.load_config(CITY)
    hist_cfg = copy.deepcopy(cfg)
    hist_cfg["pm25"]["years"] = HIST_YEARS
    hist_cfg["pm25"]["start_date"] = HIST_START
    hist_cfg["pm25"]["end_date"] = HIST_END

    gee.init_gee()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    window = f"{HIST_YEARS[0]}_{HIST_YEARS[-1]}"
    boundaries_cache = CACHE_DIR / f"{CITY}_communes.geojson"
    gdf_comm = boundaries.get_communes(hist_cfg, cache_path=boundaries_cache)
    regions_fc = gee.gdf_to_feature_collection(gdf_comm)

    print(f"Fetching ACAG PM2.5 for {HIST_START}..{HIST_END} ({len(HIST_YEARS)}y window)...")
    pm_csv = CACHE_DIR / f"{CITY}_pm25_acag_{window}.csv"
    if pm_csv.exists():
        df_pm = pd.read_csv(pm_csv)
    else:
        df_pm = fetch_pm25(hist_cfg, regions_fc, start=HIST_START, end=HIST_END)
        df_pm.to_csv(pm_csv, index=False)

    popw_csv = CACHE_DIR / f"{CITY}_pm25_acag_popweighted_{window}.csv"
    if popw_csv.exists():
        df_popw = pd.read_csv(popw_csv)
    else:
        df_popw = fetch_pop_weighted_pm25(hist_cfg, regions_fc, start=HIST_START, end=HIST_END)
        df_popw.to_csv(popw_csv, index=False)

    df = gdf_comm[["name", "area_km2"]].copy()
    df = df.merge(df_pm, on="name", how="left")
    df = df.merge(df_popw, on="name", how="left")
    if df["pm25_pop_weighted"].isna().any():
        missing = df.loc[df["pm25_pop_weighted"].isna(), "name"].tolist()
        df["pm25_pop_weighted"] = df["pm25_pop_weighted"].fillna(df["pm25_mean"])
        print(f"Warning: filled pop-weighted PM2.5 for {missing} with area mean")

    who_pm25 = cfg["air_quality"]["who_guidelines"]["pm25"]
    df["pm25_who_ratio"] = (df["pm25_mean"] / who_pm25).round(2)
    df["pm25_mean"] = df["pm25_mean"].round(2)
    df["pm25_pop_weighted"] = df["pm25_pop_weighted"].round(2)

    n_expected = cfg["expected_communes"]
    if len(df) != n_expected:
        raise ValueError(f"Expected {n_expected} rows, got {len(df)}")
    if df["name"].duplicated().any():
        raise ValueError("Duplicate commune names")
    if df.isna().any().any():
        missing = df.columns[df.isna().any()].tolist()
        raise ValueError(f"Missing values in: {missing}")

    gdf = gdf_comm[["name", "geometry"]].merge(df, on="name", how="right")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    base_name = f"{CITY}_pm25_acag_{window}"
    df.to_csv(OUT_DIR / f"{base_name}.csv", index=False)
    gdf.to_file(OUT_DIR / f"{base_name}.geojson", driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": CITY,
        "years": HIST_YEARS,
        "purpose": (
            "Antecedent cumulative PM2.5 exposure window, deliberately ending before "
            "the DEIS mortality window (2018-2022) starts, to support a temporal-"
            "precedence ecological design (Paso 2 of the chronic exposome-mortality "
            "analysis plan). NOT the production PM2.5 layer used elsewhere in the "
            "master exposome table -- do not merge into santiago_exposome_master."
        ),
        "method": (
            "ACAG/van Donkelaar satellite-derived surface PM2.5; multi-year mean "
            "2000-2017; commune zonal statistics + WorldPop population-weighted mean."
        ),
        "collection": cfg["pm25"]["collection"]["id"],
        "units": "µg/m^3",
        "columns": df.columns.tolist(),
        "n_rows": len(df),
    }
    (OUT_DIR / f"{base_name}_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )
    print(f"Wrote {base_name}.csv / .geojson ({len(df)} rows x {df.shape[1]} cols)")
    print(df[["name", "pm25_mean", "pm25_pop_weighted"]].describe())


if __name__ == "__main__":
    main()

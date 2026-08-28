"""Air-quality satellite pipeline via GEE.

Plan A: MODIS AOD (~3 km) + Sentinel-5P NO2 (~3.5 km) → zonal stats by commune.

Plan A+: Conversion of NO2 column density to surface concentration using
ERA5 boundary-layer height (physics-based approximation).

Plan B (future): ML downscaling to ~1 km using SINCA ground stations + covariates.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import numpy as np
import pandas as pd

from . import boundaries, config, gee

# Molar mass of NO2 [g/mol]
M_NO2 = 46.0055


def fetch_no2(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Fetch annual mean NO2 column density from Sentinel-5P TROPOMI [mol/m^2]."""
    aq_cfg = cfg["air_quality"]["collections"]["no2"]
    start = start or cfg["air_quality"]["start_date"]
    end = end or cfg["air_quality"]["end_date"]

    col = (
        ee.ImageCollection(aq_cfg["id"])
        .filterDate(start, end)
        .select(aq_cfg["band"])
    )
    mean_img = col.mean()
    stats = gee.image_to_stats(
        mean_img,
        regions_fc,
        band=aq_cfg["band"],
        scale=aq_cfg["scale_meters"],
        reducer="mean",
    )
    rows = gee.fc_to_dicts(stats)
    df = pd.DataFrame(rows)
    if "mean" in df.columns:
        df = df.rename(columns={"mean": "no2_mean"})
    return df


def fetch_blh(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Fetch annual mean boundary-layer height from ERA5 [m]."""
    start = start or cfg["air_quality"]["start_date"]
    end = end or cfg["air_quality"]["end_date"]

    col = (
        ee.ImageCollection("ECMWF/ERA5/HOURLY")
        .filterDate(start, end)
        .select("boundary_layer_height")
    )
    mean_img = col.mean()
    stats = gee.image_to_stats(
        mean_img,
        regions_fc,
        band="boundary_layer_height",
        scale=30_000,  # ERA5 native ~31 km; we use 30 km for zonal stats
        reducer="mean",
    )
    rows = gee.fc_to_dicts(stats)
    df = pd.DataFrame(rows)
    if "mean" in df.columns:
        df = df.rename(columns={"mean": "blh_mean"})
    return df


def fetch_aod(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Fetch annual mean AOD (470 nm) from MODIS MCD19A2."""
    aq_cfg = cfg["air_quality"]["collections"]["aod"]
    start = start or cfg["air_quality"]["start_date"]
    end = end or cfg["air_quality"]["end_date"]

    col = (
        ee.ImageCollection(aq_cfg["id"])
        .filterDate(start, end)
        .select([aq_cfg["band"], aq_cfg["qa_band"]])
    )

    qa_max = aq_cfg.get("qa_mask_max", 1)
    scale_factor = aq_cfg.get("scale_factor", 0.001)

    def mask_qa(img: ee.Image) -> ee.Image:
        qa = img.select(aq_cfg["qa_band"])
        mask = qa.bitwiseAnd(3).lte(qa_max)
        return img.updateMask(mask)

    col = col.map(mask_qa)
    mean_img = col.select(aq_cfg["band"]).mean().multiply(scale_factor)

    stats = gee.image_to_stats(
        mean_img,
        regions_fc,
        band=aq_cfg["band"],
        scale=aq_cfg["scale_meters"],
        reducer="mean",
    )
    rows = gee.fc_to_dicts(stats)
    df = pd.DataFrame(rows)
    if "mean" in df.columns:
        df = df.rename(columns={"mean": "aod_mean"})
    return df


def build_air_quality_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Run the full Plan A+ air-quality pipeline.

    Returns
    -------
    df : pd.DataFrame
        Table with columns:
        - name, area_km2
        - no2_mean          : NO2 column density [mol/m^2]
        - no2_surface_ug_m3 : estimated surface concentration [µg/m^3]
        - aod_mean          : aerosol optical depth at 470 nm [unitless]
    gdf : gpd.GeoDataFrame
        Same with geometry attached.
    """
    cfg = config.load_config(city)
    gee.init_gee()

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    year = cfg["air_quality"]["year"]

    # 1. Boundaries
    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)
    regions_fc = gee.gdf_to_feature_collection(gdf_comm)

    # 2. Fetch NO2
    no2_csv = cache_dir / f"{city}_no2_{year}.csv"
    if no2_csv.exists():
        df_no2 = pd.read_csv(no2_csv)
    else:
        df_no2 = fetch_no2(cfg, regions_fc)
        df_no2.to_csv(no2_csv, index=False)

    # 3. Fetch BLH
    blh_csv = cache_dir / f"{city}_blh_{year}.csv"
    if blh_csv.exists():
        df_blh = pd.read_csv(blh_csv)
    else:
        df_blh = fetch_blh(cfg, regions_fc)
        df_blh.to_csv(blh_csv, index=False)

    # 4. Fetch AOD
    aod_csv = cache_dir / f"{city}_aod_{year}.csv"
    if aod_csv.exists():
        df_aod = pd.read_csv(aod_csv)
    else:
        df_aod = fetch_aod(cfg, regions_fc)
        df_aod.to_csv(aod_csv, index=False)

    # 5. Merge
    df = gdf_comm[["name", "area_km2"]].copy()
    df = df.merge(df_no2[["name", "no2_mean"]], on="name", how="left")
    df = df.merge(df_blh[["name", "blh_mean"]], on="name", how="left")
    df = df.merge(df_aod[["name", "aod_mean"]], on="name", how="left")

    # 5b. Fallback for missing BLH (small communes may not intersect ERA5 grid)
    if df["blh_mean"].isna().any():
        regional_blh = df["blh_mean"].mean()
        missing_names = df.loc[df["blh_mean"].isna(), "name"].tolist()
        df["blh_mean"] = df["blh_mean"].fillna(regional_blh)
        print(f"Warning: filled missing BLH for {missing_names} with regional mean {regional_blh:.1f} m")

    # 6. Convert NO2 column density → surface concentration
    #    C_surface [µg/m^3] = column [mol/m^2] * M [g/mol] * 1e6 [µg/g] / BLH [m]
    df["no2_surface_ug_m3"] = df["no2_mean"] * M_NO2 * 1.0e6 / df["blh_mean"]

    # 7. Formatting
    df["no2_mean"] = df["no2_mean"].round(6)
    df["no2_surface_ug_m3"] = df["no2_surface_ug_m3"].round(2)
    df["blh_mean"] = df["blh_mean"].round(1)
    df["aod_mean"] = df["aod_mean"].round(4)

    # 8. Validate
    n_expected = cfg["expected_communes"]
    if len(df) != n_expected:
        raise ValueError(f"Expected {n_expected} rows, got {len(df)}")
    if df["name"].duplicated().any():
        raise ValueError("Duplicate commune names")
    if df.isna().any().any():
        missing = df.columns[df.isna().any()].tolist()
        raise ValueError(f"Missing values in: {missing}")

    # 9. Geo version
    gdf = gdf_comm[["name", "geometry"]].merge(df, on="name", how="right")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    # 10. Write outputs
    base_name = f"{city}_air_quality_satellite_{year}"
    df.to_csv(out_dir / f"{base_name}.csv", index=False)
    gdf.to_file(out_dir / f"{base_name}.geojson", driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "year": year,
        "method": "Plan A+: GEE satellite + ERA5 BLH physics-based conversion",
        "resolution_no2_m": cfg["air_quality"]["collections"]["no2"]["scale_meters"],
        "resolution_aod_m": cfg["air_quality"]["collections"]["aod"]["scale_meters"],
        "resolution_blh_m": 30_000,
        "molar_mass_no2_g_mol": M_NO2,
        "conversion_formula": "no2_surface_ug_m3 = no2_mean * 46.0055 * 1e6 / blh_mean",
        "columns": df.columns.tolist(),
        "n_rows": len(df),
    }
    meta_path = out_dir / f"{base_name}_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(f"Wrote {base_name}.csv / .geojson ({len(df)} rows x {df.shape[1]} cols)")
    return df, gdf

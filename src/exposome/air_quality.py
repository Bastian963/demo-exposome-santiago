"""Air-quality satellite pipeline via GEE.

Plan A: MODIS AOD (~3 km) + Sentinel-5P NO2 (~3.5 km) → zonal stats by commune.

Plan A+: Conversion of NO2 column density to surface concentration using
ERA5 boundary-layer height (physics-based approximation).

Plan A++: Adds Sentinel-5P O3 (~7 km) and MODIS Angstrom Exponent
(470-440 nm) as a fine-particle / black-carbon proxy. O3 is the third
WHO-mandated criteria pollutant and is increasingly recognized for its
neuroinflammatory effects. AE > 1.5 indicates fine aerosols (traffic,
biomass burning); AE < 1.0 indicates coarse aerosols (dust, sea salt).

Plan B (future): ML downscaling to ~1 km using SINCA ground stations + covariates.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import pandas as pd
from tqdm import tqdm

from . import boundaries, config, gee

# Molar mass of NO2 [g/mol]
M_NO2 = 46.0055
# Molar mass of O3 [g/mol]
M_O3 = 47.997


def _annual_no2_image(cfg: dict[str, Any], start: str, end: str) -> ee.Image:
    """Annual-mean Sentinel-5P TROPOMI NO2 column-density image [mol/m^2]."""
    aq_cfg = cfg["air_quality"]["collections"]["no2"]
    col = (
        ee.ImageCollection(aq_cfg["id"])
        .filterDate(start, end)
        .select(aq_cfg["band"])
    )
    source = ee.Image(col.first()).select(aq_cfg["band"])
    # Collection reducers lose the provider grid unless it is restored
    # explicitly.  The L3 grid is distinct from TROPOMI's coarser physical
    # observation footprint, but it must still remain the actual 0.01° grid.
    return col.mean().setDefaultProjection(source.projection())


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

    mean_img = _annual_no2_image(cfg, start, end)
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


def fetch_angstrom(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Fetch fine-particle indicators from MODIS MCD19A2.

    - Angstrom Exponent (470-550 nm) is **derived** from the two AOD
      channels (Optical_Depth_047 and Optical_Depth_055) as
      AE = -log(AOD055 / AOD047) / log(550 / 470). This is more robust
      than the precomputed AngstromExp_470-780 band, which is often
      null over land in MCD19A2.
    - FineModeFraction (0..1): fraction of AOD due to fine-mode
      aerosols (radius < 1 um). Closer proxy for traffic-related /
      black-carbon particles.

    AE > 1.5 = fine aerosols (traffic, biomass burning, black carbon).
    AE < 1.0 = coarse aerosols (dust, sea salt).
    """
    aq_cfg = cfg["air_quality"]["collections"]["angstrom"]
    start = start or cfg["air_quality"]["start_date"]
    end = end or cfg["air_quality"]["end_date"]

    bands = ["Optical_Depth_047", "Optical_Depth_055", aq_cfg["fine_mode_band"],
             aq_cfg["qa_band"]]
    col = (
        ee.ImageCollection(aq_cfg["id"])
        .filterDate(start, end)
        .select(bands)
    )

    qa_max = aq_cfg.get("qa_mask_max", 1)
    scale_factor = aq_cfg.get("scale_factor", 0.001)

    def mask_qa_and_compute_ae(img: ee.Image) -> ee.Image:
        qa = img.select(aq_cfg["qa_band"])
        mask = qa.bitwiseAnd(3).lte(qa_max)
        aod047 = img.select("Optical_Depth_047").multiply(scale_factor)
        aod055 = img.select("Optical_Depth_055").multiply(scale_factor)
        # AE_470-550 = -log(AOD550/AOD470) / log(550/470)
        # log(550/470) ≈ 0.158
        ratio = aod055.divide(aod047).log().multiply(-1.0 / 0.158).rename("ae_470_550")
        fmf = img.select(aq_cfg["fine_mode_band"]).rename("fine_mode_fraction")
        return img.addBands([ratio, fmf]).updateMask(mask)

    col = col.map(mask_qa_and_compute_ae)
    mean_img = col.select(["ae_470_550", "fine_mode_fraction"]).mean()

    ae_stats = gee.image_to_stats(
        mean_img.select("ae_470_550"),
        regions_fc,
        band="ae_470_550",
        scale=aq_cfg["scale_meters"],
        reducer="mean",
    )
    fmf_stats = gee.image_to_stats(
        mean_img.select("fine_mode_fraction"),
        regions_fc,
        band="fine_mode_fraction",
        scale=aq_cfg["scale_meters"],
        reducer="mean",
    )

    df_ae = pd.DataFrame(gee.fc_to_dicts(ae_stats)).rename(
        columns={"mean": "ae_470_550_mean"}
    )
    df_fmf = pd.DataFrame(gee.fc_to_dicts(fmf_stats)).rename(
        columns={"mean": "fine_mode_fraction_mean"}
    )
    return df_ae.merge(df_fmf, on="name", how="outer")


def fetch_o3(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Fetch annual mean total column O3 from Sentinel-5P TROPOMI [mol/m^2].

    S5P O3 native units: mol/m^2. We **deliberately do not** estimate
    a surface concentration: roughly 90% of the total column is
    stratospheric, and the column * M / BLH formula that works for NO2
    would over-estimate surface O3 by 5-10x. Use ``o3_mean`` for
    relative ranking only; for absolute surface concentrations,
    consult the SINCA ground-station network.
    """
    aq_cfg = cfg["air_quality"]["collections"]["o3"]
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
        df = df.rename(columns={"mean": "o3_mean"})
    return df


def build_air_quality_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    year: int | None = None,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Run the full Plan A++ air-quality pipeline.

    Returns
    -------
    df : pd.DataFrame
        Table with columns:
        - name, area_km2
        - no2_mean          : NO2 column density [mol/m^2]
        - no2_surface_ug_m3 : estimated surface concentration [µg/m^3]
        - no2_who_ratio     : ratio to WHO 2021 annual guideline
        - o3_mean           : O3 total column density [mol/m^2]
        - aod_mean          : aerosol optical depth at 470 nm [unitless]
        - ae_470_550_mean   : Angstrom Exponent 470-550 nm (derived, fine-particle proxy)
        - fine_mode_fraction_mean: 0-1, fraction of AOD due to fine aerosols
                                   (closer BC proxy)

        Note: ``o3_surface_ug_m3`` and ``o3_who_ratio`` are intentionally
        **not** produced. S5P O3 is a total-column measurement (~90%
        stratospheric); the column * M / BLH conversion used for NO2
        would over-estimate surface O3 by 5-10x. Absolute surface
        O3 should come from the SINCA ground-station network.

    gdf : gpd.GeoDataFrame
        Same with geometry attached.
    """
    cfg = config.load_config(city)
    gee.init_gee()

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    year = int(year if year is not None else cfg["air_quality"]["year"])
    cfg["air_quality"]["year"] = year
    cfg["air_quality"]["start_date"] = f"{year}-01-01"
    cfg["air_quality"]["end_date"] = f"{year + 1}-01-01"

    # 1. Boundaries
    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)
    regions_fc = gee.gdf_to_feature_collection(gdf_comm)

    progress = tqdm(total=5, desc=f"air_quality_satellite [{city}]", unit="step")

    # 2. Fetch NO2
    no2_csv = cache_dir / f"{city}_no2_{year}.csv"
    if no2_csv.exists():
        tqdm.write("  [no2] loading from cache …")
        df_no2 = pd.read_csv(no2_csv)
    else:
        tqdm.write("  [no2] fetching from GEE …")
        df_no2 = fetch_no2(cfg, regions_fc)
        df_no2.to_csv(no2_csv, index=False)
    progress.update(1)

    # 3. Fetch BLH
    blh_csv = cache_dir / f"{city}_blh_{year}.csv"
    if blh_csv.exists():
        tqdm.write("  [blh] loading from cache …")
        df_blh = pd.read_csv(blh_csv)
    else:
        tqdm.write("  [blh] fetching from GEE …")
        df_blh = fetch_blh(cfg, regions_fc)
        df_blh.to_csv(blh_csv, index=False)
    progress.update(1)

    # 4. Fetch AOD
    aod_csv = cache_dir / f"{city}_aod_{year}.csv"
    if aod_csv.exists():
        tqdm.write("  [aod] loading from cache …")
        df_aod = pd.read_csv(aod_csv)
    else:
        tqdm.write("  [aod] fetching from GEE …")
        df_aod = fetch_aod(cfg, regions_fc)
        df_aod.to_csv(aod_csv, index=False)
    progress.update(1)

    # 5. Fetch Angstrom Exponent + FineModeFraction (fine-particle / BC proxy)
    ae_csv = cache_dir / f"{city}_angstrom_{year}.csv"
    if ae_csv.exists():
        tqdm.write("  [angstrom] loading from cache …")
        df_ae = pd.read_csv(ae_csv)
    else:
        tqdm.write("  [angstrom] fetching from GEE …")
        df_ae = fetch_angstrom(cfg, regions_fc)
        df_ae.to_csv(ae_csv, index=False)
    progress.update(1)

    # 6. Fetch O3
    o3_csv = cache_dir / f"{city}_o3_{year}.csv"
    if o3_csv.exists():
        tqdm.write("  [o3] loading from cache …")
        df_o3 = pd.read_csv(o3_csv)
    else:
        tqdm.write("  [o3] fetching from GEE …")
        df_o3 = fetch_o3(cfg, regions_fc)
        df_o3.to_csv(o3_csv, index=False)
    progress.update(1)
    progress.close()

    # 7. Merge
    df = gdf_comm[["name", "area_km2"]].copy()
    df = df.merge(df_no2[["name", "no2_mean"]], on="name", how="left")
    df = df.merge(df_blh[["name", "blh_mean"]], on="name", how="left")
    df = df.merge(df_aod[["name", "aod_mean"]], on="name", how="left")
    df = df.merge(df_ae[["name", "ae_470_550_mean", "fine_mode_fraction_mean"]],
                  on="name", how="left")
    df = df.merge(df_o3[["name", "o3_mean"]], on="name", how="left")

    # 7b. Fallback for missing BLH (small communes may not intersect ERA5 grid)
    if df["blh_mean"].isna().any():
        regional_blh = df["blh_mean"].mean()
        missing_names = df.loc[df["blh_mean"].isna(), "name"].tolist()
        df["blh_mean"] = df["blh_mean"].fillna(regional_blh)
        print(f"Warning: filled missing BLH for {missing_names} with regional mean {regional_blh:.1f} m")

    # 7c. Fallback for missing O3/AE/NO2 (communes with no valid pixels)
    for col in ("o3_mean", "ae_470_550_mean", "fine_mode_fraction_mean", "no2_mean", "aod_mean"):
        if df[col].isna().any():
            regional = df[col].mean()
            missing = df.loc[df[col].isna(), "name"].tolist()
            df[col] = df[col].fillna(regional)
            print(f"Warning: filled {col} for {len(missing)} communes with regional mean {regional:.4f}")

    # 8. Convert NO2 column density → surface concentration
    #    C_surface [µg/m^3] = column [mol/m^2] * M [g/mol] * 1e6 [µg/g] / BLH [m]
    df["no2_surface_ug_m3"] = df["no2_mean"] * M_NO2 * 1.0e6 / df["blh_mean"]

    # 9. O3 surface is **not** computed: ~90% of the total column is
    #    stratospheric, so column * M / BLH would over-estimate surface
    #    O3 by 5-10x. We keep ``o3_mean`` (total column in mol/m^2) as a
    #    relative ranking indicator and leave absolute surface O3 to
    #    ground stations (SINCA). See docs/plan_a_plus_methodology.md,
    #    section "O3 limitation: stratospheric column".

    # 10. WHO 2021 ratio for NO2 (annual 10 µg/m^3). We do not compute
    #     a WHO ratio for O3 because we do not estimate surface O3.
    who_no2 = cfg["air_quality"]["who_guidelines"]["no2"]
    df["no2_who_ratio"] = (df["no2_surface_ug_m3"] / who_no2).round(2)

    # 11. Formatting
    df["no2_mean"] = df["no2_mean"].round(6)
    df["no2_surface_ug_m3"] = df["no2_surface_ug_m3"].round(2)
    df["no2_who_ratio"] = df["no2_who_ratio"].round(2)
    df["blh_mean"] = df["blh_mean"].round(1)
    df["aod_mean"] = df["aod_mean"].round(4)
    df["ae_470_550_mean"] = df["ae_470_550_mean"].round(3)
    df["fine_mode_fraction_mean"] = df["fine_mode_fraction_mean"].round(3)
    df["o3_mean"] = df["o3_mean"].round(6)

    # 12. Validate
    n_expected = cfg["expected_communes"]
    if len(df) != n_expected:
        raise ValueError(f"Expected {n_expected} rows, got {len(df)}")
    if df["name"].duplicated().any():
        raise ValueError("Duplicate commune names")
    if df.isna().any().any():
        missing = df.columns[df.isna().any()].tolist()
        raise ValueError(f"Missing values in: {missing}")

    # 13. Geo version
    gdf = gdf_comm[["name", "geometry"]].merge(df, on="name", how="right")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    # 14. Write outputs
    base_name = f"{city}_air_quality_satellite_{year}"
    df.to_csv(out_dir / f"{base_name}.csv", index=False)
    gdf.to_file(out_dir / f"{base_name}.geojson", driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "year": year,
        "method": "Plan A++: GEE satellite (NO2 + O3 + AOD + AE) + ERA5 BLH physics-based NO2 conversion",
        "resolution_no2_m": cfg["air_quality"]["collections"]["no2"]["scale_meters"],
        "resolution_o3_m": cfg["air_quality"]["collections"]["o3"]["scale_meters"],
        "resolution_aod_m": cfg["air_quality"]["collections"]["aod"]["scale_meters"],
        "resolution_ae_m": cfg["air_quality"]["collections"]["angstrom"]["scale_meters"],
        "resolution_blh_m": 30_000,
        "molar_mass_no2_g_mol": M_NO2,
        "molar_mass_o3_g_mol": M_O3,
        "conversion_formula_no2": "no2_surface_ug_m3 = no2_mean * 46.0055 * 1e6 / blh_mean",
        "o3_surface_NOT_computed": (
            "S5P O3 is total column (mol/m^2); ~90% is stratospheric. "
            "The same column*M/BLH formula used for NO2 would over-estimate "
            "surface O3 by 5-10x. We keep o3_mean as a relative ranking "
            "indicator and leave absolute surface O3 to ground stations."
        ),
        "who_guidelines": cfg["air_quality"]["who_guidelines"],
        "columns": df.columns.tolist(),
        "n_rows": len(df),
    }
    meta_path = out_dir / f"{base_name}_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(f"Wrote {base_name}.csv / .geojson ({len(df)} rows x {df.shape[1]} cols)")
    return df, gdf

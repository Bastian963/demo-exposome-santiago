"""Artificial light at night (ALAN) exposome layer via GEE.

Commune-level outdoor night-time light exposure from the VIIRS Day/Night Band
(monthly, stray-light corrected — ``VCMSLCFG``), averaged over a calendar year.

ALAN is a standard urban-exposome domain with growing relevance for brain
health: outdoor night-time light is associated with circadian disruption,
melatonin suppression and sleep disturbance, with emerging links to cognitive
decline, Alzheimer's disease/dementia, depression and stroke.

This module mirrors :mod:`exposome.air_quality`: GEE zonal statistics over the
52 communes, strict validation (52 rows, no duplicates, no missing values), and
CSV + GeoJSON + metadata outputs ready for ``build_master_exposome``.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import pandas as pd
from tqdm import tqdm

from . import boundaries, config, gee
from .cache import CacheIdentity, CacheStore, spatial_fingerprint

# Reducer name -> output column produced by reduceRegions / our zonal stats.
_RADIANCE_REDUCERS: list[tuple[str, str]] = [
    ("mean", "alan_radiance_mean"),
    ("median", "alan_radiance_median"),
    ("stdDev", "alan_radiance_sd"),
    ("max", "alan_radiance_max"),
]


def alan_cache_namespace(alan_cfg: dict[str, Any]) -> str:
    """Stable cache key for every provider setting that changes ALAN values."""
    collection = alan_cfg["collection"]
    population = alan_cfg["population"]
    payload = {
        "collection": {
            key: collection.get(key)
            for key in ("id", "band", "cf_band", "scale_meters")
        },
        "population": {
            key: population.get(key)
            for key in ("id", "band", "country", "year", "scale_meters")
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def _annual_radiance_image(cfg: dict[str, Any], start: str, end: str) -> ee.Image:
    """Annual-mean VIIRS DNB radiance image, cloud-free masked, clamped at 0."""
    al_cfg = cfg["alan"]["collection"]
    band = al_cfg["band"]
    cf_band = al_cfg.get("cf_band")

    coll = ee.ImageCollection(al_cfg["id"]).filterDate(start, end)

    if cf_band:
        def mask_cf(img: ee.Image) -> ee.Image:
            return img.updateMask(img.select(cf_band).gt(0))

        coll = coll.map(mask_cf)

    # ``mean()`` drops the default projection. Retain one monthly VIIRS tile's
    # 15-arc-second grid so native exports preserve provider pixels rather than
    # falling back to Earth Engine's nominal one-degree projection.
    source = ee.Image(coll.first()).select(band)
    # Average the monthly composites; clamp negative radiance (noise over dark
    # areas) to zero so exposure metrics stay physically meaningful.
    return (
        coll.select(band)
        .mean()
        .setDefaultProjection(source.projection())
        .rename(band)
        .max(0)
    )


def fetch_alan_radiance(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Fetch commune-level VIIRS DNB radiance statistics [nW/cm^2/sr]."""
    al_cfg = cfg["alan"]
    start = start or al_cfg["start_date"]
    end = end or al_cfg["end_date"]
    band = al_cfg["collection"]["band"]
    scale = al_cfg["collection"]["scale_meters"]

    rad_img = _annual_radiance_image(cfg, start, end)

    df: pd.DataFrame | None = None
    for reducer, out_col in _RADIANCE_REDUCERS:
        stats = gee.image_to_stats(
            rad_img, regions_fc, band=band, scale=scale, reducer=reducer
        )
        part = pd.DataFrame(gee.fc_to_dicts(stats))
        part = part.rename(columns={reducer: out_col})[["name", out_col]]
        df = part if df is None else df.merge(part, on="name", how="outer")

    assert df is not None
    return df


def fetch_pop_weighted_radiance(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Population-weighted mean radiance per commune: sum(rad*pop)/sum(pop)."""
    al_cfg = cfg["alan"]
    start = start or al_cfg["start_date"]
    end = end or al_cfg["end_date"]
    pop_cfg = al_cfg["population"]
    pop_img = (
        ee.ImageCollection(pop_cfg["id"])
        .filter(ee.Filter.eq("country", pop_cfg["country"]))
        .filter(ee.Filter.eq("year", pop_cfg["year"]))
        .select(pop_cfg["band"])
        .mosaic()
    )
    pop_scale = pop_cfg["scale_meters"]

    rad_img = _annual_radiance_image(cfg, start, end)

    num_img = rad_img.multiply(pop_img).rename("num")
    den_img = pop_img.rename("den")

    num = pd.DataFrame(
        gee.fc_to_dicts(
            gee.image_to_stats(num_img, regions_fc, band="num", scale=pop_scale, reducer="sum")
        )
    ).rename(columns={"sum": "_num"})[["name", "_num"]]
    den = pd.DataFrame(
        gee.fc_to_dicts(
            gee.image_to_stats(den_img, regions_fc, band="den", scale=pop_scale, reducer="sum")
        )
    ).rename(columns={"sum": "_den"})[["name", "_den"]]

    df = num.merge(den, on="name", how="outer")
    df["alan_radiance_pop_weighted"] = df["_num"] / df["_den"]
    return df[["name", "alan_radiance_pop_weighted"]]


def build_alan_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    year: int | None = None,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Run the full ALAN pipeline and export commune-level zonal statistics.

    Returns
    -------
    df : pd.DataFrame
        Columns: name, area_km2, alan_radiance_mean, alan_radiance_median,
        alan_radiance_sd, alan_radiance_max, alan_radiance_pop_weighted.
    gdf : gpd.GeoDataFrame
        Same with geometry attached.
    """
    cfg = config.load_config(city)

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    year = int(year if year is not None else cfg["alan"]["year"])
    cfg["alan"]["year"] = year
    cfg["alan"]["start_date"] = f"{year}-01-01"
    cfg["alan"]["end_date"] = f"{year + 1}-01-01"
    start = cfg["alan"]["start_date"]
    end = cfg["alan"]["end_date"]
    collection_cfg = cfg["alan"]["collection"]
    pop_cfg = cfg["alan"]["population"]
    cache_namespace = alan_cache_namespace(cfg["alan"])

    # 1. Boundaries
    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)

    spatial_key = spatial_fingerprint(
        gdf_comm,
        id_column="spatial_id" if "spatial_id" in gdf_comm.columns else "name",
    )
    radiance_identity = CacheIdentity(
        layer_id="alan",
        operation="radiance",
        parameters={
            "collection": collection_cfg,
            "start": start,
            "end_exclusive": end,
            "reducers": _RADIANCE_REDUCERS,
            "cloud_free_rule": "cf_band > 0" if collection_cfg.get("cf_band") else None,
            "negative_radiance": "clamp_to_zero",
        },
        spatial_fingerprint=spatial_key,
        algorithm_version="2",
    )
    population_identity = CacheIdentity(
        layer_id="alan",
        operation="population_weighted",
        parameters={
            "radiance": radiance_identity.payload["parameters"],
            "population": pop_cfg,
            "reducers": {"numerator": "sum", "denominator": "sum"},
        },
        spatial_fingerprint=spatial_key,
        algorithm_version="2",
    )
    radiance_store = CacheStore(cache_dir, radiance_identity)
    population_store = CacheStore(cache_dir, population_identity)
    rad_record = radiance_store.load_csv(
        str(year),
        required_columns=["name", *[column for _, column in _RADIANCE_REDUCERS]],
    )
    pop_record = population_store.load_csv(
        str(year), required_columns=["name", "alan_radiance_pop_weighted"]
    )

    # 2. Radiance statistics (mean/median/sd/max)
    needs_gee = not (rad_record.hit and pop_record.hit)
    regions_fc: ee.FeatureCollection | None = None
    if needs_gee:
        gee.init_gee()
        regions_fc = gee.gdf_to_feature_collection(gdf_comm)

    progress = tqdm(total=2, desc=f"alan [{city}]", unit="step")

    if rad_record.hit:
        tqdm.write(f"  [alan_radiance] {rad_record.reason} …")
        assert rad_record.frame is not None
        df_rad = rad_record.frame
    else:
        tqdm.write(f"  [alan_radiance] cache miss ({rad_record.reason}); fetching from GEE …")
        assert regions_fc is not None
        df_rad = fetch_alan_radiance(cfg, regions_fc)
        rad_record = radiance_store.write_csv_atomic(str(year), df_rad)
    progress.update(1)

    # 3. Population-weighted mean radiance
    if pop_record.hit:
        tqdm.write(f"  [alan_pop_weighted] {pop_record.reason} …")
        assert pop_record.frame is not None
        df_popw = pop_record.frame
    else:
        tqdm.write(
            f"  [alan_pop_weighted] cache miss ({pop_record.reason}); fetching from GEE …"
        )
        assert regions_fc is not None
        df_popw = fetch_pop_weighted_radiance(cfg, regions_fc)
        pop_record = population_store.write_csv_atomic(str(year), df_popw)
    progress.update(1)
    progress.close()

    # 4. Merge
    df = gdf_comm[["name", "area_km2"]].copy()
    df = df.merge(df_rad, on="name", how="left")
    df = df.merge(df_popw, on="name", how="left")

    # 4b. Fallback for missing population-weighting (commune not covered by the
    #     population raster): use the area mean radiance instead.
    fallback_names: list[str] = []
    if df["alan_radiance_pop_weighted"].isna().any():
        fallback_names = df.loc[df["alan_radiance_pop_weighted"].isna(), "name"].tolist()
        df["alan_radiance_pop_weighted"] = df["alan_radiance_pop_weighted"].fillna(
            df["alan_radiance_mean"]
        )
        print(
            f"Warning: filled pop-weighted ALAN for {fallback_names} with area mean radiance"
        )

    # 5. Formatting
    for col in [
        "alan_radiance_mean",
        "alan_radiance_median",
        "alan_radiance_sd",
        "alan_radiance_max",
        "alan_radiance_pop_weighted",
    ]:
        df[col] = df[col].round(4)

    # 6. Validate
    n_expected = cfg["expected_communes"]
    if len(df) != n_expected:
        raise ValueError(f"Expected {n_expected} rows, got {len(df)}")
    if df["name"].duplicated().any():
        raise ValueError("Duplicate commune names")
    if df.isna().any().any():
        missing = df.columns[df.isna().any()].tolist()
        raise ValueError(f"Missing values in: {missing}")

    # 7. Geo version
    gdf = gdf_comm[["name", "geometry"]].merge(df, on="name", how="right")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    # 8. Write outputs
    base_name = f"{city}_alan_viirs_{year}"
    df.to_csv(out_dir / f"{base_name}.csv", index=False)
    gdf.to_file(out_dir / f"{base_name}.geojson", driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "year": year,
        "start_date": start,
        "end_date_exclusive": end,
        "method": (
            "VIIRS DNB monthly (VCMSLCFG) annual-mean radiance, cloud-free "
            "masked and clamped at 0; commune zonal statistics + WorldPop "
            "population-weighted mean."
        ),
        "resolution_m": collection_cfg["scale_meters"],
        "units": "nW/cm^2/sr",
        "sources": {
            "viirs_dnb": {
                "provider": "NOAA/Colorado School of Mines (EOG)",
                "collection": collection_cfg["id"],
                "band": collection_cfg["band"],
                "cloud_free_band": collection_cfg.get("cf_band"),
            },
            "population": {
                "provider": "WorldPop",
                "collection": pop_cfg["id"],
                "band": pop_cfg["band"],
                "country": pop_cfg["country"],
                "year": pop_cfg["year"],
                "resolution_m": pop_cfg["scale_meters"],
            },
        },
        "cache_files": {
            "namespace": cache_namespace,
            "communes": boundaries_cache.as_posix(),
            "radiance_stats": (
                rad_record.data_path.as_posix() if rad_record.data_path is not None else None
            ),
            "population_weighted": (
                pop_record.data_path.as_posix() if pop_record.data_path is not None else None
            ),
        },
        "cache_fingerprints": {
            "radiance": radiance_identity.digest,
            "population_weighted": population_identity.digest,
        },
        "population_weighted_fallback": {
            "count": len(fallback_names),
            "communes": fallback_names,
            "fallback_metric": "alan_radiance_mean",
        },
        "columns": df.columns.tolist(),
        "n_rows": len(df),
    }
    meta_path = out_dir / f"{base_name}_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(f"Wrote {base_name}.csv / .geojson ({len(df)} rows x {df.shape[1]} cols)")
    return df, gdf

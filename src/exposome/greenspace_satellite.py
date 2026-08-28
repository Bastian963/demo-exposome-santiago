"""Satellite-based greenspace coverage layer from Landsat-8/9.

Produces commune-level indicators of greenness using NDVI and EVI
computed from Google Earth Engine's Landsat Collection 2 Level 2 imagery.

Landsat's 30 m resolution is coarse than Sentinel-2 but is robust against
GEE timeouts and download limits for regional-scale zonal statistics.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import pandas as pd

from . import boundaries, config, gee


# Landsat Collection 2 Level 2 surface reflectance scale/offset
SR_SCALE = 2.75e-5
SR_OFFSET = -0.2


def _apply_scale(image: ee.Image) -> ee.Image:
    """Apply Collection 2 SR scale and offset to optical bands."""
    optical = image.select(["SR_B2", "SR_B4", "SR_B5"])
    scaled = optical.multiply(SR_SCALE).add(SR_OFFSET)
    return image.addBands(scaled, None, True)


def _mask_clouds(image: ee.Image) -> ee.Image:
    """Mask clouds and cloud shadows using the QA_PIXEL band."""
    qa = image.select("QA_PIXEL")
    # Bits 3 (cloud), 4 (cloud shadow), 5 (snow); fill bit 0 is also masked
    mask = (
        qa.bitwiseAnd(1 << 0).eq(0)  # no fill
        .And(qa.bitwiseAnd(1 << 3).eq(0))  # no cloud
        .And(qa.bitwiseAnd(1 << 4).eq(0))  # no cloud shadow
        .And(qa.bitwiseAnd(1 << 5).eq(0))  # no snow
    )
    return image.updateMask(mask)


def _add_indices(image: ee.Image, ndvi_threshold: float, evi_threshold: float) -> ee.Image:
    """Add NDVI, EVI and binary greenness masks."""
    ndvi = image.normalizedDifference(["SR_B5", "SR_B4"]).rename("NDVI")
    evi = image.expression(
        "2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))",
        {
            "NIR": image.select("SR_B5"),
            "RED": image.select("SR_B4"),
            "BLUE": image.select("SR_B2"),
        },
    ).rename("EVI")
    green_ndvi = ndvi.gte(ndvi_threshold).rename("green_ndvi")
    green_evi = evi.gte(evi_threshold).rename("green_evi")
    return image.addBands([ndvi, evi, green_ndvi, green_evi])


def build_landsat_composite(
    roi: ee.Geometry,
    years: list[int],
    season_months: list[int],
    ndvi_threshold: float,
    evi_threshold: float,
) -> ee.Image:
    """Build a median NDVI/EVI composite from Landsat-8/9 Collection 2."""
    start_year = min(years)
    end_year = max(years)
    start_month = min(season_months)
    end_month = max(season_months)

    start_date = f"{start_year}-{start_month:02d}-01"
    if end_month == 12:
        end_day = "31"
    elif end_month in [4, 6, 9, 11]:
        end_day = "30"
    elif end_month == 2:
        end_day = "28"
    else:
        end_day = "31"
    end_date = f"{end_year}-{end_month:02d}-{end_day}"

    l8 = (
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2")
        .filterBounds(roi)
        .filterDate(start_date, end_date)
        .select(["SR_B2", "SR_B4", "SR_B5", "QA_PIXEL"])
    )
    l9 = (
        ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
        .filterBounds(roi)
        .filterDate(start_date, end_date)
        .select(["SR_B2", "SR_B4", "SR_B5", "QA_PIXEL"])
    )

    collection = l8.merge(l9)

    if set(season_months) != set(range(1, 13)):
        collection = collection.filter(
            ee.Filter.calendarRange(min(season_months), max(season_months), "month")
        )

    collection = collection.map(_apply_scale).map(_mask_clouds)
    with_indices = collection.map(
        lambda img: _add_indices(img, ndvi_threshold, evi_threshold)
    )
    composite = with_indices.median().clip(roi)
    return composite.select(["NDVI", "EVI", "green_ndvi", "green_evi"])


def _zonal_stats_combined(
    image: ee.Image,
    regions: ee.FeatureCollection,
    scale: int,
) -> dict[str, dict[str, Any]]:
    """Compute mean/max for NDVI/EVI and green-cover fractions in one call."""
    reducer = ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True)

    stats = image.reduceRegions(
        collection=regions,
        reducer=reducer,
        scale=scale,
        crs="EPSG:4326",
        tileScale=4,
    )

    rows = gee.fc_to_dicts(stats)
    return {r["name"]: r for r in rows if "name" in r}


def build_greenspace_coverage_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> tuple[Path, Path]:
    """Build the satellite greenspace coverage layer and write CSV + GeoJSON."""
    cfg = config.load_config(city)
    gee.init_gee()

    cache_dir = Path(cache_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"Building greenspace coverage layer for {city}")

    # Load commune boundaries
    cache_path = cache_dir / f"{city}_communes.geojson"
    communes = boundaries.get_communes(cfg, cache_path=cache_path)
    regions_fc = gee.gdf_to_feature_collection(communes)

    sat_cfg = cfg["greenspace"]["satellite"]
    print(
        f"Fetching Landsat-8/9 composite for {sat_cfg['years']} "
        f"(season months {sat_cfg['season_months']})..."
    )

    roi = regions_fc.geometry().bounds()
    composite = build_landsat_composite(
        roi=roi,
        years=sat_cfg["years"],
        season_months=sat_cfg["season_months"],
        ndvi_threshold=sat_cfg["ndvi_threshold"],
        evi_threshold=sat_cfg["evi_threshold"],
    )

    scale = 30  # Landsat native resolution
    print("Computing zonal NDVI/EVI statistics (single reduceRegions call)...")
    stats = _zonal_stats_combined(composite, regions_fc, scale)

    # Assemble results
    result = communes[["name", "area_km2", "geometry"]].copy()
    result["ndvi_mean"] = result["name"].map(lambda n: stats.get(n, {}).get("NDVI_mean"))
    result["ndvi_max"] = result["name"].map(lambda n: stats.get(n, {}).get("NDVI_max"))
    result["evi_mean"] = result["name"].map(lambda n: stats.get(n, {}).get("EVI_mean"))
    result["evi_max"] = result["name"].map(lambda n: stats.get(n, {}).get("EVI_max"))
    result["green_cover_pct_ndvi"] = result["name"].map(
        lambda n: stats.get(n, {}).get("green_ndvi_mean")
    )
    result["green_cover_pct_evi"] = result["name"].map(
        lambda n: stats.get(n, {}).get("green_evi_mean")
    )

    # Convert fractions to percentages
    result["green_cover_pct_ndvi"] = (result["green_cover_pct_ndvi"] * 100).round(2)
    result["green_cover_pct_evi"] = (result["green_cover_pct_evi"] * 100).round(2)

    # Round indices
    for col in ["ndvi_mean", "ndvi_max", "evi_mean", "evi_max"]:
        result[col] = result[col].round(4)

    # Validate output
    expected = cfg["expected_communes"]
    if len(result) != expected:
        raise ValueError(f"Expected {expected} communes, got {len(result)}")
    if result["name"].duplicated().any():
        dupes = result.loc[result["name"].duplicated(), "name"].tolist()
        raise ValueError(f"Duplicate commune names: {dupes}")
    numeric_cols = [c for c in result.columns if c not in ("name", "geometry")]
    if result[numeric_cols].isna().any().any():
        missing = result[numeric_cols].columns[result[numeric_cols].isna().any()].tolist()
        raise ValueError(f"Missing values in output columns: {missing}")

    result_geo = result.to_crs(cfg["crs"]["geographic"])

    base_name = f"{city}_greenspace_coverage"
    csv_path = out_dir / f"{base_name}.csv"
    geojson_path = out_dir / f"{base_name}.geojson"

    result.drop(columns="geometry").to_csv(csv_path, index=False)
    result_geo.to_file(geojson_path, driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "n_communes": int(len(result)),
        "collection": "LANDSAT/LC08/C02/T1_L2 + LANDSAT/LE09/C02/T1_L2",
        "years": sat_cfg["years"],
        "season_months": sat_cfg["season_months"],
        "ndvi_threshold": sat_cfg["ndvi_threshold"],
        "evi_threshold": sat_cfg["evi_threshold"],
        "scale_meters": scale,
        "cloud_mask": "QA_PIXEL",
        "note": "Landsat-8/9 used to avoid GEE timeouts with Sentinel-2 at 10 m",
        "outputs": [csv_path.name, geojson_path.name],
    }
    (out_dir / f"{base_name}_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )

    print(f"Wrote {csv_path.name}: {len(result)} rows x {result.drop(columns='geometry').shape[1]} columns")
    print(f"Wrote {geojson_path.name}")

    return csv_path, geojson_path

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
from tqdm import tqdm

from . import boundaries, config, gee
from .cache import CacheIdentity, CacheStore, spatial_fingerprint


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
    # Mask EVI outside [-1, 1] — near-zero denominators produce anomalous spikes
    # (observed evi_max ~2872); masking (not clamp) prevents blown-up pixels from
    # being counted as green in green_cover_pct_evi.
    evi = evi.updateMask(evi.gte(-1).And(evi.lte(1)))
    green_ndvi = ndvi.gte(ndvi_threshold).rename("green_ndvi")
    green_evi = evi.gte(evi_threshold).rename("green_evi")
    return image.addBands([ndvi, evi, green_ndvi, green_evi])


def _season_filter(season_months: list[int]) -> ee.Filter:
    """Return an exact calendar-month filter, including wraparound seasons."""
    months = sorted(set(int(month) for month in season_months))
    if not months or months == list(range(1, 13)):
        return ee.Filter.calendarRange(1, 12, "month")
    runs: list[list[int]] = []
    for month in months:
        if runs and month == runs[-1][-1] + 1:
            runs[-1].append(month)
        else:
            runs.append([month])
    filters = [
        ee.Filter.calendarRange(run[0], run[-1], "month")
        for run in runs
    ]
    return filters[0] if len(filters) == 1 else ee.Filter.Or(*filters)


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
        collection = collection.filter(_season_filter(season_months))

    collection = collection.map(_apply_scale).map(_mask_clouds)
    with_indices = collection.map(
        lambda img: _add_indices(img, ndvi_threshold, evi_threshold)
    )
    composite = with_indices.median().clip(roi)
    return composite.select(["NDVI", "EVI", "green_ndvi", "green_evi"])


def landsat_source_projection(roi: ee.Geometry) -> ee.Projection:
    """Return the native Landsat SR grid projection over ``roi``.

    :func:`build_landsat_composite` reduces the merged collection with
    ``.median()``, which drops the per-scene 30 m projection and leaves Earth
    Engine's 1-degree default.  Native export must pin the composite back onto
    this source grid with ``setDefaultProjection`` before the grid validator
    runs; the aggregate ``reduceRegions`` path is unaffected.  Keeping the
    collection id here means the native adapter never duplicates it.
    """
    reference = ee.Image(
        ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterBounds(roi).first()
    )
    return reference.select("SR_B4").projection()


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


def _write_coverage_figure(gdf: "gpd.GeoDataFrame", out_path: Path) -> None:
    """Write a 2-panel diagnostic map: NDVI mean and green cover % (NDVI)."""
    import matplotlib.pyplot as plt

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    plots = [
        ("ndvi_mean", "NDVI medio (Landsat-8/9, 2024)", "YlGn", "NDVI"),
        ("green_cover_pct_ndvi", "Cobertura verde NDVI≥0.20 (%)", "Greens", "%"),
    ]
    for ax, (column, title, cmap, label) in zip(axes, plots, strict=True):
        gdf.plot(
            column=column,
            ax=ax,
            cmap=cmap,
            legend=True,
            legend_kwds={"label": label, "shrink": 0.65},
            edgecolor="white",
            linewidth=0.3,
        )
        ax.set_title(title, fontsize=12)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def _write_coverage_metadata(
    path: Path,
    *,
    city: str,
    sat_cfg: dict,
    scale: int,
    n_communes: int,
    expected_units: int | None = None,
    geographic_unit: str = "spatial_unit",
    outputs: list[str],
    methodology_doc: str,
    figure: str,
    cache_fingerprint: str,
) -> None:
    """Write enriched JSON metadata for the satellite greenspace coverage layer."""
    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "geographic_unit": geographic_unit,
        "expected_communes": expected_units if expected_units is not None else n_communes,
        "expected_units": expected_units if expected_units is not None else n_communes,
        "n_communes": n_communes,
        "source": {
            "provider": "Google Earth Engine",
            "collections": [
                "LANDSAT/LC08/C02/T1_L2",
                "LANDSAT/LC09/C02/T1_L2",
            ],
            "resolution_m": scale,
            "gee_project": "exposome-api",
        },
        "collection": "LANDSAT/LC08/C02/T1_L2 + LANDSAT/LC09/C02/T1_L2",
        "years": sat_cfg["years"],
        "season_months": sat_cfg["season_months"],
        "season_note": "Southern Hemisphere spring-summer (Oct-Mar), peak greenness season",
        "ndvi_threshold": sat_cfg["ndvi_threshold"],
        "evi_threshold": sat_cfg["evi_threshold"],
        "scale_meters": scale,
        "cloud_mask": "QA_PIXEL (bits 0 fill, 3 cloud, 4 cloud shadow, 5 snow)",
        "composite_method": "Pixel-wise median of cloud-masked, scale-corrected images",
        "reducer": "mean+max via ee.Reducer.mean().combine(ee.Reducer.max(), sharedInputs=True)",
        "cache_fingerprints": {"zonal_indices": cache_fingerprint},
        "evi_sanitation": "EVI pixels outside [-1, 1] are masked before reducing (denominator instability fix)",
        "note": "Landsat-8/9 used to avoid GEE computation/download limits vs Sentinel-2 at 10 m",
        "columns": {
            "name": {"unit": "spatial-unit name", "description": "Configured spatial-unit label"},
            "area_km2": {"unit": "km²", "description": "Spatial-unit area in square kilometres"},
            "ndvi_mean": {"unit": "dimensionless [-1,1]", "description": "Mean NDVI over commune pixels, median composite"},
            "ndvi_max": {"unit": "dimensionless [-1,1]", "description": "Max NDVI over commune pixels, median composite"},
            "evi_mean": {"unit": "dimensionless [-1,1]", "description": "Mean EVI over commune pixels (anomalous pixels masked)"},
            "evi_max": {"unit": "dimensionless [-1,1]", "description": "Max EVI over commune pixels (anomalous pixels masked)"},
            "green_cover_pct_ndvi": {"unit": "percent [0,100]", "description": f"Fraction of pixels with NDVI≥{sat_cfg['ndvi_threshold']}, as %"},
            "green_cover_pct_evi": {"unit": "percent [0,100]", "description": f"Fraction of unmasked EVI pixels with EVI≥{sat_cfg['evi_threshold']}, as %"},
        },
        "limitations": [
            "30 m Landsat resolution coarser than Sentinel-2 (10 m); small urban parks may be missed.",
            "green_cover_pct_evi denominator excludes masked EVI pixels, so coverage is computed over unmasked area only.",
            "Seasonal composite uses Oct-Mar of the configured year(s); year-to-year variability not captured.",
            "Validation against independent NDVI product (e.g. MOD13A3) is pending.",
        ],
        "methodology_doc": methodology_doc,
        "diagnostic_figure": figure,
        "outputs": outputs,
    }
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")


def build_greenspace_coverage_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    figures_dir: Path = Path("figures"),
    years: list[int] | None = None,
) -> tuple[Path, Path]:
    """Build the satellite greenspace coverage layer and write CSV + GeoJSON."""
    cfg = config.load_config(city)

    cache_dir = Path(cache_dir)
    out_dir = Path(out_dir)
    figures_dir = Path(figures_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"Building greenspace coverage layer for {city}")

    # Load commune boundaries
    cache_path = cache_dir / f"{city}_communes.geojson"
    communes = boundaries.get_communes(cfg, cache_path=cache_path)

    sat_cfg = cfg["greenspace"]["satellite"]
    if years is not None:
        sat_cfg["years"] = [int(value) for value in years]
    scale = int(sat_cfg.get("scale_meters", 30))
    spatial_key = spatial_fingerprint(
        communes,
        id_column="spatial_id" if "spatial_id" in communes.columns else "name",
    )
    identity = CacheIdentity(
        layer_id="greenspace_coverage",
        operation="zonal_indices",
        parameters={
            "collections": [
                "LANDSAT/LC08/C02/T1_L2",
                "LANDSAT/LC09/C02/T1_L2",
            ],
            "bands": ["SR_B2", "SR_B4", "SR_B5", "QA_PIXEL"],
            "years": sat_cfg["years"],
            "season_months": sat_cfg["season_months"],
            "ndvi_threshold": sat_cfg["ndvi_threshold"],
            "evi_threshold": sat_cfg["evi_threshold"],
            "surface_reflectance_scale": SR_SCALE,
            "surface_reflectance_offset": SR_OFFSET,
            "qa_pixel_mask_bits": [0, 3, 4, 5],
            "evi_valid_range": [-1, 1],
            "composite": "median",
            "scale_meters": scale,
            "crs": "EPSG:4326",
            "tile_scale": 4,
            "reducers": ["mean", "max"],
        },
        spatial_fingerprint=spatial_key,
        algorithm_version="2",
    )
    store = CacheStore(cache_dir, identity)
    expected_names = communes["name"].astype(str).tolist()
    record = store.load_csv(
        "zonal",
        required_columns=[
            "name",
            "NDVI_mean",
            "NDVI_max",
            "EVI_mean",
            "EVI_max",
            "green_ndvi_mean",
            "green_evi_mean",
        ],
        expected_completed_keys=expected_names,
    )
    progress = tqdm(total=1, desc=f"greenspace_coverage [{city}]", unit="step")
    if record.hit:
        tqdm.write(f"  [zonal_ndvi_evi] {record.reason} …")
        assert record.frame is not None
        stats = {row["name"]: row for row in record.frame.to_dict("records")}
    else:
        tqdm.write(
            f"  [zonal_ndvi_evi] cache miss ({record.reason}); "
            "fetching from GEE (single reduceRegions call) …"
        )
        gee.init_gee()
        regions_fc = gee.gdf_to_feature_collection(communes)
        roi = regions_fc.geometry().bounds()
        composite = build_landsat_composite(
            roi=roi,
            years=sat_cfg["years"],
            season_months=sat_cfg["season_months"],
            ndvi_threshold=sat_cfg["ndvi_threshold"],
            evi_threshold=sat_cfg["evi_threshold"],
        )
        stats = _zonal_stats_combined(composite, regions_fc, scale)
        store.write_csv_atomic(
            "zonal",
            pd.DataFrame(list(stats.values())),
            completed_keys=stats,
        )
    progress.update(1)
    progress.close()

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
    metadata_path = out_dir / f"{base_name}_metadata.json"
    figure_path = figures_dir / f"greenspace_coverage_{city}_2panel.png"

    result.drop(columns="geometry").to_csv(csv_path, index=False)
    result_geo.to_file(geojson_path, driver="GeoJSON")

    _write_coverage_figure(result_geo, figure_path)
    _write_coverage_metadata(
        metadata_path,
        city=city,
        sat_cfg=sat_cfg,
        scale=scale,
        n_communes=int(len(result)),
        expected_units=int(cfg.get("expected_units", cfg.get("expected_communes", len(result)))),
        geographic_unit=str(cfg.get("spatial_unit_type", "spatial_unit")),
        outputs=[csv_path.name, geojson_path.name, metadata_path.name],
        methodology_doc="docs/greenspace_coverage_methodology.md",
        figure=figure_path.as_posix(),
        cache_fingerprint=identity.digest,
    )

    print(f"Wrote {csv_path.name}: {len(result)} rows x {result.drop(columns='geometry').shape[1]} columns")
    print(f"Wrote {geojson_path.name}")
    print(f"Wrote {metadata_path.name}")
    print(f"Wrote {figure_path.name}")

    return csv_path, geojson_path

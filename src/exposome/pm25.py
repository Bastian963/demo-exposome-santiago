"""High-resolution chronic PM2.5 exposome layer via GEE (ACAG / van Donkelaar).

Commune-level long-term fine particulate matter (PM2.5) exposure from the ACAG
global satellite-derived surface PM2.5 product (van Donkelaar et al.), accessed
as a Google Earth Engine asset (awesome-gee-community-catalog / sat-io). Annual
means are averaged over a multi-year window to represent *chronic* exposure.

PM2.5 is the single most-replicated environmental risk factor for dementia and
cognitive decline (Livingston et al., Lancet Commission 2024). Long-term average
exposure — not a single year — is the window relevant to brain aging, so this
layer deliberately uses a multi-year mean.

Why this layer exists: the repository already estimates surface NO2 at ~3.5 km
from Sentinel-5P, but its only PM2.5 came from the legacy CAMS reanalysis at
~11 km, which collapses ~20 communes onto the same value. ACAG resolves PM2.5 at
~1 km, recovering the intra-urban gradient (poniente/centro vs oriente) that the
NO2 upgrade already captured.

This module mirrors :mod:`exposome.alan` and :mod:`exposome.air_quality`: GEE
zonal statistics over the 52 communes, a WorldPop population-weighted mean,
strict validation (52 rows, no duplicates, no missing values), and CSV +
GeoJSON + metadata outputs ready for ``build_master_exposome``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping
from tqdm import tqdm

from . import boundaries, config, gee
from .cache import CacheIdentity, CacheStore, spatial_fingerprint

PM25_BAND = "pm25"


def _sha256_file(path: Path) -> str:
    from hashlib import sha256

    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cached_annual_raster(
    raster: Path,
    metadata_path: Path,
    *,
    year: int,
    collection_id: str,
) -> dict[str, Any] | None:
    """Return valid local annual-raster metadata without contacting GEE."""
    if not raster.is_file() or not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    support = metadata.get("temporal_support")
    if (
        metadata.get("collection") != collection_id
        or support != {
            "kind": "year",
            "year": str(year),
            "source_label": "ACAG V6.GL.02",
        }
        or metadata.get("raster_sha256") != _sha256_file(raster)
    ):
        return None
    try:
        from .native import _validate_export_grid
        from .spatial_detail import raster_grid_signature

        actual_grid = raster_grid_signature(raster)
        _validate_export_grid(
            "air_quality_pm25",
            actual_grid,
            expected_resolution_m=float(metadata["source_native_resolution_m"]),
        )
    except (ImportError, KeyError, OSError, TypeError, ValueError):
        return None
    if metadata.get("export_grid") != actual_grid:
        return None
    return metadata


def export_annual_pm25_raster(
    context: Any,
    year: int,
    output_dir: str | Path,
) -> tuple[Path, Path]:
    """Download one ACAG annual image at its verified 0.01° source grid.

    This function is called only by the human-run temporal collector.  It
    checkpoints one TIFF and one metadata file per year, and returns before
    initializing Earth Engine when that checkpoint still matches the provider
    collection, year, hash and inspected grid.
    """
    import geemap

    year = int(year)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raster = output_dir / f"pm25_{year}_native.tif"
    metadata_path = output_dir / f"pm25_{year}_native.metadata.json"
    cfg = config.load_config(context.study.id)
    collection_cfg = cfg["pm25"]["collection"]
    collection_id = str(collection_cfg["id"])
    cached = _cached_annual_raster(
        raster,
        metadata_path,
        year=year,
        collection_id=collection_id,
    )
    if cached is not None:
        return raster, metadata_path

    from .native import _gee_grid_signature, _validate_export_grid
    from .spatial_detail import raster_grid_signature

    gee.init_gee()
    units = context.load_spatial_units().to_crs(context.location.geographic_crs)
    roi = ee.Geometry(mapping(units.geometry.union_all()))
    image = _annual_pm25_image(
        cfg,
        f"{year}-01-01",
        f"{year + 1}-01-01",
    ).clip(roi)
    scale = float(collection_cfg["scale_meters"])
    source_grid = _gee_grid_signature(image)
    _validate_export_grid("air_quality_pm25", source_grid, expected_resolution_m=scale)

    partial = raster.with_name(f".{raster.stem}.partial.tif")
    partial.unlink(missing_ok=True)
    from .gee import EE_DOWNLOAD_MAX_REQUESTS, EE_DOWNLOAD_NUM_THREADS

    geemap.download_ee_image(
        image,
        filename=str(partial),
        crs=source_grid["crs"],
        crs_transform=source_grid["transform"],
        region=roi,
        resampling="near",
        # Stay under Restricted Mode's concurrency ceiling (see gee.py).
        num_threads=EE_DOWNLOAD_NUM_THREADS,
        max_requests=EE_DOWNLOAD_MAX_REQUESTS,
    )
    if not partial.is_file():
        raise RuntimeError(f"ACAG annual export did not produce {partial}")
    export_grid = raster_grid_signature(partial)
    _validate_export_grid("air_quality_pm25", export_grid, expected_resolution_m=scale)
    partial.replace(raster)

    metadata = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "study_id": context.study.id,
        "indicator_id": "pm25",
        "layer_id": "pm25",
        "collection": collection_id,
        "band": PM25_BAND,
        "units": "µg/m³",
        "source_native_resolution_m": scale,
        "source_grid": source_grid,
        "export_grid": export_grid,
        "source_support_preserved": True,
        "temporal_support": {
            "kind": "year",
            "year": str(year),
            "source_label": "ACAG V6.GL.02",
        },
        "raster": raster.name,
        "raster_sha256": _sha256_file(raster),
    }
    partial_metadata = metadata_path.with_suffix(metadata_path.suffix + ".partial")
    partial_metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    partial_metadata.replace(metadata_path)
    return raster, metadata_path


def _annual_pm25_image(cfg: dict[str, Any], start: str, end: str) -> ee.Image:
    """Multi-year mean ACAG surface PM2.5 image [µg/m^3], renamed to ``pm25``.

    Each ACAG annual image carries a single PM2.5 band whose name is not
    documented in the community catalog, so we select by configured name when
    provided and fall back to band index 0 (``band: "auto"``), then rename to a
    stable ``pm25`` band so the rest of the pipeline is name-agnostic.
    """
    pm_cfg = cfg["pm25"]["collection"]
    band = pm_cfg.get("band", "auto")
    scale_factor = pm_cfg.get("scale_factor", 1.0)

    collection = ee.ImageCollection(pm_cfg["id"]).filterDate(start, end)
    source = ee.Image(collection.first())
    if band and str(band).lower() != "auto":
        source = source.select(band)
    else:
        source = source.select(0)
    mean_img = collection.mean()
    if band and str(band).lower() != "auto":
        mean_img = mean_img.select(band)
    else:
        mean_img = mean_img.select(0)
    # ImageCollection.mean() falls back to Earth Engine's generic one-degree
    # projection.  Retain the ACAG grid so native exports do not turn a 0.01°
    # product into a handful of continent-scale cells.
    return (
        mean_img.multiply(scale_factor)
        .rename(PM25_BAND)
        .setDefaultProjection(source.projection())
    )


def fetch_pm25(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Fetch commune-level mean chronic PM2.5 [µg/m^3]."""
    pm_cfg = cfg["pm25"]
    start = start or pm_cfg["start_date"]
    end = end or pm_cfg["end_date"]
    scale = pm_cfg["collection"]["scale_meters"]

    img = _annual_pm25_image(cfg, start, end)
    stats = gee.image_to_stats(img, regions_fc, band=PM25_BAND, scale=scale, reducer="mean")
    df = pd.DataFrame(gee.fc_to_dicts(stats))
    if "mean" in df.columns:
        df = df.rename(columns={"mean": "pm25_mean"})
    return df[["name", "pm25_mean"]]


def fetch_pop_weighted_pm25(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Population-weighted mean PM2.5 per commune: sum(pm25*pop)/sum(pop).

    Reuses the ALAN WorldPop raster by default (``alan.population``) so the two
    pollution layers share an identical population denominator.
    """
    pm_cfg = cfg["pm25"]
    start = start or pm_cfg["start_date"]
    end = end or pm_cfg["end_date"]

    pop_cfg = pm_cfg.get("population") or cfg["alan"]["population"]
    pop_img = (
        ee.ImageCollection(pop_cfg["id"])
        .filter(ee.Filter.eq("country", pop_cfg["country"]))
        .filter(ee.Filter.eq("year", pop_cfg["year"]))
        .select(pop_cfg["band"])
        .mosaic()
    )
    pop_scale = pop_cfg["scale_meters"]

    pm_img = _annual_pm25_image(cfg, start, end)
    num_img = pm_img.multiply(pop_img).rename("num")
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
    df["pm25_pop_weighted"] = df["_num"] / df["_den"]
    return df[["name", "pm25_pop_weighted"]]


def build_pm25_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    years: list[int] | None = None,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Run the full chronic-PM2.5 pipeline and export commune zonal statistics.

    Returns
    -------
    df : pd.DataFrame
        Columns: name, area_km2, pm25_mean, pm25_pop_weighted, pm25_who_ratio.
    gdf : gpd.GeoDataFrame
        Same with geometry attached.
    """
    cfg = config.load_config(city)

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    years = [int(value) for value in (years or cfg["pm25"]["years"])]
    if not years:
        raise ValueError("PM2.5 requires at least one year")
    cfg["pm25"]["years"] = years
    cfg["pm25"]["start_date"] = f"{min(years)}-01-01"
    cfg["pm25"]["end_date"] = f"{max(years) + 1}-01-01"
    window = f"{years[0]}_{years[-1]}"

    # 1. Boundaries (reuse processed communes; do not re-download from OSM).
    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)
    spatial_key = spatial_fingerprint(
        gdf_comm,
        id_column="spatial_id" if "spatial_id" in gdf_comm.columns else "name",
    )
    collection_cfg = cfg["pm25"]["collection"]
    pop_cfg = cfg["pm25"].get("population") or cfg["alan"]["population"]
    common = {
        "collection": collection_cfg,
        "start": cfg["pm25"]["start_date"],
        "end_exclusive": cfg["pm25"]["end_date"],
        "output_band": PM25_BAND,
    }
    mean_identity = CacheIdentity(
        "pm25",
        "area_mean",
        {**common, "reducer": "mean"},
        spatial_key,
        "2",
    )
    population_identity = CacheIdentity(
        "pm25",
        "population_weighted",
        {
            **common,
            "population": pop_cfg,
            "reducers": {"numerator": "sum", "denominator": "sum"},
        },
        spatial_key,
        "2",
    )
    mean_store = CacheStore(cache_dir, mean_identity)
    population_store = CacheStore(cache_dir, population_identity)
    mean_record = mean_store.load_csv(window, required_columns=["name", "pm25_mean"])
    population_record = population_store.load_csv(
        window, required_columns=["name", "pm25_pop_weighted"]
    )
    regions_fc: ee.FeatureCollection | None = None
    if not (mean_record.hit and population_record.hit):
        gee.init_gee()
        regions_fc = gee.gdf_to_feature_collection(gdf_comm)

    # 2-3. Mean chronic PM2.5 + population-weighted chronic PM2.5 (each a
    # single cached GEE call).
    progress = tqdm(total=2, desc=f"pm25 [{city}]", unit="step")

    if mean_record.hit:
        tqdm.write(f"  [pm25_mean] {mean_record.reason} …")
        assert mean_record.frame is not None
        df_pm = mean_record.frame
    else:
        tqdm.write(f"  [pm25_mean] cache miss ({mean_record.reason}); fetching from GEE …")
        assert regions_fc is not None
        df_pm = fetch_pm25(cfg, regions_fc)
        mean_record = mean_store.write_csv_atomic(window, df_pm)
    progress.update(1)

    if population_record.hit:
        tqdm.write(f"  [pm25_pop_weighted] {population_record.reason} …")
        assert population_record.frame is not None
        df_popw = population_record.frame
    else:
        tqdm.write(
            f"  [pm25_pop_weighted] cache miss ({population_record.reason}); "
            "fetching from GEE …"
        )
        assert regions_fc is not None
        df_popw = fetch_pop_weighted_pm25(cfg, regions_fc)
        population_record = population_store.write_csv_atomic(window, df_popw)
    progress.update(1)
    progress.close()

    # 4. Merge
    df = gdf_comm[["name", "area_km2"]].copy()
    df = df.merge(df_pm, on="name", how="left")
    df = df.merge(df_popw, on="name", how="left")

    # 4b. Fallback for missing population-weighting (tiny communes not covered by
    #     the population raster): use the area mean PM2.5 instead.
    if df["pm25_pop_weighted"].isna().any():
        missing = df.loc[df["pm25_pop_weighted"].isna(), "name"].tolist()
        df["pm25_pop_weighted"] = df["pm25_pop_weighted"].fillna(df["pm25_mean"])
        print(f"Warning: filled pop-weighted PM2.5 for {missing} with area mean")

    # 5. WHO 2021 ratio (reuses the air-quality guideline already in config).
    who_pm25 = cfg["air_quality"]["who_guidelines"]["pm25"]
    df["pm25_who_ratio"] = df["pm25_mean"] / who_pm25

    # 6. Formatting
    df["pm25_mean"] = df["pm25_mean"].round(2)
    df["pm25_pop_weighted"] = df["pm25_pop_weighted"].round(2)
    df["pm25_who_ratio"] = df["pm25_who_ratio"].round(2)

    # 7. Validate
    n_expected = cfg["expected_communes"]
    if len(df) != n_expected:
        raise ValueError(f"Expected {n_expected} rows, got {len(df)}")
    if df["name"].duplicated().any():
        raise ValueError("Duplicate commune names")
    if df.isna().any().any():
        missing = df.columns[df.isna().any()].tolist()
        raise ValueError(f"Missing values in: {missing}")

    # 8. Geo version
    gdf = gdf_comm[["name", "geometry"]].merge(df, on="name", how="right")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    # 9. Write outputs
    base_name = f"{city}_pm25_acag_{window}"
    df.to_csv(out_dir / f"{base_name}.csv", index=False)
    gdf.to_file(out_dir / f"{base_name}.geojson", driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "years": years,
        "method": (
            "ACAG/van Donkelaar satellite-derived surface PM2.5 (AOD + GEOS-Chem "
            "+ residual CNN calibrated to ground monitors); multi-year mean as a "
            "chronic-exposure proxy; commune zonal statistics + WorldPop "
            "population-weighted mean."
        ),
        "resolution_m": cfg["pm25"]["collection"]["scale_meters"],
        "units": "µg/m^3",
        "exposure_window": "chronic (multi-year mean)",
        "who_guideline_pm25_ug_m3": who_pm25,
        "sources": {
            "pm25": {
                "provider": "Atmospheric Composition Analysis Group (WashU) — van Donkelaar et al.",
                "collection": cfg["pm25"]["collection"]["id"],
                "catalog": "awesome-gee-community-catalog (sat-io)",
            },
            "population": {
                "provider": "WorldPop",
                "collection": pop_cfg["id"],
                "year": pop_cfg["year"],
            },
        },
        "cache_fingerprints": {
            "area_mean": mean_identity.digest,
            "population_weighted": population_identity.digest,
        },
        "columns": df.columns.tolist(),
        "n_rows": len(df),
    }
    meta_path = out_dir / f"{base_name}_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(f"Wrote {base_name}.csv / .geojson ({len(df)} rows x {df.shape[1]} cols)")
    return df, gdf

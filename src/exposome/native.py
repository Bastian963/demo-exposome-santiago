"""Native-resolution products and point queries for AOI-based studies.

This module is deliberately separate from the polygon aggregation pipeline.
An AOI limits downloads, while each layer keeps the spatial support supplied by
its provider (raster, climate node, OSM feature, or street network).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import geopandas as gpd
import pandas as pd
from shapely.geometry import mapping, Point, box


@dataclass(frozen=True)
class NativeLayerSpec:
    layer_id: str
    kind: str
    native_resolution_m: float | None
    units: str
    description: str
    requires_component_products: bool = False


# Kinds whose native product is a GeoTIFF on disk at `<layer_id>_native.tif`.
# `gee_raster` and `raster` differ only in provenance: the first is exported
# from Earth Engine, the second is fetched from a provider Earth Engine does
# not serve for our cities (ECOSTRESS).  Consumers care about the file, not
# the provider, so they branch on this set instead of on a single kind.
RASTER_KINDS = frozenset({"gee_raster", "raster"})


NATIVE_LAYER_SPECS: dict[str, NativeLayerSpec] = {
    "air_quality_pm25": NativeLayerSpec("air_quality_pm25", "gee_raster", 1113, "ug/m3", "ACAG chronic surface PM2.5"),
    "alan": NativeLayerSpec("alan", "gee_raster", 463.83, "nW/cm2/sr", "VIIRS annual radiance"),
    "greenspace_coverage": NativeLayerSpec("greenspace_coverage", "gee_raster", 30, "index", "Landsat NDVI/EVI composite"),
    "greenspace_multisource": NativeLayerSpec("greenspace_multisource", "gee_raster", 1, "fraction", "Meta canopy source aggregated to a 30 m canopy-cover grid"),
    "precipitation": NativeLayerSpec("precipitation", "gee_raster", 5566, "mm", "CHIRPS period mean precipitation"),
    "climate_heat": NativeLayerSpec("climate_heat", "gee_raster", 11132, "mixed", "ERA5-Land physical heat metrics; no city-relative index"),
    "wind": NativeLayerSpec("wind", "gee_raster", 11132, "m/s", "ERA5-Land wind components and speed"),
    # Burned area (MODIS, 500 m) and active fire (FIRMS, 1 km) do not share a
    # provider grid.  They must be exported as separate products; a generic
    # multiband TIFF would put one component on the other component's grid.
    "wildfire": NativeLayerSpec(
        "wildfire",
        "gee_raster",
        500,
        "native units",
        "MODIS burned area and FIRMS fire activity",
        requires_component_products=True,
    ),
    # NO2 band only (Sentinel-5P, 1113 m) — finer than wind/wildfire above,
    # which already have native support. O3 (7000 m) and AOD (3000 m) are
    # deliberately left out: bundling them into one multi-band export would
    # force a single output scale and oversample the coarser bands, which
    # CLAUDE.md's max-resolution policy forbids. See
    # docs/resolution_manifest.md Hallazgo 3.
    "air_quality_satellite": NativeLayerSpec("air_quality_satellite", "gee_raster", 1113, "mol/m2", "Sentinel-5P TROPOMI NO2 tropospheric column density"),
    # Earth Engine hosts ECO_L2T_LSTE but has only ingested tiles over the Los
    # Angeles metro area, so no Latin American city can be served from it.  The
    # raster is produced by scripts/run_climate_lst_ecostress.py against NASA
    # Earthdata and lands on the same `<layer_id>_native.tif` contract.
    "climate_lst_ecostress": NativeLayerSpec("climate_lst_ecostress", "raster", 70, "degC", "ECOSTRESS land surface temperature binned by local solar hour"),
    "greenspace_access": NativeLayerSpec("greenspace_access", "osm_features", None, "native OSM", "OSM green-area polygons"),
    "walkability": NativeLayerSpec("walkability", "osm_network", None, "native OSM", "OSM street network"),
    "social_infrastructure": NativeLayerSpec("social_infrastructure", "osm_features", None, "native OSM", "OSM social POIs"),
    "food_environment": NativeLayerSpec("food_environment", "osm_features", None, "native OSM", "OSM food POIs"),
    "healthcare": NativeLayerSpec("healthcare", "osm_features", None, "native OSM", "OSM health POIs"),
}


def native_temporal_support(
    cfg: Mapping[str, Any], layer_id: str
) -> dict[str, Any] | None:
    """Return the exact temporal slice represented by a native raster.

    Most native products represent a period or have no browser year selector.
    Physical heat is different: its current COG is one ERA5-Land reference
    year while the aggregate study also carries Open-Meteo columns for older
    years.  Publishing this distinction prevents the reference-year COG from
    being reused for every slider stop.
    """
    if layer_id == "air_quality_pm25":
        pm25 = cfg.get("pm25", {})
        years = sorted(int(year) for year in pm25.get("years", []) or [])
        if not years:
            try:
                start_year = int(str(pm25["start_date"])[:4])
                # end_date is exclusive in the ACAG configuration.
                end_year = int(str(pm25["end_date"])[:4]) - 1
            except (KeyError, TypeError, ValueError):
                return None
        else:
            start_year, end_year = years[0], years[-1]
        return {
            "kind": "period",
            "start_year": str(start_year),
            "end_year": str(end_year),
            "aggregation": "mean",
            "source_label": "ACAG V6.GL.02",
        }
    if layer_id != "climate_heat":
        return None
    heat = cfg.get("climate_heat", cfg.get("climate", {}))
    year = int(
        heat.get(
            "year",
            cfg.get("study_period", {}).get("reference_year", 2024),
        )
    )
    return {
        "kind": "year",
        "year": str(year),
        "source_label": "ERA5-Land",
    }


def load_native_aoi(context: Any) -> gpd.GeoDataFrame:
    """Load and validate the AOI polygon for a native study."""
    if not getattr(context, "is_native", False):
        raise ValueError(f"Study {getattr(context.study, 'id', '<unknown>')!r} is not native")
    path = getattr(context, "aoi_path", None) or getattr(context, "spatial_path", None)
    if path is None or not Path(path).exists():
        raise FileNotFoundError(f"Native AOI not found: {path or '<unset>'}")
    raw = gpd.read_file(path)
    if raw.empty:
        raise ValueError(f"Native AOI is empty: {path}")
    if raw.crs is None:
        raise ValueError(f"Native AOI has no CRS: {path}")
    raw = raw.to_crs(context.location.geographic_crs)
    allowed = {"Polygon", "MultiPolygon"}
    if not set(raw.geometry.geom_type).issubset(allowed):
        raise ValueError("Native AOI must contain only Polygon or MultiPolygon geometries")
    if raw.geometry.is_empty.any() or (~raw.geometry.is_valid).any():
        raise ValueError("Native AOI contains empty or invalid geometries")
    bbox = context.location.bbox.as_tuple()
    if not raw.geometry.intersects(box(*bbox)).any():
        raise ValueError("Native AOI does not overlap the configured location bbox")
    raw = raw.copy()
    raw["aoi_id"] = [f"aoi_{i:04d}" for i in range(len(raw))]
    return raw


def aoi_geometry(aoi: gpd.GeoDataFrame) -> Any:
    """Return a single WGS84 shapely geometry for provider clipping."""
    return aoi.geometry.union_all()


def native_output_dir(context: Any, layer_id: str) -> Path:
    return Path(context.paths.layer_processed(layer_id))


def write_native_metadata(
    context: Any,
    layer_id: str,
    *,
    outputs: Sequence[Path],
    method: str,
    extra: Mapping[str, Any] | None = None,
) -> Path:
    spec = NATIVE_LAYER_SPECS[layer_id]
    out_dir = native_output_dir(context, layer_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, Any] = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "study": context.study.id,
        "location": context.location.to_dict(),
        "mode": "native",
        "aoi": {
            "path": str(context.aoi_path or context.spatial_path),
            "source": context.study.aoi_source,
            "license": context.study.aoi_license,
        },
        "layer": layer_id,
        "product_kind": spec.kind,
        "native_resolution_m": spec.native_resolution_m,
        "units": spec.units,
        "description": spec.description,
        "method": method,
        "outputs": [str(Path(item).name) for item in outputs],
    }
    if extra:
        metadata.update(dict(extra))
    path = out_dir / "metadata.json"
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _gee_image(cfg: Mapping[str, Any], layer_id: str, roi: Any) -> tuple[Any, float, str]:
    """Build a clipped EE image using the existing layer-specific composites."""
    import ee

    if layer_id == "air_quality_pm25":
        from .pm25 import _annual_pm25_image

        image = _annual_pm25_image(dict(cfg), cfg["pm25"]["start_date"], cfg["pm25"]["end_date"])
        scale = float(cfg["pm25"]["collection"]["scale_meters"])
        return image.clip(roi), scale, "pm25"
    if layer_id == "alan":
        from .alan import _annual_radiance_image

        image = _annual_radiance_image(dict(cfg), cfg["alan"]["start_date"], cfg["alan"]["end_date"])
        scale = float(cfg["alan"]["collection"]["scale_meters"])
        return image.clip(roi), scale, cfg["alan"]["collection"]["band"]
    if layer_id == "greenspace_coverage":
        from .greenspace_satellite import build_landsat_composite, landsat_source_projection

        sat = cfg["greenspace"]["satellite"]
        image = build_landsat_composite(
            roi,
            list(sat["years"]),
            list(sat["season_months"]),
            float(sat["ndvi_threshold"]),
            float(sat["evi_threshold"]),
        )
        # build_landsat_composite's .median() reduction drops the 30 m provider
        # projection, so the export collapses to EE's 1-degree fallback and
        # _validate_export_grid rejects it. Pin it back onto the Landsat SR grid,
        # mirroring the precipitation/wind/climate_heat branches above.
        image = image.setDefaultProjection(landsat_source_projection(roi))
        return image, float(sat["scale_meters"]), "NDVI,EVI,green_ndvi,green_evi"
    if layer_id == "greenspace_multisource":
        # The Meta canopy source is 1 m, but its documented uncertainty makes
        # a 1 m browser claim invalid. Aggregate the binary canopy mask to a
        # real 30 m fraction before export; this is an analysis operation, not
        # a cartographic resample.
        from .greenspace_multisource import build_canopy_image

        canopy_cfg = cfg["greenspace"]["canopy"]
        canopy_cover = build_canopy_image(
            roi,
            collection_id=canopy_cfg["collection"],
            band=canopy_cfg["band"],
            min_height_m=float(canopy_cfg["min_height_m"]),
        ).select("canopy_cover")
        analysis_scale_m = int(canopy_cfg["sample_scale_meters"])
        cover_fraction = (
            canopy_cover.reduceResolution(reducer=ee.Reducer.mean(), maxPixels=4096)
            .reproject(crs=canopy_cover.projection(), scale=analysis_scale_m)
            .rename("canopy_cover_pct")
        )
        return cover_fraction.clip(roi), float(analysis_scale_m), "canopy_cover_pct"
    if layer_id == "precipitation":
        block = cfg["precipitation"]
        collection_id = block["collection"]["id"]
        band = block["collection"]["band"]
        years = [int(year) for year in block.get("years", [])]
        if not years:
            raise ValueError("precipitation.years is required for native detail")
        thresholds = block.get("thresholds", {})
        wet_day = float(thresholds.get("wet_day_mm", 1.0))
        heavy_day = float(thresholds.get("heavy_day_mm", 10.0))
        annual_totals: list[Any] = []
        annual_cdds: list[Any] = []
        annual_heavy_days: list[Any] = []
        source_projection = (
            ee.Image(ee.ImageCollection(collection_id).first())
            .select(band)
            .projection()
        )

        for year in years:
            daily = (
                ee.ImageCollection(collection_id)
                .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
                .select(band)
            )
            # Earth Engine infers a different integer range for count bands in
            # leap years (0..366) and ordinary years (0..365).  A collection
            # of those inferred integer types is invalid.  These are period
            # means, so normalize every annual component to Float before the
            # cross-year collection is built.
            annual_totals.append(daily.sum().rename("precip_annual_mm").toFloat())
            annual_heavy_days.append(
                daily.map(lambda image: image.gte(heavy_day))
                .sum()
                .rename("precip_heavy_days_10mm")
                .toFloat()
            )

            def _dry_run_step(image: Any, state: Any) -> Any:
                previous = ee.Image(state)
                current = ee.Image(image)
                run = previous.select("dry_run").add(1).multiply(current.lt(wet_day))
                maximum = previous.select("max_dry_run").max(run)
                return run.rename("dry_run").addBands(maximum.rename("max_dry_run"))

            initial = ee.Image.constant([0, 0]).rename(["dry_run", "max_dry_run"])
            final_state = ee.Image(daily.iterate(_dry_run_step, initial))
            annual_cdds.append(
                final_state.select("max_dry_run").rename("precip_cdd_days").toFloat()
            )

        annual_mean = ee.ImageCollection.fromImages(annual_totals).mean().rename("precip_annual_mean_mm")
        cdd_mean = ee.ImageCollection.fromImages(annual_cdds).mean().rename("precip_cdd_days")
        heavy_mean = (
            ee.ImageCollection.fromImages(annual_heavy_days)
            .mean()
            .rename("precip_heavy_days_10mm")
        )
        image = (
            annual_mean.addBands(cdd_mean)
            .addBands(heavy_mean)
            .setDefaultProjection(source_projection)
            .clip(roi)
        )
        return (
            image,
            float(block["collection"]["scale_meters"]),
            "precip_annual_mean_mm,precip_cdd_days,precip_heavy_days_10mm",
        )
    if layer_id == "wind":
        block = cfg["wind"]
        coll = ee.ImageCollection(block["id"]).filterDate(
            block["start_date"], block["end_date"]
        ).select(["u_component_of_wind_10m", "v_component_of_wind_10m"])
        source_projection = (
            ee.Image(coll.first()).select("u_component_of_wind_10m").projection()
        )
        mean = coll.mean()
        speed = mean.select("u_component_of_wind_10m").pow(2).add(
            mean.select("v_component_of_wind_10m").pow(2)
        ).sqrt().rename("wind_speed_mean")
        image = mean.addBands(speed).setDefaultProjection(source_projection).clip(roi)
        return image, float(block["scale_meters"]), "u_component_of_wind_10m,v_component_of_wind_10m,wind_speed_mean"
    if layer_id == "climate_heat":
        # Materialize the *same physical metrics* used by the aggregate heat
        # layer.  The study-level heat index is deliberately absent: it is a
        # z-score across administrative summaries, not an ERA5-Land pixel.
        heat = cfg.get("climate_heat", cfg.get("climate", {}))
        year = int(heat.get("year", cfg.get("study_period", {}).get("reference_year", 2024)))
        start = f"{year}-01-01"
        end = f"{year + 1}-01-01"
        daily = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR").filterDate(start, end)
        source_projection = (
            ee.Image(daily.first()).select("temperature_2m_max").projection()
        )
        summer_months = list(
            cfg.get("climate", {}).get("seasons", {}).get("summer", [12, 1, 2])
        )
        if not summer_months or any(int(month) not in range(1, 13) for month in summer_months):
            raise ValueError("climate.seasons.summer must contain calendar months 1..12")
        resolved_summer_months = sorted({int(month) for month in summer_months})
        summer = daily.filter(
            ee.Filter.calendarRange(resolved_summer_months[0], resolved_summer_months[0], "month")
        )
        for month in resolved_summer_months[1:]:
            summer = summer.merge(daily.filter(ee.Filter.calendarRange(month, month, "month")))
        summer_tmax = (
            summer.select("temperature_2m_max")
            .mean()
            .subtract(273.15)
            .rename("summer_tmax_mean_c")
        )
        hot_days = (
            daily.select("temperature_2m_max")
            .map(lambda image: image.gte(303.15))
            .sum()
            .rename("hot_days_30c")
        )
        tropical_nights = (
            daily.select("temperature_2m_min")
            .map(lambda image: image.gte(293.15))
            .sum()
            .rename("tropical_nights_20c")
        )
        return (
            summer_tmax.addBands(hot_days)
            .addBands(tropical_nights)
            .setDefaultProjection(source_projection)
            .clip(roi),
            11132.0,
            "summer_tmax_mean_c,hot_days_30c,tropical_nights_20c",
        )
    if layer_id == "air_quality_satellite":
        from .air_quality import _annual_no2_image

        aq_cfg = cfg["air_quality"]
        image = _annual_no2_image(dict(cfg), aq_cfg["start_date"], aq_cfg["end_date"])
        no2_cfg = aq_cfg["collections"]["no2"]
        return image.clip(roi), float(no2_cfg["scale_meters"]), no2_cfg["band"]
    if layer_id == "wildfire":
        # MODIS burned area (500 m) and FIRMS fire activity (1 km) do not share
        # a provider grid, so they cannot be a single multi-band image without
        # oversampling one onto the other. They are exported as separate
        # products by _gee_component_images; see export_gee_native_layer.
        raise ValueError(
            "wildfire has no single-image native adapter; it is exported as "
            "separate component products (burned_area, active_fire)"
        )
    raise ValueError(f"Layer {layer_id!r} has no GEE native image adapter")


def _gee_component_images(
    cfg: Mapping[str, Any], layer_id: str, roi: Any
) -> list[tuple[str, Any, float, str]]:
    """Return one ``(component, image, scale, bands)`` per native source grid.

    Some native layers combine sources that do not share a provider grid.
    Rather than fuse them into a false single-scale multi-band TIFF (which the
    max-resolution policy forbids), each component is materialized on its own
    native grid and exported to its own file.  Each component's projection is
    pinned back with ``setDefaultProjection`` so a ``.max()`` reduction cannot
    collapse it to Earth Engine's 1-degree fallback.
    """
    import ee

    if layer_id == "wildfire":
        block = cfg["wildfire"]["collections"]
        years = cfg["wildfire"]["years"]
        start = f"{min(years)}-01-01"
        end = f"{max(years) + 1}-01-01"
        components: list[tuple[str, Any, float, str]] = []
        for component, band_name, reduce_fn in (
            ("burned_area", "burned_any", lambda source: source.max().gt(0)),
            ("active_fire", "fire_brightness_max", lambda source: source.max()),
        ):
            component_cfg = block[component]
            source = (
                ee.ImageCollection(component_cfg["id"])
                .filterDate(start, end)
                .select(component_cfg["band"])
            )
            source_projection = (
                ee.Image(source.first()).select(component_cfg["band"]).projection()
            )
            image = (
                reduce_fn(source)
                .rename(band_name)
                .setDefaultProjection(source_projection)
                .clip(roi)
            )
            # The strict native grid check compares the export against the real
            # provider grid, not the nominal product label: MODIS "500 m" is
            # 463.31 m and FIRMS "1 km" is 926.63 m in Earth Engine. Use the
            # source's true nominalScale (native_scale_meters) so a correct
            # export is not rejected; fall back to the nominal label if unset.
            native_scale = float(
                component_cfg.get("native_scale_meters", component_cfg["scale_meters"])
            )
            components.append((component, image, native_scale, band_name))
        return components
    raise ValueError(f"Layer {layer_id!r} has no GEE component adapter")


def _gee_grid_signature(image: Any) -> dict[str, Any]:
    """Read the first band's provider grid before exporting it.

    Passing a numeric ``scale`` to Earth Engine can silently construct a new
    grid.  A native bundle must instead carry the source CRS and affine
    transform, which also gives later publication code evidence independent of
    a manually edited metadata scale.
    """
    projection = image.select(0).projection().getInfo()
    crs = projection.get("crs") if isinstance(projection, Mapping) else None
    transform = projection.get("transform") if isinstance(projection, Mapping) else None
    if not isinstance(crs, str) or not isinstance(transform, list) or len(transform) != 6:
        raise ValueError("Earth Engine image has no concrete source CRS/transform")
    try:
        transform_values = [float(value) for value in transform]
    except (TypeError, ValueError) as exc:
        raise ValueError("Earth Engine image has an invalid source transform") from exc
    unit = "degree" if crs.upper() == "EPSG:4326" else "m"
    return {
        "crs": crs,
        "transform": transform_values,
        "resolution": {
            "x": abs(transform_values[0]),
            "y": abs(transform_values[4]),
            "unit": unit,
        },
    }


def _grid_resolution_m(grid: Mapping[str, Any]) -> float:
    """Return a grid's nominal resolution in metres for contract checks."""
    resolution = grid.get("resolution")
    if not isinstance(resolution, Mapping):
        raise ValueError("grid has no resolution")
    try:
        x = abs(float(resolution["x"]))
        y = abs(float(resolution["y"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("grid has an invalid resolution") from exc
    unit = resolution.get("unit")
    if unit == "degree":
        # Earth Engine's nominalScale uses the equatorial metre equivalent.
        return (x + y) / 2 * 111_320.0
    if unit == "m":
        return (x + y) / 2
    raise ValueError(f"unsupported grid resolution unit: {unit!r}")


def _validate_export_grid(
    layer_id: str,
    grid: Mapping[str, Any],
    *,
    expected_resolution_m: float,
) -> None:
    """Reject GEE's generic one-degree fallback and other false grids."""
    actual = _grid_resolution_m(grid)
    if expected_resolution_m <= 0:
        raise ValueError(f"Layer {layer_id!r} has no positive export resolution")
    if abs(actual / expected_resolution_m - 1.0) > 0.05:
        raise ValueError(
            f"Layer {layer_id!r} resolved to a {actual:g} m grid, expected "
            f"approximately {expected_resolution_m:g} m. A collection reducer may "
            "have lost its provider projection; use setDefaultProjection() before export."
        )


def _download_and_verify_gee_image(
    geemap: Any,
    image: Any,
    tif: Path,
    ee_roi: Any,
    *,
    layer_id: str,
    scale: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Download one native GEE image at its provider grid and verify it.

    Returns ``(source_grid, export_grid)``.  Rejects Earth Engine's 1-degree
    fallback both before and after the download, and raises loudly if the file
    was never written (a silent failure that once wrote success metadata for a
    missing .tif).
    """
    source_grid = _gee_grid_signature(image)
    _validate_export_grid(layer_id, source_grid, expected_resolution_m=scale)
    # download_ee_image (backed by geedim) tiles and reassembles large images
    # transparently, unlike ee_export_image's single synchronous request
    # (~48 MB cap) — required for greenspace_coverage over a Santiago-sized
    # AOI (~1.17 GB request, ~23x the old limit; see
    # docs/resolution_manifest.md Hallazgo 3b). It falls back to a plain
    # single-request download when the image fits, so this is safe for the
    # small exports (pm25/alan/precipitation/wind/NO2/wildfire components) too.
    from .gee import EE_DOWNLOAD_MAX_REQUESTS, EE_DOWNLOAD_NUM_THREADS

    geemap.download_ee_image(
        image,
        filename=str(tif),
        crs=source_grid["crs"],
        crs_transform=source_grid["transform"],
        region=ee_roi,
        resampling="near",
        # Stay under Restricted Mode's concurrency ceiling (see gee.py).
        num_threads=EE_DOWNLOAD_NUM_THREADS,
        max_requests=EE_DOWNLOAD_MAX_REQUESTS,
    )
    if not tif.exists():
        # Defensive guard kept even though download_ee_image raises on
        # failure rather than silently printing (unlike the old
        # ee_export_image) — without it a future regression could again
        # write success metadata for a .tif that was never created, which
        # then breaks `exposome verify` far from the actual cause.
        raise RuntimeError(
            f"GEE native export for {layer_id!r} did not produce {tif} — see the "
            "download log above for the underlying error (a common cause is "
            "exceeding GEE's export limits on a very large AOI)."
        )
    from .spatial_detail import raster_grid_signature

    export_grid = raster_grid_signature(tif)
    _validate_export_grid(layer_id, export_grid, expected_resolution_m=scale)
    return source_grid, export_grid


def export_gee_native_layer(context: Any, layer_id: str) -> tuple[Path, ...]:
    """Export a native GEE product and write provenance metadata.

    Most layers are a single provider grid: one image, one ``.tif``.  Layers
    whose spec sets ``requires_component_products`` (wildfire) combine sources
    on different native grids and are exported as one ``.tif`` per component so
    neither is oversampled onto the other's grid.  Returns the written ``.tif``
    path(s) followed by the metadata path.
    """
    import ee
    import geemap
    from . import config as legacy_config
    from . import gee as gee_helpers

    spec = NATIVE_LAYER_SPECS[layer_id]
    aoi = load_native_aoi(context)
    roi = aoi_geometry(aoi)
    cfg = legacy_config.load_config(context.study.id)
    # Resolve the quota project through the same node-local configuration used
    # by aggregated GEE layers. Credentials remain outside the repository.
    gee_helpers.init_gee()
    ee_roi = ee.Geometry(mapping(roi))
    out_dir = native_output_dir(context, layer_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    if spec.requires_component_products:
        outputs: list[Path] = []
        components_meta: list[dict[str, Any]] = []
        for component, image, scale, bands in _gee_component_images(cfg, layer_id, ee_roi):
            tif = out_dir / f"{layer_id}_{component}_native.tif"
            source_grid, export_grid = _download_and_verify_gee_image(
                geemap, image, tif, ee_roi, layer_id=layer_id, scale=scale
            )
            outputs.append(tif)
            components_meta.append(
                {
                    "component": component,
                    "output": tif.name,
                    "bands": bands.split(","),
                    "scale_m": scale,
                    "source_grid": source_grid,
                    "export_grid": export_grid,
                }
            )
        extra: dict[str, Any] = {
            "source_native_resolution_m": spec.native_resolution_m,
            "components": components_meta,
            "source_grid_verified": True,
        }
        temporal_support = native_temporal_support(cfg, layer_id)
        if temporal_support is not None:
            extra["temporal_support"] = temporal_support
        metadata = write_native_metadata(
            context,
            layer_id,
            outputs=outputs,
            method=(
                f"Source components exported separately over the {context.study.id} AOI, "
                "each on its own native provider grid (no cross-grid resampling)."
            ),
            extra=extra,
        )
        return (*outputs, metadata)

    image, scale, bands = _gee_image(cfg, layer_id, ee_roi)
    tif = out_dir / f"{layer_id}_native.tif"
    source_grid, export_grid = _download_and_verify_gee_image(
        geemap, image, tif, ee_roi, layer_id=layer_id, scale=scale
    )
    extra = {
        "bands": bands.split(","),
        "scale_m": scale,
        "source_native_resolution_m": spec.native_resolution_m,
        "analysis_resolution_m": scale,
        "source_grid": source_grid,
        "export_grid": export_grid,
        "source_grid_verified": True,
    }
    temporal_support = native_temporal_support(cfg, layer_id)
    if temporal_support is not None:
        extra["temporal_support"] = temporal_support
    metadata = write_native_metadata(
        context,
        layer_id,
        outputs=[tif],
        method=(
            f"Existing layer-specific GEE composite exported over the {context.study.id} AOI "
            "at its declared analysis grid."
        ),
        extra=extra,
    )
    return tif, metadata


def _grid_points(aoi: gpd.GeoDataFrame, step_deg: float) -> gpd.GeoDataFrame:
    geom = aoi_geometry(aoi)
    minx, miny, maxx, maxy = geom.bounds
    rows: list[dict[str, Any]] = []
    lon = minx
    index = 0
    while lon <= maxx + 1e-9:
        lat = miny
        while lat <= maxy + 1e-9:
            point = Point(lon, lat)
            if geom.covers(point):
                rows.append({"location_id": index, "source": "grid", "lon": lon, "lat": lat, "geometry": point})
                index += 1
            lat += step_deg
        lon += step_deg
    if not rows:
        point = geom.representative_point()
        rows.append({"location_id": 0, "source": "representative", "lon": point.x, "lat": point.y, "geometry": point})
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=aoi.crs)


def export_native_climate(context: Any) -> tuple[Path, Path, Path]:
    """Fetch the existing Open-Meteo grid cache over the AOI and preserve nodes."""
    from .climate.fetch_grid_openmeteo import ensure_grid_daily
    from . import config as legacy_config

    aoi = load_native_aoi(context)
    cfg = legacy_config.load_config(context.study.id)
    step = float(cfg.get("climate_heat", {}).get("grid_step_deg", 0.10))
    points = _grid_points(aoi, step)
    year = int(cfg.get("climate_heat", {}).get("year", 2024))
    cache_dir = Path(context.paths.layer_cache("climate_heat"))
    cache = cache_dir / f"climate_heat_grid_daily_{year}.csv"
    if cache.exists():
        cached = pd.read_csv(cache, usecols=["location_id", "lat", "lon"])
        expected = points[["location_id", "lat", "lon"]].sort_values("location_id").reset_index(drop=True)
        observed = cached.drop_duplicates().sort_values("location_id").reset_index(drop=True)
        if not expected.equals(observed):
            cache.unlink(missing_ok=True)
            (cache_dir / f"climate_heat_grid_daily_{year}.partial.csv").unlink(missing_ok=True)
    daily = ensure_grid_daily(
        points.drop(columns="geometry"),
        year=year,
        cache_dir=cache_dir,
        timezone=context.location.timezone or "auto",
        request_sleep_s=0,
    )
    out_dir = native_output_dir(context, "climate_heat")
    out_dir.mkdir(parents=True, exist_ok=True)
    points_path = out_dir / "climate_heat_native_points.geojson"
    daily_path = out_dir / f"climate_heat_native_daily_{year}.csv"
    points.to_file(points_path, driver="GeoJSON")
    pd.read_csv(daily).to_csv(daily_path, index=False)
    metadata = write_native_metadata(
        context,
        "climate_heat",
        outputs=[points_path, daily_path],
        method="Open-Meteo archive daily values on a regular AOI grid; nearest-node lookup, no artificial downscaling.",
        extra={"year": year, "grid_step_deg": step, "n_nodes": len(points)},
    )
    return points_path, daily_path, metadata


def _gpkg_safe_field_name(value: Any) -> str:
    """Return a conservative GeoPackage/Fiona-compatible field name."""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = re.sub(r"[^A-Za-z0-9_]", "_", text).strip("_") or "field"
    if text[0].isdigit():
        text = f"field_{text}"
    return text


def _prepare_gpkg_frame(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Sanitize raw OSM columns and values before writing a GeoPackage.

    OSM tag keys are not database field names.  In CDMX, for example,
    ``currency:MXN`` made Fiona abort after the expensive Overpass download.
    We retain every tag, but normalize field names deterministically and JSON
    encode container values that Fiona cannot serialize natively.
    """
    result = frame.copy()
    if not isinstance(result.index, pd.RangeIndex) or result.index.name is not None:
        index_names = [name for name in result.index.names if name is not None]
        if index_names and all(name not in result.columns for name in index_names):
            result = result.reset_index()
        else:
            result = result.reset_index(drop=True)

    used: set[str] = set()
    rename: dict[Any, str] = {}
    for column in result.columns:
        if column == result.geometry.name:
            safe = "geometry"
        else:
            base = _gpkg_safe_field_name(column)
            safe = base
            suffix = 2
            while safe.casefold() in used:
                safe = f"{base}_{suffix}"
                suffix += 1
        used.add(safe.casefold())
        rename[column] = safe
    result = result.rename(columns=rename).set_geometry("geometry")

    def serializable(value: Any) -> Any:
        if isinstance(value, (dict, list, tuple, set)):
            if isinstance(value, set):
                value = sorted(value, key=str)
            return json.dumps(value, ensure_ascii=False, sort_keys=isinstance(value, dict))
        return value

    for column in result.columns:
        if column != result.geometry.name and result[column].dtype == object:
            result[column] = result[column].map(serializable)
    return gpd.GeoDataFrame(result, geometry="geometry", crs=frame.crs)


def _write_gpkg_atomic(frame: gpd.GeoDataFrame, path: Path, *, layer: str) -> None:
    """Write one GeoPackage atomically so a failed export cannot look complete."""
    temporary = path.with_name(f".{path.stem}.tmp.gpkg")
    temporary.unlink(missing_ok=True)
    try:
        _prepare_gpkg_frame(frame).to_file(temporary, layer=layer, driver="GPKG")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def export_native_osm(context: Any, layer_id: str) -> tuple[Path, Path]:
    """Cache raw OSM features/network; derived point metrics remain query-time."""
    import osmnx as ox
    from .osm_fetch import fetch_features_from_bbox_tiled

    aoi = load_native_aoi(context)
    minx, miny, maxx, maxy = aoi_geometry(aoi).bounds
    out_dir = native_output_dir(context, layer_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    if layer_id == "walkability":
        graph = ox.graph_from_bbox((minx, miny, maxx, maxy), network_type="walk", simplify=True)
        nodes, edges = ox.graph_to_gdfs(graph)
        path = out_dir / "walkability_native.gpkg"
        _prepare_gpkg_frame(nodes).to_file(path, layer="nodes", driver="GPKG")
        _prepare_gpkg_frame(edges).to_file(path, layer="edges", driver="GPKG")
        metadata = write_native_metadata(context, layer_id, outputs=[path], method=f"OpenStreetMap walking network clipped to the {context.study.id} AOI.")
        return path, metadata
    tags = {
        "greenspace_access": {"leisure": ["park", "garden", "nature_reserve", "recreation_ground"], "landuse": ["recreation_ground", "forest"]},
        "social_infrastructure": {"amenity": ["library", "community_centre", "social_centre", "arts_centre", "theatre", "sports_centre"]},
        "food_environment": {"shop": ["supermarket", "greengrocer", "convenience", "market"], "amenity": ["fast_food", "restaurant", "cafe"]},
        "healthcare": {"amenity": ["hospital", "clinic", "doctors", "dentist", "pharmacy"]},
    }[layer_id]
    features = fetch_features_from_bbox_tiled(
        (minx, miny, maxx, maxy),
        tags,
        label=f"{context.study.id} {layer_id}",
    )
    if features.empty:
        features = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    path = out_dir / f"{layer_id}_native.gpkg"
    _write_gpkg_atomic(features, path, layer="features")
    metadata = write_native_metadata(context, layer_id, outputs=[path], method=f"OpenStreetMap raw features cached inside the {context.study.id} AOI; distance/count metrics are computed at query time.", extra={"tags": tags, "n_features": len(features)})
    return path, metadata


def export_native_layer(context: Any, layer_id: str) -> tuple[Path, ...]:
    if layer_id not in NATIVE_LAYER_SPECS:
        raise ValueError(f"Layer {layer_id!r} is not supported in native mode")
    kind = NATIVE_LAYER_SPECS[layer_id].kind
    if kind == "gee_raster":
        return export_gee_native_layer(context, layer_id)
    if kind == "raster":
        raise ValueError(
            f"Layer {layer_id!r} is not exported from Earth Engine. Run its dedicated "
            "collection script (scripts/run_climate_lst_ecostress.py) to produce "
            f"{layer_id}_native.tif, then publish."
        )
    if kind == "climate_points":
        return export_native_climate(context)
    return export_native_osm(context, layer_id)

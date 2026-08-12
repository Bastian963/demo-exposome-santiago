"""Year-specific spatial products for browser temporal selectors.

The administrative study geometry is only an AOI and aggregation context.  A
temporal selector may advertise one of these rasters only when the exact year,
provider grid and content hash have been checkpointed.  The functions in this
module are called by the human-run annual collector; importing them never
contacts a provider.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from shapely.geometry import mapping


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _support(year: int, source_label: str) -> dict[str, str]:
    return {"kind": "year", "year": str(year), "source_label": source_label}


def _cached(
    raster: Path,
    metadata_path: Path,
    *,
    year: int,
    source_label: str,
    adapter: str,
    source_parameters_sha256: str,
) -> bool:
    if not raster.is_file() or not metadata_path.is_file():
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            metadata.get("adapter") != adapter
            or metadata.get("temporal_support") != _support(year, source_label)
            or metadata.get("source_parameters_sha256") != source_parameters_sha256
            or metadata.get("raster_sha256") != _sha256(raster)
        ):
            return False
        from .native import _validate_export_grid
        from .spatial_detail import raster_grid_signature

        actual = raster_grid_signature(raster)
        _validate_export_grid(
            str(metadata["layer_id"]),
            actual,
            expected_resolution_m=float(metadata["analysis_resolution_m"]),
        )
        return metadata.get("export_grid") == actual
    except (ImportError, KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
        return False


def _annual_wind_image(cfg: Mapping[str, Any], year: int) -> Any:
    """Mean of hourly speed, matching ``wind_speed_mean`` in the table."""
    import ee

    block = cfg["wind"]
    collection = (
        ee.ImageCollection(block["id"])
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .select(["u_component_of_wind_10m", "v_component_of_wind_10m"])
    )
    projection = ee.Image(collection.first()).select(0).projection()

    def speed(image: Any) -> Any:
        image = ee.Image(image)
        return (
            image.select("u_component_of_wind_10m")
            .pow(2)
            .add(image.select("v_component_of_wind_10m").pow(2))
            .sqrt()
            .rename("wind_speed_mean")
        )

    return collection.map(speed).mean().setDefaultProjection(projection)


def _annual_heat_image(cfg: Mapping[str, Any], year: int) -> Any:
    import ee

    daily = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR").filterDate(
        f"{year}-01-01", f"{year + 1}-01-01"
    )
    projection = ee.Image(daily.first()).select("temperature_2m_max").projection()
    months = sorted(
        {
            int(month)
            for month in cfg.get("climate", {}).get("seasons", {}).get(
                "summer", [12, 1, 2]
            )
        }
    )
    if not months or any(month not in range(1, 13) for month in months):
        raise ValueError("climate.seasons.summer must contain calendar months 1..12")
    summer = daily.filter(ee.Filter.calendarRange(months[0], months[0], "month"))
    for month in months[1:]:
        summer = summer.merge(
            daily.filter(ee.Filter.calendarRange(month, month, "month"))
        )
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
        .toFloat()
        .rename("hot_days_30c")
    )
    tropical_nights = (
        daily.select("temperature_2m_min")
        .map(lambda image: image.gte(293.15))
        .sum()
        .toFloat()
        .rename("tropical_nights_20c")
    )
    return (
        summer_tmax.addBands(hot_days)
        .addBands(tropical_nights)
        .setDefaultProjection(projection)
    )


def _annual_precipitation_image(cfg: Mapping[str, Any], year: int) -> Any:
    import ee

    block = cfg["precipitation"]
    collection_id = block["collection"]["id"]
    band = block["collection"]["band"]
    thresholds = block.get("thresholds", {})
    wet_day = float(thresholds.get("wet_day_mm", 1.0))
    heavy_day = float(thresholds.get("heavy_day_mm", 10.0))
    daily = (
        ee.ImageCollection(collection_id)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .select(band)
    )
    projection = ee.Image(daily.first()).select(band).projection()
    total = daily.sum().toFloat().rename("precip_annual_mm")
    heavy = (
        daily.map(lambda image: image.gte(heavy_day))
        .sum()
        .toFloat()
        .rename("precip_heavy_days_10mm")
    )

    def dry_run_step(image: Any, state: Any) -> Any:
        previous = ee.Image(state)
        current = ee.Image(image)
        run = previous.select("dry_run").add(1).multiply(current.lt(wet_day))
        maximum = previous.select("max_dry_run").max(run)
        return run.rename("dry_run").addBands(maximum.rename("max_dry_run"))

    initial = ee.Image.constant([0, 0]).rename(["dry_run", "max_dry_run"])
    cdd = (
        ee.Image(daily.iterate(dry_run_step, initial))
        .select("max_dry_run")
        .toFloat()
        .rename("precip_cdd_days")
    )
    # Band order is the public temporal-indicator contract.
    return total.addBands(cdd).addBands(heavy).setDefaultProjection(projection)


def _annual_image(
    cfg: Mapping[str, Any], adapter: str, year: int
) -> tuple[Any, float, str, list[str]]:
    """Return image, analysis scale, layer id and bands for one harvest."""
    if adapter == "alan":
        from .alan import _annual_radiance_image

        block = cfg["alan"]
        image = _annual_radiance_image(
            dict(cfg), f"{year}-01-01", f"{year + 1}-01-01"
        )
        return image, float(block["collection"]["scale_meters"]), "alan", [
            str(block["collection"]["band"])
        ]
    if adapter == "air_quality_satellite":
        from .air_quality import _annual_no2_image

        block = cfg["air_quality"]["collections"]["no2"]
        image = _annual_no2_image(
            dict(cfg), f"{year}-01-01", f"{year + 1}-01-01"
        )
        return image, float(block["scale_meters"]), "air_quality_satellite", [
            str(block["band"])
        ]
    if adapter == "climate_heat":
        return (
            _annual_heat_image(cfg, year),
            11_132.0,
            "climate_heat",
            ["summer_tmax_mean_c", "hot_days_30c", "tropical_nights_20c"],
        )
    if adapter == "precipitation":
        block = cfg["precipitation"]
        return (
            _annual_precipitation_image(cfg, year),
            float(block["collection"]["scale_meters"]),
            "precipitation",
            ["precip_annual_mm", "precip_cdd_days", "precip_heavy_days_10mm"],
        )
    if adapter == "wind":
        return (
            _annual_wind_image(cfg, year),
            float(cfg["wind"]["scale_meters"]),
            "wind",
            ["wind_speed_mean"],
        )
    raise ValueError(f"Adapter {adapter!r} has no annual raster detail builder")


def _source_parameters_sha256(
    cfg: Mapping[str, Any], adapter: str, year: int
) -> str:
    """Invalidate annual checkpoints when the scientific source changes."""
    keys = {
        "alan": ("alan",),
        "air_quality_satellite": ("air_quality",),
        "climate_heat": ("climate",),
        "precipitation": ("precipitation",),
        "wind": ("wind",),
    }[adapter]
    payload = {
        "builder_schema": 1,
        "adapter": adapter,
        "year": int(year),
        "settings": {key: cfg.get(key) for key in keys},
    }
    return sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def export_annual_raster(
    context: Any,
    *,
    adapter: str,
    year: int,
    output_dir: str | Path,
    source_label: str,
) -> tuple[Path, Path]:
    """Export one AOI-clipped annual raster at its verified provider grid."""
    import ee
    import geemap

    from . import config, gee
    from .native import _gee_grid_signature, _validate_export_grid
    from .spatial_detail import raster_grid_signature

    year = int(year)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    raster = output_dir / f"{adapter}_{year}_native.tif"
    metadata_path = output_dir / f"{adapter}_{year}_native.metadata.json"
    cfg = config.load_config(context.study.id)
    parameters_sha256 = _source_parameters_sha256(cfg, adapter, year)
    if _cached(
        raster,
        metadata_path,
        year=year,
        source_label=source_label,
        adapter=adapter,
        source_parameters_sha256=parameters_sha256,
    ):
        return raster, metadata_path

    gee.init_gee()
    image, scale, layer_id, bands = _annual_image(cfg, adapter, year)
    units = context.load_spatial_units().to_crs(context.location.geographic_crs)
    roi = ee.Geometry(mapping(units.geometry.union_all()))
    image = image.clip(roi)
    source_grid = _gee_grid_signature(image)
    _validate_export_grid(layer_id, source_grid, expected_resolution_m=scale)
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
        raise RuntimeError(f"Annual {adapter} export did not produce {partial}")
    export_grid = raster_grid_signature(partial)
    _validate_export_grid(layer_id, export_grid, expected_resolution_m=scale)
    partial.replace(raster)
    metadata = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "study_id": context.study.id,
        "layer_id": layer_id,
        "adapter": adapter,
        "source_parameters_sha256": parameters_sha256,
        "bands": bands,
        "analysis_resolution_m": scale,
        "source_native_resolution_m": scale,
        "source_grid": source_grid,
        "export_grid": export_grid,
        "source_support_preserved": True,
        "temporal_support": _support(year, source_label),
        "raster": raster.name,
        "raster_sha256": _sha256(raster),
    }
    partial_metadata = metadata_path.with_suffix(metadata_path.suffix + ".partial")
    partial_metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    partial_metadata.replace(metadata_path)
    return raster, metadata_path


def export_annual_green_grid(
    context: Any,
    *,
    year: int,
    output_dir: str | Path,
    cache_dir: str | Path,
    source_label: str,
) -> tuple[Path, Path]:
    """Build one real, stable 1-km Dynamic World fraction grid for a year."""
    import ee
    import geopandas as gpd
    from shapely import make_valid, union_all
    from shapely.geometry import MultiPolygon, Polygon
    from tqdm import tqdm

    from . import config, gee
    from .greenspace_multisource import build_dynamic_world_masks
    from .spatial_detail import build_aligned_metric_grid

    year = int(year)
    output_dir = Path(output_dir)
    cache_dir = Path(cache_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    geojson_path = output_dir / f"green_{year}_1km.geojson"
    metadata_path = output_dir / f"green_{year}_1km.metadata.json"
    expected_support = _support(year, source_label)
    communes = context.load_spatial_units()
    cfg = config.load_config(context.study.id)
    dw = cfg["greenspace"]["dynamic_world"]
    months = [int(value) for value in dw["season_months"]]
    classes = [str(value) for value in dw["green_classes"]]
    sample_scale = int(dw.get("fine_scale_meters", dw["native_scale_meters"]))
    namespace = sha256(
        json.dumps(
            {
                "builder_schema": 1,
                "collection": dw["collection"],
                "year": year,
                "months": months,
                "classes": classes,
                "sample_scale": sample_scale,
                "analysis_resolution_m": 1000,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if geojson_path.is_file() and metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if (
                metadata.get("temporal_support") == expected_support
                and metadata.get("geojson_sha256") == _sha256(geojson_path)
                and metadata.get("source_parameters_sha256") == namespace
                and metadata.get("grid_alignment") == "study_aoi_metric_grid"
                and metadata.get("analysis_resolution_m") == 1000
            ):
                return geojson_path, metadata_path
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    checkpoint = cache_dir / f"green_detail_1km_{year}_{namespace[:12]}.json"
    values: dict[str, float | None] = {}
    if checkpoint.is_file():
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
        raw_values = payload.get("values")
        if not isinstance(raw_values, dict):
            raise ValueError(f"Invalid annual green checkpoint: {checkpoint}")
        values = {
            str(key): None if value is None else float(value)
            for key, value in raw_values.items()
        }

    def polygonal(geometry: Any) -> Any:
        fixed = geometry if geometry.is_valid else make_valid(geometry)
        parts: list[Any] = []

        def collect(value: Any) -> None:
            if isinstance(value, (Polygon, MultiPolygon)):
                parts.append(value)
            elif hasattr(value, "geoms"):
                for child in value.geoms:
                    collect(child)

        collect(fixed)
        if not parts:
            return None
        merged = union_all(parts)
        return merged if merged.is_valid else make_valid(merged)

    metric_crs = context.location.metric_crs or cfg["crs"]["metric"]
    grid = build_aligned_metric_grid(
        communes, spacing_m=1000, metric_crs=metric_crs
    ).to_crs("EPSG:4326")
    cells: list[dict[str, Any]] = []
    for row in grid.itertuples():
        geometry = polygonal(row.geometry)
        if geometry is not None and not geometry.is_empty and geometry.is_valid:
            cells.append({"cell_id": str(row.cell_id), "geometry": geometry})

    gee.init_gee()
    roi = gee.gdf_to_feature_collection(
        gpd.GeoDataFrame(geometry=communes.geometry, crs=communes.crs)
    ).geometry()
    green = build_dynamic_world_masks(
        roi=roi,
        years=[year],
        season_months=months,
        green_classes=classes,
    ).select("green")
    # Each batch's cell polygons are embedded directly in the reduceRegions
    # request (client-side geometries, not a server-side asset reference), so
    # the request itself -- not just the response -- counts against Earth
    # Engine's 10 MiB payload limit. 1500 was fine for cities with simpler
    # grid-cell boundaries; Medellin's more irregular/mountainous comuna
    # boundaries produce higher-vertex-count cells that overflowed it even
    # after trimming the response geometry below. Smaller batch, more
    # requests, but safely under the limit regardless of geometry complexity.
    batch_size = 200
    for start in tqdm(
        range(0, len(cells), batch_size),
        desc=f"Dynamic World annual detail {year}",
        unit="batch",
    ):
        batch = cells[start : start + batch_size]
        if all(cell["cell_id"] in values for cell in batch):
            continue
        features = [
            ee.Feature(ee.Geometry(mapping(cell["geometry"])), {"idx": start + index})
            for index, cell in enumerate(batch)
        ]
        reduced = green.reduceRegions(
            collection=ee.FeatureCollection(features),
            reducer=ee.Reducer.mean(),
            scale=sample_scale,
            crs="EPSG:4326",
            tileScale=8,
        )
        # Only idx/green are read below; reduceRegions otherwise echoes back
        # each input feature's full polygon geometry, which is what pushed
        # Medellin's batches over Earth Engine's 10 MiB getInfo() payload
        # limit (its comuna grid cells are large/complex enough that other
        # cities' batches happened to fit under it).
        reduced = reduced.map(lambda feature: ee.Feature(None, feature.toDictionary()))
        rows = gee.fc_to_dicts(reduced)
        by_index = {
            int(row["idx"]): row.get("green", row.get("mean"))
            for row in rows
            if "idx" in row
        }
        for index, cell in enumerate(batch):
            fraction = by_index.get(start + index)
            values[cell["cell_id"]] = (
                None if fraction is None else round(float(fraction) * 100, 2)
            )
        temporary = checkpoint.with_suffix(".partial.json")
        temporary.write_text(
            json.dumps({"schema_version": 1, "values": values}, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(checkpoint)

    features = [
        {
            "type": "Feature",
            "properties": {"value": values[cell["cell_id"]], "pixel_id": cell["cell_id"]},
            "geometry": mapping(cell["geometry"]),
        }
        for cell in cells
        if values.get(cell["cell_id"]) is not None
    ]
    payload = {
        "type": "FeatureCollection",
        "exposome": "green",
        "column": "green_total_pct",
        "source": source_label,
        "analysis_resolution_m": 1000,
        "source_resolution_m": 10,
        "sample_scale_m": sample_scale,
        "grid_alignment": "study_aoi_metric_grid",
        "is_synthetic": False,
        "temporal_support": expected_support,
        "n_features": len(features),
        "features": features,
    }
    partial_geojson = geojson_path.with_suffix(".partial.geojson")
    partial_geojson.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    partial_geojson.replace(geojson_path)
    metadata = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "study_id": context.study.id,
        "layer_id": "greenspace_multisource",
        "adapter": "greenspace_multisource",
        "source_parameters_sha256": namespace,
        "indicator_id": "green",
        "analysis_resolution_m": 1000,
        "source_native_resolution_m": 10,
        "sample_scale_m": sample_scale,
        "grid_alignment": "study_aoi_metric_grid",
        "source_support_preserved": True,
        "temporal_support": expected_support,
        "geojson": geojson_path.name,
        "geojson_sha256": _sha256(geojson_path),
    }
    partial_metadata = metadata_path.with_suffix(metadata_path.suffix + ".partial")
    partial_metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    partial_metadata.replace(metadata_path)
    return geojson_path, metadata_path

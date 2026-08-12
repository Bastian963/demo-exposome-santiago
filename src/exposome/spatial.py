"""Load and validate user-provided spatial units for exposome studies."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
from pyproj import CRS
from shapely.geometry import box

from exposome.studies import BoundingBox, StudyContext


SUPPORTED_SPATIAL_SUFFIXES = {".geojson", ".json", ".gpkg"}
POLYGON_TYPES = {"Polygon", "MultiPolygon"}


class SpatialValidationError(ValueError):
    """Raised when a study polygon file violates the spatial contract."""


def load_spatial_units(
    context: StudyContext,
    *,
    repair_invalid: bool = False,
) -> gpd.GeoDataFrame:
    """Load and normalize the polygons configured for ``context``.

    The returned frame is in the location's geographic CRS and always starts
    with ``spatial_id``, ``spatial_name``, ``area_km2`` and ``geometry``.
    Source attributes are retained after these canonical columns.  The chosen
    projected CRS is recorded in ``gdf.attrs['metric_crs']``.
    """
    path = context.spatial_path
    if path.suffix.lower() not in SUPPORTED_SPATIAL_SUFFIXES:
        raise SpatialValidationError(
            f"Unsupported polygon format '{path.suffix}'. "
            "Use GeoJSON (.geojson/.json) or GeoPackage (.gpkg)."
        )
    if not path.is_file():
        raise FileNotFoundError(
            f"Study polygon file not found: {path}. "
            "Provide the file configured at spatial.path before running layers."
        )

    try:
        read_options: dict[str, Any] = {}
        if context.study.spatial_layer is not None:
            read_options["layer"] = context.study.spatial_layer
        gdf = gpd.read_file(path, **read_options)
    except Exception as exc:
        raise SpatialValidationError(f"Could not read study polygons from {path}: {exc}") from exc

    return normalize_spatial_units(
        gdf,
        id_column=context.study.id_column,
        name_column=context.study.name_column,
        expected_units=context.expected_units,
        geographic_crs=context.location.geographic_crs,
        metric_crs=context.location.metric_crs,
        bbox=context.location.bbox,
        source_path=path,
        repair_invalid=repair_invalid,
    )


def normalize_spatial_units(
    gdf: gpd.GeoDataFrame,
    *,
    id_column: str,
    name_column: str | None = None,
    expected_units: int | None = None,
    geographic_crs: str | CRS = "EPSG:4326",
    metric_crs: str | CRS | None = None,
    bbox: BoundingBox | None = None,
    source_path: str | Path | None = None,
    repair_invalid: bool = False,
) -> gpd.GeoDataFrame:
    """Validate a frame and apply the canonical spatial-unit schema."""
    source = str(source_path) if source_path is not None else "GeoDataFrame"
    if not isinstance(gdf, gpd.GeoDataFrame):
        raise TypeError("gdf must be a geopandas.GeoDataFrame")
    if gdf.empty:
        raise SpatialValidationError(f"Spatial input is empty: {source}")
    if gdf.crs is None:
        raise SpatialValidationError(
            f"Spatial input has no CRS: {source}. Define its source CRS before loading it."
        )
    if id_column not in gdf.columns:
        raise SpatialValidationError(
            f"ID column '{id_column}' is missing from {source}. "
            f"Available columns: {sorted(map(str, gdf.columns))}"
        )
    if name_column is not None and name_column not in gdf.columns:
        raise SpatialValidationError(
            f"Name column '{name_column}' is missing from {source}. "
            f"Available columns: {sorted(map(str, gdf.columns))}"
        )
    if expected_units is not None and len(gdf) != expected_units:
        raise SpatialValidationError(
            f"Expected {expected_units} spatial units, found {len(gdf)} in {source}"
        )

    work = gdf.copy()
    _validate_nonempty_geometries(work, source)
    if repair_invalid and not bool(work.geometry.is_valid.all()):
        work.geometry = work.geometry.make_valid()
        _validate_nonempty_geometries(work, source)
    _validate_polygon_geometries(work, source)

    invalid = ~work.geometry.is_valid
    if bool(invalid.any()):
        positions = np.flatnonzero(invalid.to_numpy()).tolist()[:10]
        raise SpatialValidationError(
            f"Invalid geometries at row positions {positions} in {source}. "
            "Fix the source or call load_spatial_units(..., repair_invalid=True)."
        )

    spatial_ids = _normalise_ids(work[id_column], source)
    if name_column is None:
        spatial_names = spatial_ids.copy()
    else:
        names = work[name_column]
        spatial_names = names.astype("string").str.strip()
        missing_name = names.isna() | spatial_names.eq("")
        spatial_names = spatial_names.mask(missing_name, spatial_ids).astype(str)

    target_crs = _validate_geographic_crs(geographic_crs)
    try:
        work = work.to_crs(target_crs)
    except Exception as exc:
        raise SpatialValidationError(
            f"Could not transform {source} from {gdf.crs} to {target_crs.to_string()}: {exc}"
        ) from exc
    if work.geometry.name != "geometry":
        work = work.rename_geometry("geometry")

    _validate_finite_bounds(work, source)
    outside_bbox_units = 0
    if bbox is not None:
        outside_bbox_units = _validate_bbox_overlap(work, bbox, source)

    selected_metric = resolve_metric_crs(work, configured=metric_crs)
    metric = work.to_crs(selected_metric)
    areas = metric.geometry.area / 1_000_000
    zero_area = ~np.isfinite(areas.to_numpy()) | areas.le(0).to_numpy()
    if bool(zero_area.any()):
        positions = np.flatnonzero(zero_area).tolist()[:10]
        raise SpatialValidationError(
            f"Spatial units with zero or non-finite area at row positions {positions} in {source}"
        )

    work["spatial_id"] = spatial_ids.to_numpy()
    work["spatial_name"] = spatial_names.to_numpy()
    work["area_km2"] = areas.to_numpy()
    canonical = ["spatial_id", "spatial_name", "area_km2", "geometry"]
    remaining = [column for column in work.columns if column not in canonical]
    work = work[canonical + remaining].reset_index(drop=True)
    work.attrs.update(
        {
            "metric_crs": selected_metric.to_string(),
            "geographic_crs": target_crs.to_string(),
            "spatial_id_source": id_column,
            "spatial_name_source": name_column or id_column,
            "unit_count": len(work),
            "outside_bbox_units": outside_bbox_units,
            "source_path": str(source_path) if source_path is not None else None,
        }
    )
    return work


def resolve_metric_crs(
    gdf: gpd.GeoDataFrame,
    *,
    configured: str | CRS | None = None,
) -> CRS:
    """Return a configured projected CRS or estimate the local UTM CRS."""
    if configured not in (None, "", "auto"):
        try:
            crs = CRS.from_user_input(configured)
        except Exception as exc:
            raise SpatialValidationError(f"Invalid configured metric CRS: {configured}") from exc
        if not crs.is_projected:
            raise SpatialValidationError(
                f"Configured metric CRS must be projected, got {crs.to_string()}"
            )
        return crs

    try:
        estimated = gdf.estimate_utm_crs()
    except Exception as exc:
        raise SpatialValidationError(f"Could not estimate a local UTM CRS: {exc}") from exc
    if estimated is None:
        raise SpatialValidationError(
            "Could not estimate a local UTM CRS for the study polygons; "
            "set crs.metric explicitly in the location config."
        )
    crs = CRS.from_user_input(estimated)
    if not crs.is_projected:
        raise SpatialValidationError(f"Estimated CRS is not projected: {crs.to_string()}")
    return crs


def _normalise_ids(values: Any, source: str) -> Any:
    missing = values.isna()
    strings = values.astype("string").str.strip()
    blank = strings.eq("")
    invalid = missing | blank
    if bool(invalid.any()):
        positions = np.flatnonzero(invalid.to_numpy()).tolist()[:10]
        raise SpatialValidationError(
            f"Null or blank spatial IDs at row positions {positions} in {source}"
        )
    strings = strings.astype(str)
    duplicated = strings.duplicated(keep=False)
    if bool(duplicated.any()):
        duplicates = sorted(strings[duplicated].unique().tolist())[:10]
        raise SpatialValidationError(
            f"Duplicate spatial IDs in {source}: {duplicates}"
        )
    return strings


def _validate_nonempty_geometries(gdf: gpd.GeoDataFrame, source: str) -> None:
    invalid = gdf.geometry.isna() | gdf.geometry.is_empty
    if bool(invalid.any()):
        positions = np.flatnonzero(invalid.to_numpy()).tolist()[:10]
        raise SpatialValidationError(
            f"Null or empty geometries at row positions {positions} in {source}"
        )


def _validate_polygon_geometries(gdf: gpd.GeoDataFrame, source: str) -> None:
    unsupported = ~gdf.geometry.geom_type.isin(POLYGON_TYPES)
    if bool(unsupported.any()):
        kinds = sorted(gdf.loc[unsupported].geometry.geom_type.unique().tolist())
        raise SpatialValidationError(
            f"Spatial units must be Polygon or MultiPolygon; found {kinds} in {source}"
        )


def _validate_geographic_crs(value: str | CRS) -> CRS:
    try:
        crs = CRS.from_user_input(value)
    except Exception as exc:
        raise SpatialValidationError(f"Invalid geographic CRS: {value}") from exc
    if not crs.is_geographic:
        raise SpatialValidationError(
            f"Location geographic CRS must be geographic, got {crs.to_string()}"
        )
    return crs


def _validate_finite_bounds(gdf: gpd.GeoDataFrame, source: str) -> None:
    bounds = gdf.total_bounds
    if not bool(np.isfinite(bounds).all()):
        raise SpatialValidationError(f"Spatial input has non-finite bounds: {source}")


def _validate_bbox_overlap(
    gdf: gpd.GeoDataFrame,
    bbox: BoundingBox,
    source: str,
) -> int:
    wgs84 = gdf if CRS.from_user_input(gdf.crs).to_epsg() == 4326 else gdf.to_crs(4326)
    coverage = box(*bbox.as_tuple())
    intersects = wgs84.geometry.intersects(coverage)
    if not bool(intersects.any()):
        raise SpatialValidationError(
            f"Study polygons do not overlap the configured location bbox in {source}"
        )
    return int((~intersects).sum())

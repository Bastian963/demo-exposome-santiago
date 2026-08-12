"""Build browser-ready spatial-detail COGs from already materialized products.

This is intentionally a local post-processing stage.  Provider acquisition
belongs to ``exposome run`` and may take hours; ``exposome detail`` only reads
its native companion study, reprojects with nearest-neighbour sampling and
writes a COG plus an auditable metadata sidecar for the visible aggregate
study.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import math
import tempfile
from typing import Any, Iterable, Mapping

import numpy as np

from .studies import StudyContext, load_study


WEB_CRS = "EPSG:3857"

@dataclass(frozen=True)
class NativeRasterDetail:
    """One browser indicator backed by a direct native raster band."""

    native_layer: str
    source_band: int = 1


# The mapping is deliberately conservative: a raster is exposed only when the
# native companion contains the exact physical metric at a known support.
# Derived CHIRPS/SPI, city-relative indices, wildfire composites and OSM grids
# get their own builders rather than being falsely inferred from an aggregate
# table.
NATIVE_RASTER_INDICATORS = {
    "pm25": NativeRasterDetail("air_quality_pm25"),
    "no2": NativeRasterDetail("air_quality_satellite"),
    "alan": NativeRasterDetail("alan"),
    "wind": NativeRasterDetail("wind"),
    "heat_summer_tmax": NativeRasterDetail("climate_heat", source_band=1),
    "heat_hot_days": NativeRasterDetail("climate_heat", source_band=2),
    "heat_tropical_nights": NativeRasterDetail("climate_heat", source_band=3),
    "rain_annual": NativeRasterDetail("precipitation", source_band=1),
    "rain_dry_spell": NativeRasterDetail("precipitation", source_band=2),
    "rain_heavy": NativeRasterDetail("precipitation", source_band=3),
    "canopy": NativeRasterDetail("greenspace_multisource"),
}


@dataclass(frozen=True)
class DetailBuildResult:
    indicator_id: str
    source: Path | None
    output: Path | None
    action: str


def build_aligned_metric_grid(aoi: Any, *, spacing_m: float, metric_crs: str) -> Any:
    """Build one AOI-wide grid whose phase cannot depend on admin boundaries.

    The returned geometry is clipped to the dissolved AOI for display; the
    ``sample_geometry`` column retains the full regular cell for methods that
    must evaluate a local window.  Grid origins are snapped to the metric CRS
    origin, so passing the same AOI as one polygon or many communes produces
    exactly the same cell ids and positions.
    """
    import geopandas as gpd
    from shapely import make_valid, union_all
    from shapely.geometry import MultiPolygon, Polygon, box

    def polygonal(geometry: Any) -> Any:
        """Repair intersections and retain only polygonal components.

        A valid administrative multipart AOI can still produce an invalid
        polygon at a shared boundary after union/intersection. Earth Engine
        serializes those artifacts as `NaN`, so repair them before a cell ever
        leaves the local process.
        """
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
            return fixed
        merged = union_all(parts)
        return merged if merged.is_valid else make_valid(merged)

    if spacing_m <= 0:
        raise ValueError("spacing_m must be positive")
    frame = aoi.to_crs(metric_crs)
    union = polygonal(union_all([polygonal(geometry) for geometry in frame.geometry]))
    if union.is_empty:
        raise ValueError("AOI is empty")
    minx, miny, maxx, maxy = union.bounds
    x_start = math.floor(minx / spacing_m) * spacing_m
    y_start = math.floor(miny / spacing_m) * spacing_m
    rows: list[dict[str, Any]] = []
    x = x_start
    while x < maxx:
        y = y_start
        while y < maxy:
            full = box(x, y, x + spacing_m, y + spacing_m)
            if union.intersects(full):
                clipped = polygonal(union.intersection(full))
                if not clipped.is_empty:
                    rows.append(
                        {
                            "cell_id": f"{int(round(x / spacing_m))}:{int(round(y / spacing_m))}",
                            "sample_geometry": full,
                            "geometry": clipped,
                        }
                    )
            y += spacing_m
        x += spacing_m
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=metric_crs)


def _find_native_raster(layer_dir: Path) -> Path | None:
    # ``._*`` sidecars (macOS AppleDouble, e.g. on NFS/SMB-mounted native
    # studies) sort before the real file and are not valid rasters -- GDAL
    # rejects them outright ("not recognized as being in a supported file
    # format"). Never a real pipeline output on any platform.
    candidates = sorted(
        path
        for path in list(layer_dir.glob("*.tif")) + list(layer_dir.glob("*.tiff"))
        if not path.name.startswith("._")
    )
    return candidates[0] if candidates else None


def _file_sha256(path: Path) -> str:
    """Hash a materialized native product for resume-safe detail builds."""
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cached_detail_matches_source(
    sidecar: Path,
    *,
    source: Path,
    source_band: int,
    source_relative_path: str,
    temporal_support: Mapping[str, Any] | None = None,
) -> bool:
    """Return whether a detail sidecar still proves the exact source raster."""
    try:
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    source_matches = (
        metadata.get("source_path") == source_relative_path
        and metadata.get("source_band") == source_band
        and metadata.get("source_sha256") == _file_sha256(source)
    )
    temporal_matches = (
        temporal_support is None
        or metadata.get("temporal_support") == dict(temporal_support)
    )
    return source_matches and temporal_matches


def _statistics(dataset: Any, band: int) -> dict[str, float | int | None]:
    data = dataset.read(band, masked=True)
    values = np.asarray(data.compressed(), dtype="float64")
    if not values.size:
        return {"count": 0, "min": None, "max": None, "p02": None, "p98": None}
    return {
        "count": int(values.size),
        "min": float(np.nanmin(values)),
        "max": float(np.nanmax(values)),
        "p02": float(np.nanpercentile(values, 2)),
        "p98": float(np.nanpercentile(values, 98)),
    }


def raster_grid_signature(path: str | Path) -> dict[str, Any]:
    """Return the actual grid identity of a raster, never a copied claim."""
    import rasterio

    with rasterio.open(path) as dataset:
        if dataset.crs is None:
            raise ValueError(f"Raster has no CRS: {path}")
        transform = dataset.transform
        is_geographic = bool(dataset.crs.is_geographic)
        return {
            "crs": dataset.crs.to_string(),
            "transform": list(transform)[:6],
            "resolution": {
                "x": abs(float(transform.a)),
                "y": abs(float(transform.e)),
                "unit": "degree" if is_geographic else "m",
            },
            "width": int(dataset.width),
            "height": int(dataset.height),
            "count": int(dataset.count),
        }


def build_cog(
    source: str | Path,
    destination: str | Path,
    *,
    source_bands: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Write a Web-Mercator COG without inventing finer source values.

    Nearest-neighbour reprojection preserves the source sample values.  The
    resulting COG's storage pixels are cartographic transport, not a claim of
    improved scientific support; that distinction is carried by the manifest.
    """
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.shutil import copy as rio_copy
    from rasterio.vrt import WarpedVRT

    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(source) as dataset:
        if dataset.crs is None:
            raise ValueError(f"Native detail raster has no CRS: {source}")
        selected_bands = tuple(source_bands or range(1, dataset.count + 1))
        if not selected_bands or any(band < 1 or band > dataset.count for band in selected_bands):
            raise ValueError(f"Requested source bands are invalid for {source}")
        with WarpedVRT(dataset, crs=WEB_CRS, resampling=Resampling.nearest) as warped:
            with tempfile.TemporaryDirectory(prefix="brainlat-cog-") as tmp:
                intermediate = Path(tmp) / "detail-webmercator.tif"
                profile = warped.profile.copy()
                profile.update(
                    driver="GTiff",
                    tiled=True,
                    blockxsize=256,
                    blockysize=256,
                    compress="DEFLATE",
                    predictor=2,
                    BIGTIFF="IF_SAFER",
                    count=len(selected_bands),
                )
                with rasterio.open(intermediate, "w", **profile) as output:
                    for output_band, source_band in enumerate(selected_bands, start=1):
                        # Materialize a plain ndarray: Rasterio may return a
                        # masked view, whose shape assignment triggers a
                        # NumPy 2.5 deprecation inside DatasetWriter.write.
                        output.write(warped.read(source_band, masked=False), output_band)
                rio_copy(
                    intermediate,
                    destination,
                    driver="COG",
                    BLOCKSIZE=256,
                    COMPRESS="DEFLATE",
                    RESAMPLING="NEAREST",
                    OVERVIEWS="AUTO",
                    BIGTIFF="IF_SAFER",
                )
    with rasterio.open(destination) as output:
        statistics_by_band = {
            str(band): _statistics(output, band)
            for band in range(1, output.count + 1)
        }
        return {
            "crs": output.crs.to_string() if output.crs else None,
            "transform": list(output.transform)[:6],
            "width": output.width,
            "height": output.height,
            "count": output.count,
            "nodata": output.nodata,
            "statistics": statistics_by_band["1"],
            "statistics_by_band": statistics_by_band,
            "resampling": "nearest",
            "storage_kind": "cog",
            "storage_grid": raster_grid_signature(destination),
        }


def _native_companion(context: StudyContext) -> StudyContext:
    detail = context.study.raw.get("detail", {})
    if not isinstance(detail, dict) or not detail.get("native_study"):
        raise ValueError(
            f"Study {context.study.id!r} needs detail.native_study before spatial detail can be built"
        )
    companion = load_study(str(detail["native_study"]), repo_root_path=context.repo_root)
    if not companion.is_native:
        raise ValueError(f"detail.native_study {companion.study.id!r} must use mode: native")
    if companion.location.id != context.location.id:
        raise ValueError("detail native companion must belong to the same location")
    return companion


def build_study_detail(
    study: str | StudyContext,
    *,
    resume: bool = False,
    indicators: Iterable[str] | None = None,
) -> list[DetailBuildResult]:
    """Materialize available direct raster detail for one aggregate study."""
    context = load_study(study) if isinstance(study, str) else study
    if context.is_native:
        raise ValueError("Spatial detail is published into an aggregate study, not its native companion")
    companion = _native_companion(context)
    from . import config as legacy_config
    from .native import native_temporal_support

    companion_config = legacy_config.load_config(companion.study.id)
    requested = tuple(indicators or NATIVE_RASTER_INDICATORS.keys())
    unknown = sorted(set(requested) - set(NATIVE_RASTER_INDICATORS))
    if unknown:
        raise ValueError("No direct native detail adapter for: " + ", ".join(unknown))

    output_dir = context.paths.processed / "detail"
    results: list[DetailBuildResult] = []
    for indicator_id in requested:
        detail_spec = NATIVE_RASTER_INDICATORS[indicator_id]
        source = _find_native_raster(companion.paths.processed / detail_spec.native_layer)
        destination = output_dir / f"{indicator_id}.tif"
        sidecar = output_dir / f"{indicator_id}.metadata.json"
        if source is None:
            results.append(DetailBuildResult(indicator_id, None, None, "missing-native-source"))
            continue
        source_grid = raster_grid_signature(source)
        # Fail before creating a browser COG.  A nominal resolution stored in
        # metadata cannot repair a TIFF whose inspected grid is wrong.
        from .spatial_support import canonical_detail_source_grid

        if not canonical_detail_source_grid(
            indicator_id,
            {"source_grid": source_grid},
        ):
            resolution = source_grid.get("resolution")
            raise ValueError(
                f"Native source grid mismatch for {indicator_id!r}: {resolution}. "
                "Re-run its native companion after the projection-preservation fix."
            )
        source_relative_path = str(source.relative_to(companion.paths.processed))
        source_metadata_path = source.parent / "metadata.json"
        source_metadata: dict[str, Any] = {}
        if source_metadata_path.is_file():
            try:
                source_metadata = json.loads(source_metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid native metadata: {source_metadata_path}") from exc
        expected_temporal_support = source_metadata.get("temporal_support")
        if expected_temporal_support is None:
            # Backward-compatible local repair for native rasters created
            # before temporal support was written to metadata. The resolver is
            # the same one used by the native exporter and performs no provider
            # access, so `exposome detail --resume` remains a local operation.
            expected_temporal_support = native_temporal_support(
                companion_config,
                detail_spec.native_layer,
            )
        if resume and destination.is_file() and sidecar.is_file():
            if _cached_detail_matches_source(
                sidecar,
                source=source,
                source_band=detail_spec.source_band,
                source_relative_path=source_relative_path,
                temporal_support=expected_temporal_support,
            ):
                results.append(DetailBuildResult(indicator_id, source, destination, "cached"))
                continue
        metadata = build_cog(source, destination, source_bands=(detail_spec.source_band,))
        source_resolution_m = source_metadata.get("source_native_resolution_m")
        if source_resolution_m is None:
            source_resolution_m = source_metadata.get("scale_m")
        if source_resolution_m is None:
            source_resolution_m = source_metadata.get("native_resolution_m")
        metadata.update(
            {
                "indicator_id": indicator_id,
                "source_native_study": companion.study.id,
                "source_path": source_relative_path,
                "source_band": detail_spec.source_band,
                "source_sha256": _file_sha256(source),
                "analysis_resolution_m": source_metadata.get("analysis_resolution_m"),
                "source_native_resolution_m": source_resolution_m,
                "source_grid": source_grid,
                "source_support_preserved": True,
            }
        )
        if expected_temporal_support is not None:
            metadata["temporal_support"] = dict(expected_temporal_support)
        sidecar.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append(DetailBuildResult(indicator_id, source, destination, "built"))
    return results

"""Administrative summaries of Spain's SICA strategic-noise contours.

The source is vector contour geometry, not a raster.  This module therefore
does not manufacture a pixel resolution: it intersects Lden contour bands with
the study's administrative polygons and emits an explicitly administrative
summary.  Values only describe the source area at or above 55 dB(A).
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any, Iterable
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import unary_union
from tqdm import tqdm

from .raw_sources import RawSnapshotStore, RawSourceAsset


RAW_PROVIDER = "miteco"
RAW_DATASET = "sica-mer-agglomerations"
RAW_VERSION = "4f-2022"
SOURCE_CRS = "EPSG:3035"
LDEN_LAYER = "NoiseContours_allSourcesInAgglomeration_Lden"
EXPECTED_ARCHIVES = {"cataluna": 12, "pais_vasco": 4}
_BAND_RE = re.compile(r"^Lden(?:(\d{2})(\d{2})|GreaterThan(\d+))$")


@dataclass(frozen=True)
class NoiseSpainOutputs:
    table: Path
    geometry: Path
    metadata: Path
    exposure_table: Path


def _noise_settings(study: Any) -> dict[str, Any]:
    raw = getattr(getattr(study, "study", None), "raw", {})
    value = raw.get("noise_spain", {}) if isinstance(raw, dict) else {}
    if not isinstance(value, dict):
        raise ValueError("Study noise_spain settings must be a mapping")
    return value


def _region_for_study(study: Any) -> str:
    configured = _noise_settings(study).get("source_region")
    if configured in EXPECTED_ARCHIVES:
        return str(configured)
    location = getattr(getattr(study, "location", None), "id", "")
    if location in EXPECTED_ARCHIVES:
        return str(location)
    raise ValueError(
        "noise_spain is supported only for location ids "
        f"{sorted(EXPECTED_ARCHIVES)}, got {location!r}"
    )


def _assets_for_region(
    store: RawSnapshotStore,
    region: str,
    *,
    require_complete: bool,
) -> tuple[RawSourceAsset, ...]:
    snapshot = store.load(verify=True)
    if (snapshot.provider, snapshot.dataset) != (RAW_PROVIDER, RAW_DATASET):
        raise ValueError(f"Unexpected raw snapshot identity: {snapshot.manifest_path}")
    assets = tuple(asset for asset in snapshot.assets if Path(asset.path).parts[:1] == (region,))
    expected = EXPECTED_ARCHIVES[region]
    if require_complete and len(assets) != expected:
        raise ValueError(
            f"SICA snapshot has {len(assets)} {region} archives; expected {expected}"
        )
    if not assets:
        raise ValueError(f"SICA snapshot has no {region} archives: {snapshot.manifest_path}")
    return assets


def _extract_gpkg(store: RawSnapshotStore, asset: RawSourceAsset, cache_dir: Path) -> Path:
    destination = cache_dir / "gpkg" / f"{asset.sha256}.gpkg"
    if destination.is_file() and destination.stat().st_size > 0:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".gpkg.partial")
    source = store.asset_path(asset)
    with zipfile.ZipFile(source) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".gpkg")]
        if len(members) != 1:
            raise ValueError(f"{source} must contain exactly one GPKG, got {members}")
        with archive.open(members[0]) as input_handle, partial.open("wb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
    partial.replace(destination)
    return destination


def _band_midpoint(category: Any) -> float | None:
    match = _BAND_RE.match(str(category))
    if match is None:
        return None
    if match.group(3):
        return float(match.group(3)) + 2.5
    lower, upper = float(match.group(1)), float(match.group(2))
    if lower < 55:
        return None
    return (lower + upper) / 2.0


def _source_contours(
    gpkg: Path,
    source_id: str,
    *,
    source_bbox: tuple[float, float, float, float] | None = None,
    clip_geometry: object | None = None,
) -> gpd.GeoDataFrame:
    try:
        contours = gpd.read_file(gpkg, layer=LDEN_LAYER, bbox=source_bbox)
    except Exception as exc:
        raise ValueError(f"Could not read {LDEN_LAYER} from {gpkg}: {exc}") from exc
    if contours.crs is None:
        raise ValueError(f"SICA contour layer lacks CRS: {gpkg}")
    if "category" not in contours.columns:
        raise ValueError(f"SICA contour layer lacks category: {gpkg}")
    contours = contours.to_crs(SOURCE_CRS)
    contours["band_midpoint"] = contours["category"].map(_band_midpoint)
    contours = contours.loc[
        contours["band_midpoint"].notna()
        & contours.geometry.notna()
        & ~contours.geometry.is_empty
    ].copy()
    invalid = ~contours.geometry.is_valid
    if invalid.any():
        contours.loc[invalid, "geometry"] = contours.loc[invalid, "geometry"].make_valid()
    contours = contours.loc[~contours.geometry.is_empty].copy()
    if clip_geometry is not None and not contours.empty:
        contours["geometry"] = contours.geometry.intersection(clip_geometry)
        contours = contours.loc[~contours.geometry.is_empty].copy()
    if contours.empty:
        # A bbox-filtered source can legitimately contribute no >=55 band to
        # this particular administrative study. It remains provenance, but it
        # must not make a partial pilot fail or turn absence into a zero value.
        return gpd.GeoDataFrame(
            {"source_id": pd.Series(dtype="object"), "band_midpoint": pd.Series(dtype="float")},
            geometry=gpd.GeoSeries([], crs=SOURCE_CRS),
            crs=SOURCE_CRS,
        )
    contours["source_id"] = source_id
    return contours[["source_id", "band_midpoint", "geometry"]]


def _exposure_rows(gpkg: Path, source_id: str) -> pd.DataFrame:
    query = """
        SELECT agglomerationIdIdentifier, noiseSource, exposureType, noiseLevel,
               exposedPeople, exposedHospitals, exposedSchools, umeCod
        FROM ExposureValueInAgglomeration
        WHERE noiseSource = 'agglomerationAllSources'
          AND exposureType = 'mostExposedFacade'
    """
    try:
        with sqlite3.connect(gpkg) as connection:
            frame = pd.read_sql_query(query, connection)
    except Exception:
        return pd.DataFrame(
            columns=[
                "source_id", "agglomeration_id", "noise_source", "exposure_type",
                "noise_level", "exposed_people", "exposed_hospitals", "exposed_schools", "ume_code",
            ]
        )
    return frame.rename(
        columns={
            "agglomerationIdIdentifier": "agglomeration_id",
            "noiseSource": "noise_source",
            "exposureType": "exposure_type",
            "noiseLevel": "noise_level",
            "exposedPeople": "exposed_people",
            "exposedHospitals": "exposed_hospitals",
            "exposedSchools": "exposed_schools",
            "umeCod": "ume_code",
        }
    ).assign(source_id=source_id)


def _priority_dissolve(contours: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, float]:
    """Dissolve bands and let the higher Lden band own any overlap."""
    records: list[dict[str, Any]] = []
    covered = None
    raw_area = float(contours.geometry.area.sum())
    for midpoint in sorted(contours["band_midpoint"].unique(), reverse=True):
        geometry = unary_union(contours.loc[contours["band_midpoint"] == midpoint, "geometry"])
        if geometry.is_empty:
            continue
        clean = geometry if covered is None else geometry.difference(covered)
        if not clean.is_empty:
            records.append({"band_midpoint": float(midpoint), "geometry": clean})
        covered = geometry if covered is None else unary_union([covered, geometry])
    union_area = 0.0 if covered is None else float(covered.area)
    duplicate_fraction = 0.0 if raw_area == 0 else max(0.0, (raw_area - union_area) / raw_area)
    return gpd.GeoDataFrame(records, geometry="geometry", crs=SOURCE_CRS), duplicate_fraction


def _resolve_overlaps(
    contours: gpd.GeoDataFrame,
) -> tuple[gpd.GeoDataFrame, float, dict[str, float]]:
    """Resolve source and cross-source overlaps at the highest Lden band.

    SICA GeoPackages can encode nested or fragmented bands within one
    agglomeration, while neighbouring agglomerations can model a shared fringe.
    Both are representation overlaps, not duplicate exposure.  The priority
    dissolve gives every square metre one unambiguous Lden value and records
    the discarded fractions for audit.
    """
    source_clean: list[gpd.GeoDataFrame] = []
    within_source_overlap: dict[str, float] = {}
    for source_id, frame in contours.groupby("source_id", sort=True):
        dissolved, overlap = _priority_dissolve(frame)
        within_source_overlap[str(source_id)] = overlap
        source_clean.append(dissolved)
    combined = gpd.GeoDataFrame(
        pd.concat(source_clean, ignore_index=True), geometry="geometry", crs=SOURCE_CRS
    )
    resolved, cross_source_overlap = _priority_dissolve(combined)
    return resolved, cross_source_overlap, within_source_overlap


def _summarise_units(
    units: gpd.GeoDataFrame,
    contours: gpd.GeoDataFrame,
    source_contours: Iterable[gpd.GeoDataFrame],
) -> tuple[pd.DataFrame, float]:
    """Aggregate Lden bands inside each published administrative unit.

    Priority resolution deliberately happens after clipping to a unit. It is
    equivalent to dissolving the whole region first, but avoids expensive
    metropolitan unions for a small pilot and keeps the computation local to
    the actual rendered support.
    """
    metric = units.to_crs(SOURCE_CRS)
    rows: list[dict[str, Any]] = []
    total_raw_area = 0.0
    total_resolved_area = 0.0
    for unit in metric.itertuples(index=False):
        geometry = unit.geometry
        numerator = 0.0
        area_55 = 0.0
        area_65 = 0.0
        covered = None
        raw_area = 0.0
        for midpoint in sorted(contours["band_midpoint"].unique(), reverse=True):
            geometries = contours.loc[contours["band_midpoint"] == midpoint, "geometry"]
            clipped = [
                item.intersection(geometry)
                for item in geometries
                if item.intersects(geometry)
            ]
            clipped = [item for item in clipped if not item.is_empty and item.area > 0]
            if not clipped:
                continue
            band_geometry = unary_union(clipped)
            raw_area += sum(float(item.area) for item in clipped)
            clean = band_geometry if covered is None else band_geometry.difference(covered)
            area_m2 = float(clean.area)
            if area_m2 > 0:
                area_55 += area_m2
                numerator += area_m2 * float(midpoint)
                if float(midpoint) >= 67.0:
                    area_65 += area_m2
            covered = band_geometry if covered is None else unary_union([covered, band_geometry])
        has_modelled = int(area_55 > 0)
        area_km2 = float(unit.area_km2)
        total_raw_area += raw_area
        total_resolved_area += area_55
        rows.append(
            {
                "spatial_id": unit.spatial_id,
                "spatial_name": unit.spatial_name,
                "noise_lden_band_mean_dba": numerator / area_55 if has_modelled else np.nan,
                "noise_lden_ge55_area_km2": area_55 / 1_000_000 if has_modelled else np.nan,
                "noise_lden_ge55_area_pct": area_55 / (area_km2 * 1_000_000) * 100 if has_modelled else np.nan,
                "noise_lden_ge65_area_pct": area_65 / (area_km2 * 1_000_000) * 100 if has_modelled else np.nan,
                "noise_agglomeration_count": sum(
                    any(item.intersection(geometry).area > 0 for item in source.geometry)
                    for source in source_contours
                ),
                "noise_has_modelled_ge55": has_modelled,
            }
        )
    overlap_fraction = (
        0.0
        if total_raw_area == 0
        else max(0.0, (total_raw_area - total_resolved_area) / total_raw_area)
    )
    return pd.DataFrame(rows), overlap_fraction


def build_noise_spain_layer(
    *,
    study: Any,
    raw_dir: Path | None = None,
    raw_snapshot: RawSnapshotStore | None = None,
    cache_dir: Path,
    out_dir: Path,
) -> NoiseSpainOutputs:
    """Build the administrative Lden summary for one supported Spanish study."""
    if raw_snapshot is None:
        if raw_dir is None:
            raise ValueError("noise_spain requires raw_dir or raw_snapshot")
        raw_snapshot = RawSnapshotStore(manifest_root=raw_dir, payload_root=raw_dir)
    elif raw_dir is not None:
        raise ValueError("Pass either raw_dir or raw_snapshot, not both")
    region = _region_for_study(study)
    settings = _noise_settings(study)
    partial = settings.get("coverage") == "partial"
    assets = _assets_for_region(raw_snapshot, region, require_complete=not partial)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    metric_units = study.spatial_units.to_crs(SOURCE_CRS)
    study_footprint = unary_union(metric_units.geometry)
    source_frames: list[gpd.GeoDataFrame] = []
    exposure_frames: list[pd.DataFrame] = []
    source_bbox = tuple(float(value) for value in metric_units.total_bounds)
    for asset in tqdm(assets, desc=f"Ruido SICA {region}", unit="aglomeración"):
        gpkg = _extract_gpkg(raw_snapshot, asset, cache_dir)
        source_id = Path(asset.path).stem
        source_frames.append(
            _source_contours(
                gpkg,
                source_id,
                source_bbox=source_bbox,
                clip_geometry=study_footprint,
            )
        )
        exposure_frames.append(_exposure_rows(gpkg, source_id))
    all_contours = gpd.GeoDataFrame(
        pd.concat(source_frames, ignore_index=True), geometry="geometry", crs=SOURCE_CRS
    )
    summary, resolved_overlap = _summarise_units(metric_units, all_contours, source_frames)
    geometry = study.spatial_units[["spatial_id", "spatial_name", "geometry"]].merge(
        summary, on=["spatial_id", "spatial_name"], how="left", validate="one_to_one"
    )
    geometry = gpd.GeoDataFrame(geometry, geometry="geometry", crs=study.spatial_units.crs)

    stem = f"{study.study.id}_noise_spain_mer_2022"
    table_path = out_dir / f"{stem}.csv"
    geometry_path = out_dir / f"{stem}.geojson"
    metadata_path = out_dir / f"{stem}_metadata.json"
    diagnostics = out_dir / "diagnostics"
    diagnostics.mkdir(exist_ok=True)
    exposure_path = diagnostics / "agglomeration_exposure.csv"
    summary.to_csv(table_path, index=False)
    geometry.to_file(geometry_path, driver="GeoJSON")
    pd.concat(exposure_frames, ignore_index=True).to_csv(exposure_path, index=False)
    metadata_path.write_text(
        pd.Series(
            {
                "source": "SICA/MITECO Mapas Estratégicos de Ruido — cuarta fase",
                "year": 2022,
                "region": region,
                "coverage": "partial" if partial else "complete",
                "source_crs": SOURCE_CRS,
                "source_support": "vector contour bands (all sources, Lden)",
                "analysis": "area-weighted intersection with study administrative polygons",
                "rendered_support": "administrative polygons only; no fine detail published",
                "band_midpoints_dba": {"55-59": 57, "60-64": 62, "65-69": 67, "70-74": 72, ">75": 77.5},
                "included_threshold": "Lden >=55 dB(A)",
                "archive_count": len(assets),
                "archive_sha256": {asset.path: asset.sha256 for asset in assets},
                "unit_resolved_overlap_fraction": resolved_overlap,
                "columns": list(summary.columns),
                "coverage_note": (
                    "partial pilot: only validated SICA agglomerations intersecting the study are "
                    "included; null metrics and noise_has_modelled_ge55=0 mean no intersecting "
                    ">=55 dB(A) contour, not quiet conditions."
                    if partial
                    else "null metrics and noise_has_modelled_ge55=0 mean no intersecting >=55 dB(A) contour, not quiet conditions."
                ),
            }
        ).to_json(force_ascii=False, indent=2),
        encoding="utf-8",
    )
    return NoiseSpainOutputs(table_path, geometry_path, metadata_path, exposure_path)

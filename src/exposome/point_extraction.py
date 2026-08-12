"""Extract published exposome values at points, keyed by indicator.

This is the ``--source published`` path and the one the web tab mirrors.  It is
deliberately **indicator-keyed**, not layer-keyed: ``detail/<indicator_id>.tif``
is already one file per indicator, so the caller never has to know that
``heat_summer_tmax`` is band 1 of ``climate_heat`` or that ``wind`` is band 3.

:mod:`exposome.point_query` remains the layer-keyed sampler for native studies
(``--source native``).  The two produce **different tables on purpose**: this one
is long-format with one row per point x indicator x year x radius, carrying the
declared support of every value.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd

from .point_buffer import buffer_weights, sample_band
from .point_support import (
    ADMINISTRATIVE_UNIT,
    DEFAULT_RADII,
    RASTER_BLOCK,
    describe_radius,
    emits_within_buffer_sd,
    estimand_kind,
    has_support,
)

DEFAULT_DATA_ROOT = Path("webapp/public/data")

# Quality flags, worst last.  ``quality_flag`` reports the worst that applies.
FLAG_OK = "ok"
FLAG_SUB_OBSERVATION = "sub_observation"
FLAG_PARTIAL_COVERAGE = "partial_coverage"
FLAG_NO_DATA = "no_data"
FLAG_UNSUPPORTED = "unsupported_detail_type"
FLAG_NOT_PUBLISHED = "not_published_by_study"
FLAG_OUT_OF_COVERAGE = "out_of_coverage"
_FLAG_ORDER = [
    FLAG_OK,
    FLAG_SUB_OBSERVATION,
    FLAG_PARTIAL_COVERAGE,
    FLAG_NO_DATA,
    FLAG_UNSUPPORTED,
    FLAG_NOT_PUBLISHED,
    FLAG_OUT_OF_COVERAGE,
]

#: Below this share of valid data the value is flagged rather than trusted.
COVERAGE_THRESHOLD = 0.8


@dataclass(frozen=True)
class BundleStudy:
    """One published study bundle, as declared by ``catalog.json``."""

    study_id: str
    city: str
    country_code: str
    bundle: str
    bbox: tuple[float, float, float, float]
    unit_type: str | None
    root: Path

    @property
    def area(self) -> float:
        west, south, east, north = self.bbox
        return abs(east - west) * abs(north - south)

    def contains(self, lon: float, lat: float) -> bool:
        west, south, east, north = self.bbox
        return west <= lon <= east and south <= lat <= north

    @property
    def manifest(self) -> dict[str, Any]:
        return _read_json(self.root / "manifest.json")

    @property
    def palette(self) -> dict[str, Any]:
        return _read_json(self.root / "palette.json")


@lru_cache(maxsize=64)
def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def load_bundle_catalog(data_root: Path | str = DEFAULT_DATA_ROOT, *,
                        include_hidden: bool = False) -> list[BundleStudy]:
    """Every published, available study, smallest bbox first.

    Sorting by area means a point inside both a metro study and a city study
    resolves to the finer one.

    Hidden studies are excluded by default.  They are not picker-visible, and
    including them would route a CABA address to ``buenos_aires_comunas``
    (hidden, no detail COGs) instead of ``buenos_aires_amba``, purely because
    its bounding box is smaller.
    """
    data_root = Path(data_root)
    catalog = _read_json(data_root / "catalog.json")
    studies: list[BundleStudy] = []
    for record in catalog.get("studies", []):
        if not record.get("available"):
            continue
        if record.get("hidden") and not include_hidden:
            continue
        bbox = record.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        studies.append(
            BundleStudy(
                study_id=record["study_id"],
                city=record.get("city", ""),
                country_code=record.get("country_code", ""),
                bundle=record["bundle"],
                bbox=(float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])),
                unit_type=record.get("unit_type"),
                root=data_root / record["bundle"],
            )
        )
    return sorted(studies, key=lambda study: study.area)


def study_for_point(studies: Sequence[BundleStudy], lon: float, lat: float
                    ) -> BundleStudy | None:
    """Resolve a point to its containing study, or None if outside all of them.

    A pasted batch crosses countries by nature, so the study is a property of
    each row rather than of the request.
    """
    for study in studies:
        if study.contains(lon, lat):
            return study
    return None


def detail_asset(study: BundleStudy, indicator_id: str, year: int | str | None = None
                 ) -> dict[str, Any] | None:
    """The published detail asset for an indicator, from the manifest only.

    ``palette.json`` is never consulted here: its ``has_fine_layer`` flag names
    four indicators when eleven have COGs, and one of those four (``green``) has
    no ``.tif`` at all (ADR 0012 §5).
    """
    manifest = study.manifest
    if year is None:
        record = (manifest.get("spatial_indicators") or {}).get(indicator_id)
        return (record or {}).get("detail")
    temporal = (manifest.get("temporal_indicators") or {}).get(indicator_id)
    if not temporal:
        return None
    entry = (temporal.get("years") or {}).get(str(year))
    return (entry or {}).get("detail") if entry else None


def published_years(study: BundleStudy, indicator_id: str) -> list[str]:
    temporal = (study.manifest.get("temporal_indicators") or {}).get(indicator_id) or {}
    return sorted((temporal.get("years") or {}).keys())


def indicator_metadata(study: BundleStudy, indicator_id: str) -> dict[str, Any]:
    """Labels, units and the master column.  Presentation only, never availability."""
    entry = (study.palette.get("exposomes") or {}).get(indicator_id) or {}
    return {
        "label": entry.get("label"),
        "unit": entry.get("unit"),
        "column": entry.get("column"),
        "category": entry.get("category"),
    }


def _worst_flag(flags: Iterable[str]) -> str:
    ranked = [flag for flag in flags if flag in _FLAG_ORDER]
    if not ranked:
        return FLAG_OK
    return max(ranked, key=_FLAG_ORDER.index)


@lru_cache(maxsize=16)
def _master(study_root: Path):
    import geopandas as gpd

    return gpd.read_file(Path(study_root) / "master.geojson")


@lru_cache(maxsize=16)
def _projected_master(study_root: Path):
    """The master in its local metric CRS, reprojected once per study.

    Reprojecting inside the per-indicator call meant a 50-address batch with 22
    administrative indicators reprojected every polygon ~1,100 times.  Same
    shape of bug as the O(n^2) OSM scan, and the draggable-pin re-extraction in
    the tab has to feel immediate.
    """
    master = _master(study_root)
    metric = master.estimate_utm_crs()
    return master.to_crs(metric), metric


def _administrative_value(study: BundleStudy, indicator_id: str, lon: float, lat: float,
                          max_radius_m: float) -> dict[str, Any]:
    """The containing unit's value, plus boundary diagnostics — never a blend.

    Averaging across administrative units would produce a number that exists in
    neither of them, which is what ADR 0004 §5 forbids.  Fragility near a border
    is reported separately so the user can judge it.
    """
    from shapely.geometry import Point

    master = _master(study.root)
    column = indicator_metadata(study, indicator_id).get("column")
    point = Point(lon, lat)
    containing = master[master.contains(point)]
    if containing.empty or not column or column not in master.columns:
        return {
            "value": None,
            "spatial_id": None,
            "spatial_name": None,
            "units_touched": 0,
            "distance_to_boundary_m": None,
            "flag": FLAG_NOT_PUBLISHED if column not in master.columns else FLAG_NO_DATA,
        }
    row = containing.iloc[0]
    value = row.get(column)

    import geopandas as gpd

    projected, metric = _projected_master(study.root)
    point_m = gpd.GeoSeries([point], crs="EPSG:4326").to_crs(metric).iloc[0]
    boundary = projected.loc[containing.index[0]].geometry.exterior
    distance = float(point_m.distance(boundary)) if boundary is not None else None
    touched = int(projected.intersects(point_m.buffer(max(max_radius_m, 1.0))).sum())

    return {
        "value": None if pd.isna(value) else float(value),
        "spatial_id": row.get("spatial_id"),
        "spatial_name": row.get("spatial_name"),
        "units_touched": touched,
        "distance_to_boundary_m": distance,
        "flag": FLAG_OK if not pd.isna(value) else FLAG_NO_DATA,
    }


def _raster_value(study: BundleStudy, indicator_id: str, asset: dict[str, Any],
                  lon: float, lat: float, radius_m: float) -> dict[str, Any]:
    import rasterio
    from pyproj import CRS, Transformer

    path = study.root / asset["path"]
    if not path.exists():
        return {"value": None, "sd": None, "n_cells": 0, "coverage_fraction": 0.0,
                "flag": FLAG_NOT_PUBLISHED}

    band = int(asset.get("band") or 1)
    with rasterio.open(path) as src:
        transformer = Transformer.from_crs(
            CRS.from_epsg(4326), src.crs or CRS.from_epsg(4326), always_xy=True
        )
        x, y = transformer.transform(lon, lat)
        weights = buffer_weights(src, x, y, radius_m)
        if weights is None:
            return {"value": None, "sd": None, "n_cells": 0, "coverage_fraction": 0.0,
                    "flag": FLAG_OUT_OF_COVERAGE}
        stats = sample_band(src, band, weights)

    flag = FLAG_OK
    if stats["value"] is None:
        flag = FLAG_NO_DATA
    elif stats["coverage_fraction"] < COVERAGE_THRESHOLD:
        flag = FLAG_PARTIAL_COVERAGE
    return {**stats, "sd": stats["sd"], "flag": flag}


def extract_points(
    points: pd.DataFrame,
    indicators: Sequence[str],
    radii: Sequence[float] = DEFAULT_RADII,
    years: Sequence[int | str] | None = None,
    data_root: Path | str = DEFAULT_DATA_ROOT,
) -> pd.DataFrame:
    """Long-format extraction: one row per point x indicator x year x radius.

    ``points`` needs ``query_id``, ``lon`` and ``lat``; any other column is
    carried through untouched so geocoding provenance survives to the output.
    """
    studies = load_bundle_catalog(data_root)
    rows: list[dict[str, Any]] = []
    max_radius = max([float(radius) for radius in radii] or [0.0])

    carried = [
        column for column in points.columns
        if column not in {"query_id", "lon", "lat"}
    ]
    for point in points.itertuples(index=False):
        lon, lat = float(point.lon), float(point.lat)
        study = study_for_point(studies, lon, lat)
        base = {
            "query_id": getattr(point, "query_id", None),
            "lon": lon,
            "lat": lat,
            "study_id": study.study_id if study else None,
            "city": study.city if study else None,
            "country_code": study.country_code if study else None,
        }
        # Carry geocoding provenance through untouched: geocode_accuracy_m only
        # means something next to support_m, so it has to reach the same row.
        base.update({column: getattr(point, column, None) for column in carried})
        if study is None:
            rows.append({**base, "exposome_id": None, "quality_flag": FLAG_OUT_OF_COVERAGE})
            continue

        for indicator_id in indicators:
            if not has_support(indicator_id):
                rows.append({**base, "exposome_id": indicator_id,
                             "quality_flag": FLAG_NOT_PUBLISHED})
                continue
            kind = estimand_kind(indicator_id)
            meta = indicator_metadata(study, indicator_id)
            selected_years: list[int | str | None]
            if years:
                selected_years = list(years)
            else:
                selected_years = [None]

            for year in selected_years:
                rows.extend(
                    _rows_for_indicator(
                        study, indicator_id, kind, meta, base, lon, lat,
                        radii, year, max_radius,
                    )
                )
    return pd.DataFrame(rows)


def _rows_for_indicator(study, indicator_id, kind, meta, base, lon, lat, radii, year,
                        max_radius) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    common = {
        **base,
        "exposome_id": indicator_id,
        "label": meta.get("label"),
        "unit": meta.get("unit"),
        "category": meta.get("category"),
        "year": year,
        "estimand_kind": kind,
    }

    # The study's own declaration wins: a Chile-only layer says why it is
    # missing in Lima rather than surfacing as an absent master column.
    unavailable = indicator_availability(study, indicator_id)
    if unavailable is not None:
        rows.append({**common, "radius_m": None, "value": None,
                     "unavailable_reason": unavailable,
                     "quality_flag": FLAG_NOT_PUBLISHED})
        return rows

    if kind != RASTER_BLOCK:
        # One row only: an administrative or composite value has no radius.
        support = describe_radius(indicator_id, 0, lat)
        admin = _administrative_value(study, indicator_id, lon, lat, max_radius)
        rows.append({
            **common,
            "radius_m": None,
            "radius_status": support["radius_status"],
            "value": admin["value"],
            "sd_within_buffer": None,
            "n_cells": None,
            "coverage_fraction": None,
            "support_m": support["support_m"],
            "observation_support_m": support["observation_support_m"],
            "analysis_support_m": support["analysis_support_m"],
            "spatial_id": admin["spatial_id"],
            "spatial_name": admin["spatial_name"],
            "units_touched": admin["units_touched"],
            "distance_to_boundary_m": admin["distance_to_boundary_m"],
            "source_asset": "master.geojson",
            "quality_flag": admin["flag"],
        })
        return rows

    asset = detail_asset(study, indicator_id, year)
    if not asset:
        rows.append({**common, "radius_m": None, "value": None,
                     "quality_flag": FLAG_NOT_PUBLISHED})
        return rows
    if asset.get("type") != "cog":
        # ``green`` publishes a fine polygon layer, not a raster.  Saying so is
        # better than 404-ing on a .tif that was never written.
        rows.append({**common, "radius_m": None, "value": None,
                     "source_asset": asset.get("path"),
                     "quality_flag": FLAG_UNSUPPORTED})
        return rows

    for radius in radii:
        support = describe_radius(indicator_id, radius, lat)
        stats = _raster_value(study, indicator_id, asset, lon, lat, float(radius))
        emit_sd = emits_within_buffer_sd(indicator_id, radius, lat)
        rows.append({
            **common,
            "radius_m": float(radius),
            "radius_status": support["radius_status"],
            "value": stats["value"],
            # Under sub_observation the spread collapses toward zero and would
            # read as high confidence exactly where the data is least
            # informative (ADR 0012 4).
            "sd_within_buffer": stats["sd"] if emit_sd else None,
            "n_cells": stats["n_cells"],
            "coverage_fraction": stats["coverage_fraction"],
            "support_m": support["support_m"],
            "observation_support_m": support["observation_support_m"],
            "analysis_support_m": support["analysis_support_m"],
            "source_asset": asset.get("path"),
            "source_native_resolution_m": asset.get("source_native_resolution_m"),
            "quality_flag": _worst_flag([stats["flag"], support["radius_status"]]),
        })
    return rows


def indicator_availability(study: BundleStudy, indicator_id: str) -> str | None:
    """The study's own reason an indicator is unavailable, or None if it is.

    ADR 0004 §11: each indicator may declare ``available``,
    ``country_not_supported``, ``not_enabled_by_study``,
    ``not_published_by_study`` or ``coming_soon``.  Honouring it is what lets a
    Chile-only layer say *why* it is missing in Lima instead of surfacing as an
    absent column later.
    """
    record = (study.manifest.get("spatial_indicators") or {}).get(indicator_id)
    if record is None:
        return FLAG_NOT_PUBLISHED
    availability = record.get("availability") or {}
    if availability.get("status") in (None, "available"):
        return None
    return str(availability.get("reason") or availability.get("status"))


def available_indicators(study: BundleStudy) -> dict[str, str]:
    """What each indicator can deliver for this study, without reading pixels."""
    manifest = study.manifest
    spatial = manifest.get("spatial_indicators") or {}
    status: dict[str, str] = {}
    for indicator_id, record in spatial.items():
        if not has_support(indicator_id):
            status[indicator_id] = "undeclared_support"
            continue
        unavailable = indicator_availability(study, indicator_id)
        if unavailable is not None:
            status[indicator_id] = unavailable
            continue
        kind = estimand_kind(indicator_id)
        if kind != RASTER_BLOCK:
            status[indicator_id] = ADMINISTRATIVE_UNIT
            continue
        detail = record.get("detail")
        if not detail:
            status[indicator_id] = FLAG_NOT_PUBLISHED
        elif detail.get("type") == "cog":
            status[indicator_id] = "cog"
        else:
            status[indicator_id] = str(detail.get("type"))
    return status


def coverage_summary(frame: pd.DataFrame) -> dict[str, Any]:
    """Counts a caller can print or put in the extraction manifest."""
    if frame.empty:
        return {"rows": 0}
    flags = frame.get("quality_flag")
    return {
        "rows": int(len(frame)),
        "points": int(frame["query_id"].nunique()),
        "studies": sorted(frame["study_id"].dropna().unique().tolist()),
        "values": int(frame["value"].notna().sum()) if "value" in frame else 0,
        "by_flag": flags.value_counts().to_dict() if flags is not None else {},
        "sub_observation_share": (
            float((frame.get("radius_status") == FLAG_SUB_OBSERVATION).mean())
            if "radius_status" in frame
            else math.nan
        ),
    }

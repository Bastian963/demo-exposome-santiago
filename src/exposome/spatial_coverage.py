"""Coverage audit for the maximum spatial support each method can publish.

``spatial_audit`` answers whether a published manifest tells the truth.  This
module answers a different operational question: which of the details that a
method can honestly provide are still missing from a study bundle?
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .spatial_support import (
    INDICATOR_SUPPORT,
    canonical_detail_source_grid,
    publication_target,
)


@dataclass(frozen=True)
class SpatialCoverage:
    """Machine-readable completeness result for one study manifest."""

    study_id: str
    mode: str
    indicators: Mapping[str, Mapping[str, Any]]
    required: int
    complete: int
    missing: tuple[str, ...]

    @property
    def status(self) -> str:
        return "complete" if not self.missing else "partial"

    @property
    def publication_tier(self) -> str:
        # A native companion is source material for an aggregate browser map;
        # it is intentionally not promoted as a standalone city release.
        if self.mode == "native":
            return "preview"
        return "production" if self.status == "complete" else "preview"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "publication_tier": self.publication_tier,
            "required_indicators": self.required,
            "complete_indicators": self.complete,
            "missing_indicators": list(self.missing),
            "indicators": {key: dict(value) for key, value in self.indicators.items()},
        }


_LAYER_ALIASES = {
    "air_quality_pm25": {"pm25"},
}


def _layer_available(record: Mapping[str, Any], layers: Mapping[str, Any]) -> bool:
    availability = record.get("availability")
    if isinstance(availability, Mapping) and availability.get("status") in {
        "available",
        "unavailable",
    }:
        return availability.get("status") == "available"
    layer_id = str(record.get("layer_id") or "")
    candidates = {layer_id, *_LAYER_ALIASES.get(layer_id, set())}
    for candidate in candidates:
        layer = layers.get(candidate)
        if isinstance(layer, Mapping):
            if layer.get("available", True):
                return True
        elif layer is not None:
            return True
    return False


def _indicator_status(
    indicator_id: str,
    record: Mapping[str, Any],
    layers: Mapping[str, Any],
    temporal_record: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    target = record.get("publication_target")
    if not isinstance(target, Mapping):
        # Historical v3 manifests predate publication_target.  Derive their
        # obligation from today's canonical indicator declaration, rather than
        # perpetuating a stale support description that the current contract
        # has explicitly corrected (for example city-relative heat indices).
        target = publication_target(INDICATOR_SUPPORT.get(indicator_id, record))
    available = _layer_available(record, layers)
    base_required = bool(target.get("required_for_production")) and available
    detail = record.get("detail")
    rendered = record.get("rendered")
    has_detail = isinstance(detail, Mapping) and detail.get("type") in {
        "cog",
        "geojson",
        "vector_contours",
    }
    invalid_reason = None
    if isinstance(detail, Mapping) and detail.get("type") == "cog":
        if detail.get("canonical_resolution_verified") is not True:
            invalid_reason = "canonical_resolution_unverified"
        elif not canonical_detail_source_grid(indicator_id, detail):
            invalid_reason = "source_grid_mismatch"
    elif isinstance(detail, Mapping) and detail.get("type") == "vector_contours":
        from .spatial_support import validate_vector_contour_descriptor

        if validate_vector_contour_descriptor(indicator_id, detail):
            invalid_reason = "vector_contours_unverified"
    valid_detail = has_detail and invalid_reason is None
    renders_detail = isinstance(rendered, Mapping) and rendered.get("kind") in {
        "cog",
        "geojson",
        "vector_contours",
    }
    temporal_required = False
    temporal_complete = True
    missing_years: list[str] = []
    if isinstance(temporal_record, Mapping):
        spatial_target = temporal_record.get("spatial_target")
        temporal_required = (
            isinstance(spatial_target, Mapping)
            and spatial_target.get("required_for_production") is True
        )
        if not isinstance(spatial_target, Mapping):
            temporal_required = base_required
        if temporal_required:
            expected_years = temporal_record.get("expected_years")
            years = temporal_record.get("years")
            if expected_years is None and isinstance(years, Mapping):
                expected_years = [str(value) for value in years]
            if not isinstance(expected_years, list) or not isinstance(years, Mapping):
                temporal_complete = False
            else:
                for raw_year in expected_years:
                    year = str(raw_year)
                    year_record = years.get(year)
                    annual_detail = (
                        year_record.get("detail")
                        if isinstance(year_record, Mapping)
                        else None
                    )
                    valid_annual = isinstance(annual_detail, Mapping)
                    if valid_annual:
                        support = annual_detail.get("temporal_support")
                        valid_annual = (
                            annual_detail.get("source_support_preserved") is True
                            and isinstance(support, Mapping)
                            and support.get("kind") == "year"
                            and str(support.get("year")) == year
                            and (
                                (
                                    annual_detail.get("type") == "cog"
                                    and annual_detail.get("canonical_resolution_verified")
                                    is True
                                )
                                or (
                                    annual_detail.get("type") == "geojson"
                                    and annual_detail.get("analysis_grid_verified") is True
                                    and annual_detail.get("grid_alignment")
                                    == "study_aoi_metric_grid"
                                )
                            )
                        )
                    if not valid_annual:
                        missing_years.append(year)
                temporal_complete = not missing_years
    required = base_required or temporal_required
    base_complete = valid_detail and renders_detail
    state = (
        "complete"
        if required
        and (base_complete or not base_required)
        and temporal_complete
        else "missing"
        if required
        else "not_applicable"
    )
    if not temporal_complete:
        invalid_reason = "annual_detail_incomplete"
    return {
        "indicator_id": indicator_id,
        "target": dict(target),
        "layer_available": available,
        "status": state,
        "detail": detail.get("path") if isinstance(detail, Mapping) else None,
        "reason": invalid_reason,
        "temporal_required": temporal_required,
        "temporal_complete": temporal_complete,
        "missing_years": missing_years,
        "availability": dict(record.get("availability") or {}),
    }


def coverage_for_manifest(manifest: Mapping[str, Any]) -> SpatialCoverage:
    """Compute coverage from an already loaded browser manifest."""
    mode = str(manifest.get("mode") or "aggregate")
    records = manifest.get("spatial_indicators")
    if not isinstance(records, Mapping):
        raise ValueError("manifest has no spatial_indicators mapping")
    layers = manifest.get("layers")
    if not isinstance(layers, Mapping):
        layers = {}
    temporal = manifest.get("temporal_indicators")
    if not isinstance(temporal, Mapping):
        temporal = {}
    entries = {
        str(indicator_id): _indicator_status(
            str(indicator_id),
            record,
            layers,
            temporal.get(str(indicator_id))
            if isinstance(temporal.get(str(indicator_id)), Mapping)
            else None,
        )
        for indicator_id, record in records.items()
        if isinstance(record, Mapping)
    }
    if mode == "native":
        # Native bundles expose source material/downloads.  Completion is
        # evaluated on their paired aggregate study, where browser detail is
        # actually attached.
        entries = {
            key: {**value, "status": "not_applicable"}
            for key, value in entries.items()
        }
    required_entries = [
        entry
        for entry in entries.values()
        if (
            entry["target"].get("required_for_production")
            or entry.get("temporal_required")
        )
        and entry["layer_available"]
    ]
    missing = tuple(
        indicator_id
        for indicator_id, entry in entries.items()
        if entry["status"] == "missing"
    )
    complete = sum(1 for entry in required_entries if entry["status"] == "complete")
    return SpatialCoverage(
        study_id=str(manifest.get("study_id") or "<unknown>"),
        mode=mode,
        indicators=entries,
        required=len(required_entries) if mode != "native" else 0,
        complete=complete if mode != "native" else 0,
        missing=missing,
    )


def audit_spatial_coverage(bundle_path: str | Path) -> SpatialCoverage:
    """Load a published bundle and report its spatial-product coverage."""
    path = Path(bundle_path) / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid study manifest: {path}") from exc
    if not isinstance(manifest, Mapping):
        raise ValueError(f"study manifest must be an object: {path}")
    return coverage_for_manifest(manifest)

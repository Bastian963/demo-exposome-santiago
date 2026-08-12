"""Human-executable recovery plans for missing spatial products.

This module never contacts a provider.  It turns a coverage result into the
exact resumable commands that a person can run, preserving the distinction
between a native source export, aggregate master calculation and local detail
publication.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .spatial_coverage import SpatialCoverage, audit_spatial_coverage, coverage_for_manifest
from .spatial_support import indicators_for_bundle
from .layers import load_layer_catalog
from .studies import load_study


@dataclass(frozen=True)
class SpatialRecoveryPlan:
    study_id: str
    native_study: str | None
    missing_indicators: tuple[str, ...]
    commands: tuple[str, ...]
    manual_indicators: tuple[str, ...]
    required_layer_recovery: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    assessment_source: str = "configured_study"
    bundle: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "native_study": self.native_study,
            "missing_indicators": list(self.missing_indicators),
            "commands": list(self.commands),
            "manual_indicators": list(self.manual_indicators),
            "required_layer_recovery": list(self.required_layer_recovery),
            "prerequisites": list(self.prerequisites),
            "assessment_source": self.assessment_source,
            "bundle": self.bundle,
        }


# indicator -> (native source layer, aggregate calculation layer)
_DIRECT_RECIPES: Mapping[str, tuple[str, str]] = {
    "pm25": ("air_quality_pm25", "pm25"),
    "no2": ("air_quality_satellite", "air_quality_satellite"),
    "alan": ("alan", "alan"),
    "wind": ("wind", "wind"),
    "canopy": ("greenspace_multisource", "greenspace_multisource"),
    "heat_summer_tmax": ("climate_heat", "climate_heat"),
    "heat_hot_days": ("climate_heat", "climate_heat"),
    "heat_tropical_nights": ("climate_heat", "climate_heat"),
    "rain_annual": ("precipitation", "precipitation"),
    "rain_dry_spell": ("precipitation", "precipitation"),
    "rain_heavy": ("precipitation", "precipitation"),
}


def _plan_from_coverage(
    coverage: SpatialCoverage,
    *,
    context: Any,
    published_bundle: bool = False,
) -> SpatialRecoveryPlan:
    raw_detail = context.study.raw.get("detail", {})
    native_study = raw_detail.get("native_study") if isinstance(raw_detail, Mapping) else None
    missing = tuple(coverage.missing)
    catalog = load_layer_catalog()
    configured_layers = getattr(
        context,
        "enabled_layers",
        getattr(context.study, "enabled_layers", ()),
    )
    paths = getattr(context, "paths", None)
    required_layer_recovery = tuple(
        layer_id
        for layer_id in dict.fromkeys(
            catalog.resolve_id(layer_id) for layer_id in configured_layers
        )
        if paths is not None
        and not (paths.layer_processed(layer_id) / "manifest.json").is_file()
    )
    native_layers = sorted({_DIRECT_RECIPES[item][0] for item in missing if item in _DIRECT_RECIPES})
    # A published bundle already proves that each ``layer_available`` aggregate
    # artifact was materialized into the release. Missing direct raster detail
    # therefore needs only its native re-export and local COG rebuild. Re-running
    # the aggregate would contact providers again without changing that detail.
    aggregate_layers = sorted(
        {
            _DIRECT_RECIPES[item][1]
            for item in missing
            if item in _DIRECT_RECIPES
            and not published_bundle
        }
    )
    # An enabled output absent from the local Study cannot be recovered by the
    # v1->v2 migrator.  Current examples include greenspace_multisource added
    # to a historic aggregate release after its original publication.
    for layer_id in required_layer_recovery:
        if layer_id == "greenspace_multisource":
            native_layers.append(layer_id)
            aggregate_layers.append(layer_id)
        else:
            aggregate_layers.append(layer_id)
    native_layers = sorted(set(native_layers))
    aggregate_layers = sorted(set(aggregate_layers))
    commands: list[str] = []
    prerequisites: list[str] = []
    if native_layers:
        if not native_study:
            prerequisites.append(
                "declare detail.native_study with a validated dissolved AOI before native raster recovery"
            )
        else:
            commands.append(
                f"exposome run --study {native_study} --layers {','.join(native_layers)} --resume"
            )
    if not prerequisites:
        if aggregate_layers:
            commands.append(
                f"exposome run --study {coverage.study_id} --layers {','.join(aggregate_layers)} --resume"
            )
        direct_indicators = [item for item in missing if item in _DIRECT_RECIPES]
        if direct_indicators:
            commands.append(
                f"exposome detail --study {coverage.study_id} --indicators {','.join(direct_indicators)} --resume"
            )
    if "green" in missing and not prerequisites:
        commands.append(
            f"python scripts/export_webapp_green_subcomuna.py --study {coverage.study_id}"
        )
    if "healthcare" in missing and not prerequisites:
        commands.append(
            f"exposome run --study {coverage.study_id} --layers healthcare --resume"
        )
    if commands:
        commands.extend(
            [
                "python scripts/migrations/upgrade_artifact_manifests_v2.py "
                f"--study {coverage.study_id} --write --allow-stale-settings",
                f"python scripts/export_study_profiles.py --study {coverage.study_id}",
                f"exposome materialize --study {coverage.study_id}",
                f"exposome verify --study {coverage.study_id}",
                f"exposome publish --study {coverage.study_id}",
            ]
        )
    manual = tuple(item for item in missing if item not in _DIRECT_RECIPES and item not in {"green", "healthcare"})
    return SpatialRecoveryPlan(
        study_id=coverage.study_id,
        native_study=str(native_study) if native_study else None,
        missing_indicators=missing,
        commands=tuple(commands),
        manual_indicators=manual,
        required_layer_recovery=required_layer_recovery,
        prerequisites=tuple(prerequisites),
    )


def recovery_plan_for_bundle(bundle_path: str | Path, *, repo_root: str | Path) -> SpatialRecoveryPlan:
    """Create a no-provider recovery plan for one published aggregate bundle."""
    coverage: SpatialCoverage = audit_spatial_coverage(bundle_path)
    context = load_study(coverage.study_id, repo_root_path=repo_root)
    plan = _plan_from_coverage(coverage, context=context, published_bundle=True)
    return SpatialRecoveryPlan(
        **{
            **plan.__dict__,
            "assessment_source": "published_bundle",
            "bundle": str(Path(bundle_path)),
        }
    )


def recovery_plan_for_study(
    study_id: str,
    *,
    repo_root: str | Path,
    output_root: str | Path = "webapp/public/data",
    version: str = "v1",
) -> SpatialRecoveryPlan:
    """Plan an aggregate study from its publication, or config before first publish."""
    context = load_study(study_id, repo_root_path=repo_root)
    if context.is_native:
        raise ValueError("resolution plans target aggregate studies, not native companions")
    output = Path(output_root)
    if not output.is_absolute():
        output = Path(repo_root) / output
    bundle = (
        output
        / version
        / context.location.country_code.lower()
        / context.city
        / context.study.id
    )
    if (bundle / "manifest.json").exists():
        plan = recovery_plan_for_bundle(bundle, repo_root=repo_root)
        if plan.study_id != context.study.id:
            raise ValueError(
                f"Published bundle identity mismatch for {context.study.id!r}: "
                f"manifest declares {plan.study_id!r} at {bundle}"
            )
        return plan
    layers = {layer_id: {"available": True} for layer_id in context.study.enabled_layers}
    coverage = coverage_for_manifest(
        {
            "study_id": context.study.id,
            "mode": "aggregate",
            "layers": layers,
            "spatial_indicators": indicators_for_bundle([]),
        }
    )
    return _plan_from_coverage(coverage, context=context)

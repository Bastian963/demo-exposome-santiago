"""Typed Layer runner registry with one explicit legacy-function adapter.

The adapter is the temporary seam for importable ``build_*`` functions.  It
declares accepted arguments per registration and never introspects signatures.
New runners should implement ``LayerRunner`` directly and return explicit asset
roles without using :class:`LegacyFunctionAdapter`.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .config import resolved_config_scope
from .execution import (
    LayerBuildResult,
    LayerExecutionContext,
    LayerRunner,
    ProducedAsset,
)
from .noise_spain import (
    RAW_DATASET as SPAIN_NOISE_DATASET,
    RAW_PROVIDER as SPAIN_NOISE_PROVIDER,
    build_noise_spain_layer,
)
from .raw_sources import load_source_manifest


@dataclass(frozen=True)
class LegacyFunctionAdapter:
    """Explicit adapter for one importable pre-contract Layer builder."""

    module: str
    function: str
    arguments: tuple[str, ...]
    raw_snapshot: tuple[str, str, str] | None = None
    algorithm_version: str = "1"

    def __call__(self, execution: LayerExecutionContext) -> LayerBuildResult:
        study = execution.study
        candidates: dict[str, Any] = {
            "city": study.study.id,
            "cache_dir": execution.cache_dir,
            "out_dir": execution.output_dir,
            "figures_dir": execution.output_dir / "figures",
            "resume": execution.resume,
        }
        candidates.update(execution.inputs)
        source_manifests: list[Path] = []
        if self.raw_snapshot is not None:
            provider, dataset, version = self.raw_snapshot
            raw_dir = study.paths.provider_raw(provider, dataset, version)
            candidates["raw_dir"] = raw_dir
            manifest = raw_dir / "source_manifest.json"
            if manifest.is_file():
                source_manifests.append(manifest)
        kwargs = {
            name: candidates[name]
            for name in self.arguments
            if name in candidates
        }
        function = getattr(import_module(self.module), self.function)
        resolved = study.resolved_config(
            spatial_units=None if study.is_native else study.spatial_units
        )
        with resolved_config_scope(study.study.id, resolved):
            function(**kwargs)
        result = collect_legacy_assets(execution.output_dir, execution.spec)
        return LayerBuildResult(result.assets, tuple(source_manifests))


@dataclass(frozen=True)
class NoiseSpainRunner:
    """Typed runner retaining the immutable SICA snapshot as provenance."""

    algorithm_version: str = "1"

    def __call__(self, execution: LayerExecutionContext) -> LayerBuildResult:
        declared_manifest = execution.inputs.get("source_manifest")
        if declared_manifest is None:
            raise ValueError("noise_spain requires the declared source_manifest study input")
        manifest_root = declared_manifest.parent
        identity = load_source_manifest(manifest_root, verify=False)
        if (identity.provider, identity.dataset) != (SPAIN_NOISE_PROVIDER, SPAIN_NOISE_DATASET):
            raise ValueError(
                "noise_spain source_manifest must describe the canonical SICA/MITECO dataset: "
                f"{declared_manifest}"
            )
        snapshot_store = execution.study.paths.provider_snapshot(
            identity.provider,
            identity.dataset,
            identity.version,
        )
        if snapshot_store.manifest_path.resolve() != declared_manifest.resolve():
            raise ValueError(
                "noise_spain source_manifest must match the canonical provider snapshot root: "
                f"{snapshot_store.manifest_path}"
            )
        outputs = build_noise_spain_layer(
            study=execution.study,
            raw_snapshot=snapshot_store,
            cache_dir=execution.cache_dir,
            out_dir=execution.output_dir,
        )
        return LayerBuildResult(
            (
                ProducedAsset(outputs.table, "primary_table"),
                ProducedAsset(outputs.geometry, "primary_geometry"),
                ProducedAsset(outputs.metadata, "metadata"),
                ProducedAsset(outputs.exposure_table, "diagnostic"),
            ),
            (snapshot_store.manifest_path,),
        )


_COMMON = ("city", "cache_dir", "out_dir")
_FIGURES = (*_COMMON, "figures_dir")


_RUNNERS: Mapping[str, LayerRunner] = {
    "community_safety": LegacyFunctionAdapter(
        "exposome.community_safety", "build_community_safety_layer", _COMMON
    ),
    "community_violence": LegacyFunctionAdapter(
        "exposome.community_violence", "build_community_violence_layer", _COMMON
    ),
    "suicide_mortality": LegacyFunctionAdapter(
        "exposome.argentina_outcomes", "build_suicide_mortality_comparator", _COMMON
    ),
    "road_traffic_mortality": LegacyFunctionAdapter(
        "exposome.argentina_outcomes", "build_road_traffic_mortality_comparator", _COMMON
    ),
    "socioeconomic": LegacyFunctionAdapter(
        "exposome.socioeconomic", "build_socioeconomic_layer", _COMMON
    ),
    "air_quality": LegacyFunctionAdapter(
        "exposome.air_quality_legacy", "build_air_quality_legacy_layer", _COMMON
    ),
    "air_quality_pm25": LegacyFunctionAdapter(
        "exposome.pm25", "build_pm25_layer", _COMMON
    ),
    "heavy_metals": LegacyFunctionAdapter(
        "exposome.heavy_metals",
        "build_heavy_metals_layer",
        (*_COMMON, "raw_dir"),
        raw_snapshot=("mma", "retc-air-point-sources", "ckan-2026-06"),
    ),
    "air_quality_satellite": LegacyFunctionAdapter(
        "exposome.air_quality", "build_air_quality_layer", _COMMON
    ),
    "alan": LegacyFunctionAdapter("exposome.alan", "build_alan_layer", _COMMON),
    "sleep_context": LegacyFunctionAdapter(
        "exposome.sleep_context",
        "build_sleep_context_layer",
        ("city", "out_dir", "master_csv", "master_geojson"),
    ),
    "greenspace_coverage": LegacyFunctionAdapter(
        "exposome.greenspace_satellite", "build_greenspace_coverage_layer", _FIGURES
    ),
    "greenspace_multisource": LegacyFunctionAdapter(
        "exposome.greenspace_multisource",
        "build_greenspace_multisource_layer",
        _FIGURES,
    ),
    "precipitation": LegacyFunctionAdapter(
        "exposome.precipitation", "build_precipitation_layer", _COMMON
    ),
    "precipitation_spi": LegacyFunctionAdapter(
        "exposome.precipitation_spi",
        "build_precipitation_spi_layer",
        (*_COMMON, "chirps_daily_csv"),
    ),
    "climate_heat": LegacyFunctionAdapter(
        "exposome.climate.build_layer", "build_climate_heat_layer", _COMMON
    ),
    "climate_lst_ecostress": LegacyFunctionAdapter(
        "exposome.climate.ecostress_layer", "build_climate_lst_ecostress_layer", _COMMON
    ),
    "climate_openmeteo": LegacyFunctionAdapter(
        "exposome.climate_metrics",
        "build_climate_metrics_layer",
        (*_COMMON, "daily_csv"),
    ),
    "wind": LegacyFunctionAdapter("exposome.wind", "build_wind_layer", _COMMON),
    "wildfire": LegacyFunctionAdapter(
        "exposome.wildfire", "build_wildfire_layer", _COMMON
    ),
    "noise": LegacyFunctionAdapter(
        "exposome.noise", "build_noise_layer", ("city", "out_dir")
    ),
    "noise_spain": NoiseSpainRunner(),
    "greenspace_access": LegacyFunctionAdapter(
        "exposome.greenspace_access", "build_greenspace_access_layer", _FIGURES
    ),
    "walkability": LegacyFunctionAdapter(
        "exposome.walkability",
        "build_walkability_layer",
        ("city", "out_dir", "cache_dir", "resume"),
    ),
    "public_transport": LegacyFunctionAdapter(
        "exposome.public_transport", "build_public_transport_layer", _COMMON
    ),
    "social_infrastructure": LegacyFunctionAdapter(
        "exposome.social_infrastructure", "build_social_infrastructure_layer", _COMMON
    ),
    "food_environment": LegacyFunctionAdapter(
        "exposome.food_environment",
        "build_food_environment_layer",
        (*_COMMON, "resume"),
    ),
    "healthcare": LegacyFunctionAdapter(
        "exposome.healthcare", "build_healthcare_layer", _COMMON
    ),
    "demography": LegacyFunctionAdapter(
        "exposome.demography", "build_demography_layer", _FIGURES
    ),
    "food_insecurity": LegacyFunctionAdapter(
        "exposome.food_insecurity",
        "build_food_insecurity_layer",
        (*_COMMON, "raw_dir"),
    ),
    "pobreza_sae": LegacyFunctionAdapter(
        "exposome.pobreza_sae", "build_pobreza_sae_layer", (*_COMMON, "raw_dir")
    ),
    "greenspace_cv": LegacyFunctionAdapter(
        "exposome.greenspace_cv", "build_greenspace_cv_layer", _COMMON
    ),
    "neuro_mortality": LegacyFunctionAdapter(
        "exposome.neuro_mortality", "build_neuro_mortality_layer", _COMMON
    ),
    "neuro_hospitalizations": LegacyFunctionAdapter(
        "exposome.neuro_hospitalizations",
        "build_neuro_hospitalization_layer",
        _COMMON,
    ),
}


def get_layer_runner(layer_id: str) -> LayerRunner:
    try:
        return _RUNNERS[layer_id]
    except KeyError as exc:
        raise KeyError(f"No canonical runner registered for Layer {layer_id!r}") from exc


def has_importable_runner(layer_id: str) -> bool:
    """Compatibility name retained until script parity gates retire."""
    return layer_id in _RUNNERS


def runner_algorithm_version(layer_id: str) -> str:
    runner = get_layer_runner(layer_id)
    return str(getattr(runner, "algorithm_version", "1"))


def runner_identity_parameters(layer_id: str, study: Any) -> Mapping[str, Any]:
    """Return adapter choices that materially affect a complete Layer build."""
    runner = get_layer_runner(layer_id)
    raw_snapshot = getattr(runner, "raw_snapshot", None)
    if raw_snapshot is None:
        return {"runner": type(runner).__name__}
    provider, dataset, version = raw_snapshot
    manifest = study.paths.provider_raw(provider, dataset, version) / "source_manifest.json"
    return {
        "runner": type(runner).__name__,
        "raw_snapshot": {
            "provider": provider,
            "dataset": dataset,
            "version": version,
            "manifest": manifest,
        },
    }


def run_importable_layer(
    context: Any,
    spec: Any,
    output_dir: Path,
    cache_dir: Path,
) -> LayerBuildResult | None:
    """Compatibility bridge for callers not yet constructing typed contexts."""
    layer_id = str(getattr(spec, "id", spec))
    runner = _RUNNERS.get(layer_id)
    if runner is None:
        return None
    inputs = (
        context.layer_inputs(layer_id)
        if callable(getattr(context, "layer_inputs", None))
        else {}
    )
    try:
        settings = context.layer_settings(layer_id)
    except (AttributeError, KeyError, ValueError):
        settings = {}
    paths = getattr(context, "paths", None)
    interim_resolver = getattr(paths, "layer_interim", None)
    interim_dir = (
        interim_resolver(layer_id)
        if callable(interim_resolver)
        else Path(getattr(paths, "interim", output_dir.parent / "interim")) / layer_id
    )
    execution = LayerExecutionContext(
        study=context,
        spec=spec,
        settings=settings,
        inputs=inputs,
        output_dir=output_dir,
        cache_dir=cache_dir,
        interim_dir=interim_dir,
    )
    return runner(execution)


def collect_legacy_assets(output_dir: Path, spec: Any) -> LayerBuildResult:
    """Translate one legacy builder directory into explicit produced roles."""
    output_dir = Path(output_dir)
    required = set((getattr(spec, "master", None) or {}).get("required_columns", ()))
    assets: list[ProducedAsset] = []
    table_seen = False
    geometry_seen = False
    for path in sorted(candidate for candidate in output_dir.rglob("*") if candidate.is_file()):
        if path.name == "manifest.json":
            continue
        if path.name.startswith("._"):
            # macOS AppleDouble sidecar (resource fork / xattrs), written
            # automatically for every file on filesystems without native
            # xattr support (NFS/SMB mounts -- e.g. valle_aburra_native's
            # external disk). Never a real pipeline output on any platform.
            continue
        suffix = path.suffix.lower()
        rel_parts = path.relative_to(output_dir).parts
        # Non-spatial diagnostics (coverage tables, nsmallest() slices such as
        # social_infrastructure's diagnostics/*_low_access.csv) live below a
        # ``diagnostics/`` subdirectory -- see normalize_layer_outputs. They may
        # satisfy master.required_columns yet lack the spatial_id join key, so
        # they must never win the primary_table/primary_geometry role: picking
        # one demoted lima_distritos social_infrastructure's real table to
        # auxiliary and blocked `exposome materialize` (2026-07-22). This is the
        # only role site (normalize_layer_outputs reuses it), so the exclusion
        # must live here, not in the checksum pass.
        in_diagnostics = "diagnostics" in rel_parts[:-1]
        role = "auxiliary"
        columns = _columns(path) if suffix in {".csv", ".geojson"} else set()
        if in_diagnostics:
            role = "diagnostic"
        elif suffix == ".csv" and required and required.issubset(columns) and not table_seen:
            role = "primary_table"
            table_seen = True
        elif (
            suffix == ".geojson"
            and required
            and required.issubset(columns)
            and not geometry_seen
        ):
            role = "primary_geometry"
            geometry_seen = True
        elif suffix == ".json" and _is_metadata(path):
            role = "metadata"
        elif suffix in {".png", ".jpg", ".jpeg", ".pdf", ".svg"}:
            role = "diagnostic"
        elif "web" in rel_parts:
            role = "web"
        assets.append(ProducedAsset(path, role))
    return LayerBuildResult(tuple(assets))


def _columns(path: Path) -> set[str]:
    try:
        if path.suffix.lower() == ".csv":
            return set(pd.read_csv(path, nrows=0).columns)
        import geopandas as gpd

        return set(gpd.read_file(path, rows=1).columns)
    except Exception:
        return set()


def _is_metadata(path: Path) -> bool:
    if "metadata" in path.name:
        return True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    return isinstance(payload, dict) and bool(
        {"created_utc", "columns", "sources", "method"}.intersection(payload)
    )

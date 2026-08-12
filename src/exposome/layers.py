"""Declarative layer catalog, study preflight, and orchestration helpers.

The catalog describes where a layer can run and what it needs.  This module
deliberately does not import any layer implementation: preflight and dry runs
must remain offline and must not initialize Earth Engine or contact OSM.
"""
from __future__ import annotations

import json
from hashlib import sha256
import math
import os
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG_PATH = REPO_ROOT / "config" / "layers.yaml"


class CatalogError(ValueError):
    """Raised when the declarative layer catalog is invalid."""


class PreflightError(RuntimeError):
    """Raised when one or more requested layers cannot be executed."""


class LayerExecutionError(RuntimeError):
    """Raised when one or more layers failed while executing (not preflight)."""


class LayerCategory(str, Enum):
    """Portability class used by the multi-country pipeline."""

    GLOBAL = "global"
    OSM = "OSM"
    CHILE = "CL"
    DERIVED = "derived"
    COMPARATOR = "comparator"
    SOCIAL = "social"


class PreflightStatus(str, Enum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    MISSING_INPUT = "missing_input"
    RESOLUTION_WARNING = "resolution_warning"


@dataclass(frozen=True)
class LayerSpec:
    """Validated catalog entry for one exposome layer."""

    id: str
    title: str
    category: LayerCategory
    provider: str
    command: tuple[str, ...]
    pilot: bool = False
    countries: tuple[str, ...] = ()
    native_resolution_m: float | None = None
    analysis_resolution_m: float | None = None
    requirements: Mapping[str, Any] | None = None
    country_args: Mapping[str, tuple[str, ...]] | None = None
    master: Mapping[str, Any] | None = None

    @property
    def is_country_limited(self) -> bool:
        return bool(self.countries)


@dataclass(frozen=True)
class LayerCatalog:
    """Immutable, ordered collection of layer specifications."""

    version: int
    layers: Mapping[str, LayerSpec]
    pilot_layers: tuple[str, ...]
    aliases: Mapping[str, str]

    def resolve_id(self, layer_id: str) -> str:
        return self.aliases.get(layer_id, layer_id)

    def get(self, layer_id: str) -> LayerSpec:
        canonical_id = self.resolve_id(layer_id)
        try:
            return self.layers[canonical_id]
        except KeyError as exc:
            known = ", ".join(self.layers)
            raise CatalogError(f"Unknown layer {layer_id!r}. Known layers: {known}") from exc

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self.layers)


@dataclass(frozen=True)
class PreflightResult:
    layer_id: str
    status: PreflightStatus
    reasons: tuple[str, ...]
    native_resolution_m: float | None = None
    unit_resolution_m: float | None = None

    @property
    def runnable(self) -> bool:
        return self.status in {
            PreflightStatus.READY,
            PreflightStatus.RESOLUTION_WARNING,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "status": self.status.value,
            "reasons": list(self.reasons),
            "native_resolution_m": self.native_resolution_m,
            "unit_resolution_m": self.unit_resolution_m,
        }


@dataclass(frozen=True)
class LayerRunPlan:
    layer: LayerSpec
    preflight: PreflightResult
    command: tuple[str, ...]
    output_dir: Path
    cache_dir: Path
    skip: bool = False
    skip_reason: str | None = None
    resume: bool = False
    force: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer.id,
            "status": self.preflight.status.value,
            "command": list(self.command),
            "output_dir": str(self.output_dir),
            "cache_dir": str(self.cache_dir),
            "skip": self.skip,
            "skip_reason": self.skip_reason,
            "resume": self.resume,
            "force": self.force,
        }


@dataclass(frozen=True)
class LayerRunResult:
    layer_id: str
    action: str
    output_dir: Path
    normalized_files: tuple[Path, ...] = ()
    error: str | None = None


def _as_mapping(value: Any, *, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise CatalogError(f"{field} must be a mapping")
    return dict(value)


def _as_string_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CatalogError(f"{field} must be a list of strings")
    return tuple(value)


def _positive_number(value: Any, *, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise CatalogError(f"{field} must be a positive number or null")
    return float(value)


def load_layer_catalog(path: Path = DEFAULT_CATALOG_PATH) -> LayerCatalog:
    """Load and validate ``config/layers.yaml``."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Layer catalog not found: {path}")
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, Mapping):
        raise CatalogError("Layer catalog root must be a mapping")

    version = raw.get("version")
    if not isinstance(version, int) or version < 1:
        raise CatalogError("Catalog version must be a positive integer")
    raw_layers = raw.get("layers")
    if not isinstance(raw_layers, Mapping) or not raw_layers:
        raise CatalogError("Catalog must define a non-empty 'layers' mapping")

    layers: dict[str, LayerSpec] = {}
    for layer_id, entry in raw_layers.items():
        if not isinstance(layer_id, str) or not layer_id:
            raise CatalogError("Layer ids must be non-empty strings")
        if not isinstance(entry, Mapping):
            raise CatalogError(f"layers.{layer_id} must be a mapping")
        try:
            category = LayerCategory(entry.get("category"))
        except ValueError as exc:
            allowed = ", ".join(item.value for item in LayerCategory)
            raise CatalogError(
                f"layers.{layer_id}.category must be one of: {allowed}"
            ) from exc

        title = entry.get("title")
        provider = entry.get("provider")
        if not isinstance(title, str) or not title.strip():
            raise CatalogError(f"layers.{layer_id}.title must be a non-empty string")
        if not isinstance(provider, str) or not provider.strip():
            raise CatalogError(f"layers.{layer_id}.provider must be a non-empty string")
        command = _as_string_tuple(entry.get("command"), field=f"layers.{layer_id}.command")
        countries = tuple(
            country.upper()
            for country in _as_string_tuple(
                entry.get("countries"), field=f"layers.{layer_id}.countries"
            )
        )
        if category == LayerCategory.CHILE and countries != ("CL",):
            raise CatalogError(f"layers.{layer_id} classified CL must declare countries: [CL]")

        country_args_raw = _as_mapping(
            entry.get("country_args"), field=f"layers.{layer_id}.country_args"
        )
        country_args = {
            str(country).upper() if str(country).lower() != "default" else "DEFAULT":
            _as_string_tuple(args, field=f"layers.{layer_id}.country_args.{country}")
            for country, args in country_args_raw.items()
        }
        requirements = _as_mapping(
            entry.get("requirements"), field=f"layers.{layer_id}.requirements"
        )
        for key in ("capabilities", "input_layers", "study_inputs", "study_inputs_self_fetch"):
            if key in requirements:
                _as_string_tuple(
                    requirements[key], field=f"layers.{layer_id}.requirements.{key}"
                )

        layers[layer_id] = LayerSpec(
            id=layer_id,
            title=title.strip(),
            category=category,
            provider=provider.strip(),
            command=command,
            pilot=bool(entry.get("pilot", False)),
            countries=countries,
            native_resolution_m=_positive_number(
                entry.get("native_resolution_m"),
                field=f"layers.{layer_id}.native_resolution_m",
            ),
            analysis_resolution_m=_positive_number(
                entry.get("analysis_resolution_m"),
                field=f"layers.{layer_id}.analysis_resolution_m",
            ),
            requirements=requirements,
            country_args=country_args,
            master=_as_mapping(entry.get("master"), field=f"layers.{layer_id}.master"),
        )

    aliases_raw = _as_mapping(raw.get("aliases"), field="aliases")
    aliases: dict[str, str] = {}
    for alias, target in aliases_raw.items():
        if not isinstance(alias, str) or not alias:
            raise CatalogError("Catalog aliases must have non-empty string names")
        if not isinstance(target, str) or target not in layers:
            raise CatalogError(f"Alias {alias!r} targets unknown layer {target!r}")
        if alias in layers:
            raise CatalogError(f"Alias {alias!r} collides with a canonical layer id")
        aliases[alias] = target

    pilot_layers = _as_string_tuple(raw.get("pilot_layers"), field="pilot_layers")
    if len(pilot_layers) != len(set(pilot_layers)):
        raise CatalogError("pilot_layers contains duplicates")
    unknown_pilot = [layer_id for layer_id in pilot_layers if layer_id not in layers]
    if unknown_pilot:
        raise CatalogError(f"pilot_layers contains unknown ids: {unknown_pilot}")
    marked_pilot = tuple(layer_id for layer_id, spec in layers.items() if spec.pilot)
    if set(pilot_layers) != set(marked_pilot):
        raise CatalogError(
            "pilot_layers and per-layer pilot flags disagree: "
            f"list={list(pilot_layers)}, flags={list(marked_pilot)}"
        )
    return LayerCatalog(
        version=version,
        layers=layers,
        pilot_layers=pilot_layers,
        aliases=aliases,
    )


def _getattr_or_key(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _study_record(context: Any) -> Any:
    return _getattr_or_key(context, "study", context)


def _study_raw(context: Any) -> Mapping[str, Any]:
    study = _study_record(context)
    raw = _getattr_or_key(study, "raw", {})
    return raw if isinstance(raw, Mapping) else {}


def _study_id(context: Any) -> str:
    study = _study_record(context)
    return str(_getattr_or_key(study, "id", _getattr_or_key(context, "id", "study")))


def _country_code(context: Any) -> str:
    code = _getattr_or_key(context, "country_code")
    if not code:
        location = _getattr_or_key(context, "location", {})
        code = _getattr_or_key(location, "country_code")
    return str(code or "").upper()


def _enabled_layers(context: Any) -> tuple[str, ...]:
    value = _getattr_or_key(context, "enabled_layers")
    if value is None:
        value = _getattr_or_key(_study_record(context), "enabled_layers", ())
    return tuple(str(item) for item in (value or ()))


def _spatial_path(context: Any) -> Path | None:
    value = _getattr_or_key(context, "spatial_path")
    if value is None:
        value = _getattr_or_key(_study_record(context), "spatial_path")
    return Path(value) if value else None


def _unit_resolution_m(context: Any, *, derive_from_geometry: bool = True) -> float | None:
    if bool(_getattr_or_key(context, "is_native", False)) or str(
        _getattr_or_key(_study_record(context), "mode", "aggregate")
    ).casefold() == "native":
        return None
    raw = _study_raw(context)
    spatial = raw.get("spatial", {}) if isinstance(raw.get("spatial", {}), Mapping) else {}
    candidates = (
        spatial.get("nominal_resolution_m"),
        spatial.get("unit_resolution_m"),
        raw.get("nominal_resolution_m"),
        raw.get("unit_resolution_m"),
    )
    for value in candidates:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return float(value)
    if not derive_from_geometry:
        return None
    path = _spatial_path(context)
    if path is None or not path.exists():
        return None
    units = _load_spatial_units(context)
    if "area_km2" in units.columns:
        median_area_km2 = float(units["area_km2"].median())
    else:
        metric_crs = getattr(units, "attrs", {}).get("metric_crs")
        if not metric_crs:
            metric_crs = units.estimate_utm_crs()
        median_area_km2 = float(units.to_crs(metric_crs).geometry.area.median() / 1_000_000)
    if not math.isfinite(median_area_km2) or median_area_km2 <= 0:
        return None
    # A polygon has no single resolution. sqrt(median area) is an explicit,
    # reproducible characteristic width used only for honesty warnings.
    return math.sqrt(median_area_km2) * 1000


def _study_inputs(context: Any, layer_id: str) -> Mapping[str, Any]:
    resolver = _getattr_or_key(context, "layer_inputs")
    if callable(resolver):
        return resolver(layer_id)
    raw = _study_raw(context)
    for root_key in ("layer_inputs", "inputs"):
        root = raw.get(root_key, {})
        if isinstance(root, Mapping):
            layer = root.get(layer_id, {})
            if isinstance(layer, Mapping):
                return layer
    return {}


def _layer_output_dir(context: Any, layer_id: str) -> Path:
    paths = _getattr_or_key(context, "paths", {})
    resolver = _getattr_or_key(paths, "layer_processed")
    if callable(resolver):
        return Path(resolver(layer_id))
    processed = _getattr_or_key(paths, "processed")
    if processed is None:
        processed = REPO_ROOT / "data" / "processed" / _study_id(context)
    return Path(processed) / layer_id


def _layer_cache_dir(context: Any, layer_id: str) -> Path:
    paths = _getattr_or_key(context, "paths", {})
    cache = _getattr_or_key(paths, "cache")
    if cache is None:
        cache = REPO_ROOT / "cache" / _study_id(context)
    return Path(cache) / layer_id


def _dependency_available(
    context: Any,
    layer_id: str,
    requested: set[str],
    catalog: LayerCatalog,
) -> bool:
    if layer_id in requested:
        return True
    from .artifact_contract import load_layer_bundle

    try:
        load_layer_bundle(
            context,
            layer_id,
            verify=True,
            spec=catalog.get(layer_id),
        )
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return False
    return True


def preflight_layers(
    context: Any,
    *,
    catalog: LayerCatalog | None = None,
    layer_ids: Sequence[str] | None = None,
    available_capabilities: Iterable[str] | None = None,
    check_paths: bool = True,
) -> tuple[PreflightResult, ...]:
    """Validate requested layers without importing providers or using network.

    Capability checks are opt-in.  Passing ``available_capabilities`` lets a
    deployment assert that, for example, GEE authentication is available;
    omitting it keeps an offline preflight focused on static study inputs.
    """
    catalog = catalog or load_layer_catalog()
    requested_raw = tuple(layer_ids) if layer_ids is not None else _enabled_layers(context)
    requested_ids = tuple(catalog.resolve_id(layer_id) for layer_id in requested_raw)
    if not requested_ids:
        raise PreflightError(f"Study {_study_id(context)!r} does not enable any layers")
    if len(requested_ids) != len(set(requested_ids)):
        raise PreflightError(f"Requested layers contain duplicates: {list(requested_ids)}")
    specs = [catalog.get(layer_id) for layer_id in requested_ids]
    requested = set(requested_ids)
    enabled = {catalog.resolve_id(layer_id) for layer_id in _enabled_layers(context)}
    capabilities = (
        {str(item).lower() for item in available_capabilities}
        if available_capabilities is not None
        else None
    )
    spatial_path = _spatial_path(context)
    spatial_error: str | None = None
    try:
        unit_resolution_m = _unit_resolution_m(
            context, derive_from_geometry=check_paths
        )
    except Exception as exc:
        unit_resolution_m = None
        spatial_error = str(exc)
    country = _country_code(context)

    results: list[PreflightResult] = []
    for spec in specs:
        unavailable: list[str] = []
        missing: list[str] = []
        warnings: list[str] = []
        requirements = spec.requirements or {}

        if enabled and spec.id not in enabled:
            unavailable.append(f"layer is not enabled by study {_study_id(context)!r}")
        if spec.countries and country not in spec.countries:
            unavailable.append(
                f"available only in {', '.join(spec.countries)}; study country is {country or 'unknown'}"
            )
        if not spec.command:
            unavailable.append("no runner command is registered")
        if check_paths and (spatial_path is None or not spatial_path.exists()):
            missing.append(f"spatial input not found: {spatial_path or '<unset>'}")
        elif check_paths and spatial_error:
            missing.append(f"spatial input is invalid: {spatial_error}")

        for dependency in requirements.get("input_layers", []):
            if not _dependency_available(context, dependency, requested, catalog):
                missing.append(
                    f"required input layer {dependency!r} is neither requested nor already processed"
                )
        inputs = _study_inputs(context, spec.id)
        self_fetch_inputs = set(requirements.get("study_inputs_self_fetch", []))
        for input_name in requirements.get("study_inputs", []):
            value = inputs.get(input_name)
            if not value:
                missing.append(f"study input {input_name!r} is not configured")
            elif (
                check_paths
                and input_name not in self_fetch_inputs
                and not Path(value).expanduser().exists()
            ):
                missing.append(f"study input {input_name!r} not found: {value}")
        if capabilities is not None:
            required_caps = {str(item).lower() for item in requirements.get("capabilities", [])}
            missing_caps = sorted(required_caps - capabilities)
            if missing_caps:
                missing.append(f"missing capabilities: {', '.join(missing_caps)}")

        if spec.native_resolution_m and unit_resolution_m:
            ratio = spec.native_resolution_m / unit_resolution_m
            if ratio > 1:
                warnings.append(
                    f"native source resolution ({spec.native_resolution_m:g} m) is "
                    f"{ratio:.1f}x coarser than the study unit scale ({unit_resolution_m:g} m)"
                )

        if unavailable:
            status = PreflightStatus.UNAVAILABLE
            reasons = unavailable + missing + warnings
        elif missing:
            status = PreflightStatus.MISSING_INPUT
            reasons = missing + warnings
        elif warnings:
            status = PreflightStatus.RESOLUTION_WARNING
            reasons = warnings
        else:
            status = PreflightStatus.READY
            reasons = ["static requirements satisfied"]
        results.append(
            PreflightResult(
                layer_id=spec.id,
                status=status,
                reasons=tuple(reasons),
                native_resolution_m=spec.native_resolution_m,
                unit_resolution_m=unit_resolution_m,
            )
        )
    return tuple(results)


def _path_values(context: Any, spec: LayerSpec) -> dict[str, str]:
    paths = _getattr_or_key(context, "paths", {})
    output_dir = _layer_output_dir(context, spec.id)
    cache_dir = _layer_cache_dir(context, spec.id)
    processed_dir = _getattr_or_key(paths, "processed", output_dir.parent)
    values = {
        "study": _study_id(context),
        # config.load_config() resolves study ids in the transitional adapter;
        # using the location id here would collide for two studies in one city.
        "city": _study_id(context),
        "country_code": _country_code(context),
        "spatial_path": str(_spatial_path(context) or ""),
        "out_dir": str(output_dir),
        "cache_dir": str(cache_dir),
        "processed_dir": str(processed_dir),
        "figures_dir": str(output_dir / "figures"),
    }
    for name, value in _study_inputs(context, spec.id).items():
        values[f"input_{name}"] = str(value)
    return values


def render_layer_command(
    context: Any,
    spec: LayerSpec,
    *,
    python_executable: str | Path = sys.executable,
    allow_missing_placeholders: bool = False,
) -> tuple[str, ...]:
    """Render a catalog command for a concrete study."""
    if not spec.command:
        raise CatalogError(f"Layer {spec.id!r} has no command")
    if bool(_getattr_or_key(context, "is_native", False)):
        return (
            str(python_executable),
            "scripts/run_native_layer.py",
            "--study",
            _study_id(context),
            "--layer",
            spec.id,
        )
    values = _path_values(context, spec)
    rendered: list[str] = []
    for token in spec.command:
        try:
            rendered.append(token.format_map(values))
        except KeyError as exc:
            if allow_missing_placeholders:
                placeholder = "{" + exc.args[0] + "}"
                rendered.append(
                    token.replace(placeholder, f"<missing:{exc.args[0]}>")
                )
                continue
            raise CatalogError(
                f"Layer {spec.id!r} command references unavailable placeholder {exc.args[0]!r}"
            ) from exc
    country_args = spec.country_args or {}
    rendered.extend(country_args.get(_country_code(context), country_args.get("DEFAULT", ())))
    if rendered[0].endswith(".py"):
        rendered.insert(0, str(python_executable))
    return tuple(rendered)


def layer_execution_identity(context: Any, spec: LayerSpec) -> Any:
    """Build the complete identity used by resume and the Layer bundle."""
    from .cache import spatial_fingerprint
    from .execution import LayerExecutionIdentity
    from .runners import runner_algorithm_version, runner_identity_parameters

    try:
        settings = dict(context.layer_settings(spec.id))
    except (AttributeError, KeyError, ValueError):
        settings = {}
    adapter = _fingerprint_identity_paths(
        runner_identity_parameters(spec.id, context),
        root=Path(_getattr_or_key(context, "repo_root", REPO_ROOT)),
    )
    is_native = bool(_getattr_or_key(context, "is_native", False))
    if is_native:
        spatial = _file_identity(Path(_getattr_or_key(context, "aoi_path")))
        spatial_key = sha256(
            json.dumps(spatial, sort_keys=True).encode("utf-8")
        ).hexdigest()
    else:
        units = _boundary_frame(context)
        spatial_key = spatial_fingerprint(units, id_column="spatial_id")
    inputs = {
        str(name): _file_identity(Path(path))
        for name, path in _study_inputs(context, spec.id).items()
    }
    study = _study_record(context)
    period = _getattr_or_key(study, "period", {})
    algorithm_version = runner_algorithm_version(spec.id)
    if is_native:
        # Native GEE exports now preserve inspected provider grids and may
        # materialize semantically derived bands (heat/rain/canopy). Existing
        # native bundles predate that contract and must never be accepted by
        # ``--resume`` solely because their old artifact hash still verifies.
        algorithm_version = f"{algorithm_version}:native-grid-contract-v3"
    return LayerExecutionIdentity(
        study_id=_study_id(context),
        layer_id=spec.id,
        mode=str(_getattr_or_key(context, "mode", "aggregate")),
        layer_settings={"resolved": settings, "adapter": adapter},
        period=dict(period) if isinstance(period, Mapping) else {},
        spatial_fingerprint=spatial_key,
        algorithm_version=algorithm_version,
        inputs=inputs,
    )


def _file_identity(path: Path) -> dict[str, Any]:
    path = Path(path)
    record: dict[str, Any] = {"path": path.as_posix(), "exists": path.is_file()}
    if path.is_file():
        digest = sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        record.update(
            {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}
        )
    return record


def _fingerprint_identity_paths(value: Any, *, root: Path) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _fingerprint_identity_paths(item, root=root)
            for key, item in value.items()
        }
    if isinstance(value, Path):
        path = value if value.is_absolute() else root / value
        return _file_identity(path)
    if isinstance(value, (list, tuple)):
        return [_fingerprint_identity_paths(item, root=root) for item in value]
    return value


def _output_is_complete(context: Any, spec: LayerSpec) -> bool:
    """A complete output is a verified v2 bundle with the current identity."""
    from .artifact_contract import load_layer_bundle

    try:
        identity = layer_execution_identity(context, spec)
        load_layer_bundle(
            context,
            spec.id,
            verify=True,
            expected_execution_fingerprint=identity.fingerprint,
            spec=spec,
        )
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return False
    return True


def build_run_plan(
    context: Any,
    *,
    catalog: LayerCatalog | None = None,
    layer_ids: Sequence[str] | None = None,
    resume: bool = False,
    force: bool = False,
    available_capabilities: Iterable[str] | None = None,
    check_paths: bool = True,
    python_executable: str | Path = sys.executable,
) -> tuple[LayerRunPlan, ...]:
    """Create an execution plan without creating directories or files."""
    if resume and force:
        raise ValueError("--resume and --force are mutually exclusive")
    catalog = catalog or load_layer_catalog()
    preflight = preflight_layers(
        context,
        catalog=catalog,
        layer_ids=layer_ids,
        available_capabilities=available_capabilities,
        check_paths=check_paths,
    )
    plans: list[LayerRunPlan] = []
    for result in preflight:
        spec = catalog.get(result.layer_id)
        output_dir = _layer_output_dir(context, spec.id)
        complete = _output_is_complete(context, spec)
        plans.append(
            LayerRunPlan(
                layer=spec,
                preflight=result,
                command=render_layer_command(
                    context,
                    spec,
                    python_executable=python_executable,
                    allow_missing_placeholders=not result.runnable,
                ),
                output_dir=output_dir,
                cache_dir=_layer_cache_dir(context, spec.id),
                skip=bool(resume and complete and not force),
                skip_reason="verified Artifact bundle matches execution identity"
                if resume and complete
                else None,
                resume=resume,
                force=force,
            )
        )
    return tuple(plans)


def _canonical_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value).strip().casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.split())


def _load_spatial_units(context: Any) -> Any:
    """Load canonical study units, preferring the shared spatial contract."""
    try:
        from .spatial import load_spatial_units  # type: ignore[attr-defined]

        return load_spatial_units(context)
    except (ImportError, AttributeError):
        import geopandas as gpd

        path = _spatial_path(context)
        if path is None:
            raise PreflightError("Study spatial_path is not configured")
        gdf = gpd.read_file(path)
        study = _study_record(context)
        id_column = str(_getattr_or_key(study, "id_column", "spatial_id"))
        name_column = _getattr_or_key(study, "name_column", None)
        if id_column not in gdf.columns:
            raise ValueError(f"Spatial input is missing id column {id_column!r}")
        out = gdf.copy()
        out["spatial_id"] = out[id_column].astype(str).str.strip()
        if name_column and name_column in out.columns:
            out["spatial_name"] = out[name_column].astype(str).str.strip()
        else:
            out["spatial_name"] = out["spatial_id"]
        return out[["spatial_id", "spatial_name", "geometry"]]


def _boundary_frame(context: Any) -> Any:
    units = _load_spatial_units(context).copy()
    required = {"spatial_id", "spatial_name", "geometry"}
    missing = sorted(required - set(units.columns))
    if missing:
        raise ValueError(f"Canonical spatial units are missing columns: {missing}")
    units["spatial_id"] = units["spatial_id"].astype(str).str.strip()
    units["spatial_name"] = units["spatial_name"].astype(str).str.strip()
    if units["spatial_id"].eq("").any() or units["spatial_id"].duplicated().any():
        raise ValueError("Study spatial_id values must be non-empty and unique")
    if units["spatial_name"].eq("").any():
        raise ValueError("Study spatial_name values must be non-empty")
    keys = units["spatial_name"].map(_canonical_text)
    if keys.duplicated().any():
        duplicate_names = sorted(units.loc[keys.duplicated(False), "spatial_name"].unique())
        raise ValueError(
            "Study spatial names are ambiguous after normalization: "
            f"{duplicate_names}"
        )
    return units


def prepare_boundary_cache(context: Any, cache_dir: Path) -> Path:
    """Seed the legacy boundary cache from a study's explicit polygons."""
    import geopandas as gpd

    units = _boundary_frame(context)
    geographic_crs = _getattr_or_key(_getattr_or_key(context, "location", {}), "geographic_crs")
    if units.crs is None:
        if not geographic_crs:
            raise ValueError("Study polygons have no CRS and location geographic_crs is unset")
        units = units.set_crs(geographic_crs)

    metric_crs = _getattr_or_key(_getattr_or_key(context, "location", {}), "metric_crs")
    if not metric_crs:
        metric_crs = units.estimate_utm_crs()
    if metric_crs is None:
        raise ValueError("Unable to determine a metric CRS for study polygons")
    metric = units.to_crs(metric_crs)
    out = units.copy()
    out["name"] = out["spatial_name"]
    out["area_km2"] = metric.geometry.area / 1_000_000
    out = gpd.GeoDataFrame(
        out[["name", "spatial_id", "spatial_name", "area_km2", "geometry"]],
        geometry="geometry",
        crs=units.crs,
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{_study_id(context)}_communes.geojson"
    out.to_file(path, driver="GeoJSON")
    return path


def _attach_spatial_ids(frame: Any, boundaries: Any) -> Any:
    out = frame.copy()
    id_to_name = boundaries.set_index("spatial_id")["spatial_name"].to_dict()
    if "spatial_id" in out.columns:
        out["spatial_id"] = out["spatial_id"].astype(str).str.strip()
        unknown = sorted(set(out["spatial_id"]) - set(id_to_name))
        if unknown:
            raise ValueError(f"Output contains spatial_id values absent from study: {unknown}")
        expected_names = out["spatial_id"].map(id_to_name)
        if "spatial_name" in out.columns:
            mismatch = out["spatial_name"].map(_canonical_text) != expected_names.map(_canonical_text)
            if mismatch.any():
                raise ValueError("Output spatial_id/spatial_name pairs do not match study polygons")
        out["spatial_name"] = expected_names
    else:
        candidate = next(
            (column for column in ("spatial_name", "name") if column in out.columns),
            None,
        )
        if candidate is None:
            raise ValueError("Output has no spatial_id, spatial_name, or legacy name column")
        lookup = boundaries[["spatial_id", "spatial_name"]].copy()
        lookup["_spatial_key"] = lookup["spatial_name"].map(_canonical_text)
        out["_spatial_key"] = out[candidate].map(_canonical_text)
        out = out.merge(
            lookup,
            on="_spatial_key",
            how="left",
            validate="many_to_one",
            suffixes=("", "_study"),
        )
        if out["spatial_id"].isna().any():
            unknown = sorted(out.loc[out["spatial_id"].isna(), candidate].astype(str).unique())
            raise ValueError(f"Output names do not map to study polygons: {unknown}")
        if "spatial_name_study" in out.columns:
            out["spatial_name"] = out.pop("spatial_name_study")
        out = out.drop(columns=["_spatial_key"])

    front = ["spatial_id", "spatial_name"]
    remaining = [column for column in out.columns if column not in front]
    return out[front + remaining]


def _validate_primary_coverage(frame: Any, boundaries: Any, spec: LayerSpec) -> None:
    master = spec.master or {}
    required_columns = tuple(master.get("required_columns", ()))
    if not master.get("include", False) or not required_columns:
        return
    if not set(required_columns).issubset(frame.columns):
        return  # Auxiliary/temporal output from the same builder.
    if frame["spatial_id"].duplicated().any():
        raise ValueError(f"Primary output for {spec.id} has duplicate spatial_id values")
    expected = set(boundaries["spatial_id"])
    actual = set(frame["spatial_id"])
    if expected != actual:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(
            f"Primary output coverage mismatch for {spec.id}: missing={missing}, extra={extra}"
        )


def _context_metadata(context: Any, spec: LayerSpec) -> dict[str, Any]:
    study = _study_record(context)
    location = _getattr_or_key(context, "location", {})
    return {
        "layer_id": spec.id,
        "study": {
            "id": _study_id(context),
            "unit_type": _getattr_or_key(study, "unit_type"),
            "expected_units": _getattr_or_key(context, "expected_units"),
            "spatial_path": str(_spatial_path(context) or ""),
        },
        "location": {
            "id": _getattr_or_key(location, "id", _getattr_or_key(context, "city")),
            "city": _getattr_or_key(context, "city"),
            "name": _getattr_or_key(location, "name"),
            "country": _getattr_or_key(location, "country"),
            "country_code": _country_code(context),
            "timezone": _getattr_or_key(location, "timezone"),
            "geographic_crs": _getattr_or_key(location, "geographic_crs"),
            "metric_crs": _getattr_or_key(location, "metric_crs"),
        },
    }


def normalize_layer_outputs(
    context: Any,
    spec: LayerSpec,
    output_dir: Path,
    *,
    build_result: Any | None = None,
    execution_fingerprint: str | None = None,
) -> tuple[Path, ...]:
    """Attach stable spatial identifiers and study metadata to runner outputs."""
    import geopandas as gpd
    import pandas as pd

    output_dir = Path(output_dir)
    boundaries = _boundary_frame(context)
    normalized: list[Path] = []
    tabular_paths = sorted(
        path for path in output_dir.glob("*.csv") if not path.name.startswith("._")
    ) + sorted(path for path in output_dir.glob("*.geojson") if not path.name.startswith("._"))
    if not tabular_paths:
        raise FileNotFoundError(f"Layer {spec.id} produced no CSV or GeoJSON in {output_dir}")

    for path in tabular_paths:
        if path.suffix == ".csv":
            # dtype=str is required for spatial_id: pandas otherwise infers
            # int64 for all-digit id columns, silently dropping the leading
            # zero on admin codes like Peru's UBIGEO (Callao starts "07"),
            # which then fails the comparison against the string-typed
            # boundaries below.
            frame = pd.read_csv(path, dtype={"spatial_id": str})
            has_identity = bool(
                {"spatial_id", "spatial_name", "name"}.intersection(frame.columns)
            )
            required_columns = set((spec.master or {}).get("required_columns", ()))
            if not has_identity:
                if required_columns and required_columns.issubset(frame.columns):
                    raise ValueError(
                        "Primary output has no spatial_id, spatial_name, or legacy name column"
                    )
                # Builders may leave provider-native observations beside the
                # aggregate result (for example an ERA5-Land pixel-day table).
                # Keep them checksum-addressed as auxiliary assets, but never
                # pretend that they have administrative spatial identity.
                normalized.append(path)
                continue
            frame = _attach_spatial_ids(frame, boundaries)
            _validate_primary_coverage(frame, boundaries, spec)
            frame.to_csv(path, index=False)
        else:
            frame = gpd.read_file(path)
            has_identity = bool(
                {"spatial_id", "spatial_name", "name"}.intersection(frame.columns)
            )
            required_columns = set((spec.master or {}).get("required_columns", ()))
            if not has_identity:
                if required_columns and required_columns.issubset(frame.columns):
                    raise ValueError(
                        "Primary output has no spatial_id, spatial_name, or legacy name column"
                    )
                normalized.append(path)
                continue
            frame = _attach_spatial_ids(frame, boundaries)
            _validate_primary_coverage(frame, boundaries, spec)
            frame = gpd.GeoDataFrame(frame, geometry="geometry", crs=frame.crs)
            frame.to_file(path, driver="GeoJSON")
        normalized.append(path)

    metadata_paths = sorted(
        path
        for path in output_dir.glob("*.json")
        if path.name != "manifest.json" and not path.name.startswith("._")
    )
    if not metadata_paths:
        metadata_paths = [output_dir / f"{spec.id}_metadata.json"]
    context_block = _context_metadata(context, spec)
    for path in metadata_paths:
        metadata: dict[str, Any] = {}
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError(f"Layer metadata must be a JSON object: {path}")
            metadata.update(loaded)
        metadata.update(context_block)
        path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        normalized.append(path)
    # Diagnostics belong to the same layer release as the table they justify.
    # They are not interpreted as primary spatial outputs, but are checksumed
    # by the manifest and travel with a materialized artifact bundle.
    normalized.extend(
        sorted(
            path
            for path in output_dir.iterdir()
            if path.is_file()
            and not path.name.startswith("._")
            and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".pdf", ".svg"}
        )
    )
    # Non-spatial diagnostics (coverage tables, unmatched-record reports) live
    # below ``diagnostics/`` so they are not mistaken for primary layer tables.
    # They remain checksum-addressed assets of the same release.
    normalized.extend(
        sorted(
            path
            for path in output_dir.rglob("*")
            if path.is_file()
            and path.parent != output_dir
            and not path.name.startswith("._")
            and path.suffix.lower() in {".csv", ".json", ".png", ".jpg", ".jpeg", ".pdf", ".svg"}
        )
    )
    from .artifact_contract import write_layer_bundle_manifest
    from .execution import LayerBuildResult, ProducedAsset
    from .runners import collect_legacy_assets

    collected = collect_legacy_assets(output_dir, spec)
    explicit_roles = (
        {asset.path.resolve(): asset.role for asset in build_result.assets}
        if isinstance(build_result, LayerBuildResult)
        else {}
    )
    assets = tuple(
        ProducedAsset(asset.path, explicit_roles.get(asset.path.resolve(), asset.role))
        for asset in collected.assets
    )
    final_result = LayerBuildResult(
        assets,
        build_result.source_manifests
        if isinstance(build_result, LayerBuildResult)
        else (),
    )
    fingerprint = execution_fingerprint or layer_execution_identity(
        context, spec
    ).fingerprint
    manifest = write_layer_bundle_manifest(
        context,
        spec,
        output_dir,
        final_result,
        execution_fingerprint=fingerprint,
        source_manifests=final_result.source_manifests,
    )
    normalized.append(manifest)
    return tuple(normalized)


def _execute_one_layer(
    context: Any,
    plan: LayerRunPlan,
    *,
    runner: Callable[..., Any],
) -> LayerRunResult:
    """Run a single non-skipped layer plan and return its normalized result."""
    plan.output_dir.mkdir(parents=True, exist_ok=True)
    plan.cache_dir.mkdir(parents=True, exist_ok=True)
    from .artifact_contract import write_layer_bundle_manifest
    from .execution import LayerExecutionContext
    from .runners import collect_legacy_assets, get_layer_runner

    is_native = bool(_getattr_or_key(context, "is_native", False))
    if is_native:
        from .native import export_native_layer

        export_native_layer(context, plan.layer.id)
        build_result = collect_legacy_assets(plan.output_dir, plan.layer)
        identity = layer_execution_identity(context, plan.layer)
        manifest = write_layer_bundle_manifest(
            context,
            plan.layer,
            plan.output_dir,
            build_result,
            execution_fingerprint=identity.fingerprint,
        )
        return LayerRunResult(
            plan.layer.id,
            "executed",
            plan.output_dir,
            tuple(asset.path for asset in build_result.assets) + (manifest,),
        )
    prepare_boundary_cache(context, plan.cache_dir)
    build_result = None
    if runner is subprocess.run:
        paths = _getattr_or_key(context, "paths", {})
        interim_resolver = _getattr_or_key(paths, "layer_interim")
        interim_dir = (
            Path(interim_resolver(plan.layer.id))
            if callable(interim_resolver)
            else Path(_getattr_or_key(paths, "interim", plan.output_dir.parent / "interim"))
            / plan.layer.id
        )
        try:
            settings = context.layer_settings(plan.layer.id)
        except (AttributeError, KeyError, ValueError):
            settings = {}
        execution = LayerExecutionContext(
            study=context,
            spec=plan.layer,
            settings=settings,
            inputs=_study_inputs(context, plan.layer.id),
            output_dir=plan.output_dir,
            cache_dir=plan.cache_dir,
            interim_dir=interim_dir,
            resume=plan.resume,
            force=plan.force,
        )
        build_result = get_layer_runner(plan.layer.id)(execution)
    else:
        # Explicit compatibility seam used by tests and script-parity gates.
        env = os.environ.copy()
        env.setdefault("PYTHONPYCACHEPREFIX", "/tmp")
        env.setdefault("MPLCONFIGDIR", str(plan.cache_dir / ".matplotlib"))
        study_config_path = _getattr_or_key(_study_record(context), "config_path")
        if study_config_path:
            env["EXPOSOME_STUDY_CONFIG"] = str(study_config_path)
        runner(plan.command, cwd=REPO_ROOT, env=env, check=True)
        build_result = collect_legacy_assets(plan.output_dir, plan.layer)
    identity = layer_execution_identity(context, plan.layer)
    normalized = normalize_layer_outputs(
        context,
        plan.layer,
        plan.output_dir,
        build_result=build_result,
        execution_fingerprint=identity.fingerprint,
    )
    return LayerRunResult(
        plan.layer.id,
        "executed",
        plan.output_dir,
        normalized,
    )


def execute_run_plan(
    context: Any,
    plans: Sequence[LayerRunPlan],
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> tuple[LayerRunResult, ...]:
    """Execute a validated plan sequentially and normalize successful outputs.

    A layer that raises during execution (most commonly an exhausted OSM/
    Overpass retry after every mirror failed) is recorded as a "failed"
    result instead of aborting the whole run: the remaining layers still get
    a chance to execute, instead of one flaky provider blocking every other
    layer in the study (this previously stalled cdmx_native's `healthcare`
    layer behind an unrelated `food_environment` Overpass outage). Callers
    (``pipeline.run_study``) decide whether any "failed" result should block
    building the master table.
    """
    # A completed artifact is self-contained.  ``--resume`` must not require
    # raw/intermediate inputs that are only needed to recompute that layer.
    blockers = [plan for plan in plans if not plan.preflight.runnable and not plan.skip]
    if blockers:
        details = "; ".join(
            f"{plan.layer.id}={plan.preflight.status.value}: "
            f"{', '.join(plan.preflight.reasons)}"
            for plan in blockers
        )
        raise PreflightError(f"Preflight blocked execution: {details}")

    results: list[LayerRunResult] = []
    for plan in plans:
        if plan.skip:
            results.append(
                LayerRunResult(plan.layer.id, "skipped", plan.output_dir)
            )
            continue
        try:
            results.append(_execute_one_layer(context, plan, runner=runner))
        except Exception as exc:  # noqa: BLE001
            results.append(
                LayerRunResult(
                    plan.layer.id,
                    "failed",
                    plan.output_dir,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return tuple(results)


def build_master_manifest(
    context: Any,
    *,
    catalog: LayerCatalog | None = None,
    layer_ids: Sequence[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build the runtime manifest consumed by ``build_study_master``."""
    catalog = catalog or load_layer_catalog()
    selected = layer_ids if layer_ids is not None else _enabled_layers(context)
    canonical_ids = tuple(catalog.resolve_id(layer_id) for layer_id in selected)
    entries: list[dict[str, Any]] = []
    for layer_id in canonical_ids:
        spec = catalog.get(layer_id)
        master = dict(spec.master or {})
        # Comparator/publication-only layers are verified as release bundles,
        # but they are not inputs to the integrated study master.  Skip them
        # before resolving artifacts so the master boundary only consumes the
        # layer set declared by the catalog contract.
        if not master.get("include", False):
            continue
        from .artifact_contract import load_layer_bundle

        bundle = load_layer_bundle(context, spec.id, verify=True, spec=spec)
        metadata_assets = bundle.assets_with_role("metadata")
        entries.append(
            {
                "layer_id": spec.id,
                "path": str(bundle.primary_table) if bundle.primary_table else None,
                "metadata_path": (
                    str(metadata_assets[0]) if len(metadata_assets) == 1 else None
                ),
                "bundle_manifest": str(bundle.manifest_path),
                "required": bool(
                    master.get("include", False)
                    and not master.get("optional_layer", False)
                ),
                "master": master,
            }
        )
    return {"layers": entries}


def build_study_master_from_catalog(
    context: Any,
    *,
    catalog: LayerCatalog | None = None,
    layer_ids: Sequence[str] | None = None,
    strict_required: bool = True,
    write: bool = True,
) -> Any:
    """Build a study master using catalog contracts and canonical directories."""
    from .master import build_study_master

    catalog = catalog or load_layer_catalog()
    manifest = build_master_manifest(
        context, catalog=catalog, layer_ids=layer_ids
    )
    paths = _getattr_or_key(context, "paths", {})
    output_dir = Path(_getattr_or_key(paths, "processed", REPO_ROOT / "data" / "processed"))
    return build_study_master(
        context,
        layer_outputs=manifest,
        output_dir=output_dir,
        strict_required=strict_required,
        write=write,
    )

"""Typed execution contracts and dependency planning for exposome Layers."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


ASSET_ROLES = frozenset(
    {
        "primary_table",
        "primary_geometry",
        "metadata",
        "auxiliary",
        "diagnostic",
        "web",
    }
)


@dataclass(frozen=True)
class LayerExecutionIdentity:
    """Identity of a complete Layer build, distinct from operation caches."""

    study_id: str
    layer_id: str
    mode: str
    layer_settings: Mapping[str, Any]
    period: Mapping[str, Any]
    spatial_fingerprint: str
    algorithm_version: str
    inputs: Mapping[str, Any] = field(default_factory=dict)

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "layer_id": self.layer_id,
            "mode": self.mode,
            "layer_settings": _normalise_identity_value(self.layer_settings),
            "period": _normalise_identity_value(self.period),
            "spatial_fingerprint": self.spatial_fingerprint,
            "algorithm_version": self.algorithm_version,
            "inputs": _normalise_identity_value(self.inputs or {}),
        }

    @property
    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProducedAsset:
    """One explicit output returned by a Layer runner."""

    path: Path
    role: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        if self.role not in ASSET_ROLES:
            raise ValueError(f"Unsupported produced asset role: {self.role!r}")


@dataclass(frozen=True)
class LayerBuildResult:
    """Complete output contract returned through the runner interface."""

    assets: tuple[ProducedAsset, ...]
    source_manifests: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        paths = [asset.path for asset in self.assets]
        if len(paths) != len(set(paths)):
            raise ValueError("LayerBuildResult contains duplicate asset paths")
        if sum(asset.role == "primary_table" for asset in self.assets) > 1:
            raise ValueError("LayerBuildResult has more than one primary_table")
        if sum(asset.role == "primary_geometry" for asset in self.assets) > 1:
            raise ValueError("LayerBuildResult has more than one primary_geometry")
        object.__setattr__(
            self,
            "source_manifests",
            tuple(Path(path) for path in self.source_manifests),
        )


@dataclass(frozen=True)
class LayerRequirements:
    """Typed dependencies and capabilities for one Layer."""

    capabilities: tuple[str, ...] = ()
    input_layers: tuple[str, ...] = ()
    study_inputs: tuple[str, ...] = ()
    self_fetch_inputs: tuple[str, ...] = ()
    requires_master: bool = False
    official_optional: bool = False

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "LayerRequirements":
        raw = dict(value or {})
        known = {
            "capabilities",
            "input_layers",
            "study_inputs",
            "study_inputs_self_fetch",
            "requires_master",
            "official_optional",
        }
        unknown = sorted(set(raw) - known)
        if unknown:
            raise ValueError(f"Unknown Layer requirement keys: {unknown}")
        study_inputs = _string_tuple(raw.get("study_inputs"), "study_inputs")
        explicit_master = raw.get("requires_master")
        if explicit_master is not None and not isinstance(explicit_master, bool):
            raise ValueError("requires_master must be a boolean")
        official_optional = raw.get("official_optional", False)
        if not isinstance(official_optional, bool):
            raise ValueError("official_optional must be a boolean")
        inferred_master = bool({"master_csv", "master_geojson"}.intersection(study_inputs))
        return cls(
            capabilities=_string_tuple(raw.get("capabilities"), "capabilities"),
            input_layers=_string_tuple(raw.get("input_layers"), "input_layers"),
            study_inputs=study_inputs,
            self_fetch_inputs=_string_tuple(
                raw.get("study_inputs_self_fetch"), "study_inputs_self_fetch"
            ),
            requires_master=inferred_master if explicit_master is None else explicit_master,
            official_optional=official_optional,
        )


@dataclass(frozen=True)
class LayerExecutionContext:
    """Only input accepted by a canonical in-process Layer runner."""

    study: Any
    spec: Any
    settings: Mapping[str, Any]
    inputs: Mapping[str, Path]
    output_dir: Path
    cache_dir: Path
    interim_dir: Path
    resume: bool = False
    force: bool = False

    def __post_init__(self) -> None:
        if self.resume and self.force:
            raise ValueError("resume and force are mutually exclusive")
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "cache_dir", Path(self.cache_dir))
        object.__setattr__(self, "interim_dir", Path(self.interim_dir))
        object.__setattr__(
            self,
            "inputs",
            {str(key): Path(value) for key, value in self.inputs.items()},
        )

    @property
    def layer_id(self) -> str:
        return str(getattr(self.spec, "id", self.spec))


LayerRunner = Callable[[LayerExecutionContext], LayerBuildResult]


@dataclass(frozen=True)
class ExecutionStage:
    """A topologically ordered group; master is materialized before the group."""

    layer_ids: tuple[str, ...]
    materialize_master_before: bool = False


@dataclass(frozen=True)
class StudyExecutionGraph:
    """Validated topological execution plan for requested Layers."""

    stages: tuple[ExecutionStage, ...]

    @property
    def ordered_layer_ids(self) -> tuple[str, ...]:
        return tuple(layer_id for stage in self.stages for layer_id in stage.layer_ids)


def build_execution_graph(
    specs: Mapping[str, Any],
    requested_layer_ids: Sequence[str],
    *,
    available_bundle_ids: Iterable[str] = (),
) -> StudyExecutionGraph:
    """Topologically order requested Layers and insert one master barrier.

    Dependencies not requested are never fetched implicitly.  They must be
    listed in ``available_bundle_ids``, which the caller derives exclusively
    from verified Artifact bundles.
    """
    requested = tuple(map(str, requested_layer_ids))
    if len(requested) != len(set(requested)):
        raise ValueError(f"Requested Layers contain duplicates: {requested}")
    unknown_requested = sorted(set(requested) - set(specs))
    if unknown_requested:
        raise ValueError(f"Unknown requested Layers: {unknown_requested}")
    available = set(map(str, available_bundle_ids))
    requirements = {
        layer_id: LayerRequirements.from_mapping(getattr(specs[layer_id], "requirements", None))
        for layer_id in requested
    }
    dependencies: dict[str, set[str]] = {layer_id: set() for layer_id in requested}
    for layer_id, requirement in requirements.items():
        for dependency in requirement.input_layers:
            if dependency not in specs:
                raise ValueError(f"Layer {layer_id!r} declares unknown dependency {dependency!r}")
            if dependency in dependencies:
                dependencies[layer_id].add(dependency)
            elif dependency not in available:
                raise ValueError(
                    f"Layer {layer_id!r} requires unrequested Layer {dependency!r} "
                    "without a verified bundle"
                )

    levels = _topological_levels(requested, dependencies)
    ordered = tuple(layer_id for level in levels for layer_id in level)
    before_master = tuple(
        layer_id for layer_id in ordered if not requirements[layer_id].requires_master
    )
    after_master = tuple(
        layer_id for layer_id in ordered if requirements[layer_id].requires_master
    )
    invalid = [
        (layer_id, dependency)
        for layer_id in before_master
        for dependency in dependencies[layer_id]
        if dependency in after_master
    ]
    if invalid:
        raise ValueError(f"Non-master Layers depend on master-dependent Layers: {invalid}")
    stages: list[ExecutionStage] = []
    master_inserted = False
    for level in levels:
        ordinary = tuple(
            layer_id for layer_id in level if not requirements[layer_id].requires_master
        )
        dependent = tuple(
            layer_id for layer_id in level if requirements[layer_id].requires_master
        )
        if ordinary:
            stages.append(ExecutionStage(ordinary))
        if dependent:
            stages.append(
                ExecutionStage(
                    dependent,
                    materialize_master_before=not master_inserted,
                )
            )
            master_inserted = True
    return StudyExecutionGraph(tuple(stages))


def _topological_order(
    requested: Sequence[str],
    dependencies: Mapping[str, set[str]],
) -> tuple[str, ...]:
    remaining = {layer_id: set(values) for layer_id, values in dependencies.items()}
    order_index = {layer_id: index for index, layer_id in enumerate(requested)}
    ordered: list[str] = []
    while remaining:
        ready = sorted(
            (layer_id for layer_id, values in remaining.items() if not values),
            key=order_index.__getitem__,
        )
        if not ready:
            cycle = {key: sorted(values) for key, values in remaining.items()}
            raise ValueError(f"Layer dependency cycle detected: {cycle}")
        for layer_id in ready:
            ordered.append(layer_id)
            remaining.pop(layer_id)
        for values in remaining.values():
            values.difference_update(ready)
    return tuple(ordered)


def _topological_levels(
    requested: Sequence[str],
    dependencies: Mapping[str, set[str]],
) -> tuple[tuple[str, ...], ...]:
    remaining = {layer_id: set(values) for layer_id, values in dependencies.items()}
    order_index = {layer_id: index for index, layer_id in enumerate(requested)}
    levels: list[tuple[str, ...]] = []
    while remaining:
        ready = tuple(
            sorted(
                (layer_id for layer_id, values in remaining.items() if not values),
                key=order_index.__getitem__,
            )
        )
        if not ready:
            cycle = {key: sorted(values) for key, values in remaining.items()}
            raise ValueError(f"Layer dependency cycle detected: {cycle}")
        levels.append(ready)
        for layer_id in ready:
            remaining.pop(layer_id)
        for values in remaining.values():
            values.difference_update(ready)
    return tuple(levels)


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} contains duplicates")
    return tuple(value)


def _normalise_identity_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalise_identity_value(item)
            for key, item in sorted(value.items())
        }
    if isinstance(value, (list, tuple)):
        return [_normalise_identity_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_normalise_identity_value(item) for item in value)
    if isinstance(value, Path):
        return value.as_posix()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Unsupported Layer execution identity value: {type(value).__name__}")

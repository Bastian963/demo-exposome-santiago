"""Strict v2 contracts for Layer Artifact bundles and Study releases."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

import pandas as pd

from .execution import LayerBuildResult, ProducedAsset


LAYER_MANIFEST_SCHEMA_VERSION = 2
RELEASE_MANIFEST_SCHEMA_VERSION = 2
LAYER_MANIFEST_NAME = "manifest.json"
RELEASE_MANIFEST_NAME = "release_manifest.json"


@dataclass(frozen=True)
class BundleAsset:
    path: str
    role: str
    media_type: str
    bytes: int
    sha256: str

    @property
    def relative_path(self) -> Path:
        return Path(self.path)


@dataclass(frozen=True)
class LayerArtifactBundle:
    manifest_path: Path
    layer_id: str
    study_id: str
    mode: str
    execution_fingerprint: str
    assets: tuple[BundleAsset, ...]
    primary_table: Path | None
    primary_geometry: Path | None
    source_manifests: tuple[Mapping[str, Any], ...]

    def assets_with_role(self, role: str) -> tuple[Path, ...]:
        return tuple(
            self.manifest_path.parent / asset.path for asset in self.assets if asset.role == role
        )


@dataclass(frozen=True)
class ReleaseAsset:
    path: str
    role: str
    media_type: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class StudyRelease:
    manifest_path: Path
    study_id: str
    mode: str
    settings_fingerprint: str
    layers: Mapping[str, LayerArtifactBundle]
    assets: tuple[ReleaseAsset, ...]

    def asset(self, role: str) -> Path | None:
        matches = [asset for asset in self.assets if asset.role == role]
        if len(matches) > 1:
            raise ValueError(f"Release has multiple assets with role {role!r}")
        return None if not matches else self.manifest_path.parent / matches[0].path


def write_layer_bundle_manifest(
    context: Any,
    spec: Any,
    output_dir: str | Path,
    result: LayerBuildResult,
    *,
    execution_fingerprint: str,
    source_manifests: Iterable[str | Path] = (),
) -> Path:
    """Write a v2 Layer manifest from explicit produced-asset roles."""
    if not execution_fingerprint:
        raise ValueError("execution_fingerprint must be non-empty")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    assets = tuple(_bundle_asset(output_dir, asset) for asset in result.assets)
    _validate_asset_roles(assets, spec=spec, mode=_mode(context))
    sources = tuple(_source_manifest_reference(context, path) for path in source_manifests)
    payload = {
        "schema_version": LAYER_MANIFEST_SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "layer_id": str(getattr(spec, "id", spec)),
        "study_id": _study_id(context),
        "mode": _mode(context),
        "execution_fingerprint": execution_fingerprint,
        "spatial_contract": _spatial_contract(context),
        "primary_table": _path_for_role(assets, "primary_table"),
        "primary_geometry": _path_for_role(assets, "primary_geometry"),
        "assets": [_asset_dict(asset) for asset in assets],
        "source_manifests": list(sources),
    }
    path = output_dir / LAYER_MANIFEST_NAME
    _atomic_json(path, payload)
    return path


def load_layer_bundle(
    context: Any,
    layer_id: str,
    *,
    verify: bool = True,
    expected_execution_fingerprint: str | None = None,
    spec: Any | None = None,
) -> LayerArtifactBundle:
    paths = getattr(context, "paths", None)
    resolver = getattr(paths, "layer_processed", None)
    if not callable(resolver):
        raise TypeError("Study context paths do not provide layer_processed")
    manifest_path = Path(resolver(layer_id)) / LAYER_MANIFEST_NAME
    return load_layer_bundle_manifest(
        manifest_path,
        context=context,
        expected_layer_id=layer_id,
        verify=verify,
        expected_execution_fingerprint=expected_execution_fingerprint,
        spec=spec,
    )


def load_layer_bundle_manifest(
    manifest_path: str | Path,
    *,
    context: Any,
    expected_layer_id: str,
    verify: bool = True,
    expected_execution_fingerprint: str | None = None,
    spec: Any | None = None,
) -> LayerArtifactBundle:
    """Read and optionally verify one v2 Layer bundle."""
    manifest_path = Path(manifest_path)
    payload = _load_json(manifest_path)
    if payload.get("schema_version") != LAYER_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported Layer manifest schema: {manifest_path}")
    if payload.get("layer_id") != expected_layer_id:
        raise ValueError(f"Layer manifest identity mismatch: {manifest_path}")
    if payload.get("study_id") != _study_id(context):
        raise ValueError(f"Layer manifest Study identity mismatch: {manifest_path}")
    if payload.get("mode") != _mode(context):
        raise ValueError(f"Layer manifest mode mismatch: {manifest_path}")
    execution_fingerprint = payload.get("execution_fingerprint")
    if not isinstance(execution_fingerprint, str) or not execution_fingerprint:
        raise ValueError(f"Layer manifest is missing execution_fingerprint: {manifest_path}")
    if (
        expected_execution_fingerprint is not None
        and execution_fingerprint != expected_execution_fingerprint
    ):
        raise ValueError(f"Layer execution fingerprint is stale: {manifest_path}")
    raw_assets = payload.get("assets")
    if not isinstance(raw_assets, list):
        raise ValueError(f"Layer manifest assets must be a list: {manifest_path}")
    assets = tuple(_bundle_asset_from_mapping(value, manifest_path) for value in raw_assets)
    _validate_manifest_assets(manifest_path.parent, assets, verify=verify)
    _validate_asset_roles(assets, spec=spec, mode=_mode(context))
    primary_table = _declared_primary(payload, assets, "primary_table", manifest_path)
    primary_geometry = _declared_primary(payload, assets, "primary_geometry", manifest_path)
    if verify and primary_table is not None and spec is not None:
        _validate_primary_columns(primary_table, spec)
    raw_sources = payload.get("source_manifests", [])
    if not isinstance(raw_sources, list) or not all(isinstance(item, Mapping) for item in raw_sources):
        raise ValueError(f"Invalid source_manifests in {manifest_path}")
    _validate_source_references(context, raw_sources, verify=verify)
    return LayerArtifactBundle(
        manifest_path=manifest_path,
        layer_id=expected_layer_id,
        study_id=_study_id(context),
        mode=_mode(context),
        execution_fingerprint=execution_fingerprint,
        assets=assets,
        primary_table=primary_table,
        primary_geometry=primary_geometry,
        source_manifests=tuple(raw_sources),
    )


def write_study_release(
    context: Any,
    bundles: Iterable[LayerArtifactBundle],
    assets: Iterable[tuple[str, str | Path]],
    *,
    expected_layer_ids: Iterable[str],
) -> Path:
    """Write a complete v2 Study release; missing or extra Layers are errors."""
    root = Path(context.paths.processed)
    root.mkdir(parents=True, exist_ok=True)
    bundle_map = {bundle.layer_id: bundle for bundle in bundles}
    expected = set(map(str, expected_layer_ids))
    if set(bundle_map) != expected:
        missing = sorted(expected - set(bundle_map))
        extra = sorted(set(bundle_map) - expected)
        raise ValueError(f"Study release Layer set mismatch; missing={missing}, extra={extra}")
    layer_refs = []
    for layer_id in sorted(bundle_map):
        manifest = bundle_map[layer_id].manifest_path
        relative = _relative_contained(root, manifest)
        layer_refs.append(
            {
                "layer_id": layer_id,
                "path": relative,
                "bytes": manifest.stat().st_size,
                "sha256": _sha256_file(manifest),
            }
        )
    release_assets = tuple(_release_asset(root, role, path) for role, path in assets)
    _validate_release_roles(release_assets, mode=_mode(context))
    from .settings import resolve_settings

    settings = resolve_settings(context)
    payload = {
        "schema_version": RELEASE_MANIFEST_SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "study_id": _study_id(context),
        "mode": _mode(context),
        "settings_fingerprint": settings.fingerprint,
        "layers": layer_refs,
        "assets": [_release_asset_dict(asset) for asset in release_assets],
    }
    path = root / RELEASE_MANIFEST_NAME
    _atomic_json(path, payload)
    return path


def load_release(
    context: Any,
    *,
    verify: bool = True,
    allow_stale_settings: bool = False,
    expected_layer_ids: Iterable[str] | None = None,
    specs: Mapping[str, Any] | None = None,
) -> StudyRelease:
    """Load a complete v2 Study release and every declared Layer bundle.

    ``allow_stale_settings`` exists only for explicit local recovery tools.
    Runtime verification and publication keep the strict default.
    """
    root = Path(context.paths.processed)
    path = root / RELEASE_MANIFEST_NAME
    payload = _load_json(path)
    if payload.get("schema_version") != RELEASE_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported Study release schema: {path}")
    if payload.get("study_id") != _study_id(context):
        raise ValueError(f"Study release identity mismatch: {path}")
    if payload.get("mode") != _mode(context):
        raise ValueError(f"Study release mode mismatch: {path}")
    from .settings import resolve_settings

    settings_fingerprint = resolve_settings(context).fingerprint
    if (
        payload.get("settings_fingerprint") != settings_fingerprint
        and not allow_stale_settings
    ):
        raise ValueError(f"Study release settings fingerprint is stale: {path}")
    raw_layers = payload.get("layers")
    if not isinstance(raw_layers, list):
        raise ValueError(f"Study release Layers must be a list: {path}")
    refs = [_release_layer_ref(value, path) for value in raw_layers]
    ids = [str(ref["layer_id"]) for ref in refs]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Study release contains duplicate Layer IDs: {path}")
    if expected_layer_ids is not None and set(ids) != set(map(str, expected_layer_ids)):
        raise ValueError(f"Study release does not contain the exact enabled Layer set: {path}")
    bundles: dict[str, LayerArtifactBundle] = {}
    for ref in refs:
        manifest = _safe_resolve(root, str(ref["path"]))
        if verify:
            _verify_file_record(manifest, ref, f"Layer manifest {ref['layer_id']}")
        layer_id = str(ref["layer_id"])
        bundles[layer_id] = load_layer_bundle_manifest(
            manifest,
            context=context,
            expected_layer_id=layer_id,
            verify=verify,
            spec=None if specs is None else specs.get(layer_id),
        )
    raw_assets = payload.get("assets")
    if not isinstance(raw_assets, list):
        raise ValueError(f"Study release assets must be a list: {path}")
    assets = tuple(_release_asset_from_mapping(value, path) for value in raw_assets)
    _validate_release_manifest_assets(root, assets, verify=verify)
    _validate_release_roles(assets, mode=_mode(context))
    return StudyRelease(
        manifest_path=path,
        study_id=_study_id(context),
        mode=_mode(context),
        settings_fingerprint=str(payload.get("settings_fingerprint") or ""),
        layers=bundles,
        assets=assets,
    )


def _bundle_asset(root: Path, produced: ProducedAsset) -> BundleAsset:
    path = produced.path
    if not path.is_absolute():
        path = root / path
    relative = _relative_contained(root, path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return BundleAsset(
        path=relative,
        role=produced.role,
        media_type=_media_type(path),
        bytes=path.stat().st_size,
        sha256=_sha256_file(path),
    )


def _bundle_asset_from_mapping(value: Any, manifest_path: Path) -> BundleAsset:
    if not isinstance(value, Mapping):
        raise ValueError(f"Invalid Layer asset in {manifest_path}")
    try:
        return BundleAsset(
            path=str(value["path"]),
            role=str(value["role"]),
            media_type=str(value["media_type"]),
            bytes=int(value["bytes"]),
            sha256=str(value["sha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Layer asset in {manifest_path}: {value!r}") from exc


def _release_asset(root: Path, role: str, raw_path: str | Path) -> ReleaseAsset:
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    relative = _relative_contained(root, path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return ReleaseAsset(
        path=relative,
        role=str(role),
        media_type=_media_type(path),
        bytes=path.stat().st_size,
        sha256=_sha256_file(path),
    )


def _release_asset_from_mapping(value: Any, manifest_path: Path) -> ReleaseAsset:
    if not isinstance(value, Mapping):
        raise ValueError(f"Invalid release asset in {manifest_path}")
    try:
        return ReleaseAsset(
            path=str(value["path"]),
            role=str(value["role"]),
            media_type=str(value["media_type"]),
            bytes=int(value["bytes"]),
            sha256=str(value["sha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid release asset in {manifest_path}: {value!r}") from exc


def _validate_manifest_assets(root: Path, assets: Sequence[BundleAsset], *, verify: bool) -> None:
    paths = [asset.path for asset in assets]
    if len(paths) != len(set(paths)):
        raise ValueError("Layer manifest contains duplicate asset paths")
    for asset in assets:
        path = _safe_resolve(root, asset.path)
        if verify:
            _verify_file_record(path, _asset_dict(asset), f"Layer asset {asset.path}")


def _validate_release_manifest_assets(
    root: Path, assets: Sequence[ReleaseAsset], *, verify: bool
) -> None:
    paths = [asset.path for asset in assets]
    if len(paths) != len(set(paths)):
        raise ValueError("Study release contains duplicate asset paths")
    for asset in assets:
        path = _safe_resolve(root, asset.path)
        if verify:
            _verify_file_record(path, _release_asset_dict(asset), f"release asset {asset.path}")


def _validate_asset_roles(assets: Sequence[BundleAsset], *, spec: Any, mode: str) -> None:
    tables = [asset for asset in assets if asset.role == "primary_table"]
    geometries = [asset for asset in assets if asset.role == "primary_geometry"]
    if len(tables) > 1 or len(geometries) > 1:
        raise ValueError("Layer bundle has ambiguous primary assets")
    include = bool(getattr(spec, "master", None) and getattr(spec, "master").get("include"))
    if mode == "aggregate" and include and len(tables) != 1:
        raise ValueError("Master Layer bundle must declare exactly one primary_table")


def _validate_release_roles(assets: Sequence[ReleaseAsset], *, mode: str) -> None:
    roles = [asset.role for asset in assets]
    if len(roles) != len(set(roles)):
        raise ValueError("Study release contains duplicate asset roles")
    if mode == "aggregate" and not {"master_csv", "master_geojson"}.issubset(roles):
        raise ValueError("Aggregate release requires master_csv and master_geojson")


def _declared_primary(
    payload: Mapping[str, Any],
    assets: Sequence[BundleAsset],
    role: str,
    manifest_path: Path,
) -> Path | None:
    declared = payload.get(role)
    matching = [asset.path for asset in assets if asset.role == role]
    if declared in (None, ""):
        if matching:
            raise ValueError(f"{role} asset is not declared at manifest top level: {manifest_path}")
        return None
    if matching != [declared]:
        raise ValueError(f"{role} declaration does not match asset roles: {manifest_path}")
    return _safe_resolve(manifest_path.parent, str(declared))


def _validate_primary_columns(path: Path, spec: Any) -> None:
    master = dict(getattr(spec, "master", {}) or {})
    required = {"spatial_id", *map(str, master.get("required_columns", ())) }
    columns = set(pd.read_csv(path, nrows=0).columns)
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Primary table {path} is missing required columns: {missing}")


def _source_manifest_reference(context: Any, raw_path: str | Path) -> dict[str, Any]:
    root = Path(context.repo_root)
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    relative = _relative_contained(root, path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": relative, "bytes": path.stat().st_size, "sha256": _sha256_file(path)}


def _validate_source_references(
    context: Any, references: Sequence[Mapping[str, Any]], *, verify: bool
) -> None:
    if not references:
        return
    root = Path(context.repo_root)
    for reference in references:
        if not all(key in reference for key in ("path", "bytes", "sha256")):
            raise ValueError("Invalid source manifest reference")
        path = _safe_resolve(root, str(reference["path"]))
        # Raw source manifests are provenance links, not release assets. A
        # materialized release may verify without the provider snapshot.
        if verify and path.exists():
            _verify_file_record(path, reference, "source manifest")


def _release_layer_ref(value: Any, manifest_path: Path) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(
        key in value for key in ("layer_id", "path", "bytes", "sha256")
    ):
        raise ValueError(f"Invalid Layer reference in {manifest_path}")
    return value


def _verify_file_record(path: Path, record: Mapping[str, Any], label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing {label}: {path}")
    if path.stat().st_size != int(record["bytes"]):
        raise ValueError(f"{label} size mismatch: {path}")
    if _sha256_file(path) != record["sha256"]:
        raise ValueError(f"{label} checksum mismatch: {path}")


def _relative_contained(root: Path, path: Path) -> str:
    root = root.resolve()
    path = path.resolve()
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Artifact escapes declared root {root}: {path}") from exc


def _safe_resolve(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe artifact path: {relative!r}")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Artifact path escapes root: {relative!r}") from exc
    return resolved


def _path_for_role(assets: Sequence[BundleAsset], role: str) -> str | None:
    matches = [asset.path for asset in assets if asset.role == role]
    return matches[0] if matches else None


def _asset_dict(asset: BundleAsset) -> dict[str, Any]:
    return {
        "path": asset.path,
        "role": asset.role,
        "media_type": asset.media_type,
        "bytes": asset.bytes,
        "sha256": asset.sha256,
    }


def _release_asset_dict(asset: ReleaseAsset) -> dict[str, Any]:
    return {
        "path": asset.path,
        "role": asset.role,
        "media_type": asset.media_type,
        "bytes": asset.bytes,
        "sha256": asset.sha256,
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Manifest must contain an object: {path}")
    return payload


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    staged = path.with_name(f".{path.name}.{uuid4().hex}.partial")
    staged.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(staged, path)


def _study_id(context: Any) -> str:
    study = getattr(context, "study", context)
    return str(getattr(study, "id", ""))


def _mode(context: Any) -> str:
    return str(getattr(context, "mode", "native" if getattr(context, "is_native", False) else "aggregate"))


def _spatial_contract(context: Any) -> dict[str, Any]:
    if _mode(context) == "native":
        return {"support": "native", "aoi_path": str(getattr(context, "aoi_path", "") or "")}
    study = getattr(context, "study", context)
    return {
        "support": "aggregate",
        "id_column": "spatial_id",
        "name_column": "spatial_name",
        "expected_units": getattr(context, "expected_units", None),
        "unit_type": getattr(study, "unit_type", None),
        "source_path": str(getattr(context, "spatial_path", "") or ""),
    }


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _media_type(path: Path) -> str:
    return {
        ".csv": "text/csv",
        ".geojson": "application/geo+json",
        ".json": "application/json",
        ".tif": "image/tiff",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".pdf": "application/pdf",
        ".svg": "image/svg+xml",
        ".gpkg": "application/geopackage+sqlite3",
        ".pbf": "application/vnd.mapbox-vector-tile",
    }.get(path.suffix.lower(), "application/octet-stream")

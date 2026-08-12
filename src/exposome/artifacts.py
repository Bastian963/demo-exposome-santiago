"""Compatibility facade for the strict v2 Artifact bundle contract.

Canonical execution writes manifests through :mod:`artifact_contract` from an
explicit ``LayerBuildResult``.  ``write_layer_manifest`` remains only for
migration/tests that still hand over a list of files.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

from .artifact_contract import (
    BundleAsset as ArtifactAsset,
    LAYER_MANIFEST_NAME as MANIFEST_NAME,
    LAYER_MANIFEST_SCHEMA_VERSION as SCHEMA_VERSION,
    write_layer_bundle_manifest,
)
from .execution import LayerBuildResult, ProducedAsset

__all__ = [
    "ArtifactAsset",
    "MANIFEST_NAME",
    "SCHEMA_VERSION",
    "primary_table_from_manifest",
    "write_layer_manifest",
]


def write_layer_manifest(
    context: Any,
    spec: Any,
    output_dir: Path,
    files: Iterable[Path],
    *,
    execution_fingerprint: str | None = None,
) -> Path:
    """Adapt legacy file lists into a v2 bundle; do not use for new runners."""
    from .runners import collect_legacy_assets

    output_dir = Path(output_dir)
    allowed = {Path(path).resolve() for path in files if Path(path).is_file()}
    collected = collect_legacy_assets(output_dir, spec)
    assets = tuple(
        ProducedAsset(asset.path, asset.role)
        for asset in collected.assets
        if not allowed or asset.path.resolve() in allowed
    )
    result = LayerBuildResult(assets)
    fingerprint = execution_fingerprint or _compatibility_fingerprint(
        context, spec, assets
    )
    return write_layer_bundle_manifest(
        context,
        spec,
        output_dir,
        result,
        execution_fingerprint=fingerprint,
    )


def primary_table_from_manifest(output_dir: str | Path) -> Path | None:
    """Return a checksum-verified primary table from a v2 manifest only."""
    root = Path(output_dir)
    manifest_path = root / MANIFEST_NAME
    payload = _load_json(manifest_path)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Unsupported Layer manifest schema: {manifest_path}")
    primary = payload.get("primary_table")
    if primary in (None, ""):
        return None
    matching = [
        asset
        for asset in payload.get("assets", [])
        if isinstance(asset, dict) and asset.get("role") == "primary_table"
    ]
    if len(matching) != 1 or matching[0].get("path") != primary:
        raise ValueError(f"Ambiguous primary_table declaration: {manifest_path}")
    path = _safe_asset(root, str(primary))
    _verify(path, matching[0])
    return path


def _compatibility_fingerprint(
    context: Any,
    spec: Any,
    assets: tuple[ProducedAsset, ...],
) -> str:
    study = getattr(context, "study", context)
    payload = {
        "adapter": "legacy-file-list-v2",
        "study_id": str(getattr(study, "id", "")),
        "layer_id": str(getattr(spec, "id", spec)),
        "mode": str(getattr(context, "mode", "aggregate")),
        "files": [asset.path.name for asset in assets],
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid Layer manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Layer manifest must contain an object: {path}")
    return payload


def _safe_asset(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe Layer asset path: {relative!r}")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Layer asset escapes bundle: {relative!r}") from exc
    return resolved


def _verify(path: Path, record: dict[str, Any]) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.stat().st_size != int(record.get("bytes", -1)):
        raise ValueError(f"Layer asset size mismatch: {path}")
    digest = sha256(path.read_bytes()).hexdigest()
    if digest != record.get("sha256"):
        raise ValueError(f"Layer asset checksum mismatch: {path}")

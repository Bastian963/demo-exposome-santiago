"""Upgrade one verified v1 Study release to strict v2 manifests.

Dry-run is the default. The migration is local and never calls a provider. It
keeps ``*.v1.json`` backups and restores them if v2 verification fails.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Mapping

import typer


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from exposome.artifact_contract import (  # noqa: E402
    LAYER_MANIFEST_SCHEMA_VERSION,
    RELEASE_MANIFEST_SCHEMA_VERSION,
    load_release,
    write_layer_bundle_manifest,
    write_study_release,
)
from exposome.cache import spatial_fingerprint  # noqa: E402
from exposome.execution import (  # noqa: E402
    LayerBuildResult,
    LayerExecutionIdentity,
    ProducedAsset,
)
from exposome.layers import load_layer_catalog  # noqa: E402
from exposome.layers import layer_execution_identity  # noqa: E402
from exposome.settings import resolve_settings  # noqa: E402
from exposome.studies import StudyContext, load_study  # noqa: E402


_MASTER_ROLE_MAP = {
    "csv": "master_csv",
    "geojson": "master_geojson",
    "metadata": "master_metadata",
    "report": "master_report",
}


def upgrade_release(
    context: StudyContext,
    *,
    write: bool,
    allow_stale_settings: bool = False,
) -> tuple[str, ...]:
    root = context.paths.processed
    release_path = root / "release_manifest.json"
    release_payload = _load_json(release_path)
    schema = release_payload.get("schema_version")
    if schema == RELEASE_MANIFEST_SCHEMA_VERSION:
        expected = _expected_layers(context)
        # A partial recovery may have re-run one Layer after an earlier v2
        # release was written, so its release checksum is intentionally stale
        # until this explicit rebind repairs the index.
        release = load_release(
            context,
            expected_layer_ids=expected,
            verify=not allow_stale_settings,
            allow_stale_settings=allow_stale_settings,
        )
        if allow_stale_settings:
            return _rebind_v2_execution_identities(context, release, write=write)
        return (f"ALREADY v2: {release_path}",)
    if schema != 1:
        raise ValueError(f"Unsupported source release schema {schema!r}: {release_path}")
    _verify_v1_release(
        context,
        release_payload,
        allow_stale_settings=allow_stale_settings,
    )
    expected = _expected_layers(context)
    layer_entries = {
        str(entry["layer_id"]): entry
        for entry in release_payload.get("layers", [])
        if isinstance(entry, Mapping) and entry.get("layer_id")
    }
    unexpected = sorted(set(layer_entries) - set(expected))
    if unexpected:
        raise ValueError(
            "v1 release contains Layer IDs no longer enabled: " + ", ".join(unexpected)
        )
    prepared = []
    existing_bundles = []
    catalog = load_layer_catalog()
    for layer_id in expected:
        entry = layer_entries.get(layer_id)
        # A new required Layer can be produced while recovering a historic v1
        # release, so it has no v1 reference by definition.  It is accepted
        # only as an already verified v2 bundle at its canonical location.
        manifest_path = (
            root / str(entry["path"])
            if entry is not None
            else root / layer_id / "manifest.json"
        )
        if not manifest_path.is_file():
            if entry is None:
                raise ValueError(
                    f"New required Layer {layer_id!r} has no v2 bundle yet: {manifest_path}. "
                    "Run the recovery-plan command for that Layer before migration."
                )
            raise FileNotFoundError(f"Missing v1 Layer manifest: {manifest_path}")
        payload = _load_json(manifest_path)
        schema = payload.get("schema_version")
        if schema == 1:
            if entry is None:
                raise ValueError(
                    f"New required Layer {layer_id!r} must be re-run into a v2 bundle: {manifest_path}"
                )
            prepared.append(
                _prepare_layer(
                    context,
                    layer_id,
                    manifest_path,
                    current_identity=allow_stale_settings,
                )
            )
        elif schema == LAYER_MANIFEST_SCHEMA_VERSION:
            from exposome.artifact_contract import load_layer_bundle

            existing_bundles.append(
                load_layer_bundle(context, layer_id, spec=catalog.get(layer_id))
            )
        else:
            raise ValueError(
                f"Unsupported Layer manifest schema {schema!r}: {manifest_path}"
            )
    release_assets = _release_assets(root, release_payload, mode=context.mode)
    messages = [
        f"READY {layer_id}: {manifest_path} -> schema v{LAYER_MANIFEST_SCHEMA_VERSION}"
        for layer_id, manifest_path, *_ in prepared
    ]
    messages.extend(
        f"RETAIN v{LAYER_MANIFEST_SCHEMA_VERSION}: {bundle.manifest_path}"
        for bundle in existing_bundles
    )
    messages.append(f"READY release: {release_path} -> schema v{RELEASE_MANIFEST_SCHEMA_VERSION}")
    if not write:
        return tuple(messages)

    backups: list[tuple[Path, Path]] = []
    try:
        backups.append((release_path, _backup_v1(release_path)))
        for _, manifest_path, _, _, _, _ in prepared:
            backups.append((manifest_path, _backup_v1(manifest_path)))
        bundles = list(existing_bundles)
        for layer_id, manifest_path, spec, result, fingerprint, source_manifests in prepared:
            write_layer_bundle_manifest(
                context,
                spec,
                manifest_path.parent,
                result,
                execution_fingerprint=fingerprint,
                source_manifests=source_manifests,
            )
            from exposome.artifact_contract import load_layer_bundle

            bundles.append(load_layer_bundle(context, layer_id, spec=spec))
        write_study_release(
            context,
            bundles,
            release_assets,
            expected_layer_ids=expected,
        )
        load_release(
            context,
            expected_layer_ids=expected,
            specs={layer_id: spec for layer_id, _, spec, *_ in prepared},
        )
    except Exception:
        for destination, backup in reversed(backups):
            if backup.is_file():
                shutil.copy2(backup, destination)
        raise
    return tuple([*messages, "WRITE complete; v1 backups retained for rollback"])


def _prepare_layer(
    context: StudyContext,
    layer_id: str,
    manifest_path: Path,
    *,
    current_identity: bool = False,
):
    payload = _load_json(manifest_path)
    if payload.get("schema_version") != 1:
        raise ValueError(f"Expected v1 Layer manifest: {manifest_path}")
    if payload.get("layer_id") != layer_id:
        raise ValueError(f"Layer identity mismatch: {manifest_path}")
    if payload.get("study_id") != context.study.id:
        raise ValueError(f"Study identity mismatch: {manifest_path}")
    catalog = load_layer_catalog()
    spec = catalog.get(layer_id)
    assets = []
    for raw in payload.get("assets", []):
        if not isinstance(raw, Mapping) or not raw.get("path") or not raw.get("role"):
            raise ValueError(f"Invalid v1 asset in {manifest_path}")
        relative = Path(str(raw["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe v1 asset path in {manifest_path}: {relative}")
        asset_path = manifest_path.parent / relative
        assets.append(ProducedAsset(asset_path, str(raw["role"])))
    result = LayerBuildResult(tuple(assets))
    identity = (
        layer_execution_identity(context, spec)
        if current_identity
        else LayerExecutionIdentity(
            study_id=context.study.id,
            layer_id=layer_id,
            mode=context.mode,
            layer_settings=context.layer_settings(layer_id),
            period=context.study.period,
            spatial_fingerprint=_context_spatial_fingerprint(context),
            algorithm_version="legacy-v1-verified",
        )
    )
    source_manifests = tuple(
        context.repo_root / str(ref["path"])
        for ref in payload.get("source_manifests", [])
        if isinstance(ref, Mapping) and ref.get("path")
    )
    return (
        layer_id,
        manifest_path,
        spec,
        result,
        identity.fingerprint,
        source_manifests,
    )


def _rebind_v2_execution_identities(
    context: StudyContext,
    release: Any,
    *,
    write: bool,
) -> tuple[str, ...]:
    """Explicitly bind verified migrated bundles to the current execution identity.

    This recovery path is deliberately gated by ``--allow-stale-settings``.
    It is for a v1 release whose affected Layers have already been re-run and
    whose remaining, verified historic bundles were accepted by the operator.
    """
    from exposome.artifact_contract import load_layer_bundle

    root = context.paths.processed
    catalog = load_layer_catalog()
    stale = []
    for layer_id in _expected_layers(context):
        bundle = release.layers[layer_id]
        identity = layer_execution_identity(context, catalog.get(layer_id))
        if bundle.execution_fingerprint == identity.fingerprint:
            continue
        source_paths = tuple(
            context.repo_root / str(reference["path"])
            for reference in bundle.source_manifests
            if reference.get("path") and (context.repo_root / str(reference["path"])).is_file()
        )
        result = LayerBuildResult(
            tuple(
                ProducedAsset(bundle.manifest_path.parent / asset.path, asset.role)
                for asset in bundle.assets
            ),
            source_paths,
        )
        stale.append((layer_id, bundle.manifest_path, catalog.get(layer_id), result, identity.fingerprint))

    messages = [
        f"REBIND {layer_id}: {manifest_path} -> current execution identity"
        for layer_id, manifest_path, *_ in stale
    ]
    if not write:
        return tuple(messages or ["READY current v2 execution identities and release assets"])

    backups: list[tuple[Path, Path]] = []
    try:
        for _, manifest_path, _, _, _ in stale:
            backup = manifest_path.with_name(f"{manifest_path.stem}.pre_rebind.json")
            shutil.copy2(manifest_path, backup)
            backups.append((manifest_path, backup))
        release_backup = root / "release_manifest.pre_rebind.json"
        shutil.copy2(release.manifest_path, release_backup)
        backups.append((release.manifest_path, release_backup))

        for layer_id, manifest_path, spec, result, fingerprint in stale:
            write_layer_bundle_manifest(
                context,
                spec,
                manifest_path.parent,
                result,
                execution_fingerprint=fingerprint,
                source_manifests=result.source_manifests,
            )
        bundles = [
            load_layer_bundle(
                context,
                layer_id,
                verify=True,
                expected_execution_fingerprint=layer_execution_identity(
                    context, catalog.get(layer_id)
                ).fingerprint,
                spec=catalog.get(layer_id),
            )
            for layer_id in _expected_layers(context)
        ]
        assets = tuple(
            (asset.role, root / asset.path) for asset in release.assets
        )
        write_study_release(
            context,
            bundles,
            assets,
            expected_layer_ids=_expected_layers(context),
        )
        load_release(context, expected_layer_ids=_expected_layers(context))
    except Exception:
        for destination, backup in reversed(backups):
            if backup.is_file():
                shutil.copy2(backup, destination)
        raise
    return tuple(
        [
            *(messages or ["RETAIN current v2 execution identities"]),
            "WRITE complete; pre-rebind backups retained for rollback",
        ]
    )


def _context_spatial_fingerprint(context: StudyContext) -> str:
    if context.is_native:
        path = context.aoi_path
        if path is None or not path.is_file():
            raise FileNotFoundError(f"Native Study AOI is missing: {path}")
        return _sha256_file(path)
    return spatial_fingerprint(context.load_spatial_units())


def _release_assets(
    root: Path,
    payload: Mapping[str, Any],
    *,
    mode: str,
) -> tuple[tuple[str, Path], ...]:
    assets = []
    for entry in payload.get("master_assets", []):
        if not isinstance(entry, Mapping) or not entry.get("role") or not entry.get("path"):
            raise ValueError("Invalid v1 master asset")
        old_role = str(entry["role"])
        role = _MASTER_ROLE_MAP.get(old_role, f"master_{old_role}")
        relative = Path(str(entry["path"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Unsafe v1 master asset path: {relative}")
        assets.append((role, root / relative))
    roles = {role for role, _ in assets}
    if mode == "aggregate" and not {"master_csv", "master_geojson"}.issubset(roles):
        raise ValueError("v1 aggregate release lacks master CSV or GeoJSON")
    for directory in (
        "profiles",
        "profiles_meta",
        "subcomuna",
        "annual",
        "detail",
        "analysis/web",
    ):
        directory_path = root / directory
        if directory_path.is_dir():
            for path in sorted(
                candidate for candidate in directory_path.rglob("*") if candidate.is_file()
            ):
                relative = path.relative_to(root).as_posix()
                assets.append((f"publication/{relative}", path))
    for name in ("zipcodes.json", "location_profile_axes.json"):
        path = root / name
        if path.is_file():
            assets.append((f"publication/{name}", path))
    return tuple(assets)


def _verify_v1_release(
    context: StudyContext,
    payload: Mapping[str, Any],
    *,
    allow_stale_settings: bool,
) -> None:
    """Verify the old checksum contract without allowing it into runtime."""
    if payload.get("study_id") != context.study.id:
        raise ValueError("v1 release Study identity mismatch")
    current_settings = resolve_settings(context).fingerprint
    if payload.get("settings_fingerprint") != current_settings and not allow_stale_settings:
        raise ValueError(
            "v1 release settings fingerprint is stale; re-run changed layers or "
            "pass --allow-stale-settings only after doing so"
        )
    root = context.paths.processed
    for entry in payload.get("layers", []):
        if not isinstance(entry, Mapping) or not entry.get("path"):
            raise ValueError("Invalid v1 Layer reference")
        manifest_path = _safe_path(root, str(entry["path"]))
        manifest = _load_json(manifest_path)
        schema = manifest.get("schema_version")
        if schema == 1:
            # A recovery may have replaced other Layer manifests without
            # replacing the old v1 release index.  In the explicit escape-hatch
            # mode, verify the manifest's own assets instead of treating that
            # stale index checksum as the source of truth.
            if not allow_stale_settings:
                _verify_v1_file(manifest_path, entry, "Layer manifest")
            for asset in manifest.get("assets", []):
                if not isinstance(asset, Mapping) or not asset.get("path"):
                    raise ValueError(f"Invalid v1 asset in {manifest_path}")
                asset_path = _safe_path(manifest_path.parent, str(asset["path"]))
                _verify_v1_file(asset_path, asset, "Layer asset")
        elif schema != LAYER_MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"Unsupported Layer manifest schema {schema!r}: {manifest_path}")
    for entry in payload.get("master_assets", []):
        if not isinstance(entry, Mapping) or not entry.get("path"):
            raise ValueError("Invalid v1 master asset")
        master_path = _safe_path(root, str(entry["path"]))
        if allow_stale_settings:
            if not master_path.is_file():
                raise FileNotFoundError(f"Missing v1 master asset: {master_path}")
        else:
            _verify_v1_file(master_path, entry, "master asset")


def _safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe v1 artifact path: {relative}")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"v1 artifact escapes release root: {relative}") from exc
    return resolved


def _verify_v1_file(path: Path, record: Mapping[str, Any], label: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Missing v1 {label}: {path}")
    if record.get("bytes") is not None and path.stat().st_size != int(record["bytes"]):
        raise ValueError(f"v1 {label} size mismatch: {path}")
    if record.get("sha256") != _sha256_file(path):
        raise ValueError(f"v1 {label} checksum mismatch: {path}")


def _expected_layers(context: StudyContext) -> tuple[str, ...]:
    catalog = load_layer_catalog()
    return tuple(dict.fromkeys(catalog.resolve_id(value) for value in context.enabled_layers))


def _backup_v1(path: Path) -> Path:
    backup = path.with_name(f"{path.stem}.v1{path.suffix}")
    if backup.is_file():
        if backup.read_bytes() != path.read_bytes():
            raise ValueError(f"Existing v1 backup differs from source: {backup}")
        return backup
    shutil.copy2(path, backup)
    return backup


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"JSON must contain an object: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(
    study: str = typer.Option(..., "--study"),
    write: bool = typer.Option(False, "--write", help="Activate v2 after validation"),
    allow_stale_settings: bool = typer.Option(
        False,
        "--allow-stale-settings",
        help="Allow an explicitly recovered mixed v1/v2 release after changed layers were re-run",
    ),
) -> None:
    context = load_study(study)
    for message in upgrade_release(
        context,
        write=write,
        allow_stale_settings=allow_stale_settings,
    ):
        typer.echo(message)
    if not write:
        typer.echo("Dry-run only; pass --write after reviewing this report.")


if __name__ == "__main__":
    typer.run(main)

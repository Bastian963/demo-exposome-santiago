"""Immutable, checksum-addressed handoffs between collection and GEMMA nodes."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Iterable, Mapping

from .releases import canonical_enabled_layers, load_release
from .studies import load_study


HANDOFF_SCHEMA_VERSION = 1
MANIFEST_NAME = "handoff_manifest.json"
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_DENIED_PARTS = {".git", ".venv", "cache", "tmp", ".netrc"}


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        return resolved.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Handoff asset escapes repository root: {path}") from exc


def _safe_relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or any(part in _DENIED_PARTS for part in path.parts):
        raise ValueError(f"Unsafe handoff path: {value!r}")
    return path


def _record(path: Path, root: Path, *, role: str, study_id: str | None = None) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Handoff asset must be a regular file: {path}")
    return {
        "path": _relative(root, path),
        "role": role,
        "study_id": study_id,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _config_fingerprint(path: Path, root: Path) -> dict[str, str]:
    """Describe a configuration the receiving repository must already share."""
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Study configuration must be a regular file: {path}")
    return {"path": _relative(root, path), "sha256": _sha256(path)}


def _release_records(context: Any) -> list[tuple[Path, str]]:
    """Return the complete durable closure of one verified study release."""
    release = load_release(
        context,
        verify=True,
        expected_layer_ids=canonical_enabled_layers(context),
    )
    records: list[tuple[Path, str]] = [(release.manifest_path, "release_manifest")]
    for bundle in release.layers.values():
        records.append((bundle.manifest_path, "layer_manifest"))
        records.extend((bundle.manifest_path.parent / asset.path, f"layer/{asset.role}") for asset in bundle.assets)
        for source in bundle.source_manifests:
            raw = context.repo_root / str(source["path"])
            records.append((raw, "source_manifest"))
    records.extend((release.manifest_path.parent / asset.path, f"release/{asset.role}") for asset in release.assets)
    records.append((context.study.spatial_path, "spatial_reference"))
    if context.study.aoi_path is not None:
        records.append((context.study.aoi_path, "aoi_reference"))
    return records


def export_handoff(
    *,
    node_id: str,
    studies: Iterable[str],
    output_root: str | Path,
    repo_root: str | Path,
    operations: str | Path | None = None,
    run_id: str | None = None,
    dry_run: bool = False,
) -> Path | dict[str, Any]:
    """Freeze verified study releases into a new immutable handoff directory."""
    if not _SAFE_ID.fullmatch(node_id):
        raise ValueError("node_id must be a lowercase slug")
    root = Path(repo_root).resolve()
    study_ids = tuple(dict.fromkeys(map(str, studies)))
    if not study_ids:
        raise ValueError("At least one --study is required")
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("Cannot determine producer Git commit")
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + commit[:8]
    if not _SAFE_ID.fullmatch(run_id):
        raise ValueError("run_id must be a lowercase slug")

    selected: list[dict[str, Any]] = []
    assets: dict[str, dict[str, Any]] = {}
    for study_id in study_ids:
        context = load_study(study_id, repo_root_path=root)
        for path, role in _release_records(context):
            item = _record(path, root, role=role, study_id=study_id)
            previous = assets.get(item["path"])
            if previous and previous["sha256"] != item["sha256"]:
                raise ValueError(f"Conflicting handoff asset path: {item['path']}")
            assets[item["path"]] = item
        selected.append(
            {
                "study_id": study_id,
                "layers": list(canonical_enabled_layers(context)),
                # The central checkout must already contain the reviewed
                # configuration. A collection node exports its fingerprint,
                # never an unreviewed replacement configuration.
                "configurations": {
                    "study": _config_fingerprint(context.study.config_path, root),
                    "location": _config_fingerprint(context.location.config_path, root),
                },
            }
        )

    if operations is not None:
        operations_path = Path(operations).resolve()
        for name in ("summary.json", "summary.md", "incident_candidates.md"):
            source = operations_path / name
            if source.is_file():
                item = _record(source, operations_path, role="operation_summary")
                item["path"] = f"operations/{name}"
                assets[item["path"]] = item

    payload: dict[str, Any] = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "handoff_id": f"{node_id}/{run_id}",
        "node_id": node_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository": {
            "commit": commit,
            "branch": subprocess.run(
                ["git", "-C", str(root), "branch", "--show-current"],
                check=True, capture_output=True, text=True,
            ).stdout.strip(),
        },
        "status": "complete",
        "studies": selected,
        "artifacts": [assets[key] for key in sorted(assets)],
        "exclusions": [".git", ".venv", "cache", "credentials", "OAuth tokens"],
    }
    if dry_run:
        return payload
    destination = Path(output_root).resolve() / node_id / run_id
    if destination.exists():
        raise FileExistsError(f"Handoff destination already exists: {destination}")
    destination.mkdir(parents=True)
    for item in payload["artifacts"]:
        relative = _safe_relative(item["path"])
        source = (operations_path / relative.name) if str(relative).startswith("operations/") else root / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if _sha256(target) != item["sha256"]:
            raise RuntimeError(f"Checksum changed while exporting {relative}")
    (destination / MANIFEST_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def validate_handoff(handoff: str | Path) -> dict[str, Any]:
    """Validate all immutable handoff assets before any central write."""
    root = Path(handoff).resolve()
    manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != HANDOFF_SCHEMA_VERSION:
        raise ValueError("Unsupported handoff schema_version")
    handoff_id = str(manifest.get("handoff_id", ""))
    if len(handoff_id.split("/")) != 2 or not all(_SAFE_ID.fullmatch(part) for part in handoff_id.split("/")):
        raise ValueError("Invalid handoff_id")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("Handoff artifacts must be a non-empty list")
    seen: set[str] = set()
    for item in artifacts:
        relative = _safe_relative(str(item.get("path", "")))
        if relative.as_posix() in seen:
            raise ValueError(f"Duplicate handoff asset: {relative}")
        seen.add(relative.as_posix())
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or unsafe handoff asset: {relative}")
        if path.stat().st_size != int(item.get("size_bytes", -1)) or _sha256(path) != item.get("sha256"):
            raise ValueError(f"Checksum mismatch for handoff asset: {relative}")
    return manifest


def _check_configuration_compatibility(manifest: Mapping[str, Any], target_root: Path) -> None:
    """Reject outputs when central configuration differs from the collection run."""
    for study in manifest.get("studies", []):
        study_id = str(study.get("study_id", "?"))
        configurations = study.get("configurations", {})
        if not isinstance(configurations, Mapping):
            raise ValueError(f"Handoff study {study_id} lacks configuration fingerprints")
        for kind in ("study", "location"):
            item = configurations.get(kind)
            if not isinstance(item, Mapping):
                raise ValueError(f"Handoff study {study_id} lacks {kind} configuration fingerprint")
            relative = _safe_relative(str(item.get("path", "")))
            current = target_root / relative
            if current.is_symlink() or not current.is_file() or _sha256(current) != item.get("sha256"):
                raise ValueError(
                    f"Configuration mismatch for {study_id} ({kind}): "
                    "merge the reviewed collection configuration before importing its release"
                )


def import_handoff(
    *,
    handoff: str | Path,
    repo_root: str | Path,
    staging_root: str | Path,
    promote: bool = False,
) -> dict[str, Any]:
    """Stage a verified handoff and optionally promote non-conflicting assets."""
    manifest = validate_handoff(handoff)
    source_root = Path(handoff).resolve()
    target_root = Path(repo_root).resolve()
    _check_configuration_compatibility(manifest, target_root)
    stage = Path(staging_root).resolve() / str(manifest["handoff_id"]).replace("/", "__")
    if stage.exists():
        raise FileExistsError(f"Staging destination already exists: {stage}")
    stage.mkdir(parents=True)
    accepted: list[str] = []
    deduplicated: list[str] = []
    collisions: list[str] = []
    for item in manifest["artifacts"]:
        relative = _safe_relative(str(item["path"]))
        source = source_root / relative
        staged = stage / relative
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, staged)
        # Operation summaries stay beside the staged handoff as collection
        # evidence. They are not part of the central product tree.
        if item.get("role") == "operation_summary":
            continue
        destination = target_root / relative
        if destination.exists():
            if destination.is_symlink() or not destination.is_file() or _sha256(destination) != item["sha256"]:
                collisions.append(relative.as_posix())
            else:
                deduplicated.append(relative.as_posix())
        else:
            accepted.append(relative.as_posix())
    report = {"handoff_id": manifest["handoff_id"], "accepted": accepted, "deduplicated": deduplicated, "collisions": collisions, "promoted": []}
    (stage / "acceptance_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if promote:
        if collisions:
            raise ValueError("Refusing promotion due to content collisions: " + ", ".join(collisions))
        for relative_text in accepted:
            relative = _safe_relative(relative_text)
            destination = target_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".handoff-partial")
            shutil.copy2(stage / relative, temporary)
            if _sha256(temporary) != _sha256(stage / relative):
                raise RuntimeError(f"Staged checksum changed for {relative}")
            temporary.replace(destination)
            report["promoted"].append(relative_text)
        (stage / "acceptance_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report

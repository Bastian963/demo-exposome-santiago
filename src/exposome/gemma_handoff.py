"""Offline, integrity-checked handoff of a published bundle to GEMMA.

The compute machine and the local GEMMA machine intentionally do not share
their ignored ``webapp/public/data`` trees through Git.  This module builds a
small, explicit archive containing one published bundle and imports it only
after checking every file hash.  It does not contact a service or read any
raw/provider cache.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


HANDOFF_SCHEMA_VERSION = 1


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError(f"unsafe relative path: {value!r}")
    return path


def _bundle_relative(bundle: Path, data_root: Path) -> PurePosixPath:
    try:
        relative = bundle.resolve().relative_to(data_root.resolve())
    except ValueError as exc:
        raise ValueError(f"bundle must be inside data root {data_root}") from exc
    path = _safe_relative(relative.as_posix())
    if len(path.parts) < 4 or path.parts[0] != "v1":
        raise ValueError("bundle must follow data/v1/<iso2>/<city>/<study>")
    return path


def _read_manifest(path: Path) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"published bundle has no manifest.json: {path}")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid bundle manifest: {manifest_path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("study_id"), str):
        raise ValueError("bundle manifest must contain a string study_id")
    return payload


def bundle_inventory(bundle: str | Path) -> list[dict[str, Any]]:
    """Return sorted hashes for regular files of one published bundle."""
    root = Path(bundle)
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"bundle may not contain symlinks: {path}")
        if not path.is_file():
            continue
        relative = _safe_relative(path.relative_to(root).as_posix())
        records.append(
            {
                "path": relative.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256_path(path),
            }
        )
    if not any(record["path"] == "manifest.json" for record in records):
        raise FileNotFoundError(f"published bundle has no manifest.json: {root}")
    return records


def create_handoff(
    bundle: str | Path,
    output: str | Path,
    *,
    data_root: str | Path,
) -> dict[str, Any]:
    """Write an uncompressed tar handoff and return its metadata."""
    bundle_path = Path(bundle).resolve()
    if not bundle_path.is_dir():
        raise FileNotFoundError(f"published bundle directory not found: {bundle_path}")
    manifest = _read_manifest(bundle_path)
    relative = _bundle_relative(bundle_path, Path(data_root))
    files = bundle_inventory(bundle_path)
    handoff = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "study_id": manifest["study_id"],
        "bundle": relative.as_posix(),
        "manifest_sha256": next(record["sha256"] for record in files if record["path"] == "manifest.json"),
        "files": files,
    }
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(handoff, ensure_ascii=False, indent=2).encode("utf-8")
    with tarfile.open(destination, "w") as archive:
        info = tarfile.TarInfo("handoff.json")
        info.size = len(payload)
        info.mtime = 0
        archive.addfile(info, io.BytesIO(payload))
        for record in files:
            archive.add(bundle_path / record["path"], arcname=f"bundle/{record['path']}", recursive=False)
    return handoff


def _read_handoff(archive: tarfile.TarFile) -> tuple[dict[str, Any], dict[str, tarfile.TarInfo]]:
    members = archive.getmembers()
    by_name: dict[str, tarfile.TarInfo] = {}
    for member in members:
        path = _safe_relative(member.name)
        if member.name in by_name:
            raise ValueError(f"archive has duplicate member: {member.name}")
        if not (member.isfile() or member.isdir()):
            raise ValueError(f"archive contains unsupported member: {member.name}")
        if path.parts[0] not in {"handoff.json", "bundle"}:
            raise ValueError(f"archive contains unexpected member: {member.name}")
        if path.parts[0] == "handoff.json" and len(path.parts) != 1:
            raise ValueError(f"archive contains unexpected member: {member.name}")
        by_name[member.name] = member
    info = by_name.get("handoff.json")
    if info is None or not info.isfile():
        raise ValueError("archive has no handoff.json")
    source = archive.extractfile(info)
    assert source is not None
    try:
        payload = json.loads(source.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("archive handoff.json is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != HANDOFF_SCHEMA_VERSION:
        raise ValueError("unsupported handoff schema")
    if not isinstance(payload.get("study_id"), str):
        raise ValueError("handoff has no study_id")
    _safe_relative(str(payload.get("bundle", "")))
    if not str(payload["bundle"]).startswith("v1/"):
        raise ValueError("handoff bundle must be inside v1")
    records = payload.get("files")
    if not isinstance(records, list) or not records:
        raise ValueError("handoff has no file inventory")
    expected: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("handoff has invalid file inventory")
        path = _safe_relative(str(record.get("path", ""))).as_posix()
        digest = record.get("sha256")
        size = record.get("bytes")
        if not isinstance(digest, str) or len(digest) != 64 or not isinstance(size, int) or size < 0:
            raise ValueError(f"invalid inventory record: {path}")
        if path in expected:
            raise ValueError(f"duplicate inventory path: {path}")
        expected.add(path)
    actual = {name.removeprefix("bundle/") for name, item in by_name.items() if item.isfile() and name.startswith("bundle/")}
    if actual != expected:
        raise ValueError("archive files do not exactly match its inventory")
    if "manifest.json" not in expected:
        raise ValueError("handoff inventory has no manifest.json")
    return payload, by_name


def inspect_handoff(archive_path: str | Path) -> dict[str, Any]:
    """Validate an archive without writing to a GEMMA data directory."""
    with tarfile.open(archive_path, "r:*") as archive:
        payload, members = _read_handoff(archive)
        expected = {record["path"]: record for record in payload["files"]}
        for path, record in expected.items():
            handle = archive.extractfile(members[f"bundle/{path}"])
            assert handle is not None
            digest = hashlib.sha256()
            total = 0
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                total += len(chunk)
            if total != record["bytes"] or digest.hexdigest() != record["sha256"]:
                raise ValueError(f"integrity check failed for {path}")
        if expected["manifest.json"]["sha256"] != payload.get("manifest_sha256"):
            raise ValueError("handoff manifest hash does not match inventory")
    return payload


def _write_archive_files(archive: tarfile.TarFile, members: dict[str, tarfile.TarInfo], destination: Path, records: Iterable[dict[str, Any]]) -> None:
    for record in records:
        relative = _safe_relative(record["path"])
        output = destination.joinpath(*relative.parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        source = archive.extractfile(members[f"bundle/{relative.as_posix()}"])
        assert source is not None
        with output.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)


def _matches_inventory(bundle: Path, records: Iterable[dict[str, Any]]) -> bool:
    """Whether an existing destination is exactly the archived file set."""
    expected = {record["path"]: record for record in records}
    try:
        actual = bundle_inventory(bundle)
    except (FileNotFoundError, ValueError):
        return False
    if {record["path"] for record in actual} != set(expected):
        return False
    return all(
        record["bytes"] == expected[record["path"]]["bytes"]
        and record["sha256"] == expected[record["path"]]["sha256"]
        for record in actual
    )


def import_handoff(
    archive_path: str | Path,
    *,
    data_root: str | Path,
    repo_root: str | Path,
    replace: bool = False,
) -> dict[str, Any]:
    """Verify then install a handoff, refusing a divergent existing bundle."""
    payload = inspect_handoff(archive_path)
    target_relative = _safe_relative(payload["bundle"])
    destination_root = Path(data_root).resolve()
    destination = destination_root.joinpath(*target_relative.parts)
    if destination.exists():
        if _matches_inventory(destination, payload["files"]):
            installed = False
        elif not replace:
            raise FileExistsError(f"destination already has a different bundle: {destination}; rerun with --replace")
        else:
            installed = True
    else:
        installed = True
    if installed:
        destination_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".gemma-handoff-", dir=destination_root) as temporary:
            stage = Path(temporary) / "bundle"
            with tarfile.open(archive_path, "r:*") as archive:
                _, members = _read_handoff(archive)
                _write_archive_files(archive, members, stage, payload["files"])
            _read_manifest(stage)
            backup = destination.with_name(f".{destination.name}.gemma-handoff-previous")
            if backup.exists():
                shutil.rmtree(backup)
            if destination.exists():
                os.replace(destination, backup)
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage, destination)
            except Exception:
                if backup.exists() and not destination.exists():
                    os.replace(backup, destination)
                raise
            finally:
                if backup.exists():
                    shutil.rmtree(backup)
    from .publishing import build_catalog, write_catalog

    catalog = build_catalog(repo_root=repo_root, output_root=destination_root)
    catalog_path = write_catalog(catalog, destination_root)
    return {"installed": installed, "bundle": destination, "catalog": catalog_path, "study_id": payload["study_id"]}

"""Immutable manifests for durable provider source snapshots."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4


SOURCE_MANIFEST_NAME = "source_manifest.json"
SOURCE_MANIFEST_SCHEMA_VERSION = 1
RAW_PAYLOAD_ROOT_ENV = "GEMMA_RAW_PAYLOAD_ROOT"


@dataclass(frozen=True)
class RawSourceAsset:
    path: str
    year: int | None
    url: str
    resource_id: str | None
    media_type: str
    bytes: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "year": self.year,
            "url": self.url,
            "resource_id": self.resource_id,
            "media_type": self.media_type,
            "bytes": self.bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class RawSourceSnapshot:
    """Validated immutable manifest plus the local root holding its payloads."""

    root: Path
    payload_root: Path
    provider: str
    dataset: str
    version: str
    license: str
    assets: tuple[RawSourceAsset, ...]
    manifest_path: Path

    def asset_path(self, asset: RawSourceAsset) -> Path:
        """Resolve one verified payload without leaking storage placement to runners."""
        return self.payload_root / asset.path


@dataclass(frozen=True)
class RawSnapshotStore:
    """One storage seam for a versioned raw manifest and its binary payloads.

    ``manifest_root`` remains inside the repository and is small enough to
    version. ``payload_root`` may be an external volume.  Assets stay relative
    to the payload root so manifests never contain host-specific paths.
    """

    manifest_root: Path
    payload_root: Path

    @property
    def manifest_path(self) -> Path:
        return self.manifest_root / SOURCE_MANIFEST_NAME

    def asset_path(self, asset: RawSourceAsset) -> Path:
        return self.payload_root / asset.path

    def load(self, *, verify: bool = True) -> RawSourceSnapshot:
        return load_source_manifest(
            self.manifest_root,
            payload_root=self.payload_root,
            verify=verify,
        )


def build_raw_source_asset(
    root: str | Path,
    path: str | Path,
    *,
    url: str,
    year: int | None = None,
    resource_id: str | None = None,
) -> RawSourceAsset:
    root = Path(root).resolve()
    path = Path(path).resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"Raw source asset escapes snapshot root: {path}") from exc
    if not path.is_file():
        raise FileNotFoundError(path)
    return RawSourceAsset(
        path=relative,
        year=year,
        url=str(url),
        resource_id=None if resource_id in (None, "") else str(resource_id),
        media_type=_media_type(path),
        bytes=path.stat().st_size,
        sha256=_sha256_file(path),
    )


def write_source_manifest(
    root: str | Path,
    *,
    provider: str,
    dataset: str,
    version: str,
    license_name: str,
    assets: Iterable[RawSourceAsset],
    payload_root: str | Path | None = None,
) -> Path:
    """Write an immutable source manifest, or accept an identical existing one."""
    root = Path(root)
    payload_root = root if payload_root is None else Path(payload_root)
    root.mkdir(parents=True, exist_ok=True)
    ordered = tuple(sorted(assets, key=lambda asset: (asset.year or -1, asset.path)))
    if not ordered:
        raise ValueError("Raw source snapshot needs at least one asset")
    _validate_assets(payload_root, ordered, verify=True)
    stable = {
        "schema_version": SOURCE_MANIFEST_SCHEMA_VERSION,
        "provider": str(provider),
        "dataset": str(dataset),
        "version": str(version),
        "license": str(license_name),
        "assets": [asset.as_dict() for asset in ordered],
    }
    path = root / SOURCE_MANIFEST_NAME
    if path.is_file():
        existing = _load_json(path)
        existing_stable = {key: value for key, value in existing.items() if key != "created_utc"}
        if existing_stable != stable:
            raise ValueError(
                f"Refusing to mutate immutable raw snapshot {root}; choose a new version"
            )
        return path
    payload = {**stable, "created_utc": datetime.now(timezone.utc).isoformat()}
    _atomic_json(path, payload)
    return path


def load_source_manifest(
    root: str | Path,
    *,
    payload_root: str | Path | None = None,
    verify: bool = True,
) -> RawSourceSnapshot:
    root = Path(root)
    payload_root = root if payload_root is None else Path(payload_root)
    path = root / SOURCE_MANIFEST_NAME
    payload = _load_json(path)
    if payload.get("schema_version") != SOURCE_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"Unsupported source manifest schema: {path}")
    raw_assets = payload.get("assets")
    if not isinstance(raw_assets, list):
        raise ValueError(f"Source manifest assets must be a list: {path}")
    assets = tuple(_asset_from_mapping(value, path) for value in raw_assets)
    _validate_assets(payload_root, assets, verify=verify)
    return RawSourceSnapshot(
        root=root,
        payload_root=payload_root,
        provider=_required_text(payload, "provider", path),
        dataset=_required_text(payload, "dataset", path),
        version=_required_text(payload, "version", path),
        license=_required_text(payload, "license", path),
        assets=assets,
        manifest_path=path,
    )


def _asset_from_mapping(value: Any, manifest_path: Path) -> RawSourceAsset:
    if not isinstance(value, Mapping):
        raise ValueError(f"Invalid source asset in {manifest_path}")
    try:
        year = value.get("year")
        return RawSourceAsset(
            path=str(value["path"]),
            year=None if year is None else int(year),
            url=str(value["url"]),
            resource_id=(
                None if value.get("resource_id") in (None, "") else str(value["resource_id"])
            ),
            media_type=str(value["media_type"]),
            bytes=int(value["bytes"]),
            sha256=str(value["sha256"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid source asset in {manifest_path}: {value!r}") from exc


def _validate_assets(root: Path, assets: tuple[RawSourceAsset, ...], *, verify: bool) -> None:
    seen_paths: set[str] = set()
    seen_years: set[int] = set()
    resolved_root = root.resolve()
    for asset in assets:
        if Path(asset.path).is_absolute() or ".." in Path(asset.path).parts:
            raise ValueError(f"Unsafe raw source asset path: {asset.path!r}")
        if asset.path in seen_paths:
            raise ValueError(f"Duplicate raw source asset path: {asset.path}")
        seen_paths.add(asset.path)
        if asset.year is not None:
            if asset.year in seen_years:
                raise ValueError(f"Duplicate raw source year: {asset.year}")
            seen_years.add(asset.year)
        path = (root / asset.path).resolve()
        try:
            path.relative_to(resolved_root)
        except ValueError as exc:
            raise ValueError(f"Raw source asset escapes snapshot: {asset.path}") from exc
        if not verify:
            continue
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size != asset.bytes:
            raise ValueError(f"Raw source asset size mismatch: {path}")
        if _sha256_file(path) != asset.sha256:
            raise ValueError(f"Raw source asset checksum mismatch: {path}")


def _required_text(payload: Mapping[str, Any], key: str, path: Path) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Source manifest is missing {key}: {path}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid source manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Source manifest must contain an object: {path}")
    return payload


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    staged = path.with_name(f".{path.name}.{uuid4().hex}.partial")
    staged.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(staged, path)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _media_type(path: Path) -> str:
    return {
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".json": "application/json",
        ".zip": "application/zip",
        ".geojson": "application/geo+json",
    }.get(path.suffix.lower(), "application/octet-stream")

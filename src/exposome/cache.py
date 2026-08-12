"""Validated, operation-scoped caches for provider-backed computations.

Cache entries are acceleration and resume state, never scientific source data.
Every reusable entry is tied to a complete execution identity and published
through a checksum-bearing sidecar.  The sidecar is replaced last, so a failed
rewrite cannot make an older complete generation unreadable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

import pandas as pd


CACHE_SCHEMA_VERSION = 1
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class CacheIdentity:
    """Immutable identity for one cacheable scientific operation."""

    layer_id: str
    operation: str
    parameters: Mapping[str, Any]
    spatial_fingerprint: str
    algorithm_version: str
    schema_version: int = CACHE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _validate_name(self.layer_id, "layer_id")
        _validate_name(self.operation, "operation")
        if not self.spatial_fingerprint:
            raise ValueError("spatial_fingerprint must be non-empty")
        if not self.algorithm_version:
            raise ValueError("algorithm_version must be non-empty")
        if self.schema_version != CACHE_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported cache identity schema_version: {self.schema_version}"
            )

    @property
    def payload(self) -> dict[str, Any]:
        """Return the canonical, persisted identity payload."""
        return {
            "schema_version": self.schema_version,
            "layer_id": self.layer_id,
            "operation": self.operation,
            "parameters": _normalise_json(self.parameters),
            "spatial_fingerprint": self.spatial_fingerprint,
            "algorithm_version": self.algorithm_version,
        }

    @property
    def digest(self) -> str:
        """Full SHA-256 digest; shortened forms are display-only."""
        return sha256(_canonical_json(self.payload).encode("utf-8")).hexdigest()

    @property
    def display_digest(self) -> str:
        return self.digest[:12]


@dataclass(frozen=True)
class CacheRecord:
    """Result of inspecting or reading one cache key."""

    hit: bool
    reason: str
    sidecar_path: Path
    data_path: Path | None = None
    frame: pd.DataFrame | None = None
    completed_keys: tuple[str, ...] = ()
    state: str | None = None


class CacheStore:
    """Filesystem implementation of validated CSV cache entries."""

    def __init__(self, root: str | Path, identity: CacheIdentity):
        self.root = Path(root)
        self.identity = identity

    @property
    def entry_dir(self) -> Path:
        return (
            self.root
            / f"v{CACHE_SCHEMA_VERSION}"
            / self.identity.operation
            / self.identity.digest
        )

    def sidecar_path(self, key: str) -> Path:
        _validate_name(key, "cache key")
        return self.entry_dir / f"{key}.cache.json"

    def inspect_csv(
        self,
        key: str,
        *,
        required_columns: Iterable[str] = (),
        expected_completed_keys: Iterable[str] | None = None,
        allow_partial: bool = False,
        read: bool = False,
    ) -> CacheRecord:
        """Validate identity, sidecar, payload checksum and completeness."""
        sidecar_path = self.sidecar_path(key)
        if not sidecar_path.is_file():
            return CacheRecord(False, "sidecar missing", sidecar_path)
        try:
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return CacheRecord(False, f"invalid sidecar: {exc}", sidecar_path)
        if not isinstance(sidecar, dict):
            return CacheRecord(False, "sidecar is not an object", sidecar_path)
        if sidecar.get("schema_version") != CACHE_SCHEMA_VERSION:
            return CacheRecord(False, "sidecar schema mismatch", sidecar_path)
        if sidecar.get("identity_digest") != self.identity.digest:
            return CacheRecord(False, "identity digest mismatch", sidecar_path)
        if sidecar.get("identity") != self.identity.payload:
            return CacheRecord(False, "identity payload mismatch", sidecar_path)

        state = str(sidecar.get("state") or "")
        if state not in {"complete", "partial"}:
            return CacheRecord(False, f"invalid cache state: {state!r}", sidecar_path)
        if state == "partial" and not allow_partial:
            return CacheRecord(
                False,
                "cache entry is partial",
                sidecar_path,
                completed_keys=_completed_keys(sidecar),
                state=state,
            )

        raw_name = sidecar.get("data_file")
        if not isinstance(raw_name, str) or not _SAFE_NAME.fullmatch(raw_name):
            return CacheRecord(False, "unsafe or missing data filename", sidecar_path)
        data_path = sidecar_path.parent / raw_name
        if data_path.parent.resolve() != self.entry_dir.resolve():
            return CacheRecord(False, "data path escapes cache entry", sidecar_path)
        if not data_path.is_file():
            return CacheRecord(False, "data file missing", sidecar_path, data_path)
        try:
            actual_bytes = data_path.stat().st_size
        except OSError as exc:
            return CacheRecord(False, f"cannot stat data file: {exc}", sidecar_path, data_path)
        if actual_bytes != sidecar.get("bytes"):
            return CacheRecord(False, "data size mismatch", sidecar_path, data_path)
        if _sha256_file(data_path) != sidecar.get("sha256"):
            return CacheRecord(False, "data checksum mismatch", sidecar_path, data_path)

        completed = _completed_keys(sidecar)
        if expected_completed_keys is not None:
            missing = sorted(set(map(str, expected_completed_keys)) - set(completed))
            if missing:
                return CacheRecord(
                    False,
                    f"completed keys missing: {missing}",
                    sidecar_path,
                    data_path,
                    completed_keys=completed,
                    state=state,
                )
        declared_columns = tuple(map(str, sidecar.get("columns", ())))
        missing_columns = sorted(set(map(str, required_columns)) - set(declared_columns))
        if missing_columns:
            return CacheRecord(
                False,
                f"required columns missing: {missing_columns}",
                sidecar_path,
                data_path,
                completed_keys=completed,
                state=state,
            )

        frame: pd.DataFrame | None = None
        if read:
            try:
                frame = pd.read_csv(data_path)
            except Exception as exc:  # pandas exposes multiple parser exceptions
                return CacheRecord(
                    False,
                    f"cannot read CSV: {exc}",
                    sidecar_path,
                    data_path,
                    completed_keys=completed,
                    state=state,
                )
            if tuple(map(str, frame.columns)) != declared_columns:
                return CacheRecord(
                    False,
                    "CSV columns do not match sidecar",
                    sidecar_path,
                    data_path,
                    completed_keys=completed,
                    state=state,
                )
            if len(frame) != sidecar.get("rows"):
                return CacheRecord(
                    False,
                    "CSV row count does not match sidecar",
                    sidecar_path,
                    data_path,
                    completed_keys=completed,
                    state=state,
                )
        return CacheRecord(
            True,
            "validated cache hit" if state == "complete" else "validated partial checkpoint",
            sidecar_path,
            data_path,
            frame,
            completed,
            state,
        )

    def load_csv(
        self,
        key: str,
        *,
        required_columns: Iterable[str] = (),
        expected_completed_keys: Iterable[str] | None = None,
    ) -> CacheRecord:
        return self.inspect_csv(
            key,
            required_columns=required_columns,
            expected_completed_keys=expected_completed_keys,
            read=True,
        )

    def load_checkpoint_csv(
        self,
        key: str,
        *,
        required_columns: Iterable[str] = (),
    ) -> CacheRecord:
        return self.inspect_csv(
            key,
            required_columns=required_columns,
            allow_partial=True,
            read=True,
        )

    def write_csv_atomic(
        self,
        key: str,
        frame: pd.DataFrame,
        *,
        completed_keys: Iterable[str] = (),
    ) -> CacheRecord:
        return self._publish_csv(key, frame, state="complete", completed_keys=completed_keys)

    def checkpoint_csv(
        self,
        key: str,
        frame: pd.DataFrame,
        *,
        completed_keys: Iterable[str],
    ) -> CacheRecord:
        return self._publish_csv(key, frame, state="partial", completed_keys=completed_keys)

    def _publish_csv(
        self,
        key: str,
        frame: pd.DataFrame,
        *,
        state: str,
        completed_keys: Iterable[str],
    ) -> CacheRecord:
        _validate_name(key, "cache key")
        if state not in {"complete", "partial"}:
            raise ValueError(f"Unsupported cache state: {state}")
        directory = self.entry_dir
        directory.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        staged = directory / f".{key}.{token}.csv.partial"
        frame.to_csv(staged, index=False)
        data_hash = _sha256_file(staged)
        data_name = f"{key}.{data_hash}.csv"
        data_path = directory / data_name
        if data_path.exists():
            staged.unlink()
        else:
            os.replace(staged, data_path)

        sidecar = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "identity_digest": self.identity.digest,
            "identity": self.identity.payload,
            "state": state,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "data_file": data_name,
            "media_type": "text/csv",
            "bytes": data_path.stat().st_size,
            "sha256": data_hash,
            "rows": len(frame),
            "columns": list(map(str, frame.columns)),
            "completed_keys": sorted(set(map(str, completed_keys))),
        }
        sidecar_path = self.sidecar_path(key)
        _atomic_json(sidecar_path, sidecar)
        self._remove_unreferenced_generations(key, keep=data_name)
        return self.inspect_csv(
            key,
            expected_completed_keys=completed_keys if state == "complete" else None,
            allow_partial=state == "partial",
            read=True,
        )

    def _remove_unreferenced_generations(self, key: str, *, keep: str) -> None:
        """Remove only old complete generations after publishing the new pointer."""
        for candidate in self.entry_dir.glob(f"{key}.*.csv"):
            if candidate.name != keep:
                candidate.unlink(missing_ok=True)


def spatial_fingerprint(
    frame: Any,
    *,
    id_column: str = "spatial_id",
) -> str:
    """Fingerprint ordered IDs, CRS and geometry without source-path assumptions."""
    if id_column not in frame.columns:
        raise ValueError(f"Spatial frame is missing {id_column!r}")
    if "geometry" not in frame.columns:
        raise ValueError("Spatial frame is missing geometry")
    if frame[id_column].astype(str).duplicated().any():
        raise ValueError(f"Spatial frame has duplicate {id_column!r} values")
    crs = getattr(frame, "crs", None)
    records = []
    ordered = frame.assign(_cache_id=frame[id_column].astype(str)).sort_values("_cache_id")
    for cache_id, geometry in ordered[["_cache_id", "geometry"]].itertuples(
        index=False, name=None
    ):
        records.append(
            {
                "spatial_id": cache_id,
                "geometry_wkb": None if geometry is None else geometry.wkb_hex,
            }
        )
    payload = {"crs": None if crs is None else str(crs), "records": records}
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.{uuid4().hex}.partial")
    staged.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(staged, path)


def _completed_keys(payload: Mapping[str, Any]) -> tuple[str, ...]:
    raw = payload.get("completed_keys", ())
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    return tuple(sorted(set(map(str, raw))))


def _normalise_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalise_json(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalise_json(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_normalise_json(item) for item in value), key=_canonical_json)
    if isinstance(value, Path):
        return value.as_posix()
    if hasattr(value, "item") and callable(value.item):
        return _normalise_json(value.item())
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Cache identity contains unsupported value: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_name(value: str, label: str) -> None:
    if not isinstance(value, str) or not _SAFE_NAME.fullmatch(value):
        raise ValueError(f"{label} must match {_SAFE_NAME.pattern}: {value!r}")

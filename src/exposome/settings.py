"""Strict, composable settings for config-driven exposome studies.

This is the replacement for inheriting one city's YAML configuration from
another city.  Layer defaults are shared because the provider is shared;
country, location, and study YAML files only describe deliberate overrides.

The returned legacy mapping is temporary.  New runners should consume the
typed :class:`ResolvedSettings` object or their layer mapping directly.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

from .studies import StudyConfigError, StudyContext


_LAYER_FILE_KEYS = frozenset({"schema_version", "id", "settings"})
_COUNTRY_FILE_KEYS = frozenset({"schema_version", "country_code", "overrides"})


@dataclass(frozen=True)
class ResolvedSettings:
    """Immutable record of settings composed for one study.

    ``values`` remains a mapping during the migration because existing layer
    implementations expect nested dictionaries.  :meth:`legacy_mapping`
    returns a private deep copy, preventing old runners from mutating the
    resolved source of truth.
    """

    study_id: str
    country_code: str
    values: Mapping[str, Any]
    sources: tuple[Path, ...]
    fingerprint: str

    def legacy_mapping(self) -> dict[str, Any]:
        return deepcopy(dict(self.values))

    def layer(self, layer_id: str) -> Mapping[str, Any]:
        value = self.values.get(layer_id)
        if not isinstance(value, Mapping):
            raise StudyConfigError(
                f"Resolved settings for {self.study_id!r} have no mapping for layer {layer_id!r}"
            )
        return value


def resolve_settings(context: StudyContext) -> ResolvedSettings:
    """Compose layer defaults, country, location and study overrides.

    Precedence is fixed and intentionally narrow:

    ``layer defaults < country overrides < location overrides < study overrides``.

    This function never treats a city config as a shared default.  The old
    Santiago YAML is consumed only by the separate legacy adapter in
    :mod:`exposome.config` while its settings are being extracted.
    """

    root = context.repo_root
    values: dict[str, Any] = {}
    sources: list[Path] = []

    layer_dir = root / "config" / "layers"
    for path in sorted(layer_dir.glob("*.yaml")):
        layer_id, settings = _load_layer_file(path)
        values[layer_id] = settings
        sources.append(path)

    if not values:
        raise StudyConfigError(
            f"No layer defaults found in {layer_dir}; run the config migration first"
        )

    country_path = root / "config" / "countries" / f"{context.country_code.lower()}.yaml"
    if country_path.exists():
        country_code, overrides = _load_country_file(country_path)
        if country_code != context.country_code:
            raise StudyConfigError(
                f"Country settings {country_path} declare {country_code}, expected {context.country_code}"
            )
        _deep_merge(values, overrides)
        sources.append(country_path)

    for owner, raw, path in (
        ("location", context.location.raw, context.location.config_path),
        ("study", context.study.raw, context.study.config_path),
    ):
        overrides = raw.get("layer_overrides", {})
        if overrides in (None, {}):
            continue
        if not isinstance(overrides, Mapping):
            raise StudyConfigError(f"{owner} layer_overrides must be a YAML mapping: {path}")
        _deep_merge(values, dict(overrides))
        sources.append(path)

    canonical = json.dumps(values, sort_keys=True, ensure_ascii=False, default=str)
    return ResolvedSettings(
        study_id=context.study.id,
        country_code=context.country_code,
        values=values,
        sources=tuple(sources),
        fingerprint=sha256(canonical.encode("utf-8")).hexdigest(),
    )


def _load_layer_file(path: Path) -> tuple[str, dict[str, Any]]:
    raw = _read_mapping(path)
    _validate_exact_keys(raw, _LAYER_FILE_KEYS, path)
    if raw.get("schema_version") != 1:
        raise StudyConfigError(f"Unsupported layer settings schema_version in {path}")
    layer_id = str(raw.get("id") or "").strip()
    if not layer_id:
        raise StudyConfigError(f"Layer settings are missing id: {path}")
    if path.stem != layer_id:
        raise StudyConfigError(f"Layer settings id must match filename: {path}")
    settings = raw.get("settings")
    if not isinstance(settings, Mapping):
        raise StudyConfigError(f"Layer settings must contain a mapping: {path}")
    return layer_id, deepcopy(dict(settings))


def _load_country_file(path: Path) -> tuple[str, dict[str, Any]]:
    raw = _read_mapping(path)
    _validate_exact_keys(raw, _COUNTRY_FILE_KEYS, path)
    if raw.get("schema_version") != 1:
        raise StudyConfigError(f"Unsupported country settings schema_version in {path}")
    country_code = str(raw.get("country_code") or "").strip().upper()
    if len(country_code) != 2:
        raise StudyConfigError(f"Country settings require ISO-2 country_code: {path}")
    overrides = raw.get("overrides", {})
    if not isinstance(overrides, Mapping):
        raise StudyConfigError(f"Country overrides must be a mapping: {path}")
    return country_code, deepcopy(dict(overrides))


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise StudyConfigError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise StudyConfigError(f"Configuration must be a YAML mapping: {path}")
    return raw


def _validate_exact_keys(raw: Mapping[str, Any], expected: frozenset[str], path: Path) -> None:
    unknown = sorted(set(raw).difference(expected))
    missing = sorted(expected.difference(raw))
    if unknown or missing:
        details = []
        if unknown:
            details.append(f"unknown keys: {unknown}")
        if missing:
            details.append(f"missing keys: {missing}")
        raise StudyConfigError(f"Invalid settings schema in {path}: {'; '.join(details)}")


def _deep_merge(target: dict[str, Any], updates: Mapping[str, Any]) -> None:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = deepcopy(value)

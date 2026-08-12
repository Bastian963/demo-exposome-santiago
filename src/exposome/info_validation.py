"""Validate the info-panel contract for the registry and published bundles.

Two independent gates:

* :func:`validate_registry` — ``config/layer_info`` covers the layer catalog,
  every declared methodology doc exists, and webapp keys match the palette.
* :func:`validate_bundle` — a published bundle can render all five info tabs
  (FUENTE/ESPECIFICACIONES/METODOLOGIA/CITACION/DESCARGAR) for every exposome
  the study actually carries, replicating the browser's lookup chain.

Both return ``(errors, warnings)``; the publish CLI treats errors as fatal.
An absent DOI warns only until it is either supplied or explicitly curated as
``doi_status: not_assigned``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import yaml

from .layer_info import load_layer_info_registry, resolve_layer_info

# Fields renderExposomeInfoTabs() requires non-empty to fill FUENTE and
# ESPECIFICACIONES (webapp/src/main.js).
REQUIRED_SOURCE_FIELDS = (
    "name",
    "url",
    "license",
    "spatial_resolution",
    "temporal_coverage",
    "validation",
)

# Palette exposomes that intentionally have no registry entry.
PALETTE_EXCEPTIONS: frozenset[str] = frozenset()


def _exposome_data_id(exposome_id: str) -> str:
    """Mirror exposomeDataId() in webapp/src/main.js."""
    return "air_quality_pm25" if exposome_id == "pm25" else exposome_id


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_registry(repo_root: str | Path) -> tuple[list[str], list[str]]:
    root = Path(repo_root)
    errors: list[str] = []
    warnings: list[str] = []
    registry = load_layer_info_registry(root)

    catalog_path = root / "config" / "layers.yaml"
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    catalog_layers = set((catalog.get("layers") or {}).keys())
    for layer_id in sorted(catalog_layers):
        if layer_id not in registry:
            errors.append(f"catalog layer {layer_id!r} has no config/layer_info entry")

    palette_path = root / "webapp" / "public" / "palette.json"
    palette = _load_json(palette_path) if palette_path.exists() else {}
    palette_exposomes: Mapping[str, Any] = palette.get("exposomes", {})

    claimed_keys: dict[str, str] = {}
    for layer_id, entry in registry.items():
        for key in entry.get("webapp_keys", []):
            if key in claimed_keys and claimed_keys[key] != layer_id:
                errors.append(
                    f"webapp key {key!r} claimed by both {claimed_keys[key]!r} and {layer_id!r}"
                )
            claimed_keys[key] = layer_id
            if palette_exposomes and key not in palette_exposomes:
                errors.append(
                    f"layer {layer_id!r} declares webapp key {key!r} missing from palette.json"
                )
        scopes = [(None, None)]
        scopes += [(code, None) for code in (entry.get("countries") or {})]
        scopes += [(None, study) for study in (entry.get("studies") or {})]
        for country_code, study_id in scopes:
            info = resolve_layer_info(entry, country_code=country_code, study_id=study_id)
            doc_ref = info.get("methodology_doc")
            if doc_ref:
                doc = root / str(doc_ref)
                if not doc.is_file():
                    errors.append(
                        f"layer {layer_id!r} declares missing methodology_doc: {doc_ref}"
                    )
            else:
                warnings.append(f"layer {layer_id!r} declares no methodology_doc")
            name = (info.get("source") or {}).get("name", "")
            if str(name).startswith("{"):
                errors.append(f"layer {layer_id!r} source.name looks like a stringified dict")
            citation = info.get("citation") or {}
            if not citation.get("doi") and citation.get("doi_status") != "not_assigned":
                warnings.append(f"layer {layer_id!r} has no DOI (citation.doi)")

    for exposome_id, expo in palette_exposomes.items():
        if expo.get("parent") or expo.get("status") == "coming_soon":
            continue
        candidates = [
            exposome_id,
            expo.get("source_id") or expo.get("parent") or exposome_id,
            _exposome_data_id(exposome_id),
        ]
        if exposome_id in PALETTE_EXCEPTIONS:
            continue
        if not any(key in claimed_keys or key in registry for key in candidates):
            errors.append(
                f"palette exposome {exposome_id!r} resolves to no layer_info entry "
                f"(tried {candidates})"
            )
    return errors, warnings


def published_bundles(repo_root: str | Path, output_root: str | Path | None = None) -> list[Path]:
    root = Path(repo_root)
    data_root = Path(output_root) if output_root else root / "webapp" / "public" / "data"
    return sorted(
        manifest.parent for manifest in data_root.glob("v1/*/*/*/manifest.json")
    )


def validate_bundle(bundle: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    label = bundle.name
    try:
        manifest = _load_json(bundle / "manifest.json")
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{label}: unreadable manifest.json ({exc})"], warnings

    sources_path = bundle / "sources.json"
    if not sources_path.exists():
        errors.append(f"{label}: missing sources.json")
        source_map: Mapping[str, Any] = {}
    else:
        payload = _load_json(sources_path)
        source_map = payload.get("sources", payload)

    palette_path = bundle / "palette.json"
    palette_exposomes: Mapping[str, Any] = {}
    if palette_path.exists():
        palette_exposomes = _load_json(palette_path).get("exposomes", {})

    columns = set(manifest.get("columns") or [])
    mode = manifest.get("mode", "aggregate")
    methodology_dir = bundle / "methodology"

    def check_entry(display_id: str, entry: Mapping[str, Any] | None) -> None:
        if entry is None:
            errors.append(f"{label}: exposome {display_id!r} has no sources entry")
            return
        for field in REQUIRED_SOURCE_FIELDS:
            if not str(entry.get(field) or "").strip():
                errors.append(
                    f"{label}: exposome {display_id!r} sources entry missing {field!r}"
                )
        if str(entry.get("name", "")).startswith("{"):
            errors.append(f"{label}: exposome {display_id!r} name is a stringified dict")
        if not entry.get("doi") and entry.get("doi_status") != "not_assigned":
            warnings.append(f"{label}: exposome {display_id!r} has no DOI")

    if mode == "native":
        for layer_id in (manifest.get("layers") or {}):
            check_entry(layer_id, source_map.get(layer_id))
            if not (methodology_dir / f"{layer_id}.json").is_file():
                errors.append(f"{label}: native layer {layer_id!r} missing methodology JSON")
    else:
        child_columns: dict[str, list[str]] = {}
        for expo in palette_exposomes.values():
            parent = expo.get("parent")
            if parent and expo.get("column"):
                child_columns.setdefault(parent, []).append(expo["column"])
        for exposome_id, expo in palette_exposomes.items():
            if expo.get("parent") or expo.get("status") == "coming_soon":
                continue
            column = expo.get("column")
            if columns:
                if column:
                    if column not in columns:
                        continue  # this study does not carry the exposome
                else:
                    # column-less group: carried only if a child column is
                    children = child_columns.get(exposome_id, [])
                    if not any(child in columns for child in children):
                        continue
            source_id = expo.get("source_id") or expo.get("parent") or exposome_id
            entry = (
                source_map.get(exposome_id)
                or source_map.get(source_id)
                or source_map.get(_exposome_data_id(exposome_id))
            )
            check_entry(exposome_id, entry)
            methodology_id = _exposome_data_id(
                expo.get("methodology_id") or expo.get("parent") or exposome_id
            )
            candidates = [methodology_id, exposome_id]
            if entry and entry.get("layer_id"):
                candidates.append(str(entry["layer_id"]))
            if not any((methodology_dir / f"{cand}.json").is_file() for cand in candidates):
                errors.append(
                    f"{label}: exposome {exposome_id!r} missing methodology JSON "
                    f"(tried {candidates})"
                )
        for asset_key in ("master_geojson", "master_csv"):
            asset = (manifest.get("assets") or {}).get(asset_key)
            if not asset:
                errors.append(f"{label}: manifest missing {asset_key} asset (DESCARGAR)")
            elif not (bundle / asset["path"]).is_file():
                errors.append(f"{label}: {asset_key} asset not on disk: {asset['path']}")

    spatial_indicators = manifest.get("spatial_indicators") or {}
    records = (
        spatial_indicators.values()
        if isinstance(spatial_indicators, Mapping)
        else spatial_indicators
    )
    for record in records:
        if not isinstance(record, Mapping):
            continue
        detail = record.get("detail") or {}
        detail_path = detail.get("path")
        if detail_path and not (bundle / detail_path).is_file():
            errors.append(f"{label}: spatial indicator detail missing on disk: {detail_path}")
    return errors, warnings

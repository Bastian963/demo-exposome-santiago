"""Study release facade backed exclusively by the strict v2 contract."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_contract import (
    RELEASE_MANIFEST_NAME,
    RELEASE_MANIFEST_SCHEMA_VERSION,
    load_layer_bundle,
    load_release,
    write_study_release,
)


SCHEMA_VERSION = RELEASE_MANIFEST_SCHEMA_VERSION


def canonical_enabled_layers(context: Any) -> tuple[str, ...]:
    from .layers import load_layer_catalog

    catalog = load_layer_catalog()
    return tuple(
        dict.fromkeys(catalog.resolve_id(layer_id) for layer_id in context.enabled_layers)
    )


def write_release_manifest(context: Any, master: Any) -> Path:
    """Write a complete v2 release from verified bundles and master assets."""
    expected = canonical_enabled_layers(context)
    bundles = [
        load_layer_bundle(context, layer_id, verify=True)
        for layer_id in expected
    ]
    role_map = {
        "csv": "master_csv",
        "geojson": "master_geojson",
        "coverage": "master_coverage",
        "metadata": "master_metadata",
    }
    assets = [
        (role_map.get(str(role), str(role)), Path(path))
        for role, path in getattr(master, "paths", {}).items()
        if Path(path).is_file()
    ]
    publication_roots = (
        "profiles",
        "profiles_meta",
        "subcomuna",
        "annual",
        "detail",
        "analysis/web",
    )
    for directory in publication_roots:
        root = Path(context.paths.processed) / directory
        if not root.is_dir():
            continue
        for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            if path.name.startswith("._"):
                continue  # macOS AppleDouble sidecar (NFS/SMB mounts), never a real asset
            relative = path.relative_to(context.paths.processed).as_posix()
            assets.append((f"publication/{relative}", path))
    for name in ("zipcodes.json", "location_profile_axes.json"):
        path = Path(context.paths.processed) / name
        if path.is_file():
            assets.append((f"publication/{name}", path))
    return write_study_release(
        context,
        bundles,
        assets,
        expected_layer_ids=expected,
    )


__all__ = [
    "RELEASE_MANIFEST_NAME",
    "SCHEMA_VERSION",
    "canonical_enabled_layers",
    "load_release",
    "write_release_manifest",
]

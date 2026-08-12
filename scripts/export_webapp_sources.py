"""Export the legacy-root sources.json from the layer-info registry.

The per-study bundles get their sources.json from ``exposome publish``; this
flat, webapp-key-keyed copy exists only for the pre-manifest fallback in
``webapp/src/data-repository.js``.  The content lives in
``config/layer_info/<layer_id>.yaml`` — edit there, never here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.layer_info import (  # noqa: E402
    build_sources_entry,
    load_layer_info_registry,
    resolve_layer_info,
)

DST = REPO_ROOT / "webapp" / "public" / "data" / "sources.json"


def build_root_sources(country_code: str = "CL") -> dict[str, dict]:
    registry = load_layer_info_registry(REPO_ROOT)
    sources: dict[str, dict] = {}
    for layer_id, entry in registry.items():
        info = resolve_layer_info(entry, country_code=country_code)
        record = build_sources_entry(info)
        for key in info.get("webapp_keys", []):
            sources[key] = record
    return sources


def main() -> None:
    DST.parent.mkdir(parents=True, exist_ok=True)
    sources = build_root_sources()
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2)
    print(f"  Wrote: {DST} ({len(sources)} sources)")


if __name__ == "__main__":
    main()

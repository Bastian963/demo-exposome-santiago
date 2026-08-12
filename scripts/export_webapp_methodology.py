"""Export legacy-root methodology JSON from the layer-info registry.

The per-study bundles get their methodology/ from ``exposome publish``; these
root copies exist only for the pre-manifest fallback in
``webapp/src/data-repository.js``.  Each layer's ``methodology_doc`` is
declared in ``config/layer_info/<layer_id>.yaml`` — edit there, never here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.layer_info import (  # noqa: E402
    build_methodology_json,
    load_layer_info_registry,
    resolve_layer_info,
)

DST_DIR = REPO_ROOT / "webapp" / "public" / "data" / "methodology"


def main(country_code: str = "CL") -> None:
    DST_DIR.mkdir(parents=True, exist_ok=True)
    registry = load_layer_info_registry(REPO_ROOT)
    for layer_id, entry in registry.items():
        info = resolve_layer_info(entry, country_code=country_code)
        payload = build_methodology_json(layer_id, info, REPO_ROOT)
        if payload is None:
            print(f"  SKIP: {layer_id} declares no methodology_doc")
            continue
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        names = [layer_id] + [k for k in info.get("webapp_keys", []) if k != layer_id]
        for name in names:
            dst = DST_DIR / f"{name}.json"
            dst.write_text(text, encoding="utf-8")
        print(f"  Wrote: {layer_id} -> {', '.join(names)} ({len(payload['raw'])} chars)")


if __name__ == "__main__":
    main()

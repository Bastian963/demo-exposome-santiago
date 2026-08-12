"""Compatibility export derived from the configured study catalog.

New deployments should use ``publish_webapp.py``; this file only preserves the
legacy ``cities.json`` asset for older builds.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.publishing import build_catalog


def main() -> None:
    output = REPO_ROOT / "webapp" / "public" / "data"
    catalog = build_catalog(repo_root=REPO_ROOT, output_root=output)
    payload = {
        "created_utc": catalog["created_utc"],
        "default_center": [-65, -25],
        "default_zoom": 3,
        "global_center": [-65, -25],
        "global_zoom": 3,
        "continents": catalog["continents"],
        "cities": catalog["cities"],
    }
    destination = output / "cities.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {destination} ({len(payload['cities'])} available cities)")


if __name__ == "__main__":
    main()

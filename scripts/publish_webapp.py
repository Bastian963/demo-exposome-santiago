"""Publish one or more configured studies for the web application."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.publishing import build_catalog, publish_study, write_catalog
from exposome.studies import load_study


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", action="append", help="Study id; repeat for multiple studies")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "webapp" / "public" / "data",
        help="Web data root (default: webapp/public/data)",
    )
    parser.add_argument("--version", default="v1")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    study_ids = args.study or ["santiago_communes"]
    for study_id in study_ids:
        result = publish_study(
            load_study(study_id),
            output_root=args.output,
            version=args.version,
            clean=args.clean,
        )
        print(f"published {result.study_id}: {result.path}")
    catalog = build_catalog(
        repo_root=REPO_ROOT, output_root=args.output, version=args.version
    )
    catalog_path = write_catalog(catalog, args.output)
    print(f"catalog: {catalog_path}")
    print(json.dumps(catalog, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

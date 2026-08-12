"""Export per-unit profile JSONs for any study built on the general pipeline.

Each profile is a JSON file at
``data/processed/<country>/<location>/<study>/profiles/{slug}.json``:

    {"name": ..., "slug": ..., "indicators": {<numeric master columns>}}

This is the minimal contract `showSidePanelForProfile` (webapp/src/main.js)
needs to open the side panel on click; `cluster`/`ebi`/`lisa_quadrant`/
`timeseries` are optional and degrade to "-" when absent.

Unlike the Santiago-only legacy `export_webapp_profiles.py` (which reads
272 hardcoded Santiago sidecar CSVs), this script is study-aware and only
needs `master.csv`. Run it for any study before `publish_webapp.py`, which
copies `processed/<study>/profiles/` into the web bundle
(`_copy_aggregate_assets` in src/exposome/publishing.py).

Slug parity is load-bearing: this uses the same `slugify` as
src/exposome/publishing.py, which stamps `properties.slug` on master.geojson
features at publish time. If the two ever diverge, clicks 404.
"""
from __future__ import annotations

import argparse
import json
import numbers
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.publishing import slugify  # noqa: E402
from exposome.studies import load_study  # noqa: E402
from exposome.temporal_exposomes import completed_annual_products  # noqa: E402

NON_INDICATOR_COLUMNS = {"spatial_id", "spatial_name", "name", "slug", "geometry"}


def _round(value: object, decimals: int = 3) -> object:
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        as_float = float(value)
        if as_float != as_float:  # NaN
            return None
        return round(as_float, decimals)
    return value


def export_profiles(study_id: str) -> Path:
    context = load_study(study_id)
    master_csv = context.paths.processed / "master.csv"
    if not master_csv.exists():
        raise FileNotFoundError(f"{master_csv} not found; run scripts/run_exposome.py --study {study_id} first")
    # Spatial identifiers are keys, not numbers.  Reading them with pandas'
    # default inference strips significant leading zeroes (for example
    # Medellin commune ``01``), which prevents annual products from joining to
    # otherwise valid profiles.
    master = pd.read_csv(master_csv, dtype={"spatial_id": str})
    palette_path = REPO_ROOT / "webapp" / "public" / "palette.json"
    palette = json.loads(palette_path.read_text(encoding="utf-8")) if palette_path.exists() else {}
    temporal_specs = {
        layer_id: definition.get("year_columns", {})
        for layer_id, definition in palette.get("exposomes", {}).items()
        if isinstance(definition.get("year_columns"), dict)
    }
    annual_by_spatial_id: dict[str, dict[str, list[dict[str, object]]]] = {}
    for spec, year, _manifest, annual_path in completed_annual_products(context):
        if not spec.indicators:
            continue
        annual = pd.read_csv(annual_path, dtype={"spatial_id": str})
        for indicator in spec.indicators:
            if indicator.value_column not in annual.columns:
                raise ValueError(
                    f"{annual_path} lacks temporal value column {indicator.value_column!r}"
                )
            for _, annual_row in annual.iterrows():
                value = _round(annual_row[indicator.value_column])
                if value is None:
                    continue
                series = annual_by_spatial_id.setdefault(
                    str(annual_row["spatial_id"]), {}
                ).setdefault(indicator.exposome_id, [])
                series.append({"year": str(year), "value": value})
    for by_indicator in annual_by_spatial_id.values():
        for points in by_indicator.values():
            points.sort(key=lambda point: str(point["year"]))

    profiles_dir = context.paths.processed / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)

    indicator_columns = [c for c in master.columns if c not in NON_INDICATOR_COLUMNS]
    written = 0
    slugs: set[str] = set()
    for _, row in master.iterrows():
        name = str(row["name"])
        slug = slugify(name)
        if slug in slugs:
            raise ValueError(f"Duplicate slug '{slug}' for study {study_id} (name={name!r})")
        slugs.add(slug)
        indicators = {col: _round(row[col]) for col in indicator_columns}
        timeseries = {}
        for layer_id, columns in temporal_specs.items():
            points = [
                {"year": str(period), "value": _round(row[column])}
                for period, column in columns.items()
                if column in master.columns and _round(row[column]) is not None
            ]
            if points:
                timeseries[layer_id] = points
        spatial_id = str(row["spatial_id"]) if "spatial_id" in master.columns else ""
        for exposome_id, points in annual_by_spatial_id.get(spatial_id, {}).items():
            timeseries[exposome_id] = points
        profile = {
            "name": name,
            "slug": slug,
            "indicators": indicators,
            "timeseries": timeseries,
        }
        (profiles_dir / f"{slug}.json").write_text(
            json.dumps(profile, ensure_ascii=False), encoding="utf-8"
        )
        written += 1

    print(f"{study_id}: wrote {written} profiles -> {profiles_dir.relative_to(REPO_ROOT)}")
    return profiles_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True, action="append", help="Study id; repeatable.")
    args = parser.parse_args()
    for study_id in args.study:
        export_profiles(study_id)


if __name__ == "__main__":
    main()

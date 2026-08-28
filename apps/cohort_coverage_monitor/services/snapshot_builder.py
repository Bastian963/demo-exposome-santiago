import json
from datetime import datetime, timezone
import sys
from pathlib import Path

# Need to ensure we can import the src.exposome.cohort_reporting module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from apps.cohort_coverage_monitor.config import (
    REGISTRY_PATH, 
    RAW_PARTICIPANTS_PATH, 
    CATALOG_PATH, 
    MANIFESTS_BASE_PATH,
    SNAPSHOT_PATH
)
from apps.cohort_coverage_monitor.services.catalog_reader import read_catalog_exposomes
from apps.cohort_coverage_monitor.domain.models import PublicSnapshot, CitySnapshot
from src.exposome.cohort_reporting import build_cohort_report
from src.exposome.studies import load_location

# Cities with neither a published manifest nor a config/locations/<iso2>/<slug>.yaml
# yet (still in the "preparing" queue per docs/cohort_latam_week.md). Approximate
# metro centroids only, for placing a marker on the coverage map -- not derived
# from participant data.
FALLBACK_CENTROIDS = {
    "belo_horizonte": (-19.92, -43.94),
    "arequipa": (-16.41, -71.54),
    "cartagena": (10.39, -75.51),
    "barranquilla": (10.96, -74.80),
    "cali": (3.45, -76.53),
}


def _resolve_center(slug: str) -> list[float]:
    """[lon, lat] for a city missing from the catalog/manifest lookup."""
    try:
        location = load_location(slug)
        bbox = location.bbox
        return [(bbox.west + bbox.east) / 2, (bbox.south + bbox.north) / 2]
    except FileNotFoundError:
        pass
    if slug in FALLBACK_CENTROIDS:
        lat, lon = FALLBACK_CENTROIDS[slug]
        return [lon, lat]
    return [0.0, 0.0]


def build_snapshot():
    print(f"Loading base cohort report...")
    report = build_cohort_report(
        registry_path=REGISTRY_PATH,
        raw_path=RAW_PARTICIPANTS_PATH,
        catalog_path=CATALOG_PATH
    )

    print("Reading catalog and manifests for exposomes...")
    exposome_data = read_catalog_exposomes(CATALOG_PATH, MANIFESTS_BASE_PATH)

    cities = []
    for row in report.rows:
        slug = row.get("catalog_slug", row.get("id"))
        exp_info = exposome_data.get(slug, {
            "available_count": 0,
            "expected_count": 0,
            "available_list": [],
            "center": [0.0, 0.0]
        })
        if exp_info["center"] == [0.0, 0.0]:
            exp_info = {**exp_info, "center": _resolve_center(row["id"])}

        cities.append(CitySnapshot(
            id=row["id"],
            metro=row["metro"],
            country=row["country"],
            lat=exp_info["center"][1],
            lon=exp_info["center"][0],
            participants=row["n"],
            pct_total=row["pct_total"],
            status=row["status"],
            publication_tier=row["publication_tier"],
            available_exposomes_count=exp_info["available_count"],
            expected_exposomes_count=exp_info["expected_count"],
            available_exposomes=exp_info["available_list"],
            next_action=row.get("next_action"),
            rank=row["rank"]
        ))
    
    snapshot = PublicSnapshot(
        total_participants=report.total_participants,
        priority_participants=report.priority_participants,
        minimum_participants=report.minimum_participants,
        updated_at=report.updated_at,
        catalog_created_utc=report.catalog_created_utc,
        snapshot_generated_at=datetime.now(timezone.utc).isoformat(),
        cities=cities
    )

    # Ensure parent dir exists
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        f.write(snapshot.to_json(indent=2))

    print(f"Snapshot successfully written to {SNAPSHOT_PATH}")
    print(f"Included {len(cities)} cities with {report.total_participants} total participants.")

if __name__ == "__main__":
    try:
        build_snapshot()
    except Exception as e:
        print(f"Failed to build snapshot: {e}")
        sys.exit(1)

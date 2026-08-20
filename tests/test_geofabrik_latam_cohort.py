from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_geofabrik_latam_cohort import load_inventory, status_for  # noqa: E402


def inventory() -> dict:
    return {
        "schema_version": 1,
        "campaign": "test",
        "version": "260819",
        "provider": "geofabrik",
        "dataset": "osm-regional-extract",
        "supported_layers": ["greenspace_access", "food_environment", "healthcare", "social_infrastructure"],
        "snapshots": [{
            "id": "peru", "label": "Perú", "source_path": "south-america",
            "page_url": "https://download.geofabrik.de/south-america/peru.html",
            "pbf_url": "https://download.geofabrik.de/south-america/peru-260819.osm.pbf",
            "filename": "peru.osm.pbf", "countries": ["PE"], "covers": ["lima"],
        }],
    }


class GeofabrikLatamCohortTests(unittest.TestCase):
    def write_inventory(self, root: Path, payload: dict) -> dict:
        config = root / "config/operations/geofabrik_latam_cohort.yaml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(yaml.safe_dump(payload), encoding="utf-8")
        return load_inventory(config)

    def test_inventory_rejects_walkability_and_duplicate_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            payload = inventory()
            payload["supported_layers"].append("walkability")
            with self.assertRaisesRegex(ValueError, "four tag-based"):
                self.write_inventory(Path(temp), payload)
            payload = inventory()
            payload["snapshots"].append(dict(payload["snapshots"][0]))
            with self.assertRaisesRegex(ValueError, "duplicate snapshot"):
                self.write_inventory(Path(temp), payload)

    def test_status_requires_a_matching_manifest_and_optional_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            loaded = self.write_inventory(root, inventory())
            snapshot = loaded["snapshots"][0]
            self.assertEqual(status_for(root, loaded, snapshot, verify_hash=False)[0], "missing")
            pbf = root / "data/raw/geofabrik/peru/260819/peru.osm.pbf"
            pbf.parent.mkdir(parents=True)
            pbf.write_bytes(b"valid pbf fixture")
            self.assertEqual(status_for(root, loaded, snapshot, verify_hash=False)[0], "unfrozen")
            manifest = pbf.parent / "source_manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": 1, "provider": "geofabrik", "dataset": "osm-regional-extract", "version": "260819",
                "assets": [{"path": "peru.osm.pbf", "resource_id": "peru", "url": snapshot["page_url"],
                            "bytes": pbf.stat().st_size, "sha256": hashlib.sha256(pbf.read_bytes()).hexdigest()}],
            }), encoding="utf-8")
            self.assertEqual(status_for(root, loaded, snapshot, verify_hash=True)[0], "ready")
            pbf.write_bytes(b"changed")
            self.assertEqual(status_for(root, loaded, snapshot, verify_hash=True)[0], "invalid")


if __name__ == "__main__":
    unittest.main()

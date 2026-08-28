import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from apps.cohort_coverage_monitor.services.snapshot_loader import load_snapshot
from apps.cohort_coverage_monitor.domain.models import PublicSnapshot

class TestSnapshotLoader(unittest.TestCase):
    def test_load_snapshot(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            data = {
                "total_participants": 1000,
                "priority_participants": 500,
                "minimum_participants": 25,
                "updated_at": "2026-08-27",
                "snapshot_generated_at": "2026-08-27T10:00:00",
                "cities": [],
                "catalog_created_utc": None
            }
            json.dump(data, f)
            temp_path = f.name
            
        with patch("apps.cohort_coverage_monitor.services.snapshot_loader.SNAPSHOT_PATH", Path(temp_path)):
            snapshot = load_snapshot()
            self.assertIsInstance(snapshot, PublicSnapshot)
            self.assertEqual(snapshot.total_participants, 1000)
            self.assertEqual(len(snapshot.cities), 0)

if __name__ == "__main__":
    unittest.main()

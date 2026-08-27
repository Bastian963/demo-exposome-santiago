import unittest
from unittest.mock import patch, MagicMock
from apps.cohort_coverage_monitor.services.snapshot_builder import build_snapshot

class TestSnapshotBuilder(unittest.TestCase):
    
    @patch("apps.cohort_coverage_monitor.services.snapshot_builder.build_cohort_report")
    @patch("apps.cohort_coverage_monitor.services.snapshot_builder.read_catalog_exposomes")
    @patch("apps.cohort_coverage_monitor.services.snapshot_builder.open")
    @patch("apps.cohort_coverage_monitor.services.snapshot_builder.SNAPSHOT_PATH")
    def test_build_snapshot(self, mock_path, mock_open, mock_read_catalog, mock_build_cohort):
        mock_report = MagicMock()
        mock_report.rows = []
        mock_report.total_participants = 100
        mock_report.priority_participants = 100
        mock_report.minimum_participants = 25
        mock_report.updated_at = "2026-08-27"
        mock_report.catalog_created_utc = None
        
        mock_build_cohort.return_value = mock_report
        mock_read_catalog.return_value = {}
        
        # Run builder
        build_snapshot()
        
        # Verify it fetched and opened the file to write
        mock_build_cohort.assert_called_once()
        mock_read_catalog.assert_called_once()
        mock_open.assert_called_once()

if __name__ == "__main__":
    unittest.main()

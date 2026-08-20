from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.run_osm_recovery_week import _city_osm_complete, _post_status, _task_status  # noqa: E402


class OsmRecoveryWeekTests(unittest.TestCase):
    def test_success_completes_task_without_resetting_failure_history(self) -> None:
        self.assertEqual(_task_status(0, 2, 3), ("completed", 2))

    def test_failed_task_becomes_review_after_bounded_attempts(self) -> None:
        self.assertEqual(_task_status(1, 1, 3), ("pending", 2))
        self.assertEqual(_task_status(1, 2, 3), ("needs_review", 3))

    def test_city_is_complete_only_when_every_osm_task_is_complete(self) -> None:
        state = {"tasks": {"aggregate:healthcare": {"status": "completed"}, "native:healthcare": {"status": "pending"}}}
        self.assertFalse(_city_osm_complete(state))
        state["tasks"]["native:healthcare"]["status"] = "completed"
        self.assertTrue(_city_osm_complete(state))

    def test_deferred_publication_slice_remains_pending(self) -> None:
        self.assertEqual(_post_status(0, {"success": 10, "deferred": 2}), "pending")
        self.assertEqual(_post_status(0, {"success": 12}), "completed")
        self.assertEqual(_post_status(1, {"failed": 1}), "needs_review")


if __name__ == "__main__":
    unittest.main()

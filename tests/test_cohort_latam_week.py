from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.run_cohort_latam_week import _classify  # noqa: E402


class CohortLatamWeekTests(unittest.TestCase):
    def test_deferred_slice_stays_pending_without_counting_as_failure(self) -> None:
        self.assertEqual(_classify({"success": 8, "deferred": 3}, 1, 3), ("pending", 1))

    def test_repeated_failures_require_review(self) -> None:
        self.assertEqual(_classify({"failed": 1}, 1, 3), ("pending", 2))
        self.assertEqual(_classify({"blocked": 1}, 2, 3), ("needs_review", 3))

    def test_all_success_marks_city_complete(self) -> None:
        self.assertEqual(_classify({"success": 42}, 0, 3), ("completed", 0))


if __name__ == "__main__":
    unittest.main()

import unittest
from apps.cohort_coverage_monitor.domain.models import PublicSnapshot, CitySnapshot
from apps.cohort_coverage_monitor.services.metrics import (
    calculate_summary_metrics,
    get_participants_by_status,
    get_participants_by_tier
)

class TestMetrics(unittest.TestCase):
    def setUp(self):
        self.snapshot = PublicSnapshot(
            total_participants=1000,
            priority_participants=500,
            minimum_participants=25,
            updated_at="2026-08-27",
            snapshot_generated_at="2026-08-27T10:00:00",
            cities=[
                CitySnapshot(
                    id="city_a", metro="City A", country="Country A", lat=0.0, lon=0.0,
                    participants=300, pct_total=30.0, status="published", publication_tier="production",
                    available_exposomes_count=2, expected_exposomes_count=3, available_exposomes=["exp1", "exp2"], rank=1
                ),
                CitySnapshot(
                    id="city_b", metro="City B", country="Country B", lat=0.0, lon=0.0,
                    participants=200, pct_total=20.0, status="ready", publication_tier="preview",
                    available_exposomes_count=1, expected_exposomes_count=1, available_exposomes=["exp3"], rank=2
                ),
                CitySnapshot(
                    id="city_c", metro="City C", country="Country C", lat=0.0, lon=0.0,
                    participants=100, pct_total=10.0, status="running", publication_tier="none",
                    available_exposomes_count=0, expected_exposomes_count=0, available_exposomes=[], rank=3
                ),
                CitySnapshot(
                    id="city_d", metro="City D", country="Country D", lat=0.0, lon=0.0,
                    participants=50, pct_total=5.0, status="preparing", publication_tier="none",
                    available_exposomes_count=0, expected_exposomes_count=0, available_exposomes=[], rank=4
                )
            ]
        )

    def test_calculate_summary_metrics(self):
        metrics = calculate_summary_metrics(self.snapshot)
        self.assertEqual(metrics["total_participants"], 1000)
        self.assertEqual(metrics["priority_participants"], 500)
        self.assertEqual(metrics["priority_coverage_pct"], 50.0)
        
        # both A and B are visible (production/preview) => 300 + 200 = 500
        self.assertEqual(metrics["visible_participants"], 500)
        self.assertEqual(metrics["visible_coverage_pct"], 50.0)
        
        self.assertEqual(metrics["published_cities"], 1)
        self.assertEqual(metrics["running_cities"], 1)
        self.assertEqual(metrics["remaining_cities"], 1)
        self.assertEqual(metrics["unique_exposomes_count"], 3)
        self.assertEqual(
            metrics["cities_by_status"],
            {"published": 1, "ready": 1, "running": 1, "preparing": 1},
        )

    def test_participants_by_status(self):
        counts = get_participants_by_status(self.snapshot)
        self.assertEqual(counts.get("published"), 300)
        self.assertEqual(counts.get("ready"), 200)

    def test_participants_by_tier(self):
        counts = get_participants_by_tier(self.snapshot)
        self.assertEqual(counts.get("production"), 300)
        self.assertEqual(counts.get("preview"), 200)
        self.assertEqual(counts.get("none"), 500) # 1000 total - 500 accounted

if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest
from pathlib import Path

from exposome.hospitalization_controls_v2_1 import (
    EXPECTED_EXPOSURES,
    extension_fingerprint,
    extension_tasks,
    load_extension_config,
)
from exposome.hospitalization_controls_v2_1_runner import _control_clear


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    REPO_ROOT / "config/analyses/hospitalization_annual_v2_1_controls.yaml"
)
BASELINE_FINGERPRINT = (
    "452459e12737f8c4ce135155c0551707e53d1701ae6c31ecef9cd1fd7f28bc38"
)


class HospitalizationControlsV21Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_extension_config(CONFIG_PATH)

    def test_registry_is_exactly_eight_exposures_by_two_timings(self) -> None:
        tasks = extension_tasks(self.config)
        self.assertEqual(len(tasks), 16)
        self.assertEqual({task.exposure for task in tasks}, set(EXPECTED_EXPOSURES))
        self.assertEqual(
            {task.variant for task in tasks}, {"primary__same_year", "primary__lag1"}
        )
        self.assertTrue(all(task.outcome == "injury_poisoning" for task in tasks))

    def test_extension_is_bound_to_completed_frozen_baseline(self) -> None:
        fingerprint, inputs, baseline = extension_fingerprint(
            REPO_ROOT, CONFIG_PATH, self.config
        )
        self.assertEqual(baseline["scientific_fingerprint"], BASELINE_FINGERPRINT)
        self.assertEqual(len(fingerprint), 64)
        self.assertIn("baseline_acceptance", inputs)
        self.assertIn("run_state_implementation", inputs)

    def test_extension_rejects_a_different_baseline_fingerprint(self) -> None:
        invalid = json.loads(json.dumps(self.config))
        invalid["baseline"]["expected_fingerprint"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            extension_fingerprint(REPO_ROOT, CONFIG_PATH, invalid)

    def test_bayesian_control_requires_diagnostics_and_no_supported_direction(self) -> None:
        clear = {
            "diagnostics": {"diagnostics_passed": True},
            "effect": {
                "probability_within_direction": 0.97,
                "rr_within_hdi_low": 1.01,
                "rr_within_hdi_high": 1.08,
            },
        }
        self.assertTrue(_control_clear(clear, 0.975))
        directional = json.loads(json.dumps(clear))
        directional["effect"]["probability_within_direction"] = 0.975
        self.assertFalse(_control_clear(directional, 0.975))
        failed = json.loads(json.dumps(clear))
        failed["diagnostics"]["diagnostics_passed"] = False
        self.assertFalse(_control_clear(failed, 0.975))


if __name__ == "__main__":
    unittest.main()

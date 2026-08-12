from __future__ import annotations

import sys
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.multicity_overnight import (  # noqa: E402
    BatchTask,
    build_task_plan,
    execute_task_plan,
    load_batch_config,
    select_cities,
    validate_batch_studies,
)


class MulticityOvernightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.batch = load_batch_config(
            "config/operations/multicity_14.yaml", repo_root=ROOT
        )

    def test_config_declares_seven_city_pairs_and_portable_14(self) -> None:
        self.assertEqual(len(self.batch.portable_layers), 14)
        self.assertEqual(len(self.batch.cities), 9)
        validate_batch_studies(self.batch, repo_root=ROOT)

    def test_plan_splits_provider_work_by_layer_and_temporal_product(self) -> None:
        city = select_cities(self.batch, ["lima"])
        tasks = build_task_plan(self.batch, repo_root=ROOT, cities=city)
        keys = {task.key for task in tasks}
        self.assertEqual(
            len([key for key in keys if key.startswith("lima:aggregate:")]),
            14,
        )
        self.assertEqual(
            len([key for key in keys if key.startswith("lima:native:")]),
            14,
        )
        self.assertIn("lima:temporal:pm25", keys)
        self.assertIn("lima:temporal:wind", keys)
        self.assertIn("lima:resolution:detail", keys)
        self.assertIn("lima:publish:temporal-gate", keys)
        self.assertIn("lima:publish:preview-production", keys)
        self.assertIn("lima:publish:webapp", keys)
        self.assertIn("lima:validate:production", keys)

    def test_phase_selection_keeps_preflight_but_omits_provider_layers(self) -> None:
        city = select_cities(self.batch, ["bogota_localidades"])
        tasks = build_task_plan(
            self.batch,
            repo_root=ROOT,
            cities=city,
            phases=("validate",),
        )
        self.assertEqual(
            [task.phase for task in tasks],
            ["preflight", "preflight", "validate", "validate"],
        )

    def test_executor_records_failure_and_blocks_only_its_dependency(self) -> None:
        tasks = (
            BatchTask("a", "test", "test", "fails", ("/usr/bin/false",)),
            BatchTask(
                "b",
                "test",
                "test",
                "blocked",
                ("/usr/bin/true",),
                requires=("a",),
            ),
            BatchTask("c", "other", "test", "independent", ("/usr/bin/true",)),
        )
        with tempfile.TemporaryDirectory() as temporary:
            run_dir = Path(temporary) / "run"
            results = execute_task_plan(
                tasks,
                repo_root=ROOT,
                run_dir=run_dir,
                max_hours=None,
                attempts=1,
                retry_wait_minutes=0,
            )
            self.assertEqual([result.status for result in results], ["failed", "blocked", "success"])
            self.assertTrue((run_dir / "summary.json").is_file())
            self.assertTrue((run_dir / "incident_candidates.md").is_file())


if __name__ == "__main__":
    unittest.main()

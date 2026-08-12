"""Tests for pipeline.run_study's per-layer failure handling.

A layer that raises during execute_run_plan is now recorded as a "failed"
LayerRunResult instead of aborting the study (see test_layer_catalog.py's
``test_layer_failure_does_not_abort_remaining_layers``). run_study must not
build (or rebuild) the master table when any layer failed -- a master built
from a run with a missing required layer would silently mix in stale or
absent data -- and must surface which layers failed. These are pure offline
unit tests: load_study/build_run_plan/execute_run_plan/master-building are
all mocked so no real study config or provider is touched.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.layers import LayerExecutionError, LayerRunResult  # noqa: E402
from exposome.execution import ExecutionStage, StudyExecutionGraph  # noqa: E402
from exposome.pipeline import materialize_study_release, run_study  # noqa: E402


def _fake_plan(layer_id: str) -> SimpleNamespace:
    return SimpleNamespace(layer=SimpleNamespace(id=layer_id))


class RunStudyFailureHandlingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = SimpleNamespace(
            is_native=False,
            study=SimpleNamespace(id="test_study"),
            enabled_layers=("layer_ok", "layer_bad"),
        )
        self.catalog = SimpleNamespace(
            layers={},
            get=lambda layer_id: SimpleNamespace(requirements={}),
            resolve_id=lambda layer_id: layer_id,
        )
        for target, value in (
            ("exposome.pipeline.load_study", self.context),
            ("exposome.pipeline.load_layer_catalog", self.catalog),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_failed_layer_skips_master_and_raises_with_summary(self) -> None:
        plans = (_fake_plan("layer_ok"), _fake_plan("layer_bad"))
        results = (
            LayerRunResult("layer_ok", "executed", Path("/tmp/ok")),
            LayerRunResult("layer_bad", "failed", Path("/tmp/bad"), error="ConnectionError: boom"),
        )
        with (
            patch("exposome.pipeline.canonical_enabled_layers", return_value=("layer_ok", "layer_bad")),
            patch("exposome.pipeline._verified_bundle_ids", return_value=set()),
            patch(
                "exposome.pipeline.build_execution_graph",
                return_value=StudyExecutionGraph((ExecutionStage(("layer_ok", "layer_bad")),)),
            ),
            patch("exposome.pipeline.build_run_plan", return_value=plans),
            patch("exposome.pipeline.execute_run_plan", return_value=results),
            patch("exposome.pipeline.build_study_master_from_catalog") as master_mock,
            patch("exposome.pipeline.write_release_manifest") as manifest_mock,
        ):
            with self.assertRaises(LayerExecutionError) as ctx:
                run_study("test_study", resume=True)

        master_mock.assert_not_called()
        manifest_mock.assert_not_called()
        self.assertIn("layer_bad", str(ctx.exception))
        summary = getattr(ctx.exception, "summary", None)
        self.assertIsNotNone(summary)
        self.assertEqual([result.action for result in summary.results], ["executed", "failed"])
        self.assertIsNone(summary.master)

    def test_all_layers_succeed_builds_master(self) -> None:
        self.context.enabled_layers = ("layer_ok",)
        plans = (_fake_plan("layer_ok"),)
        results = (LayerRunResult("layer_ok", "executed", Path("/tmp/ok")),)
        with (
            patch("exposome.pipeline.canonical_enabled_layers", return_value=("layer_ok",)),
            patch("exposome.pipeline._verified_bundle_ids", return_value=set()),
            patch(
                "exposome.pipeline.build_execution_graph",
                return_value=StudyExecutionGraph((ExecutionStage(("layer_ok",)),)),
            ),
            patch("exposome.pipeline.build_run_plan", return_value=plans),
            patch("exposome.pipeline.execute_run_plan", return_value=results),
            patch("exposome.pipeline.build_study_master_from_catalog", return_value="MASTER") as master_mock,
            patch("exposome.pipeline.write_release_manifest", return_value="MANIFEST") as manifest_mock,
        ):
            summary = run_study("test_study", resume=True)

        master_mock.assert_called_once()
        manifest_mock.assert_called_once()
        self.assertEqual(summary.master, "MASTER")
        self.assertEqual(summary.release_manifest, "MANIFEST")

    def test_materialize_rebuilds_only_from_verified_local_bundles(self) -> None:
        with (
            patch("exposome.pipeline.canonical_enabled_layers", return_value=("layer_ok",)),
            patch("exposome.pipeline._verified_bundle_ids", return_value={"layer_ok"}),
            patch("exposome.pipeline.build_study_master_from_catalog", return_value="MASTER") as master_mock,
            patch("exposome.pipeline.write_release_manifest", return_value="RELEASE") as release_mock,
        ):
            summary = materialize_study_release("test_study")

        master_mock.assert_called_once()
        release_mock.assert_called_once_with(self.context, "MASTER")
        self.assertEqual(summary.master, "MASTER")
        self.assertEqual(summary.release_manifest, "RELEASE")

    def test_materialize_rejects_missing_or_legacy_bundles(self) -> None:
        with (
            patch("exposome.pipeline.canonical_enabled_layers", return_value=("layer_ok", "layer_bad")),
            patch("exposome.pipeline._verified_bundle_ids", return_value={"layer_ok"}),
        ):
            with self.assertRaisesRegex(ValueError, "layer_bad"):
                materialize_study_release("test_study")


if __name__ == "__main__":
    unittest.main()

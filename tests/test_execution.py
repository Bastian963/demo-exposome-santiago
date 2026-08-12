from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from exposome.execution import (
    LayerBuildResult,
    LayerExecutionContext,
    LayerExecutionIdentity,
    LayerRequirements,
    ProducedAsset,
    build_execution_graph,
)


def _spec(*, input_layers: list[str] | None = None, requires_master: bool = False):
    return SimpleNamespace(
        requirements={
            "input_layers": input_layers or [],
            "requires_master": requires_master,
        }
    )


class ExecutionContractTests(unittest.TestCase):
    def test_execution_identity_is_order_stable_and_layer_selective(self) -> None:
        left = LayerExecutionIdentity(
            study_id="study",
            layer_id="pm25",
            mode="aggregate",
            layer_settings={"scale": 1113, "band": "pm25"},
            period={"start": "2020-01-01", "end": "2020-12-31"},
            spatial_fingerprint="spatial-a",
            algorithm_version="1",
        )
        right = LayerExecutionIdentity(
            study_id="study",
            layer_id="pm25",
            mode="aggregate",
            layer_settings={"band": "pm25", "scale": 1113},
            period={"end": "2020-12-31", "start": "2020-01-01"},
            spatial_fingerprint="spatial-a",
            algorithm_version="1",
        )
        changed = LayerExecutionIdentity(
            study_id="study",
            layer_id="pm25",
            mode="aggregate",
            layer_settings={"band": "pm25", "scale": 1000},
            period=right.period,
            spatial_fingerprint="spatial-a",
            algorithm_version="1",
        )
        self.assertEqual(left.fingerprint, right.fingerprint)
        self.assertNotEqual(left.fingerprint, changed.fingerprint)

    def test_build_result_rejects_ambiguous_primary_table(self) -> None:
        with self.assertRaisesRegex(ValueError, "more than one primary_table"):
            LayerBuildResult(
                (
                    ProducedAsset(Path("a.csv"), "primary_table"),
                    ProducedAsset(Path("b.csv"), "primary_table"),
                )
            )

    def test_context_rejects_resume_and_force(self) -> None:
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            LayerExecutionContext(
                study=object(),
                spec=SimpleNamespace(id="pm25"),
                settings={},
                inputs={},
                output_dir=Path("out"),
                cache_dir=Path("cache"),
                interim_dir=Path("interim"),
                resume=True,
                force=True,
            )

    def test_requirements_infer_master_from_transitional_input_name(self) -> None:
        parsed = LayerRequirements.from_mapping(
            {"study_inputs": ["master_csv"], "official_optional": True}
        )
        self.assertTrue(parsed.requires_master)
        self.assertTrue(parsed.official_optional)


class ExecutionGraphTests(unittest.TestCase):
    def test_topological_order_and_master_barrier(self) -> None:
        specs = {
            "base": _spec(),
            "derived": _spec(input_layers=["base"]),
            "sleep": _spec(input_layers=["derived"], requires_master=True),
        }
        graph = build_execution_graph(specs, ["sleep", "derived", "base"])
        self.assertEqual([stage.layer_ids for stage in graph.stages], [
            ("base",),
            ("derived",),
            ("sleep",),
        ])
        self.assertTrue(graph.stages[2].materialize_master_before)

    def test_unrequested_dependency_requires_verified_bundle(self) -> None:
        specs = {"base": _spec(), "derived": _spec(input_layers=["base"])}
        with self.assertRaisesRegex(ValueError, "without a verified bundle"):
            build_execution_graph(specs, ["derived"])
        graph = build_execution_graph(specs, ["derived"], available_bundle_ids=["base"])
        self.assertEqual(graph.ordered_layer_ids, ("derived",))

    def test_unknown_dependency_fails(self) -> None:
        specs = {"derived": _spec(input_layers=["missing"])}
        with self.assertRaisesRegex(ValueError, "unknown dependency"):
            build_execution_graph(specs, ["derived"])

    def test_cycle_fails(self) -> None:
        specs = {
            "a": _spec(input_layers=["b"]),
            "b": _spec(input_layers=["a"]),
        }
        with self.assertRaisesRegex(ValueError, "cycle"):
            build_execution_graph(specs, ["a", "b"])


if __name__ == "__main__":
    unittest.main()

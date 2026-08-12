from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.spatial_plan import recovery_plan_for_bundle, recovery_plan_for_study  # noqa: E402
from exposome.spatial_support import indicators_for_bundle  # noqa: E402


class SpatialPlanTests(unittest.TestCase):
    def test_plan_separates_native_aggregate_and_local_detail_commands(self) -> None:
        records = indicators_for_bundle([])
        for indicator_id, record in records.items():
            record["publication_target"]["required_for_production"] = indicator_id in {
                "alan",
                "heat_hot_days",
                "green",
                "healthcare",
            }
        manifest = {
            "study_id": "example_aggregate",
            "mode": "aggregate",
            "layers": {
                "alan": {"available": True},
                "climate_heat": {"available": True},
                "greenspace_multisource": {"available": True},
                "healthcare": {"available": True},
            },
            "spatial_indicators": records,
        }
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            context = type("Context", (), {"study": type("Study", (), {"raw": {"detail": {"native_study": "example_native"}}})()})()
            with patch("exposome.spatial_plan.load_study", return_value=context):
                plan = recovery_plan_for_bundle(bundle, repo_root=ROOT)
        self.assertIn("exposome run --study example_native --layers alan,climate_heat --resume", plan.commands)
        self.assertNotIn(
            "exposome run --study example_aggregate --layers alan,climate_heat --resume",
            plan.commands,
        )
        self.assertIn("exposome detail --study example_aggregate --indicators alan,heat_hot_days --resume", plan.commands)
        self.assertIn("python scripts/export_webapp_green_subcomuna.py --study example_aggregate", plan.commands)
        self.assertIn("exposome run --study example_aggregate --layers healthcare --resume", plan.commands)

    def test_unpublished_configured_city_gets_a_plan(self) -> None:
        with tempfile.TemporaryDirectory() as output:
            plan = recovery_plan_for_study(
                "cdmx_alcaldias", repo_root=ROOT, output_root=output
            )
        self.assertEqual(plan.native_study, "cdmx_native")
        self.assertIn("alan", plan.missing_indicators)
        self.assertIn("green", plan.missing_indicators)
        self.assertEqual(plan.manual_indicators, ())
        self.assertEqual(plan.assessment_source, "configured_study")

    def test_published_study_uses_bundle_instead_of_synthetic_gaps(self) -> None:
        records = indicators_for_bundle([])
        for indicator_id, record in records.items():
            record["publication_target"]["required_for_production"] = indicator_id == "alan"
        records["alan"]["detail"] = {
            "type": "cog",
            "path": "detail/alan.tif",
            "canonical_resolution_verified": True,
            "source_grid": {
                "crs": "EPSG:4326",
                "resolution": {"x": 1 / 240, "y": 1 / 240, "unit": "degree"},
            },
        }
        records["alan"]["rendered"] = {
            "kind": "cog",
            "label": "radiancia VIIRS nativa",
            "resolution": {"value": 463.83, "unit": "m"},
        }
        manifest = {
            "study_id": "example_aggregate",
            "mode": "aggregate",
            "layers": {"alan": {"available": True}},
            "spatial_indicators": records,
        }
        study = type(
            "Study",
            (),
            {
                "id": "example_aggregate",
                "raw": {"detail": {"native_study": "example_native"}},
                "enabled_layers": ("alan",),
            },
        )()
        context = type(
            "Context",
            (),
            {
                "study": study,
                "is_native": False,
                "city": "example_city",
                "location": type("Location", (), {"country_code": "ZZ"})(),
            },
        )()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            bundle = output / "v1" / "zz" / "example_city" / "example_aggregate"
            bundle.mkdir(parents=True)
            (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with patch("exposome.spatial_plan.load_study", return_value=context):
                plan = recovery_plan_for_study(
                    "example_aggregate", repo_root=ROOT, output_root=output
                )
        self.assertEqual(plan.missing_indicators, ())
        self.assertEqual(plan.commands, ())
        self.assertEqual(plan.assessment_source, "published_bundle")
        self.assertEqual(plan.bundle, str(bundle))

    def test_study_without_native_companion_reports_a_prerequisite(self) -> None:
        with tempfile.TemporaryDirectory() as output:
            plan = recovery_plan_for_study(
                "buenos_aires_zipcodes", repo_root=ROOT, output_root=output
            )
        self.assertEqual(plan.commands, ())
        self.assertTrue(plan.prerequisites)


if __name__ == "__main__":
    unittest.main()

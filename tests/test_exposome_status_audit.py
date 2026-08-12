from __future__ import annotations

import csv
import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import audit_exposome_status as audit  # noqa: E402


RUN_ARTIFACT_TESTS = os.environ.get("EXPOSOME_RUN_ARTIFACT_TESTS") == "1"


class ExposomeStatusAuditTest(unittest.TestCase):
    def test_canonical_rows_come_from_study_catalog(self) -> None:
        rows = audit.build_rows()
        names = {row["layer_id"] for row in rows}

        # 29 since noise_spain earned a dashboard row: it is materialized for
        # both Spanish studies, so it finally has real outputs to review.
        self.assertEqual(len(rows), 29)
        self.assertIn("alan", names)
        self.assertIn("wildfire", names)
        self.assertIn("healthcare", names)
        self.assertIn("greenspace_cv", names)
        self.assertIn("neuro_mortality", names)

    def test_audit_csv_detects_missing_columns_and_name_issues(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "layer.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["name", "value"])
                writer.writeheader()
                writer.writerow({"name": "A", "value": "1"})
                writer.writerow({"name": "A", "value": "2"})
                writer.writerow({"name": "", "value": "3"})

            result = audit.audit_csv(path, ["name", "value", "missing_col"])

        self.assertEqual(result.rows, 3)
        self.assertEqual(result.unique_names, 1)
        self.assertEqual(result.duplicate_names, "A")
        self.assertEqual(result.missing_names, 1)
        self.assertEqual(result.missing_required_columns, ["missing_col"])

    def test_merge_manual_preserves_existing_review_fields(self) -> None:
        rows = [
            audit.with_manual_defaults(
                {
                    "layer_id": "alan",
                    "factor": "ALAN",
                    "category": "master_required",
                    "required_or_optional": "required",
                }
            )
        ]
        manual = {
            "alan": {
                "review_status": "checked",
                "review_tool": "codex",
                "review_date": "2026-06-28",
                "review_doc": "docs/review_prompts/alan.md",
                "blockers": "",
                "next_action": "none",
                "final_check": "true",
            }
        }

        merged = audit.merge_manual(rows, manual)

        self.assertEqual(merged[0]["review_status"], "checked")
        self.assertEqual(merged[0]["review_tool"], "codex")
        self.assertEqual(merged[0]["final_check"], "true")

    def test_study_audit_reports_expected_units_and_canonical_paths(self) -> None:
        report = audit.build_study_audit("santiago_communes")

        self.assertEqual(report.study_id, "santiago_communes")
        self.assertEqual(report.expected_units, 52)
        self.assertEqual(report.observed_units, 52)
        self.assertEqual(report.status, "ready")
        self.assertEqual(
            report.paths["processed"],
            "data/processed/cl/santiago/santiago_communes",
        )
        self.assertEqual(
            report.master_outputs["coverage"],
            "data/processed/cl/santiago/santiago_communes/master_coverage.csv",
        )

    def test_count_geojson_units_is_dependency_free(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "units.geojson"
            path.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {"type": "Feature", "properties": {}, "geometry": None},
                            {"type": "Feature", "properties": {}, "geometry": None},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            self.assertEqual(audit.count_geojson_units(path), 2)

    def test_study_cli_accepts_dynamic_expected_units(self) -> None:
        report = audit.build_study_audit("buenos_aires_zipcodes")
        parsed = audit.parse_args(["--study", "buenos_aires_zipcodes"])

        self.assertEqual(parsed.study, "buenos_aires_zipcodes")
        self.assertIsNone(report.expected_units)
        self.assertEqual(
            report.paths["raw"],
            "data/raw",
        )

    @unittest.skipUnless(RUN_ARTIFACT_TESTS, "requires a materialized Santiago release")
    def test_generated_rows_have_prompt_for_each_layer(self) -> None:
        rows = audit.merge_manual(audit.build_rows(), audit.read_manual_fields())

        self.assertEqual(len(rows), 29)
        self.assertTrue(
            all(
                row["review_doc"] == f"docs/review_prompts/{row['layer_id']}.md"
                for row in rows
            )
        )
        self.assertTrue(all(row["auto_status"] == "ready_for_review" for row in rows if row["required_or_optional"] == "required"))
        self.assertIn("neuro_mortality", {row["layer_id"] for row in rows if row["category"] == "comparator"})
        socioeconomic = next(row for row in rows if row["layer_id"] == "socioeconomic")
        self.assertEqual(socioeconomic["methodology_doc"], "docs/socioeconomic_methodology.md")

    def test_air_quality_satellite_row_uses_canonical_cli(self) -> None:
        rows = audit.merge_manual(audit.build_rows(), audit.read_manual_fields())
        row = next(item for item in rows if item["layer_id"] == "air_quality_satellite")

        self.assertEqual(
            row["run_command"],
            "exposome run --study santiago_communes --layers air_quality_satellite --resume",
        )

    def test_air_quality_row_keeps_legacy_methodology_but_not_legacy_execution(self) -> None:
        rows = audit.merge_manual(audit.build_rows(), audit.read_manual_fields())
        row = next(item for item in rows if item["layer_id"] == "air_quality")

        self.assertEqual(
            row["run_command"],
            "exposome run --study santiago_communes --layers air_quality --resume",
        )
        self.assertEqual(row["methodology_doc"], "docs/air_quality_legacy_methodology.md")

    def test_all_audited_layers_have_existing_methodology_documents(self) -> None:
        rows = audit.build_rows()

        for row in rows:
            with self.subTest(layer=row["layer_id"]):
                self.assertTrue(row["methodology_doc"])
                self.assertTrue((REPO_ROOT / row["methodology_doc"]).is_file())

        mappings = {row["layer_id"]: row["methodology_doc"] for row in rows}
        self.assertEqual(mappings["climate_openmeteo"], "docs/climate_openmeteo_methodology.md")
        self.assertEqual(mappings["food_insecurity"], "docs/food_insecurity_methodology.md")


if __name__ == "__main__":
    unittest.main()

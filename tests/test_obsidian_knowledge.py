from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_obsidian_knowledge as knowledge  # noqa: E402


FIELDS = [
    "layer_id",
    "factor",
    "category",
    "required_or_optional",
    "run_command",
    "csv_path",
    "geojson_path",
    "metadata_path",
    "methodology_doc",
    "figure_or_map",
    "in_master",
    "auto_status",
    "review_status",
    "review_doc",
    "blockers",
    "next_action",
    "final_check",
]


class ObsidianKnowledgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "docs" / "review_prompts").mkdir(parents=True)
        (self.root / "config" / "studies").mkdir(parents=True)
        (self.root / "config" / "layers").mkdir(parents=True)
        (self.root / "src" / "exposome").mkdir(parents=True)
        (self.root / "docs" / "sample_methodology.md").write_text("# Método\n", encoding="utf-8")
        (self.root / "docs" / "exposome_status.md").write_text("# Estado\n", encoding="utf-8")
        (self.root / "docs" / "review_prompts" / "sample.md").write_text("# Revisión\n", encoding="utf-8")
        (self.root / "config" / "layers" / "sample.yaml").write_text("provider: local\n", encoding="utf-8")
        (self.root / "src" / "exposome" / "sample.py").write_text("\"\"\"Sample.\"\"\"\n", encoding="utf-8")
        (self.root / "config" / "studies" / "área_piloto.yaml").write_text(
            "\n".join(
                [
                    "schema_version: 1",
                    "id: area_piloto",
                    "location: cl/santiago",
                    "hidden: true",
                    "period:",
                    "  start_date: '2024-01-01'",
                    "  end_date: '2024-12-31'",
                    "layers:",
                    "  - sample",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        self.status_path = self.root / "docs" / "exposome_status.csv"
        self.generated_dir = self.root / "docs" / "knowledge" / "generated"
        self._write_rows([self._row()])

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _row(self, **updates: str) -> dict[str, str]:
        row = {
            "layer_id": "sample",
            "factor": "Exposición áérea",
            "category": "master_optional",
            "required_or_optional": "optional",
            "run_command": "exposome run --study area_piloto --layers sample --resume",
            "csv_path": "data/processed/sample.csv",
            "geojson_path": "data/processed/sample.geojson",
            "metadata_path": "data/processed/sample.json",
            "methodology_doc": "docs/sample_methodology.md",
            "figure_or_map": "",
            "in_master": "true",
            "auto_status": "ready_for_review",
            "review_status": "checked",
            "review_doc": "docs/review_prompts/sample.md",
            "blockers": "",
            "next_action": "Revisar en Ñuñoa",
            "final_check": "true",
        }
        row.update(updates)
        return row

    def _write_rows(self, rows: list[dict[str, str]]) -> None:
        with self.status_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def _build(self, *, generated_dir: Path | None = None) -> tuple[dict[Path, str], list[str]]:
        return knowledge.build_outputs(
            root=self.root,
            status_path=self.status_path,
            studies_dir=self.root / "config" / "studies",
            generated_dir=generated_dir or self.generated_dir,
        )

    def test_generation_is_deterministic_utf8_and_checks_cleanly(self) -> None:
        first, errors = self._build()
        second, second_errors = self._build()

        self.assertEqual(errors, [])
        self.assertEqual(second_errors, [])
        self.assertEqual(first, second)
        layer_page = first[self.generated_dir / "layers" / "sample.md"]
        self.assertIn("Exposición áérea", layer_page)
        self.assertIn("Ñuñoa", layer_page)

        knowledge.write_outputs(first, self.generated_dir)
        self.assertEqual(knowledge.check_outputs(second, self.generated_dir), [])

    def test_check_detects_outdated_and_orphan_files(self) -> None:
        outputs, errors = self._build()
        self.assertEqual(errors, [])
        knowledge.write_outputs(outputs, self.generated_dir)
        catalog = self.generated_dir / "catalogo-capas.md"
        catalog.write_text("stale", encoding="utf-8")
        orphan = self.generated_dir / "layers" / "obsolete.md"
        orphan.write_text("obsolete", encoding="utf-8")

        messages = knowledge.check_outputs(outputs, self.generated_dir)

        self.assertTrue(any("out-of-date" in message for message in messages))
        self.assertTrue(any("orphan" in message for message in messages))

    def test_missing_methodology_and_duplicate_ids_are_rejected(self) -> None:
        self._write_rows([self._row(methodology_doc="docs/missing.md"), self._row()])

        outputs, errors = self._build()

        self.assertEqual(outputs, {})
        self.assertTrue(any("duplicate layer_id" in error for error in errors))
        self.assertTrue(any("methodology does not exist" in error for error in errors))

    def test_undeclared_shared_methodology_is_rejected(self) -> None:
        self._write_rows([self._row(), self._row(layer_id="second")])

        _, errors = self._build()

        self.assertTrue(any("undeclared shared methodology" in error for error in errors))

    def test_hidden_study_and_optional_layer_are_rendered(self) -> None:
        outputs, errors = self._build()

        self.assertEqual(errors, [])
        study_page = outputs[self.generated_dir / "studies" / "area_piloto.md"]
        layer_page = outputs[self.generated_dir / "layers" / "sample.md"]
        self.assertIn("hidden: true", study_page)
        self.assertIn("required: false", layer_page)

    def test_broken_markdown_link_is_detected(self) -> None:
        source = self.generated_dir / "bad.md"
        errors = knowledge.validate_markdown_links({source: "[roto](missing.md)\n"})
        self.assertEqual(len(errors), 1)
        self.assertIn("broken local link", errors[0])

    def test_curated_knowledge_links_are_checked(self) -> None:
        curated = self.root / "docs" / "knowledge" / "00-inicio.md"
        curated.parent.mkdir(parents=True)
        curated.write_text("[roto](missing.md)\n", encoding="utf-8")

        outputs, errors = self._build()

        self.assertNotEqual(outputs, {})
        self.assertTrue(any("00-inicio.md" in error and "broken local link" in error for error in errors))

    def test_output_directory_cannot_escape_knowledge_tree(self) -> None:
        outputs, errors = self._build(generated_dir=self.root / "elsewhere")
        self.assertEqual(outputs, {})
        self.assertTrue(any("must stay" in error for error in errors))


if __name__ == "__main__":
    unittest.main()

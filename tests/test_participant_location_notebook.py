from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import nbformat
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "cohort" / "participant_location_rankings.ipynb"
RAW = ROOT / "data" / "raw" / "zipcodes" / "2026-07" / "participant_locations.csv"
EXPECTED_SHA256 = "201212bec01688d40c87f6310956e9d2c43f9193e14a81bb3d61a50bdd818e32"


class ParticipantLocationNotebookTest(unittest.TestCase):
    def test_notebook_is_valid_executed_and_uses_python_312(self) -> None:
        notebook = nbformat.read(NOTEBOOK, as_version=4)
        nbformat.validate(notebook)

        code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
        self.assertTrue(code_cells)
        self.assertTrue(all(cell.execution_count is not None for cell in code_cells))
        self.assertFalse(any(output.output_type == "error" for cell in code_cells for output in cell.outputs))
        self.assertEqual(notebook.metadata.kernelspec.name, "python3")
        # Notebook metadata records the patch release (e.g. 3.12.12), while
        # the reproducibility contract is the supported Python 3.12 series.
        self.assertTrue(str(notebook.metadata.language_info.version).startswith("3.12"))
        self.assertFalse(any("execution" in cell.metadata for cell in code_cells))

    def test_notebook_has_privacy_guards_and_no_raw_row_display(self) -> None:
        notebook = nbformat.read(NOTEBOOK, as_version=4)
        code_source = "\n".join(cell.source for cell in notebook.cells if cell.cell_type == "code")

        self.assertIn("MIN_CELL_N = 5", code_source)
        self.assertIn("privacy_safe_rank", code_source)
        self.assertIn('counts["n"] < MIN_CELL_N', code_source)
        self.assertIn('apply_astro_paper_style("paper")', code_source)
        self.assertEqual(code_source.count("save_paper_figure("), 4)
        for forbidden in ("raw.head(", "display(raw", "print(raw", "raw.to_csv("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, code_source)

    def test_saved_outputs_do_not_reveal_known_rare_raw_categories(self) -> None:
        notebook = nbformat.read(NOTEBOOK, as_version=4)
        outputs = [output for cell in notebook.cells if cell.cell_type == "code" for output in cell.outputs]
        serialized = json.dumps(outputs, ensure_ascii=False)

        for rare_value in ("PERALLILLO", "FERRENATE", "ITALIA", "PANAMA", "GUATEMALA", "ARUBA", "CANADA"):
            with self.subTest(rare_value=rare_value):
                self.assertNotIn(rare_value, serialized)

    @unittest.skipUnless(RAW.is_file(), "requires the local, gitignored cohort delivery")
    def test_raw_contract_and_checksum(self) -> None:
        self.assertEqual(hashlib.sha256(RAW.read_bytes()).hexdigest(), EXPECTED_SHA256)
        with RAW.open(encoding="utf-8-sig") as handle:
            header = handle.readline().rstrip("\r\n").split(",")
            rows = sum(1 for _ in handle)
        self.assertEqual(header, ["City", "State", "Country"])
        self.assertEqual(rows, 3_874)

    @unittest.skipUnless(RAW.is_file(), "requires the local, gitignored cohort delivery")
    def test_notebook_executes_top_to_bottom_in_clean_kernel(self) -> None:
        notebook = nbformat.read(NOTEBOOK, as_version=4)
        for cell in notebook.cells:
            if cell.cell_type == "code":
                cell.execution_count = None
                cell.outputs = []

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / NOTEBOOK.name
            nbformat.write(notebook, temp_path)
            client = NotebookClient(
                notebook,
                timeout=180,
                kernel_name="python3",
                resources={"metadata": {"path": str(ROOT)}},
                record_timing=False,
            )
            executed = client.execute(cwd=str(ROOT))

        code_cells = [cell for cell in executed.cells if cell.cell_type == "code"]
        self.assertTrue(all(cell.execution_count is not None for cell in code_cells))
        self.assertFalse(any(output.output_type == "error" for cell in code_cells for output in cell.outputs))


if __name__ == "__main__":
    unittest.main()

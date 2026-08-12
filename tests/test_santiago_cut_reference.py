from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.spatial import load_spatial_units  # noqa: E402
from exposome.studies import load_study  # noqa: E402


class SantiagoCutReferenceTests(unittest.TestCase):
    def test_reference_has_complete_stable_cut_contract(self) -> None:
        context = load_study("santiago_communes", repo_root_path=ROOT)
        units = load_spatial_units(context)

        self.assertEqual(len(units), 52)
        self.assertEqual(units["spatial_id"].str.fullmatch(r"13\d{3}").sum(), 52)
        self.assertFalse(units["spatial_id"].duplicated().any())
        self.assertTrue({"legacy_name", "slug"}.issubset(units.columns))
        self.assertEqual(units.loc[units["spatial_name"] == "Santiago", "spatial_id"].item(), "13101")

    def test_reference_metadata_records_provenance(self) -> None:
        path = ROOT / "data" / "reference" / "cl" / "santiago" / "santiago_communes" / "metadata.json"
        metadata = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["unit_count"], 52)
        self.assertEqual(metadata["spatial_id"], "CUT comuna, 5-digit string")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.studies import load_study  # noqa: E402


class ReferencePathTests(unittest.TestCase):
    def test_existing_multi_city_studies_use_versioned_reference_inputs(self) -> None:
        for study_id in (
            "santiago_communes",
            "buenos_aires_comunas",
            "buenos_aires_amba",
            "caba_native",
        ):
            with self.subTest(study=study_id):
                context = load_study(study_id, repo_root_path=ROOT)
                path = context.aoi_path if context.is_native else context.spatial_path
                self.assertIsNotNone(path)
                self.assertIn("data/reference/", str(path))
                self.assertTrue(Path(path).is_file())


if __name__ == "__main__":
    unittest.main()

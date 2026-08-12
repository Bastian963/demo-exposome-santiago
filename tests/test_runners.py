from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.layers import load_layer_catalog  # noqa: E402
from exposome.runners import has_importable_runner  # noqa: E402


class RunnerRegistryTests(unittest.TestCase):
    def test_every_catalogued_layer_has_an_in_process_runner(self) -> None:
        catalog = load_layer_catalog()
        missing = [layer_id for layer_id in catalog.ids if not has_importable_runner(layer_id)]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()

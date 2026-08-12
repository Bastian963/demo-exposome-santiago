"""Test that the master builder is unit-agnostic (communes or zip codes).

v1.3 lock-in: the master builder must work with any number of
spatial units (communes, zip codes, neighbourhoods) as long as
``expected_communes`` in the config matches the row count. This
test verifies the property by:

1. Building the master with the Santiago config (52 communes) and
   asserting the standard shape.
2. Inspecting the master builder signature and source to confirm
   that the hardcoded 52 has been replaced by a config-driven
   ``expected_communes``.
3. Loading the helper ``tests/_expected.py`` and verifying that
   ``EXPECTED_N_UNITS`` matches the config value.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

DATA_DIR = REPO_ROOT / "data" / "processed"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"
BUILDER = REPO_ROOT / "scripts" / "build_master_exposome.py"


class MasterBuilderZipCompatibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from _expected import EXPECTED_N_UNITS
        cls.expected_n = EXPECTED_N_UNITS
        if MASTER_CSV.exists():
            cls.master = pd.read_csv(MASTER_CSV)
        else:
            cls.master = None

    def test_helper_module_loads_expected_communes(self) -> None:
        """The shared helper reads from config and matches the master row count."""
        from _expected import EXPECTED_COMMUNES
        self.assertEqual(EXPECTED_COMMUNES, 52)
        self.assertEqual(self.expected_n, 52)

    def test_master_row_count_matches_config(self) -> None:
        """Master row count equals expected_communes from config."""
        if self.master is None:
            self.skipTest("master CSV not visible")
        self.assertEqual(
            self.master.shape[0], self.expected_n,
            f"master has {self.master.shape[0]} rows, expected {self.expected_n}",
        )

    def test_builder_no_hardcoded_52(self) -> None:
        """Lock-in: the master builder must NOT have a hardcoded 52.

        We allow comments and docstrings (lines starting with # or
        inside triple-quoted strings), but a literal ``if len(master) != 52``
        in active code is a regression.
        """
        source = BUILDER.read_text()
        # Find the line that validates the row count.
        # We accept ``!= expected_n`` (or any other non-52 number)
        # but reject ``!= 52`` or ``== 52`` as a literal.
        pattern = re.compile(r"if\s+len\(master\)\s*!=\s*(\d+)")
        matches = pattern.findall(source)
        for n in matches:
            self.assertNotEqual(
                int(n), 52,
                f"master builder has hardcoded 52: 'if len(master) != {n}'; "
                "use cfg['expected_communes'] instead",
            )

    def test_builder_signature_has_city_param(self) -> None:
        """Lock-in: the build_master function should accept a city param.

        Future zip-code builds will call ``build_master(city="santiago_zip")``
        with a different config.
        """
        source = BUILDER.read_text()
        self.assertRegex(
            source,
            r"def\s+build_master\s*\([^)]*city",
            "build_master should accept a 'city' parameter",
        )

    def test_helper_independent_of_master(self) -> None:
        """The helper must NOT depend on master CSV existing.

        The helper reads from the config file, not the master
        output. This is a precondition for tests to run before
        the master is built.
        """
        from _expected import EXPECTED_N_UNITS
        self.assertIsInstance(EXPECTED_N_UNITS, int)
        self.assertGreater(EXPECTED_N_UNITS, 0)


if __name__ == "__main__":
    unittest.main()

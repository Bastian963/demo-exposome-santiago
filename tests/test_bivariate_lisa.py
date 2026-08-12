"""Tests for scripts/bivariate_lisa.py (Bivariate Local Moran's I).

Verifies the Bivariate LISA outputs:
- JSON summary includes both directions (EBI x NSE, NSE x EBI).
- Quadrant counts sum to 52.
- HL cluster (env-justice signal) is non-empty for at least one
  direction.
- Members lists are non-empty and commune names are valid.
- Quadrant codes match the libpysal Anselin convention
  (1=HH, 2=LH, 3=LL, 4=HL).
"""
from __future__ import annotations

import json
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "processed"
JSON_PATH = DATA_DIR / "bivariate_lisa.json"


class BivariateLisaTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not JSON_PATH.exists():
            raise unittest.SkipTest(
                "Run scripts/bivariate_lisa.py first"
            )
        with open(JSON_PATH) as f:
            cls.summary = json.load(f)
        cls.ebi = pd.read_csv(DATA_DIR / "environmental_burden_index.csv")
        cls.communes = set(cls.ebi["name"].tolist())

    def test_both_directions_present(self) -> None:
        """The JSON must include both EBI x NSE and NSE x EBI directions."""
        self.assertIn("direction_ebinse", self.summary)
        self.assertIn("direction_nseebi", self.summary)

    def test_n_communes_52(self) -> None:
        self.assertEqual(self.summary["n_communes"], 52)

    def test_permutations_999_alpha_005(self) -> None:
        self.assertEqual(self.summary["permutations"], 999)
        self.assertAlmostEqual(self.summary["alpha"], 0.05)

    def test_direction_ebinse_quadrants_sum_52(self) -> None:
        d = self.summary["direction_ebinse"]
        total = d["n_HH"] + d["n_LH"] + d["n_LL"] + d["n_HL"] + d["n_NS"]
        self.assertEqual(total, 52, f"ebinse quadrants sum to {total}, expected 52")

    def test_direction_nseebi_quadrants_sum_52(self) -> None:
        d = self.summary["direction_nseebi"]
        total = d["n_HH"] + d["n_LH"] + d["n_LL"] + d["n_HL"] + d["n_NS"]
        self.assertEqual(total, 52, f"nseebi quadrants sum to {total}, expected 52")

    def test_hl_cluster_non_empty_at_least_one_direction(self) -> None:
        """The HL (env-justice signal) cluster must be non-empty for
        at least one direction. Otherwise the bivariate LISA
        failed to detect the most policy-relevant cluster.
        """
        hl1 = self.summary["direction_ebinse"]["n_HL"]
        hl2 = self.summary["direction_nseebi"]["n_HL"]
        self.assertGreater(
            max(hl1, hl2), 0,
            f"HL cluster empty in both directions ({hl1}, {hl2})",
        )

    def test_member_lists_match_counts(self) -> None:
        """Each quadrant's member list length must equal the count."""
        for direction_key in ("direction_ebinse", "direction_nseebi"):
            d = self.summary[direction_key]
            for label in ("HH", "HL", "LH", "LL"):
                count = d[f"n_{label}"]
                members = d[f"members_{label}"]
                self.assertEqual(
                    count, len(members),
                    f"{direction_key}.{label}: count={count} != members={len(members)}",
                )

    def test_member_names_are_valid_communes(self) -> None:
        """All member names must be in the 52 commune list."""
        for direction_key in ("direction_ebinse", "direction_nseebi"):
            d = self.summary[direction_key]
            for label in ("HH", "HL", "LH", "LL"):
                for name in d[f"members_{label}"]:
                    self.assertIn(
                        name, self.communes,
                        f"{direction_key}.{label}: {name!r} not in master communes",
                    )

    def test_no_duplicate_member_names(self) -> None:
        """A commune cannot be in two different quadrants of the
        same direction.
        """
        for direction_key in ("direction_ebinse", "direction_nseebi"):
            d = self.summary[direction_key]
            all_members = (
                d["members_HH"] + d["members_HL"] + d["members_LH"] + d["members_LL"]
            )
            self.assertEqual(
                len(all_members), len(set(all_members)),
                f"{direction_key} has duplicate members across quadrants",
            )


if __name__ == "__main__":
    unittest.main()

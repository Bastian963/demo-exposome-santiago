"""Tests for scripts/compare_exposome_vs_neuro.py.

Verifies that:
- The script produces the expected output artefacts.
- The 14 exposome axes x 15 outcomes correlation matrix has the
  right shape (140 pairs, or less if some columns are missing).
- The significant pairs filter (|rho| > 0.3, p < 0.05) is
  internally consistent.
- The summary JSON includes the top-20 |rho| pairs.
- The CSV and JSON round-trip match.
"""
from __future__ import annotations

import json
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

DATA_DIR = REPO_ROOT / "data" / "processed"
CORR_CSV = DATA_DIR / "exposome_vs_neuro.csv"
SIG_CSV = DATA_DIR / "exposome_vs_neuro_significant.csv"
SUMMARY_JSON = DATA_DIR / "exposome_vs_neuro.json"


class ExposomeVsNeuroTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CORR_CSV.exists():
            raise unittest.SkipTest(
                "Run scripts/compare_exposome_vs_neuro.py first"
            )
        cls.corr = pd.read_csv(CORR_CSV)
        cls.sig = (
            pd.read_csv(SIG_CSV) if SIG_CSV.exists() else None
        )
        with open(SUMMARY_JSON) as f:
            cls.summary = json.load(f)

    def test_corr_csv_has_expected_shape(self) -> None:
        """The CSV should have 14 axes x 15 outcomes = 210 pairs max.

        Some pairs are dropped if their column is missing from the
        source data; we expect at least 100.
        """
        self.assertGreaterEqual(
            len(self.corr), 100,
            f"only {len(self.corr)} pairs, expected >= 100",
        )
        for col in ("axis", "outcome", "outcome_kind", "rho", "p_value"):
            self.assertIn(col, self.corr.columns, f"missing {col!r}")

    def test_axes_count_is_14(self) -> None:
        """The summary must list 14 exposome axes."""
        self.assertEqual(
            self.summary["n_axes"], 14,
            f"axes={self.summary['n_axes']}, expected 14",
        )

    def test_outcomes_count_is_15(self) -> None:
        """The summary must list 15 outcomes (5 mort + 10 hosp)."""
        self.assertEqual(
            self.summary["n_outcomes"], 15,
            f"outcomes={self.summary['n_outcomes']}, expected 15",
        )

    def test_outcome_kinds_split(self) -> None:
        """Outcomes must split into mortality + hospitalization."""
        kinds = set(self.corr["outcome_kind"].unique())
        self.assertIn("mortality", kinds)
        self.assertIn("hospitalization", kinds)

    def test_significant_pairs_filter_consistent(self) -> None:
        """Significant pairs (|rho| > 0.3, p < 0.05) must be a strict
        subset of all pairs and internally consistent with the CSV.
        """
        self.assertIsNotNone(self.sig, "sig CSV not found")
        # Self-consistency: every sig pair is in corr.
        merged = self.sig.merge(
            self.corr,
            on=["axis", "outcome", "outcome_kind"],
            suffixes=("_sig", "_all"),
        )
        self.assertEqual(len(merged), len(self.sig))
        # Filter condition: rho abs > 0.3 AND p_value < 0.05.
        valid = self.sig.dropna(subset=["rho", "p_value"])
        self.assertTrue(
            (valid["rho"].abs() > 0.3).all(),
            "sig CSV has rows with |rho| <= 0.3",
        )
        self.assertTrue(
            (valid["p_value"] < 0.05).all(),
            "sig CSV has rows with p_value >= 0.05",
        )

    def test_summary_top_pairs_match_csv(self) -> None:
        """The JSON's top-20 |rho| pairs must be the top-20 of the CSV."""
        csv_top = (
            self.corr.dropna(subset=["rho"])
            .assign(abs_rho=lambda d: d["rho"].abs())
            .sort_values("abs_rho", ascending=False)
            .head(20)
        )
        json_top = pd.DataFrame(self.summary["top_20_abs_rho_pairs"])
        csv_set = set(
            zip(csv_top["axis"], csv_top["outcome"], csv_top["outcome_kind"]),
        )
        json_set = set(
            zip(json_top["axis"], json_top["outcome"], json_top["outcome_kind"]),
        )
        self.assertEqual(
            csv_set, json_set,
            "summary top-20 pairs do not match CSV top-20",
        )

    def test_summary_significant_count_matches_csv(self) -> None:
        """The JSON's n_significant_pairs must match the CSV row count."""
        self.assertEqual(
            self.summary["n_significant_pairs"], len(self.sig),
            f"summary n_significant={self.summary['n_significant_pairs']} "
            f"!= sig CSV len={len(self.sig)}",
        )

    def test_rho_in_minus1_to_1(self) -> None:
        """All non-NaN rho must be in [-1, 1]."""
        r = self.corr["rho"].dropna()
        self.assertGreaterEqual(r.min(), -1.0)
        self.assertLessEqual(r.max(), 1.0)

    def test_p_value_in_0_to_1(self) -> None:
        """All non-NaN p_value must be in [0, 1]."""
        p = self.corr["p_value"].dropna()
        self.assertGreaterEqual(p.min(), 0.0)
        self.assertLessEqual(p.max(), 1.0)


if __name__ == "__main__":
    unittest.main()

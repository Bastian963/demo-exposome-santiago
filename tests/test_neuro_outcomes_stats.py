from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.neuro_mortality import compute_exposome_correlations  # noqa: E402
from exposome.neuro_outcomes_stats import add_fdr_q_values, benjamini_hochberg  # noqa: E402


class NeuroOutcomesStatsTest(unittest.TestCase):
    def test_benjamini_hochberg_known_values(self) -> None:
        pvals = pd.Series([0.01, 0.04, 0.03, None], index=["a", "b", "c", "d"])
        qvals = benjamini_hochberg(pvals)
        self.assertAlmostEqual(qvals.loc["a"], 0.03)
        self.assertAlmostEqual(qvals.loc["b"], 0.04)
        self.assertAlmostEqual(qvals.loc["c"], 0.04)
        self.assertTrue(pd.isna(qvals.loc["d"]))

    def test_add_fdr_q_values_skips_invalid_rows(self) -> None:
        df = pd.DataFrame(
            {
                "status": ["ok", "missing_exposure", "ok"],
                "spearman_p": [0.01, 0.001, 0.04],
                "pearson_p": [0.2, None, 0.8],
                "kendall_p": [0.3, 0.1, 0.6],
                "partial_spearman_p": [None, 0.2, 0.5],
            }
        )
        out = add_fdr_q_values(df)
        self.assertIn("spearman_q", out.columns)
        self.assertAlmostEqual(out.loc[0, "spearman_q"], 0.02)
        self.assertTrue(pd.isna(out.loc[1, "spearman_q"]))
        self.assertTrue((out.loc[[0, 2], ["spearman_q", "pearson_q", "kendall_q"]] <= 1).all().all())

    def test_correlation_table_has_sensitivity_and_fdr_columns(self) -> None:
        mortality = pd.DataFrame(
            {
                "name": [f"C{i}" for i in range(12)],
                "outcome": ["dementia"] * 12,
                "mortality_rate_age_adjusted_per_100k": [2 * i for i in range(12)],
                "mortality_rate_crude_per_100k": [2 * i for i in range(12)],
            }
        )
        master = pd.DataFrame(
            {
                "name": [f"C{i}" for i in range(12)],
                "exposure": list(range(12)),
            }
        )
        out = compute_exposome_correlations(
            mortality_df=mortality,
            master_df=master,
            exposures=["exposure"],
            outcomes=["dementia"],
            covariates=[],
        )
        row = out.iloc[0]
        expected_cols = {
            "spearman_rho",
            "spearman_p",
            "spearman_q",
            "pearson_r",
            "pearson_p",
            "pearson_q",
            "kendall_tau",
            "kendall_p",
            "kendall_q",
            "partial_spearman_rho",
            "partial_spearman_p",
            "partial_spearman_q",
        }
        self.assertTrue(expected_cols.issubset(out.columns))
        self.assertAlmostEqual(row["spearman_rho"], 1.0)
        self.assertAlmostEqual(row["pearson_r"], 1.0)
        self.assertAlmostEqual(row["kendall_tau"], 1.0)
        self.assertAlmostEqual(row["partial_spearman_rho"], 1.0)
        self.assertTrue(0 <= row["spearman_q"] <= 1)


if __name__ == "__main__":
    unittest.main()

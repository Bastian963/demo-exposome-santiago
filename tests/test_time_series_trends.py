"""Tests for the time-series trends analysis (Mann-Kendall + Sen's slope)."""
from __future__ import annotations

import json
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "processed"
FIG_DIR = REPO_ROOT / "figures"

TRENDS_CSV = DATA_DIR / "time_series_trends.csv"
TRENDS_JSON = DATA_DIR / "time_series_trends_summary.json"
FIG_TRENDS = FIG_DIR / "time_series_trends.png"

EXPECTED_VARIABLES = {
    "tmax_mean_annual_c",
    "hot_days_30c",
    "precip_annual_mm",
    "fire_detections",
}


class TimeSeriesTrendsTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if TRENDS_CSV.exists():
            cls.trends = pd.read_csv(TRENDS_CSV)
        else:
            cls.trends = None
        if TRENDS_JSON.exists():
            cls.summary = json.loads(TRENDS_JSON.read_text())
        else:
            cls.summary = None

    def test_csv_exists(self) -> None:
        self.assertTrue(TRENDS_CSV.exists(), f"Missing: {TRENDS_CSV}")

    def test_json_exists(self) -> None:
        self.assertTrue(TRENDS_JSON.exists(), f"Missing: {TRENDS_JSON}")

    def test_figure_exists(self) -> None:
        self.assertTrue(FIG_TRENDS.exists(), f"Missing: {FIG_TRENDS}")
        self.assertGreater(FIG_TRENDS.stat().st_size, 30_000)

    def test_csv_shape(self) -> None:
        if self.trends is None:
            self.skipTest("CSV not visible")
        # 52 communes x 4 variables = 208 rows.
        self.assertEqual(self.trends.shape[0], 208)
        for col in ("name", "variable", "n_years",
                    "sen_slope_per_year", "p_value", "trend_class"):
            self.assertIn(col, self.trends.columns,
                          f"Missing column: {col}")

    def test_variables_covered(self) -> None:
        if self.trends is None:
            self.skipTest("CSV not visible")
        variables = set(self.trends["variable"].unique())
        missing = EXPECTED_VARIABLES - variables
        self.assertFalse(
            missing, f"missing variables: {missing}",
        )

    def test_sen_slope_is_float(self) -> None:
        if self.trends is None:
            self.skipTest("CSV not visible")
        self.assertTrue(
            self.trends["sen_slope_per_year"].dtype.kind == "f",
            f"sen_slope_per_year not float: {self.trends['sen_slope_per_year'].dtype}",
        )

    def test_p_value_in_range(self) -> None:
        if self.trends is None:
            self.skipTest("CSV not visible")
        p = self.trends["p_value"]
        self.assertGreaterEqual(p.min(), 0.0)
        self.assertLessEqual(p.max(), 1.0)

    def test_at_least_one_variable_has_significant_trend(self) -> None:
        """At least one of the 4 variables should have a commune
        with a significant (p<0.05) trend. With 10 years of data
        and 52 communes, some significant trends are expected by
        chance alone, and climate drivers like fire detections
        are known to have increased in central Chile."""
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        per_var = self.summary["per_variable"]
        any_sig = any(
            (v["n_significant_increasing"] + v["n_significant_decreasing"]) >= 1
            for v in per_var.values()
        )
        self.assertTrue(
            any_sig,
            f"no variable has a significant trend: {per_var}",
        )

    def test_n_years_complete(self) -> None:
        if self.trends is None:
            self.skipTest("CSV not visible")
        # Each (commune, variable) should have ~10 years.
        for _, row in self.trends.iterrows():
            self.assertGreaterEqual(
                int(row["n_years"]), 5,
                f"{row['name']} / {row['variable']} has < 5 years",
            )

    def test_trend_class_values(self) -> None:
        if self.trends is None:
            self.skipTest("CSV not visible")
        valid = {"significant_increasing", "significant_decreasing",
                 "no_trend"}
        for cls in self.trends["trend_class"]:
            self.assertIn(
                cls, valid,
                f"unknown trend class: {cls!r}",
            )

    def test_summary_method_documents_mann_kendall(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        self.assertIn("Mann-Kendall", self.summary["method"])
        self.assertIn("Sen", self.summary["method"])


if __name__ == "__main__":
    unittest.main()

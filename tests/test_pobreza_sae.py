"""Tests for the poverty SAE exposome layer (offline, official MDSF workbooks)."""
from __future__ import annotations

import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.pobreza_sae import (  # noqa: E402
    INCOME_FILES,
    MULTI_FILES,
    read_income_year,
    read_multi_year,
)

DATA_DIR = REPO_ROOT / "data" / "processed"
RAW_DIR = REPO_ROOT / "data" / "raw" / "pobreza_sae"


@unittest.skipUnless(RAW_DIR.exists(), f"Missing raw data at {RAW_DIR}")
class ParserTest(unittest.TestCase):
    """Offline parsing tests against the versioned raw workbooks."""

    def test_income_years_have_52_rm_communes(self) -> None:
        for year in INCOME_FILES:
            df = read_income_year(RAW_DIR, year)
            self.assertEqual(len(df), 52, f"income {year}")
            self.assertEqual(df["comuna_code"].nunique(), 52)

    def test_multi_years_have_52_rm_communes(self) -> None:
        for year in MULTI_FILES:
            df = read_multi_year(RAW_DIR, year)
            self.assertEqual(len(df), 52, f"multi {year}")
            self.assertEqual(df["comuna_code"].nunique(), 52)

    def test_income_spot_values_2022(self) -> None:
        df = read_income_year(RAW_DIR, 2022)
        # La Pintana = CUT 13112, Vitacura = CUT 13132
        la_pintana = df.loc[df["comuna_code"] == 13112].iloc[0]
        vitacura = df.loc[df["comuna_code"] == 13132].iloc[0]
        self.assertAlmostEqual(la_pintana["pobreza_ing_2022"], 9.29, places=2)
        self.assertAlmostEqual(vitacura["pobreza_ing_2022"], 0.89, places=2)

    def test_multi_spot_values_2022(self) -> None:
        df = read_multi_year(RAW_DIR, 2022)
        la_pintana = df.loc[df["comuna_code"] == 13112].iloc[0]
        self.assertAlmostEqual(la_pintana["pobreza_multi_2022"], 27.00, places=2)

    def test_income_2024_spot_value(self) -> None:
        df = read_income_year(RAW_DIR, 2024)
        la_pintana = df.loc[df["comuna_code"] == 13112].iloc[0]
        self.assertAlmostEqual(la_pintana["pobreza_ing_2024"], 23.30, places=2)

    def test_sae_type_values_are_mapped(self) -> None:
        df = read_income_year(RAW_DIR, 2024)
        self.assertTrue(
            set(df["pobreza_ing_sae_type_2024"].unique()).issubset(
                {"directa_sintetica", "sintetica"}
            )
        )

    def test_regression_income_not_equal_multi_la_pintana_2022(self) -> None:
        """Guards against reintroducing the pobreza_pct/pobreza_multi_pct
        mislabeling bug (a third-party CSV previously served 2022 IPM
        values under the income-poverty label -- see
        docs/pobreza_sae_methodology.md)."""
        inc = read_income_year(RAW_DIR, 2022)
        multi = read_multi_year(RAW_DIR, 2022)
        inc_val = inc.loc[inc["comuna_code"] == 13112, "pobreza_ing_2022"].iloc[0]
        multi_val = multi.loc[multi["comuna_code"] == 13112, "pobreza_multi_2022"].iloc[0]
        self.assertNotAlmostEqual(inc_val, multi_val, places=1)
        self.assertAlmostEqual(inc_val, 9.29, places=2)
        self.assertAlmostEqual(multi_val, 27.00, places=2)

    def test_change_columns_arithmetic(self) -> None:
        inc17 = read_income_year(RAW_DIR, 2017).set_index("comuna_code")["pobreza_ing_2017"]
        inc22 = read_income_year(RAW_DIR, 2022).set_index("comuna_code")["pobreza_ing_2022"]
        expected = (inc22 - inc17).round(2)
        # Spot check on La Pintana matches the layer's own change column
        # once built (build_pobreza_sae_layer computes the same subtraction).
        self.assertAlmostEqual(expected.loc[13112], round(9.29 - 14.14, 2), places=2)


@unittest.skipUnless(
    (DATA_DIR / "santiago_pobreza_sae.csv").exists(),
    "Missing canonical CSV; run scripts/run_pobreza_sae.py first.",
)
class BuiltLayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.df = pd.read_csv(DATA_DIR / "santiago_pobreza_sae.csv")

    def test_52_communes_no_duplicates(self) -> None:
        self.assertEqual(len(self.df), 52)
        self.assertEqual(self.df["name"].nunique(), 52)
        self.assertEqual(self.df["name"].duplicated().sum(), 0)

    def test_required_columns_present_and_populated(self) -> None:
        required = [
            "pobreza_ing_2017", "pobreza_ing_2020", "pobreza_ing_2022", "pobreza_ing_2024",
            "pobreza_multi_2017", "pobreza_multi_2022", "pobreza_multi_2024",
            "pobreza_ing_change_2017_2022", "pobreza_multi_change_2017_2024",
        ]
        for col in required:
            self.assertIn(col, self.df.columns)
            self.assertEqual(self.df[col].isna().sum(), 0, col)

    def test_la_pintana_spot_values(self) -> None:
        row = self.df.loc[self.df["name"] == "La Pintana"].iloc[0]
        self.assertAlmostEqual(row["pobreza_ing_2022"], 9.29, places=2)
        self.assertAlmostEqual(row["pobreza_multi_2022"], 27.00, places=2)
        self.assertAlmostEqual(row["pobreza_ing_2024"], 23.30, places=2)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome import demography  # noqa: E402


class DemographyTest(unittest.TestCase):
    def test_census_count_columns_coerce_suppressed_cells(self) -> None:
        raw = pd.DataFrame(
            {
                "PERSONAS": ["10", "0", "5"],
                "HOMBRES": ["*", "0", "2"],
                "MUJERES": ["*", "0", "3"],
            }
        )

        out = demography._coerce_census_count_columns(raw, ["PERSONAS", "HOMBRES", "MUJERES"])

        self.assertEqual(out["PERSONAS"].tolist(), [10, 0, 5])
        self.assertTrue(pd.isna(out.loc[0, "HOMBRES"]))
        self.assertTrue(pd.isna(out.loc[0, "MUJERES"]))
        self.assertEqual(out.loc[2, "HOMBRES"], 2)
        self.assertEqual(out.loc[2, "MUJERES"], 3)

    def test_scale_integer_components_matches_total_exactly(self) -> None:
        components = pd.DataFrame(
            {
                "a": [4.0, 5.0],
                "b": [21.0, 5.0],
                "c": [2.0, 1.0],
            }
        )
        total = pd.Series([30, 12])

        out = demography._scale_integer_components_to_total(components, total)

        self.assertEqual(out.sum(axis=1).tolist(), [30, 12])
        self.assertTrue(all(pd.api.types.is_integer_dtype(out[col]) for col in out.columns))
        self.assertTrue((out >= 0).all().all())

    def test_load_commune_demography_handles_suppression_without_string_concat(self) -> None:
        manzanas = pd.DataFrame(
            {
                "COMUNA": [13101, 13101, 13102, 13102],
                "PERSONAS": [10, 20, 7, 13],
                "HOMBRES": ["*", "9", "*", "6"],
                "MUJERES": ["*", "11", "*", "7"],
                "EDAD_0A5": ["*", "2", "1", "*"],
                "EDAD_6A14": ["2", "*", "*", "2"],
                "EDAD_15A64": ["6", "15", "4", "8"],
                "EDAD_65YMAS": ["*", "2", "*", "1"],
            }
        )
        code_name = pd.DataFrame(
            {
                "comuna_code": [13101, 13102],
                "name": ["Santiago", "Cerrillos"],
            }
        )

        with (
            patch.object(demography, "load_region_manzanas", return_value=manzanas),
            patch.object(demography, "load_comuna_code_name_map", return_value=code_name),
        ):
            out = demography.load_commune_demography(Path("cache"))

        numeric_cols = [col for col in out.columns if col != "name"]
        for col in numeric_cols:
            self.assertTrue(pd.api.types.is_numeric_dtype(out[col]), col)
        self.assertEqual((out["pop_male"] + out["pop_female"]).tolist(), out["pop_total"].tolist())
        age_sum = out["pop_0_14"] + out["pop_15_64"] + out["pop_65_plus"]
        self.assertEqual(age_sum.tolist(), out["pop_total"].tolist())
        self.assertEqual(out["name"].tolist(), ["Santiago", "Cerrillos"])


if __name__ == "__main__":
    unittest.main()

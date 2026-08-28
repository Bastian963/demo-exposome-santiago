from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.neuro_hospitalizations import (  # noqa: E402
    aggregate_outcome_hospitalizations,
    classify_egress_age_bin,
    compute_commune_rates,
    compute_exposome_correlations,
    prepare_hospitalization_records,
)


class NeuroHospitalizationsTest(unittest.TestCase):
    def test_classify_egress_age_bin(self) -> None:
        self.assertEqual(classify_egress_age_bin("menor de un año"), "0_14")
        self.assertEqual(classify_egress_age_bin("1 a 9"), "0_14")
        self.assertEqual(classify_egress_age_bin("10 a 19"), "0_14")
        self.assertEqual(classify_egress_age_bin("20 a 29"), "15_64")
        self.assertEqual(classify_egress_age_bin("60 a 69"), "65_plus")
        self.assertEqual(classify_egress_age_bin("70 a 79"), "65_plus")
        self.assertEqual(classify_egress_age_bin("90 y más"), "65_plus")

    def test_prepare_records_filters_rm_and_maps_fields(self) -> None:
        raw = pd.DataFrame(
            {
                "ANO_EGRESO": [2006, 2006, 2006],
                "COMUNA_RESIDENCIA": [13101, 13101, 5101],
                "GLOSA_COMUNA_RESIDENCIA": ["Santiago", "Santiago", "Valparaíso"],
                "REGION_RESIDENCIA": [13, 13, 5],
                "GLOSA_REGION_RESIDENCIA": ["Metropolitana de Santiago", "Metropolitana de Santiago", "Valparaíso"],
                "DIAG1": ["F32", "I64", "F20"],
                "GRUPO_EDAD": ["30 a 39", "80 a 89", "40 a 49"],
                "SEXO": ["MUJER", "HOMBRE", "HOMBRE"],
                "DIAS_ESTADA": [4, 10, 3],
                "CONDICION_EGRESO": [1, 2, 1],
            }
        )
        code_map = pd.DataFrame({"comuna_code": [13101], "name": ["Santiago"]})
        cfg = {
            "neuro_hospitalizations": {
                "region_code": 13,
                "years": [2006],
                "source": {
                    "region_filter": "Metropolitana",
                    "in_hospital_death_values": ["2"],
                    "columns": {
                        "year": "ANO_EGRESO",
                        "commune_code": "COMUNA_RESIDENCIA",
                        "commune_name": "GLOSA_COMUNA_RESIDENCIA",
                        "region_code": "REGION_RESIDENCIA",
                        "region_name": "GLOSA_REGION_RESIDENCIA",
                        "cause": "DIAG1",
                        "age_group": "GRUPO_EDAD",
                        "sex": "SEXO",
                        "days_stay": "DIAS_ESTADA",
                        "discharge_condition": "CONDICION_EGRESO",
                    },
                },
            }
        }
        out = prepare_hospitalization_records(raw, cfg, code_map)
        self.assertEqual(len(out), 2)
        self.assertEqual(out["age_bin"].tolist(), ["15_64", "65_plus"])
        self.assertEqual(out["in_hospital_death"].tolist(), [0, 1])
        self.assertAlmostEqual(out["days_stay"].sum(), 14.0)

    def test_aggregate_and_rate_calculation(self) -> None:
        records = pd.DataFrame(
            [
                {"name": "Alpha", "year": 2006, "age_bin": "15_64", "cause_code": "F32", "admissions": 1.0, "days_stay": 4.0, "in_hospital_death": 0},
                {"name": "Alpha", "year": 2006, "age_bin": "65_plus", "cause_code": "G30", "admissions": 1.0, "days_stay": 8.0, "in_hospital_death": 0},
                {"name": "Beta", "year": 2006, "age_bin": "65_plus", "cause_code": "I64", "admissions": 1.0, "days_stay": 10.0, "in_hospital_death": 1},
            ]
        )
        aggregated = aggregate_outcome_hospitalizations(records)
        demo = pd.DataFrame(
            {
                "name": ["Alpha", "Beta"],
                "pop_total": [1000, 1000],
                "pop_0_14": [200, 200],
                "pop_15_64": [600, 600],
                "pop_65_plus": [200, 200],
            }
        )
        rates = compute_commune_rates(aggregated, demo, [2006])
        mood_alpha = rates[(rates["name"] == "Alpha") & (rates["outcome"] == "mood")].iloc[0]
        self.assertAlmostEqual(mood_alpha["hospital_admissions_total"], 1.0)
        self.assertAlmostEqual(mood_alpha["hospital_days_total"], 4.0)
        self.assertIn("hospital_rate_age_adjusted_per_100k", rates.columns)

    def test_correlation_table_returns_expected_rows(self) -> None:
        hospital = pd.DataFrame(
            {
                "name": [f"C{i}" for i in range(12)] * 2,
                "outcome": ["mental_all"] * 12 + ["cerebrovascular"] * 12,
                "hospital_rate_age_adjusted_per_100k": list(range(10, 22)) + list(range(30, 42)),
                "hospital_rate_crude_per_100k": list(range(10, 22)) + list(range(30, 42)),
            }
        )
        master = pd.DataFrame(
            {
                "name": [f"C{i}" for i in range(12)],
                "pm25_pop_weighted": list(range(12)),
                "nse_index": list(range(100, 112)),
                "demo_pct_pop_65_plus": [10 + i for i in range(12)],
            }
        )
        out = compute_exposome_correlations(
            hospital_df=hospital,
            master_df=master,
            exposures=["pm25_pop_weighted"],
            outcomes=["mental_all", "cerebrovascular"],
            covariates=["nse_index", "demo_pct_pop_65_plus"],
        )
        self.assertEqual(len(out), 2)
        self.assertTrue((out["status"] == "ok").all())


if __name__ == "__main__":
    unittest.main()

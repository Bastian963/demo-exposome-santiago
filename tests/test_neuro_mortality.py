from __future__ import annotations

import json
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.neuro_mortality import (  # noqa: E402
    AGE_BINS,
    aggregate_outcome_deaths,
    classify_age_bin,
    compute_commune_rates,
    compute_exposome_correlations,
    prepare_mortality_records,
)

DATA_DIR = REPO_ROOT / "data" / "processed"
MORT_CSV = DATA_DIR / "santiago_neuro_mortality_2018_2022.csv"
MORT_GEOJSON = DATA_DIR / "santiago_neuro_mortality_2018_2022.geojson"
MORT_META = DATA_DIR / "santiago_neuro_mortality_2018_2022_metadata.json"
MORT_FIG = REPO_ROOT / "figures" / "neuro_outcomes_santiago_4panel.png"


class NeuroMortalityTest(unittest.TestCase):
    def test_classify_age_bin_from_number_and_text(self) -> None:
        self.assertEqual(classify_age_bin(7, None), "0_14")
        self.assertEqual(classify_age_bin(45, None), "15_64")
        self.assertEqual(classify_age_bin(80, None), "65_plus")
        self.assertEqual(classify_age_bin(None, "15 a 64 años"), "15_64")
        self.assertEqual(classify_age_bin(None, "65 y más"), "65_plus")
        self.assertEqual(classify_age_bin(10, None, "2"), "0_14")
        self.assertEqual(classify_age_bin(28, None, "3"), "0_14")
        self.assertIsNone(classify_age_bin(5, None, "0"))

    def test_prepare_records_accepts_row_level_or_count_column(self) -> None:
        raw = pd.DataFrame(
            {
                "anio": [2020, 2020, 2020, 2021],
                "causa": ["G30.1", "I64", "X70", "F03"],
                "comuna": ["Santiago", "Providencia", "Santiago", "Providencia"],
                "edad": [80, 76, 30, 90],
                "n": [2, 1, 3, 4],
            }
        )
        code_map = pd.DataFrame(
            {
                "comuna_code": [13101, 13114],
                "name": ["Santiago", "Providencia"],
            }
        )
        cfg = {
            "neuro_mortality": {
                "years": [2020, 2021],
                "source": {
                    "columns": {
                        "year": "anio",
                        "cause": "causa",
                        "commune_name": "comuna",
                        "age": "edad",
                        "deaths": "n",
                    }
                },
            }
        }
        out = prepare_mortality_records(raw, cfg, code_map)
        self.assertEqual(len(out), 4)
        self.assertAlmostEqual(out["deaths"].sum(), 10.0)
        self.assertEqual(sorted(out["age_bin"].dropna().unique().tolist()), ["15_64", "65_plus"])

    def test_prepare_records_filters_region_and_maps_age_type(self) -> None:
        raw = pd.DataFrame(
            {
                "AÑO": [2019, 2019, 2019],
                "COD_COMUNA": [13101, 13101, 13102],
                "COMUNA": ["Santiago", "Santiago", "Cerrillos"],
                "NOMBRE_REGION": ["Metropolitana de Santiago", "Valparaíso", "Metropolitana de Santiago"],
                "DIAG1": ["G30", "G30", "I64"],
                "EDAD_TIPO": [2, 1, 4],
                "EDAD_CANT": [10, 80, 1],
            }
        )
        code_map = pd.DataFrame(
            {
                "comuna_code": [13101, 13102],
                "name": ["Santiago", "Cerrillos"],
            }
        )
        cfg = {
            "neuro_mortality": {
                "years": [2019],
                "source": {
                    "region_filter": "Metropolitana",
                    "columns": {
                        "year": "AÑO",
                        "commune_code": "COD_COMUNA",
                        "commune_name": "COMUNA",
                        "region_name": "NOMBRE_REGION",
                        "cause": "DIAG1",
                        "age": "EDAD_CANT",
                        "age_type": "EDAD_TIPO",
                    }
                },
            }
        }
        out = prepare_mortality_records(raw, cfg, code_map)
        self.assertEqual(len(out), 2)
        self.assertEqual(out["name"].tolist(), ["Santiago", "Cerrillos"])
        self.assertEqual(out["age_bin"].tolist(), ["0_14", "0_14"])

    def test_aggregate_and_rate_calculation(self) -> None:
        records = pd.DataFrame(
            [
                {"name": "Alpha", "year": 2020, "age_bin": "65_plus", "cause_code": "G30", "deaths": 5.0},
                {"name": "Alpha", "year": 2021, "age_bin": "65_plus", "cause_code": "F03", "deaths": 3.0},
                {"name": "Alpha", "year": 2021, "age_bin": "15_64", "cause_code": "X70", "deaths": 2.0},
                {"name": "Beta", "year": 2020, "age_bin": "65_plus", "cause_code": "I64", "deaths": 4.0},
                {"name": "Beta", "year": 2021, "age_bin": "65_plus", "cause_code": "I61", "deaths": 6.0},
            ]
        )
        aggregated = aggregate_outcome_deaths(records)
        demo = pd.DataFrame(
            {
                "name": ["Alpha", "Beta"],
                "pop_total": [1000, 1000],
                "pop_0_14": [200, 200],
                "pop_15_64": [600, 600],
                "pop_65_plus": [200, 200],
            }
        )
        rates = compute_commune_rates(aggregated, demo, [2020, 2021])
        dementia_alpha = rates[(rates["name"] == "Alpha") & (rates["outcome"] == "dementia")].iloc[0]
        self.assertAlmostEqual(dementia_alpha["mortality_deaths_total"], 8.0)
        self.assertAlmostEqual(dementia_alpha["mortality_rate_crude_per_100k"], 400.0)
        self.assertGreater(dementia_alpha["mortality_rate_age_adjusted_per_100k"], 0.0)
        self.assertIn("mortality_rate_65_plus_per_100k", rates.columns)
        self.assertEqual(set(AGE_BINS), {"0_14", "15_64", "65_plus"})

    def test_correlation_table_returns_expected_rows(self) -> None:
        mortality = pd.DataFrame(
            {
                "name": [f"C{i}" for i in range(12)] * 2,
                "outcome": ["dementia"] * 12 + ["cerebrovascular"] * 12,
                "mortality_rate_age_adjusted_per_100k": list(range(10, 22)) + list(range(30, 42)),
                "mortality_rate_crude_per_100k": list(range(10, 22)) + list(range(30, 42)),
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
            mortality_df=mortality,
            master_df=master,
            exposures=["pm25_pop_weighted"],
            outcomes=["dementia", "cerebrovascular"],
            covariates=["nse_index", "demo_pct_pop_65_plus"],
        )
        self.assertEqual(len(out), 2)
        self.assertTrue((out["status"] == "ok").all())
        self.assertTrue((out["n_pairs"] == 12).all())
        for col in [
            "pearson_r",
            "pearson_p",
            "pearson_q",
            "kendall_tau",
            "kendall_p",
            "kendall_q",
            "spearman_q",
            "partial_spearman_q",
        ]:
            self.assertIn(col, out.columns)


class NeuroMortalityOutputTest(MaterializedArtifactTestCase):
    """Offline tests against the on-disk mortality outputs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.df = pd.read_csv(MORT_CSV) if MORT_CSV.exists() else None
        cls.metadata = json.loads(MORT_META.read_text()) if MORT_META.exists() else None

    def test_csv_and_geojson_exist(self) -> None:
        self.assertTrue(MORT_CSV.exists())
        self.assertTrue(MORT_GEOJSON.exists())
        self.assertTrue(MORT_META.exists())

    def test_figure_exists(self) -> None:
        self.assertTrue(MORT_FIG.exists())
        self.assertGreater(MORT_FIG.stat().st_size, 50_000)

    def test_csv_shape_10_outcomes_x_52(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(self.df["name"].nunique(), 52)
        self.assertEqual(self.df.shape[0], 520)
        self.assertEqual(set(self.df["outcome"].unique()),
                         {"all_cause", "alzheimer", "cerebrovascular", "dementia", "parkinsonism",
                          "cardiovascular", "respiratory",
                          "respiratory_pneumonia", "respiratory_acute_lower", "respiratory_copd"})

    def test_rate_sanity(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in ("mortality_rate_crude_per_100k", "mortality_rate_age_adjusted_per_100k"):
            self.assertGreaterEqual(self.df[col].min(), 0.0)
            self.assertLessEqual(self.df[col].max(), 5000.0,
                                 f"{col} max implausibly high")
            self.assertLess(self.df[col].isna().sum(), 0.05 * len(self.df),
                            f"{col} has too many NaN")

    def test_geojson_matches_csv(self) -> None:
        if not MORT_GEOJSON.exists() or self.df is None:
            self.skipTest("geojson or csv not visible")
        import geopandas as gpd
        gdf = gpd.read_file(MORT_GEOJSON)
        self.assertEqual(gdf["name"].nunique(), 52)
        self.assertEqual(set(gdf["name"]), set(self.df["name"]))

    def test_metadata_documents_coverage_window(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata not visible")
        self.assertIn("coverage_window", self.metadata)
        cw = self.metadata["coverage_window"]
        self.assertEqual(cw["start"], 2018)
        self.assertEqual(cw["end"], 2022)
        self.assertEqual(cw["n_years"], 5)
        # Must mention the temporal mismatch with hospitalizations.
        self.assertIn("temporal_mismatch_with_hospitalizations", cw)

    def test_metadata_years_aligned(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata not visible")
        self.assertEqual(self.metadata["years"], [2018, 2019, 2020, 2021, 2022])


if __name__ == "__main__":
    unittest.main()

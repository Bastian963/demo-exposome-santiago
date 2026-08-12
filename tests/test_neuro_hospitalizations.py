from __future__ import annotations

import json
import hashlib
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
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

DATA_DIR = REPO_ROOT / "data" / "processed"
HOSP_CSV = DATA_DIR / "santiago_neuro_hospitalizations_2006_2006.csv"
HOSP_GEOJSON = DATA_DIR / "santiago_neuro_hospitalizations_2006_2006.geojson"
HOSP_META = DATA_DIR / "santiago_neuro_hospitalizations_2006_2006_metadata.json"
HOSP_FIG = REPO_ROOT / "figures" / "neuro_outcomes_santiago_4panel.png"
ANNUAL_DIR = (
    DATA_DIR / "cl/santiago/santiago_communes/neuro_hospitalizations"
)
ANNUAL_EXPECTED = ANNUAL_DIR / "santiago_neuro_hospitalizations_annual_expected.csv.gz"
ANNUAL_MANIFEST = ANNUAL_DIR / "manifest.json"


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


class NeuroHospitalizationsOutputTest(MaterializedArtifactTestCase):
    """Offline tests against the on-disk hospitalization outputs (2006 only)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.df = pd.read_csv(HOSP_CSV) if HOSP_CSV.exists() else None
        cls.metadata = json.loads(HOSP_META.read_text()) if HOSP_META.exists() else None

    def test_csv_and_geojson_exist(self) -> None:
        self.assertTrue(HOSP_CSV.exists())
        self.assertTrue(HOSP_GEOJSON.exists())
        self.assertTrue(HOSP_META.exists())

    def test_figure_exists(self) -> None:
        self.assertTrue(HOSP_FIG.exists())
        self.assertGreater(HOSP_FIG.stat().st_size, 50_000)

    def test_csv_shape_15_outcomes_x_52(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(self.df["name"].nunique(), 52)
        self.assertEqual(self.df.shape[0], 780)
        self.assertEqual(set(self.df["outcome"].unique()),
                         {"all_cause", "alzheimer", "anxiety_stress", "cerebrovascular",
                          "dementia", "mental_all", "mood", "parkinsonism",
                          "psychosis", "substance",
                          "cardiovascular", "respiratory", "respiratory_pneumonia",
                          "respiratory_acute_lower", "respiratory_copd"})

    def test_rate_sanity(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in ("hospital_rate_crude_per_100k", "hospital_rate_age_adjusted_per_100k"):
            self.assertGreaterEqual(self.df[col].min(), 0.0)
            self.assertLessEqual(self.df[col].max(), 30000.0,
                                 f"{col} max implausibly high")

    def test_los_sanity(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        # Mean LOS is sensitive to outliers in small communes; we only
        # check it is in a plausible order of magnitude (< 3 years).
        self.assertGreaterEqual(self.df["hospital_mean_los_days"].min(), 0.0)
        self.assertLessEqual(self.df["hospital_mean_los_days"].max(), 1000.0,
                             "mean LOS > 3 years is implausible for any outcome")

    def test_geojson_matches_csv(self) -> None:
        if not HOSP_GEOJSON.exists() or self.df is None:
            self.skipTest("geojson or csv not visible")
        import geopandas as gpd
        gdf = gpd.read_file(HOSP_GEOJSON)
        self.assertEqual(gdf["name"].nunique(), 52)
        self.assertEqual(set(gdf["name"]), set(self.df["name"]))

    def test_metadata_documents_coverage_window(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata not visible")
        self.assertIn("coverage_window", self.metadata)
        cw = self.metadata["coverage_window"]
        self.assertEqual(cw["start"], 2006)
        self.assertEqual(cw["end"], 2006)
        self.assertEqual(cw["n_years"], 1)
        # Must warn about the temporal mismatch.
        self.assertIn("temporal_mismatch", cw)
        self.assertIn("exposome", cw["temporal_mismatch"].lower())

    def test_metadata_documents_coverage_gap(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata not visible")
        self.assertIn("coverage_gap", self.metadata)
        gap = self.metadata["coverage_gap"]
        self.assertEqual(gap["status"], "documented_known_gap")
        self.assertIn(2017, gap["missing_years"])
        self.assertIn(2023, gap["missing_years"])
        self.assertGreaterEqual(len(gap["remediation_steps"]), 4)
        self.assertIn("estimated_effort_hours", gap)

    def test_metadata_use_cases_split(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata not visible")
        self.assertIn("use_cases_with_2006_only", self.metadata)
        self.assertIn("use_cases_requiring_full_window", self.metadata)
        self.assertGreaterEqual(len(self.metadata["use_cases_with_2006_only"]), 2)
        self.assertGreaterEqual(len(self.metadata["use_cases_requiring_full_window"]), 2)


class AnnualHospitalizationsMaterializedTest(MaterializedArtifactTestCase):
    """Contract tests for the annual 2011–2020 confirmatory input."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.annual = pd.read_csv(ANNUAL_EXPECTED, dtype={"spatial_id": str})
        cls.manifest = json.loads(ANNUAL_MANIFEST.read_text(encoding="utf-8"))

    def test_complete_commune_year_outcome_cube(self) -> None:
        self.assertEqual(len(self.annual), 52 * 10 * 16)
        self.assertEqual(self.annual["spatial_id"].nunique(), 52)
        self.assertEqual(self.annual["outcome"].nunique(), 16)
        self.assertEqual(set(self.annual["year"]), set(range(2011, 2021)))
        self.assertEqual(
            self.annual.duplicated(["spatial_id", "year", "outcome"]).sum(), 0
        )
        observed_cells = set(
            self.annual[["spatial_id", "year", "outcome"]].itertuples(
                index=False, name=None
            )
        )
        expected_cells = {
            (spatial_id, year, outcome)
            for spatial_id in self.annual["spatial_id"].unique()
            for year in range(2011, 2021)
            for outcome in self.annual["outcome"].unique()
        }
        self.assertEqual(observed_cells, expected_cells)

    def test_counts_expected_values_and_population_are_valid(self) -> None:
        required = {
            "spatial_id",
            "spatial_name",
            "year",
            "outcome",
            "observed",
            "expected",
            "population_person_years",
        }
        self.assertEqual(set(self.annual.columns), required)
        self.assertFalse(self.annual.isna().any().any())
        self.assertTrue(self.annual["observed"].ge(0).all())
        self.assertTrue(self.annual["expected"].gt(0).all())
        self.assertTrue(self.annual["population_person_years"].gt(0).all())

    def test_manifest_hash_matches_annual_expected_table(self) -> None:
        asset = next(
            row
            for row in self.manifest["assets"]
            if row["path"] == ANNUAL_EXPECTED.name
        )
        digest = hashlib.sha256(ANNUAL_EXPECTED.read_bytes()).hexdigest()
        self.assertEqual(digest, asset["sha256"])
        self.assertEqual(ANNUAL_EXPECTED.stat().st_size, asset["bytes"])


if __name__ == "__main__":
    unittest.main()

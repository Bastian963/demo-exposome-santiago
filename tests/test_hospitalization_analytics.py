from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.hospitalization_analytics import (  # noqa: E402
    ALL_OUTCOMES,
    HARMONIZED_AGE_BANDS,
    aggregate_hospitalization_stream,
    archive_inventory,
    complete_cube_with_population,
    compute_window_smr,
    harmonize_age_group,
    normalize_sex,
)


SOURCE_CONFIG = {
    "sep": ";",
    "encoding": "latin1",
    "chunksize": 2,
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
}


class HospitalizationAnalyticsTest(unittest.TestCase):
    def test_harmonizes_source_variants(self) -> None:
        self.assertEqual(normalize_sex("HOMBRE"), "male")
        self.assertEqual(normalize_sex("2"), "female")
        self.assertEqual(harmonize_age_group("MENOR DE 1 AÑO"), "0_9")
        self.assertEqual(harmonize_age_group("15 A 19 AÑOS"), "10_19")
        self.assertEqual(harmonize_age_group("80 AÑOS Y MÁS"), "80_plus")

    def test_streams_zip_and_builds_population_completed_cube(self) -> None:
        rows = pd.DataFrame(
            [
                [2018, 13101, "Santiago", 13, "Metropolitana", "I21.0", "70 a 79", "HOMBRE", 3, 1],
                [2018, 13101, "Santiago", 13, "Metropolitana", "J44.1", "60 A 69 AÑOS", "MUJER", 5, 2],
                [2018, 13101, "Santiago", 13, "Metropolitana", "F32", "15 A 19 AÑOS", "2", 2, 1],
                [2018, 5101, "Valparaíso", 5, "Valparaíso", "I21", "70 a 79", "HOMBRE", 1, 1],
                ["*", 13101, "Santiago", 13, "Metropolitana", "I63", "70 a 79", "HOMBRE", 1, 1],
                [2018, 99999, "No válida", 13, "Metropolitana", "I63", "70 a 79", "HOMBRE", 1, 1],
            ],
            columns=list(SOURCE_CONFIG["columns"].values()),
        )
        crosswalk = pd.DataFrame(
            {
                "spatial_id": ["13101", "13102"],
                "spatial_name": ["Santiago", "Cerrillos"],
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "EGRESOS_2018.zip"
            csv_bytes = rows.to_csv(index=False, sep=";").encode("latin1")
            dictionary = b"test data dictionary"
            with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
                archive.writestr("EGRE_DATOS_ABIERTOS_2018.csv", csv_bytes)
                archive.writestr("Diccionario.xlsx", dictionary)

            inventory = archive_inventory([archive_path])
            self.assertTrue(inventory[0]["crc_ok"])
            self.assertEqual(
                inventory[0]["dictionary_sha256"], hashlib.sha256(dictionary).hexdigest()
            )

            cube_counts, qc = aggregate_hospitalization_stream(
                [archive_path], SOURCE_CONFIG, crosswalk, [2018], chunksize=2
            )

        all_cause = cube_counts[cube_counts["outcome"] == "all_cause"]
        self.assertEqual(int(all_cause["admissions"].sum()), 3)
        self.assertEqual(int(qc["totals"]["unknown_year_rows"]), 1)
        self.assertEqual(int(qc["totals"]["invalid_commune_rows"]), 1)
        self.assertEqual(int(cube_counts["in_hospital_deaths"].sum() > 0), 1)

        population_rows = []
        for spatial_id, spatial_name in zip(
            crosswalk["spatial_id"], crosswalk["spatial_name"]
        ):
            for sex in ("male", "female"):
                for age_band in HARMONIZED_AGE_BANDS:
                    population_rows.append(
                        {
                            "spatial_id": spatial_id,
                            "spatial_name": spatial_name,
                            "year": 2018,
                            "sex": sex,
                            "age_band": age_band,
                            "population": 100,
                        }
                    )
        population = pd.DataFrame(population_rows)
        cube = complete_cube_with_population(cube_counts, population)
        expected_rows = 2 * 2 * len(HARMONIZED_AGE_BANDS) * len(ALL_OUTCOMES)
        self.assertEqual(len(cube), expected_rows)

        summary = compute_window_smr(cube, [2018], "test")
        regional_all_cause = summary[summary["outcome"] == "all_cause"]
        self.assertEqual(int(regional_all_cause["observed"].sum()), 3)
        self.assertAlmostEqual(float(regional_all_cause["expected"].sum()), 3.0)


if __name__ == "__main__":
    unittest.main()

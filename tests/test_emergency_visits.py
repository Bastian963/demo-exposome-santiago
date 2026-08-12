from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pandas as pd

from exposome.emergency_visits import (
    add_heat_exposures,
    aggregate_emergency_zip,
    build_regional_temperature,
    build_stable_crosswalk,
    fit_poisson_hac,
    retention_verdict,
)


BASE_COLUMNS = [
    "IdEstablecimiento",
    "NEstablecimiento",
    "IdCausa",
    "GlosaCausa",
    "Total",
    "Menores_1",
    "De_1_a_4",
    "De_5_a_14",
    "De_15_a_64",
    "De_65_y_mas",
    "fecha",
    "semana",
    "GLOSATIPOESTABLECIMIENTO",
    "GLOSATIPOATENCION",
    "GlosaTipoCampana",
]
GEO_COLUMNS = [
    "CodigoRegion",
    "NombreRegion",
    "CodigoDependencia",
    "NombreDependencia",
    "CodigoComuna",
    "NombreComuna",
]


def write_zip(path: Path, rows: list[dict[str, str]], *, geography: bool) -> None:
    columns = BASE_COLUMNS + (GEO_COLUMNS if geography else [])
    csv_path = path.with_suffix(".csv")
    with csv_path.open("w", encoding="latin1", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname=csv_path.name)
    csv_path.unlink()


def row(
    *,
    establishment: str = "A",
    cause: str = "12",
    total: int = 10,
    date: str = "01/01/2024",
    region: str = "13",
) -> dict[str, str]:
    values = {
        "IdEstablecimiento": establishment,
        "NEstablecimiento": f"Hospital {establishment}",
        "IdCausa": cause,
        "GlosaCausa": cause,
        "Total": str(total),
        "Menores_1": "0",
        "De_1_a_4": "0",
        "De_5_a_14": "0",
        "De_15_a_64": str(total // 2),
        "De_65_y_mas": str(total - total // 2),
        "fecha": date,
        "semana": "1",
        "GLOSATIPOESTABLECIMIENTO": "Hospital",
        "GLOSATIPOATENCION": "Indiferenciado",
        "GlosaTipoCampana": "Ninguna",
        "CodigoRegion": region,
        "NombreRegion": "Metropolitana" if region == "13" else "Otra",
        "CodigoDependencia": "1",
        "NombreDependencia": "Servicio",
        "CodigoComuna": "13101" if region == "13" else "05101",
        "NombreComuna": "Santiago" if region == "13" else "Valparaíso",
    }
    return values


class EmergencyVisitAggregationTests(unittest.TestCase):
    def test_direct_geography_keeps_causes_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "AtencionesUrgencia2024.zip"
            rows = [
                row(cause="12", total=10),
                row(cause="13", total=4),
                row(cause="12", total=99, establishment="B", region="5"),
            ]
            write_zip(path, rows, geography=True)
            result = aggregate_emergency_zip(path, year=2024)
        circulatory = result.daily[result.daily["outcome"].eq("circulatory")].iloc[0]
        ami = result.daily[result.daily["outcome"].eq("ami")].iloc[0]
        self.assertEqual(circulatory["count_total"], 10)
        self.assertEqual(ami["count_total"], 4)
        self.assertEqual(circulatory["reporting_establishments"], 1)
        self.assertEqual(result.diagnostics["age_mismatch_rows"], 0)

    def test_historical_rows_use_only_stable_rm_crosswalk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "AtencionesUrgencia2022.zip"
            rows = [row(establishment="A"), row(establishment="B"), row(establishment="C")]
            write_zip(path, rows, geography=False)
            result = aggregate_emergency_zip(
                path,
                year=2022,
                stable_crosswalk={"A": "13", "B": "5"},
            )
        self.assertEqual(result.daily["count_total"].sum(), 10)
        self.assertAlmostEqual(result.diagnostics["mapped_relevant_fraction"], 2 / 3)

    def test_crosswalk_excludes_location_conflicts(self) -> None:
        records = pd.DataFrame(
            [
                ["A", 2023, "13", "13101", "Santiago"],
                ["A", 2024, "13", "13101", "Santiago"],
                ["B", 2023, "13", "13101", "Santiago"],
                ["B", 2024, "13", "13102", "Cerrillos"],
                ["C", 2023, "13", np.nan, np.nan],
                ["C", 2024, "13", np.nan, np.nan],
            ],
            columns=["establishment_id", "year", "region_code", "commune_code", "commune_name"],
        )
        stable, summary = build_stable_crosswalk(records)
        self.assertEqual(stable, {"A": "13", "C": "13"})
        self.assertFalse(summary.set_index("establishment_id").loc["B", "stable"])


class EmergencyVisitExposureTests(unittest.TestCase):
    def test_population_weighted_temperature_and_lags(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = [f"C{i:02d}" for i in range(52)]
            demography = pd.DataFrame({"name": names, "pop_total": [1] * 51 + [49]})
            climate_rows = []
            for day in pd.date_range("2024-01-01", periods=10):
                for index, name in enumerate(names):
                    value = 10.0 if index < 51 else 20.0
                    climate_rows.append(
                        {
                            "name": name,
                            "date": day,
                            "temperature_2m_max": value,
                            "temperature_2m_mean": value - 5,
                            "apparent_temperature_max": value + 1,
                            "precipitation_sum": 0,
                        }
                    )
            climate = pd.DataFrame(climate_rows)
            climate_path = root / "climate.csv"
            demography_path = root / "demography.csv"
            climate.to_csv(climate_path, index=False)
            demography.to_csv(demography_path, index=False)
            regional, metadata = build_regional_temperature(climate_path, demography_path)
        self.assertEqual(metadata["communes"], 52)
        self.assertAlmostEqual(regional.iloc[0]["temperature_2m_max"], 14.9)
        exposed, thresholds = add_heat_exposures(regional)
        self.assertIn("heat_excess_lag03", exposed)
        self.assertAlmostEqual(thresholds["temperature_2m_max"], 14.9)

    def test_poisson_recovers_known_heat_effect(self) -> None:
        rng = np.random.default_rng(42)
        dates = pd.date_range("2023-01-01", periods=365)
        exposure = np.tile([0.0, 1.0, 2.0, 3.0, 0.0], 73)
        reporters = np.full(len(dates), 100)
        expected = reporters * np.exp(1.2 + 0.12 * exposure)
        frame = pd.DataFrame(
            {
                "date": dates,
                "count": rng.poisson(expected),
                "reporting_establishments": reporters,
                "heat_excess_lag03": exposure,
                "stratum": dates.to_period("M").astype(str)
                + "_"
                + dates.dayofweek.astype(str),
            }
        )
        result = fit_poisson_hac(frame, exposure="heat_excess_lag03")
        self.assertTrue(result["converged"])
        self.assertAlmostEqual(result["beta"], 0.12, delta=0.04)

    def test_valid_null_is_retained_but_bad_crosswalk_drops_historical_years(self) -> None:
        dates = pd.date_range("2023-01-01", periods=100)
        frame = pd.DataFrame(
            {
                "date": dates,
                "heat_day": [1] * 60 + [0] * 40,
                "reporting_establishments": [100] * 100,
            }
        )
        null = {"beta": 0.0, "p_value": 1.0, "converged": True}
        verdict = retention_verdict(
            direct_frame=frame,
            primary_result=null,
            nb_result=null,
            placebo_result=null,
            yearly_diagnostics=[{"year": 2022, "mapped_relevant_fraction": 0.95}],
            expected_direct_days=100,
        )
        self.assertEqual(verdict["verdict"], "keep_direct_years")
        self.assertEqual(verdict["direct_gate_reasons"], [])


if __name__ == "__main__":
    unittest.main()

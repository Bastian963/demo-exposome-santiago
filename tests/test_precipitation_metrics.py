from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.precipitation import calculate_precipitation_metrics  # noqa: E402


class PrecipitationMetricsTest(unittest.TestCase):
    def test_calculates_chronic_extreme_and_latest_year_metrics(self) -> None:
        rows = []
        series = {
            2023: [0, 0, 2, 12, 0, 25, 0, 0, 0, 5],
            2024: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
        }
        for year, values in series.items():
            for day, value in enumerate(values, start=1):
                rows.append(
                    {
                        "name": "Alpha",
                        "date": f"{year}-01-{day:02d}",
                        "precipitation_mm": value,
                    }
                )

        df = pd.DataFrame(rows)
        out = calculate_precipitation_metrics(df, latest_year=2024)
        self.assertEqual(len(out), 1)
        row = out.iloc[0]

        self.assertEqual(row["name"], "Alpha")
        self.assertAlmostEqual(row["precip_annual_mean_mm"], 27.0)
        self.assertAlmostEqual(row["precip_annual_sd_mm"], 17.0)
        self.assertAlmostEqual(row["precip_annual_cv"], 17.0 / 27.0)
        self.assertAlmostEqual(row["precip_wet_days"], 7.0)
        self.assertAlmostEqual(row["precip_wet_day_pct"], 70.0)
        self.assertAlmostEqual(row["precip_heavy_days_10mm"], 1.0)
        self.assertAlmostEqual(row["precip_very_heavy_days_20mm"], 0.5)
        self.assertAlmostEqual(row["precip_rx1day_mm"], 13.0)
        self.assertAlmostEqual(row["precip_rx5day_mm"], 22.0)
        self.assertAlmostEqual(row["precip_cdd_days"], 1.5)
        self.assertAlmostEqual(row["precip_cwd_days"], 6.0)
        self.assertAlmostEqual(row["precip_intensity_wet_day_mm"], 6.0)
        self.assertAlmostEqual(row["precip_winter_mean_mm"], 0.0)
        self.assertAlmostEqual(row["precip_summer_mean_mm"], 27.0)
        self.assertAlmostEqual(row["precip_latest_year_mm"], 10.0)
        self.assertAlmostEqual(row["precip_latest_anomaly_mm"], -34.0)
        self.assertAlmostEqual(row["precip_latest_anomaly_pct"], -77.272727, places=5)
        self.assertEqual(row["precip_n_years"], 2)
        self.assertEqual(row["precip_n_days"], 20)
        self.assertAlmostEqual(row["precip_extremes_index"], 50.0)

    def test_extremes_index_is_bounded_for_multiple_communes(self) -> None:
        df = pd.DataFrame(
            [
                {"name": "Dry", "date": "2024-01-01", "precipitation_mm": 0},
                {"name": "Dry", "date": "2024-01-02", "precipitation_mm": 0},
                {"name": "Wet", "date": "2024-01-01", "precipitation_mm": 20},
                {"name": "Wet", "date": "2024-01-02", "precipitation_mm": 30},
            ]
        )

        out = calculate_precipitation_metrics(df, latest_year=2024)

        self.assertTrue(out["precip_extremes_index"].between(0, 100).all())
        wet_index = out.loc[out["name"] == "Wet", "precip_extremes_index"].iloc[0]
        dry_index = out.loc[out["name"] == "Dry", "precip_extremes_index"].iloc[0]
        self.assertGreater(wet_index, dry_index)


if __name__ == "__main__":
    unittest.main()

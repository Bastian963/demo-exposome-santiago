"""The annual wildfire product must be a per-year frame, not a multi-year summary.

`build_wildfire_layer` collapses every year into one row per unit and adds
multi-year metrics; `fire_trend_km2_per_decade` needs at least three years to
fit a slope. The temporal pipeline calls the wildfire adapter one year at a
time, so it used to get a summary frame whose trend merge had nothing to merge:
`pd.DataFrame([])` carries no `name` column, and the merge died with
`KeyError: 'name'`.

Seven cities never hit it because they carry a `<study>_wildfire_annual_*.csv`
left over from older runs, which short-circuits the rebuild. The Spanish
studies were the first without that inherited cache, and all 10 of their
wildfire years failed on 2026-08-10.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome import wildfire  # noqa: E402

# Exactly what every other city's annual wildfire product already carries.
ANNUAL_COLUMNS = {
    "name",
    "burned_km2",
    "detections",
    "brightness_max_k",
    "area_km2",
    "fire_burned_pct",
}


def _units() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"name": ["A", "B"], "area_km2": [100.0, 200.0]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)],
        crs="EPSG:4326",
    )


def _annual(years: list[int]) -> pd.DataFrame:
    rows = [
        {
            "name": name,
            "year": year,
            "burned_km2": 1.0,
            "detections": 5.0,
            "brightness_max_k": 300.0,
        }
        for year in years
        for name in ("A", "B")
    ]
    return pd.DataFrame(rows)


class AnnualWildfireContractTests(unittest.TestCase):
    def _run(self, years: list[int]) -> pd.DataFrame:
        cfg = {"wildfire": {"years": years}}
        with (
            patch.object(wildfire.config, "load_config", return_value=cfg),
            patch.object(wildfire.boundaries, "get_communes", return_value=_units()),
            patch.object(wildfire, "fetch_annual_metrics", return_value=_annual(years)),
        ):
            return wildfire.build_wildfire_annual_frame("study", Path("cache"), years=years)

    def test_single_year_does_not_raise_and_keeps_the_year_column(self) -> None:
        """The exact call the temporal pipeline makes -- one year at a time."""
        frame = self._run([2015])

        self.assertEqual(len(frame), 2)
        self.assertEqual(sorted(frame["year"].unique()), [2015])
        self.assertTrue(ANNUAL_COLUMNS.issubset(frame.columns), sorted(frame.columns))

    def test_rows_stay_per_unit_per_year_instead_of_collapsing(self) -> None:
        frame = self._run([2015, 2016, 2017])

        self.assertEqual(len(frame), 6)  # 2 units x 3 years, not 2 summary rows
        self.assertNotIn("fire_trend_km2_per_decade", frame.columns)
        self.assertNotIn("fire_burned_area_km2_total", frame.columns)

    def test_burned_pct_is_relative_to_unit_area(self) -> None:
        frame = self._run([2015]).set_index("name")

        self.assertAlmostEqual(frame.loc["A", "fire_burned_pct"], 1.0)  # 1 km2 of 100
        self.assertAlmostEqual(frame.loc["B", "fire_burned_pct"], 0.5)  # 1 km2 of 200


class TrendMergeRegressionTests(unittest.TestCase):
    def test_aggregate_survives_fewer_than_three_years(self) -> None:
        """The original crash: an empty trend frame has no 'name' to merge on."""
        cfg = {
            "wildfire": {
                "years": [2015],
                "index_weights": {
                    "burned_pct": 0.4,
                    "detection_density": 0.4,
                    "recurrence": 0.2,
                },
            }
        }

        df = wildfire.aggregate_metrics(_annual([2015]), _units(), cfg)

        self.assertIn("fire_trend_km2_per_decade", df.columns)
        self.assertTrue(df["fire_trend_km2_per_decade"].isna().all())


if __name__ == "__main__":
    unittest.main()

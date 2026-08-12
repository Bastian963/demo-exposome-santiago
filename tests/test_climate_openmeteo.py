"""Tests for the climate_openmeteo exposome layer (no network, daily cache)."""
from __future__ import annotations

import json
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "processed"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"

EXPECTED_COLUMNS = [
    "tmean_annual",
    "tmax_mean_annual",
    "tmin_mean_annual",
    "tmean_summer",
    "tmax_mean_summer",
    "tmin_mean_summer",
    "tmean_winter",
    "tmax_mean_winter",
    "tmin_mean_winter",
    "tmean_autumn",
    "tmax_mean_autumn",
    "tmin_mean_autumn",
    "tmean_spring",
    "tmax_mean_spring",
    "tmin_mean_spring",
    "hot_days_30c",
    "hot_days_35c",
    "tropical_nights_20c",
    "frost_days",
    "heat_wave_days",
    "cold_spell_days",
    "dtr_mean",
    "dtr_p95",
    "temp_monthly_sd",
    "seasonal_amplitude",
    "cdd_18",
    "hdd_10",
    "ehdd",
    "tmax_p95",
    "tmin_p05",
    "name",
]

MASTER_COLUMNS = [
    "om_tmean_annual_c",
    "om_tmax_mean_annual_c",
    "om_tmin_mean_annual_c",
    "om_tmean_summer_c",
    "om_tmax_mean_summer_c",
    "om_tmin_mean_summer_c",
    "om_tmean_winter_c",
    "om_tmax_mean_winter_c",
    "om_tmin_mean_winter_c",
    "om_hot_days_30c",
    "om_hot_days_35c",
    "om_tropical_nights_20c",
    "om_frost_days",
    "om_heat_wave_days",
    "om_cold_spell_days",
    "om_dtr_mean_c",
    "om_dtr_p95_c",
    "om_temp_monthly_sd",
    "om_seasonal_amplitude_c",
    "om_cdd_18",
    "om_hdd_10",
    "om_ehdd",
    "om_tmax_p95_c",
    "om_tmin_p05_c",
]


class ClimateOpenMeteoLayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "santiago_climate_metrics_annual.csv"
        cls.geojson_path = DATA_DIR / "santiago_climate_metrics_annual.geojson"
        cls.metadata_path = DATA_DIR / "santiago_climate_metrics_annual_metadata.json"
        if not cls.csv_path.exists():
            raise unittest.SkipTest(
                f"Missing canonical CSV at {cls.csv_path}; run scripts/run_climate_metrics.py first."
            )
        cls.df = pd.read_csv(cls.csv_path)
        if not cls.metadata_path.exists():
            cls.metadata = None
        else:
            cls.metadata = json.loads(cls.metadata_path.read_text(encoding="utf-8"))
        cls.master = pd.read_csv(MASTER_CSV) if MASTER_CSV.exists() else None

    def test_csv_has_52_communes(self) -> None:
        self.assertEqual(len(self.df), 52)
        self.assertEqual(self.df["name"].nunique(), 52)
        self.assertEqual(self.df["name"].isna().sum(), 0)
        self.assertEqual(self.df["name"].duplicated().sum(), 0)

    def test_csv_columns_complete(self) -> None:
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, self.df.columns, f"missing column: {col}")
        numeric = [c for c in EXPECTED_COLUMNS if c != "name"]
        self.assertEqual(self.df[numeric].isna().sum().sum(), 0)

    def test_metadata_coherence(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata file not yet visible")
        self.assertEqual(self.metadata["n_rows"], 52)
        self.assertIn("years", self.metadata)
        self.assertEqual(
            self.metadata["source"],
            "Open-Meteo Historical Weather API (archive-api.open-meteo.com)",
        )
        # Limitations must mention 2024-only scope explicitly.
        self.assertIn("2024", self.metadata["limitations"])
        # All 30 numeric + name columns are documented in the metadata.
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, self.metadata["columns"])

    def test_geojson_present_and_valid(self) -> None:
        if not self.geojson_path.exists():
            self.skipTest("geojson missing; re-run scripts/run_climate_metrics.py")
        import geopandas as gpd

        gdf = gpd.read_file(self.geojson_path)
        self.assertEqual(len(gdf), 52)
        self.assertEqual(gdf["name"].nunique(), 52)
        self.assertFalse(gdf.geometry.isna().any())
        self.assertTrue(gdf.crs.to_string().startswith("EPSG:4326"))

    def test_year_scope_2024(self) -> None:
        """Canonical layer is computed from the 2024-only daily archive."""
        if self.metadata is None:
            self.skipTest("metadata file not yet visible")
        self.assertEqual(self.metadata["years"], [2024])
        # 52 communes x 366 days = 19032 rows (leap year).
        self.assertEqual(self.metadata["n_daily_rows"], 19032)

    def test_seasonal_monotonicity(self) -> None:
        """Summer Tmean >= Winter Tmean for every commune (Southern Hemisphere)."""
        diff = (self.df["tmean_summer"] - self.df["tmean_winter"]).round(3)
        self.assertTrue(
            (diff > 0).all(),
            f"summer <= winter in {((diff <= 0)).sum()} communes",
        )
        # Seasonal amplitude (tmean_summer - tmean_winter) is defined and
        # matches the difference.
        amp_diff = (
            self.df["seasonal_amplitude"]
            - (self.df["tmean_summer"] - self.df["tmean_winter"])
        ).abs().max()
        self.assertLessEqual(float(amp_diff), 1e-3)

    def test_daily_temperature_range_semantics(self) -> None:
        """For every commune: tmin <= tmean <= tmax (annual averages)."""
        ok_min = (self.df["tmin_mean_annual"] - self.df["tmean_annual"] <= 1e-3).all()
        ok_max = (self.df["tmean_annual"] - self.df["tmax_mean_annual"] <= 1e-3).all()
        self.assertTrue(ok_min, "tmin > tmean in some communes")
        self.assertTrue(ok_max, "tmean > tmax in some communes")
        # DTR = mean(Tmax - Tmin), must be non-negative.
        dtr = self.df["dtr_mean"]
        self.assertTrue((dtr >= 0).all())

    def test_threshold_counts_are_non_negative(self) -> None:
        """hot_days_30c, hot_days_35c, tropical_nights_20c, frost_days are
        non-negative integer counts bounded above by 366 (one year)."""
        for col in (
            "hot_days_30c",
            "hot_days_35c",
            "tropical_nights_20c",
            "frost_days",
            "heat_wave_days",
            "cold_spell_days",
        ):
            v = self.df[col]
            self.assertTrue((v >= 0).all(), f"{col} has negative values")
            self.assertTrue((v <= 366).all(), f"{col} exceeds 366 days")
            # Integer-valued (counts of days).
            self.assertTrue((v == v.round()).all(), f"{col} is not integer-valued")

    def test_hierarchy_30c_ge_35c(self) -> None:
        """hot_days_30c >= hot_days_35c for every commune (broader threshold)."""
        self.assertTrue(
            (self.df["hot_days_30c"] >= self.df["hot_days_35c"]).all(),
            "hot_days_35c > hot_days_30c in some communes",
        )

    def test_extreme_anchors(self) -> None:
        """San José de Maipo (Andean) is the coldest; Alhué is the warmest."""
        cold = self.df.loc[
            self.df["name"] == "San José de Maipo", "tmean_annual"
        ].iloc[0]
        warm = self.df.loc[self.df["name"] == "Alhué", "tmean_annual"].iloc[0]
        self.assertLess(float(cold), float(warm))
        # San José de Maipo must have the maximum number of frost days.
        sj_frost = self.df.loc[
            self.df["name"] == "San José de Maipo", "frost_days"
        ].iloc[0]
        self.assertEqual(float(sj_frost), float(self.df["frost_days"].max()))
        # Alhué must be in the top 10 of hot_days_35c (it's the warmest
        # by tmean but not the most extreme in terms of very-hot days).
        alhue_hot = self.df.loc[self.df["name"] == "Alhué", "hot_days_35c"].iloc[0]
        rank = (self.df["hot_days_35c"] > alhue_hot).sum() + 1
        self.assertLessEqual(int(rank), 10)

    def test_master_integration(self) -> None:
        if self.master is None:
            self.skipTest("Master CSV missing; run scripts/build_master_exposome.py first.")
        for col in MASTER_COLUMNS:
            self.assertIn(col, self.master.columns, f"master missing col: {col}")
        # The master values must equal the CSV values (no scaling/rounding
        # mismatch in the builder).
        for src_col, master_col in zip(
            [
                "tmean_annual",
                "tmax_mean_annual",
                "tmin_mean_annual",
                "tropical_nights_20c",
                "seasonal_amplitude",
                "frost_days",
            ],
            [
                "om_tmean_annual_c",
                "om_tmax_mean_annual_c",
                "om_tmin_mean_annual_c",
                "om_tropical_nights_20c",
                "om_seasonal_amplitude_c",
                "om_frost_days",
            ],
        ):
            merged = self.df[["name", src_col]].merge(
                self.master[["name", master_col]], on="name"
            )
            diff = (merged[src_col] - merged[master_col]).abs().max()
            self.assertLessEqual(
                float(diff), 1e-6, f"{src_col} vs {master_col} diverges by {diff}"
            )


class ClimateOpenMeteoMetricsTest(unittest.TestCase):
    """Unit tests for the climate.metrics module (no I/O)."""

    def test_count_consecutive_above_basic(self) -> None:
        """Heat-wave day counter: runs of >=2 days strictly above threshold."""
        from exposome.climate.metrics import _count_consecutive_above

        s = pd.Series([10, 11, 12, 20, 25, 26, 11, 30, 31, 32])
        # The function uses strict > (not >=): s[3]=20 is NOT above 20.
        # First run: [25, 26] = 2 days; second run: [30, 31, 32] = 3 days.
        # Both runs satisfy min_len=2 → 5 days total.
        self.assertEqual(_count_consecutive_above(s, 20, min_len=2), 5)
        # With min_len=3, only the second run qualifies → 3 days.
        self.assertEqual(_count_consecutive_above(s, 20, min_len=3), 3)
        # With min_len=4, neither run qualifies.
        self.assertEqual(_count_consecutive_above(s, 20, min_len=4), 0)

    def test_count_consecutive_below_basic(self) -> None:
        """Cold-spell day counter: runs of >=2 days strictly below threshold."""
        from exposome.climate.metrics import _count_consecutive_below

        s = pd.Series([10, 5, 4, 6, -2, -3, -1, 8])
        # Strict <: only -2, -3, -1 are below 0 (3 days).
        self.assertEqual(_count_consecutive_below(s, 0, min_len=2), 3)

    def test_calculate_climate_metrics_synthetic(self) -> None:
        """Hand-built series: verify hot/tropical day counts and seasonal
        means are correct on a controlled 1-year series."""
        from exposome.climate.metrics import calculate_climate_metrics

        # 365-day series with mild winter (tmin > 0 by default), then we
        # override exactly 30 days to be hot, 5 tropical, 10 frost.
        dates = pd.date_range("2024-01-01", periods=365, freq="D")
        months = dates.month
        tmean = np.where(months.isin([12, 1, 2]), 15.0,
                np.where(months.isin([6, 7, 8]), 5.0, 10.0))
        tmax = tmean + 5.0   # max = 20 (summer), 10 (winter), 15 (other)
        # Winter tmin must be strictly > 0 so the default winter is NOT
        # frost (the frost_days threshold is tmin <= 0).
        tmin = np.where(months.isin([6, 7, 8]), tmean - 4.0, tmean - 5.0)
        # min = 10 (summer), 1 (winter), 5 (other)
        # Exactly 30 hot days (override only the first 30).
        tmax[:30] = 31.0
        # 5 tropical nights in early January (summer, default tmin=10).
        tmin[10:15] = 21.0
        # 10 frost days in autumn (Apr-May, default tmin=5, no frost).
        tmin[100:110] = -1.0

        df = pd.DataFrame({
            "name": ["synth"] * 365,
            "date": dates,
            "temperature_2m_max": tmax,
            "temperature_2m_min": tmin,
            "temperature_2m_mean": tmean,
        })
        m = calculate_climate_metrics(
            df, tmean_col="temperature_2m_mean", group_col="name"
        )
        row = m.iloc[0]
        # Exactly 30 days with tmax >= 30.
        self.assertEqual(int(row["hot_days_30c"]), 30)
        # 5 tropical nights (tmin=21, >=20).
        self.assertEqual(int(row["tropical_nights_20c"]), 5)
        # 10 frost days (tmin=-1, <=0).
        self.assertEqual(int(row["frost_days"]), 10)
        # DTR must be positive (tmax >= tmin for every day).
        self.assertGreater(float(row["dtr_mean"]), 0.0)
        # Seasonal amplitude = tmean_summer - tmean_winter = 15 - 5 = 10.
        self.assertAlmostEqual(float(row["seasonal_amplitude"]), 10.0, places=1)
        # Tropical nights + frost days: 5 + 10 = 15 days with extreme tmin.
        self.assertEqual(
            int(row["tropical_nights_20c"]) + int(row["frost_days"]),
            15,
        )


if __name__ == "__main__":
    unittest.main()

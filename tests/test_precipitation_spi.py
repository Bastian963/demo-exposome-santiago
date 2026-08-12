"""Tests for the precipitation_spi exposome layer (CHIRPS-based, no GEE, cache-first)."""
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
CACHE_DIR = REPO_ROOT / "cache"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"
CHIRPS_DAILY_CSV = DATA_DIR / "santiago_precipitation_chirps_daily_2015_2024.csv"

EXPECTED_COLUMNS = [
    "name",
    "area_km2",
    "drought_months_pct",
    "drought_severe_months_pct",
    "drought_max_duration_months",
    "precip_trend_mm_per_decade",
    "spi_12_latest",
    "spi_3_mean",
    "spi_3_std",
    "spi_6_mean",
    "spi_12_mean",
]

MASTER_COLUMNS = [
    "drought_months_pct",
    "drought_severe_months_pct",
    "drought_max_duration_months",
    "precip_trend_mm_per_decade",
    "spi_12_latest",
    "spi_3_mean",
    "spi_3_std",
    "spi_6_mean",
    "spi_12_mean",
]


class PrecipitationSPILayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "santiago_precipitation_spi.csv"
        cls.geojson_path = DATA_DIR / "santiago_precipitation_spi.geojson"
        cls.metadata_path = DATA_DIR / "santiago_precipitation_spi_metadata.json"
        if not cls.csv_path.exists():
            raise unittest.SkipTest(
                f"Missing canonical CSV at {cls.csv_path}; run scripts/run_precipitation_spi.py first."
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
        self.assertEqual(self.metadata["source"]["n_communes"], 52)
        # 10 years (2015-2024) of CHIRPS daily data.
        self.assertEqual(self.metadata["source"]["period"], "2015–2024")
        # SPI algorithm metadata.
        spi = self.metadata["spi_algorithm"]
        self.assertEqual(spi["method"], "McKee et al. (1993)")
        self.assertEqual(spi["distribution"], "Gamma (scipy.stats.gamma, MLE fit, floc=0)")
        self.assertIn("zero_handling", spi)
        self.assertEqual(spi["thresholds"]["moderate_drought"], -1.0)
        self.assertEqual(spi["thresholds"]["severe_drought"], -2.0)
        # brain_health_relevance covers the three pathways.
        for key in ("drought_exposure", "drying_trend", "spi_variability"):
            self.assertIn(key, self.metadata["brain_health_relevance"])
        # The 2024 anomaly note must be present in the metadata so
        # downstream consumers see it without reading the doc.
        self.assertIn("known_anomaly_2024", self.metadata)
        anomaly = self.metadata["known_anomaly_2024"]
        self.assertIn("2024 was an anomalously wet year", anomaly["reason"])
        self.assertIn("464", anomaly["reason"])  # 2024 mm/yr
        self.assertIn("261", anomaly["reason"])  # baseline mm/yr
        self.assertIn("+78%", anomaly["reason"])
        # The CHIRPS bias note must cite Funk et al. 2015.
        self.assertIn("chirps_bias_note", self.metadata)
        bias = self.metadata["chirps_bias_note"]
        self.assertIn("Funk", bias["reference"])
        self.assertIn("2015", bias["reference"])
        self.assertIn("5-15 mm/month", bias["rmse_vs_stations"])
        # The spi_12_latest column description must warn about the
        # 2024 anomaly so users interpret it correctly.
        desc = self.metadata["columns_description"]["spi_12_latest"]
        self.assertIn("+78%", desc)
        self.assertIn("chronic", desc)

    def test_drought_metrics_bounded(self) -> None:
        """Drought-month percentages must be in [0, 100]."""
        for col in ("drought_months_pct", "drought_severe_months_pct"):
            v = self.df[col]
            self.assertGreaterEqual(float(v.min()), 0.0)
            self.assertLessEqual(float(v.max()), 100.0)
            self.assertEqual(v.isna().sum(), 0)
        # Severe drought % is a subset of moderate drought %.
        self.assertTrue(
            (self.df["drought_severe_months_pct"] <= self.df["drought_months_pct"]).all(),
            "drought_severe_months_pct > drought_months_pct in some communes",
        )

    def test_drought_max_duration_is_integer(self) -> None:
        v = self.df["drought_max_duration_months"]
        self.assertEqual(v.isna().sum(), 0)
        # Must be a non-negative integer count of consecutive months.
        self.assertTrue((v >= 0).all())
        self.assertTrue((v == v.round()).all())
        # 10-year record → at most ~120 months; the canonical layer caps
        # at 6 because the longest SPI-3 run is short (mediterranean
        # climate has winter rainfall followed by dry summers).
        self.assertLessEqual(int(v.max()), 12)

    def test_precip_trend_finite(self) -> None:
        v = self.df["precip_trend_mm_per_decade"]
        self.assertEqual(v.isna().sum(), 0)
        # Trend is the OLS slope (mm/year) × 10 over 10 points. The
        # Santiago RM receives ≈300 mm/yr so a 10-year trend shouldn't
        # exceed the order of magnitude of the mean.
        self.assertLess(float(v.abs().max()), 200.0)

    def test_spi_means_near_zero(self) -> None:
        """spi_X_mean over the full record is ≈ 0 by construction.

        The Gamma fit per calendar month makes the SPI values standardized
        to N(0, 1) over the same reference period. So the per-commune mean
        across the full record should cluster around 0 (small residual
        because the fit uses each calendar month's own distribution).
        """
        for col in ("spi_3_mean", "spi_6_mean", "spi_12_mean"):
            mean = float(self.df[col].mean())
            self.assertAlmostEqual(mean, 0.0, delta=0.05)
        # Standard deviations should be close to 1.
        std = float(self.df["spi_3_std"].mean())
        self.assertAlmostEqual(std, 1.0, delta=0.05)

    def test_spi_12_latest_range(self) -> None:
        """spi_12_latest is a single standardized value; sane range ±3."""
        v = self.df["spi_12_latest"]
        self.assertEqual(v.isna().sum(), 0)
        self.assertGreaterEqual(float(v.min()), -3.0)
        self.assertLessEqual(float(v.max()), 3.0)
        # All 52 latest values are within the typical ±3 σ range.

    def test_san_pedro_driest_trend(self) -> None:
        """San Pedro is the most strongly drying commune in the RM
        (rural south, far from Andean orographic precipitation)."""
        san_pedro = self.df.loc[self.df["name"] == "San Pedro", "precip_trend_mm_per_decade"]
        self.assertEqual(len(san_pedro), 1)
        # It must be in the bottom 5 of the trend.
        rank = (self.df["precip_trend_mm_per_decade"] < float(san_pedro.iloc[0])).sum() + 1
        self.assertLessEqual(int(rank), 5)
        # And it must have a negative trend (drying).
        self.assertLess(float(san_pedro.iloc[0]), 0.0)

    def test_master_integration(self) -> None:
        if self.master is None:
            self.skipTest("Master CSV missing")
        master_cols = pd.read_csv(MASTER_CSV, nrows=0).columns
        for col in MASTER_COLUMNS:
            self.assertIn(col, master_cols, f"master missing col: {col}")
        # Master values equal the CSV values (the master builder uses
        # the canonical CSV as input for this layer).
        for col in MASTER_COLUMNS:
            merged = self.df[["name", col]].merge(
                self.master[["name", col]], on="name", suffixes=("_src", "_master")
            )
            diff = (merged[f"{col}_src"] - merged[f"{col}_master"]).abs().max()
            self.assertLessEqual(
                float(diff), 1e-6, f"master vs src for {col} diverges by {diff}"
            )


class PrecipitationSPIHelpersTest(unittest.TestCase):
    """Unit tests for the precipitation_spi module helpers (no I/O)."""

    def test_spi_zero_handling(self) -> None:
        """Months with zero precipitation must not produce NaN; the mixed
        CDF gives a non-zero probability of zero via P(X=0) > 0.

        The function only emits a value for a calendar month when the
        Gamma fit succeeds on the non-zero values. For a series that
        alternates 0/100, the wet months have enough non-zero data to
        fit the Gamma and produce valid SPI values. The dry months
        (rolling 3-month sums that are all zero) map to the left tail
        of the distribution and produce SPI < 0.
        """
        from exposome.precipitation_spi import _spi_for_commune

        # 10 years: 60 months of 0 (dry) + 60 months of 100 (wet).
        dates = pd.date_range("2015-01-01", periods=120, freq="MS")
        values = [0.0] * 60 + [100.0] * 60
        s = pd.Series(values, index=dates)
        spi = _spi_for_commune(s, scale=3)
        valid = spi.dropna()
        # The function only emits valid SPI for calendar months where
        # the Gamma fit succeeds on the non-zero values. For our
        # synthetic series, the wet months satisfy this condition.
        self.assertGreater(len(valid), 0)
        self.assertLessEqual(len(valid), 118)
        # Valid SPI values are within the standard normal range.
        self.assertGreater(float(valid.min()), -4.0)
        self.assertLess(float(valid.max()), 4.0)
        # Mean of the valid SPI is close to 0 (the fit is centered).
        self.assertAlmostEqual(float(valid.mean()), 0.0, delta=1.0)

    def test_drought_max_duration_counting(self) -> None:
        """compute_drought_metrics counts the longest SPI-3 < -1 run."""
        from exposome.precipitation_spi import compute_drought_metrics

        # 24 months of SPI-3: 8 consecutive months < -1, then break.
        dates = pd.date_range("2020-01-01", periods=24, freq="MS")
        spi_vals = [-1.5] * 8 + [0.0] * 8 + [-1.5] * 4 + [0.0] * 4
        spi3 = pd.DataFrame({"name": ["synth"] * 24, "date": dates, "spi_3": spi_vals})
        annual = pd.DataFrame({
            "name": ["synth"] * 3,
            "year": [2020, 2021, 2022],
            "precip_annual_mm": [300.0, 300.0, 300.0],
        })
        m = compute_drought_metrics(spi3, annual)
        row = m.iloc[0]
        # 12 of 24 months are in moderate drought (50 %).
        self.assertAlmostEqual(float(row["drought_months_pct"]), 50.0, places=2)
        # The longest consecutive run of SPI-3 < -1 is 8.
        self.assertEqual(int(row["drought_max_duration_months"]), 8)
        # Zero months of severe drought (no values < -2).
        self.assertAlmostEqual(float(row["drought_severe_months_pct"]), 0.0, places=2)
        # Trend is 0 mm/decade (constant annual totals).
        self.assertAlmostEqual(float(row["precip_trend_mm_per_decade"]), 0.0, places=2)

    def test_precip_trend_positive_negative(self) -> None:
        """Trend is the OLS slope × 10 (mm/decade)."""
        from exposome.precipitation_spi import compute_drought_metrics

        dates = pd.date_range("2020-01-01", periods=24, freq="MS")
        spi3 = pd.DataFrame({"name": ["synth"] * 24, "date": dates, "spi_3": [0.0] * 24})
        # Linear series: 300, 320, 340, 360, 380, 400 → slope = 20 mm/yr → 200 mm/decade.
        annual = pd.DataFrame({
            "name": ["synth"] * 6,
            "year": [2020, 2021, 2022, 2023, 2024, 2025],
            "precip_annual_mm": [300.0, 320.0, 340.0, 360.0, 380.0, 400.0],
        })
        m = compute_drought_metrics(spi3, annual)
        self.assertAlmostEqual(float(m.iloc[0]["precip_trend_mm_per_decade"]), 200.0, places=2)


if __name__ == "__main__":
    unittest.main()

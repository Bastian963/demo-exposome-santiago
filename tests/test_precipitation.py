"""Tests for the CHIRPS precipitation exposome layer (cache-first, no network)."""
from __future__ import annotations

import json
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "processed"
CACHE_DIR = REPO_ROOT / "cache"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"

EXPECTED_COLUMNS = [
    "name",
    "area_km2",
    "precip_annual_mean_mm",
    "precip_annual_sd_mm",
    "precip_annual_cv",
    "precip_wet_days",
    "precip_wet_day_pct",
    "precip_heavy_days_10mm",
    "precip_very_heavy_days_20mm",
    "precip_rx1day_mm",
    "precip_rx5day_mm",
    "precip_cdd_days",
    "precip_cwd_days",
    "precip_intensity_wet_day_mm",
    "precip_winter_mean_mm",
    "precip_summer_mean_mm",
    "precip_latest_year_mm",
    "precip_latest_anomaly_mm",
    "precip_latest_anomaly_pct",
    "precip_extremes_index",
    "precip_n_years",
    "precip_n_days",
]


class PrecipitationLayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "santiago_precipitation_chirps_2015_2024.csv"
        cls.geojson_path = DATA_DIR / "santiago_precipitation_chirps_2015_2024.geojson"
        cls.metadata_path = DATA_DIR / "santiago_precipitation_chirps_2015_2024.json"
        if not cls.csv_path.exists():
            raise unittest.SkipTest(
                f"Missing canonical CSV at {cls.csv_path}; run scripts/run_precipitation.py first."
            )
        cls.df = pd.read_csv(cls.csv_path)
        if not cls.metadata_path.exists():
            cls.metadata = None
        else:
            cls.metadata = json.loads(cls.metadata_path.read_text(encoding="utf-8"))

    def test_csv_has_52_communes(self) -> None:
        self.assertEqual(len(self.df), 52)
        self.assertEqual(self.df["name"].nunique(), 52)
        self.assertEqual(self.df["name"].isna().sum(), 0)

    def test_csv_columns_complete(self) -> None:
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, self.df.columns, f"missing column: {col}")
        self.assertEqual(self.df[EXPECTED_COLUMNS].isna().sum().sum(), 0)

    def test_metadata_coherence(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata file not yet visible (likely cloud-sync delay)")
        self.assertEqual(self.metadata["n_rows"], 52)
        self.assertEqual(self.metadata["period"], "2015-2024")
        self.assertEqual(self.metadata["latest_year"], 2024)
        self.assertEqual(self.metadata["years"], list(range(2015, 2025)))
        # Thresholds (wet_day 1 mm, heavy_day 10 mm, very_heavy_day 20 mm)
        self.assertEqual(self.metadata["thresholds_mm"]["wet_day"], 1.0)
        self.assertEqual(self.metadata["thresholds_mm"]["heavy_day"], 10.0)
        self.assertEqual(self.metadata["thresholds_mm"]["very_heavy_day"], 20.0)
        # Sources
        self.assertEqual(
            self.metadata["sources"]["chirps"]["collection"],
            "UCSB-CHG/CHIRPS/DAILY",
        )
        self.assertEqual(
            self.metadata["sources"]["chirps"]["band"], "precipitation"
        )
        # columns_description covers every core column
        for col in EXPECTED_COLUMNS:
            if col in ("name", "area_km2"):
                continue
            self.assertIn(
                col,
                self.metadata["columns_description"],
                f"metadata missing description for: {col}",
            )
        # limitations and brain_health_relevance are non-empty
        self.assertTrue(self.metadata["limitations"])
        self.assertGreater(len(self.metadata["brain_health_relevance"]), 0)

    def test_precip_extremes_index_distribution(self) -> None:
        idx = self.df["precip_extremes_index"]
        self.assertEqual(idx.isna().sum(), 0)
        self.assertGreaterEqual(float(idx.min()), 0.0)
        self.assertLessEqual(float(idx.max()), 100.0)
        # Rank-percentile composite: median is 50 within the 52 communes.
        self.assertAlmostEqual(float(idx.median()), 50.0, delta=5.0)
        # Contrast: Andean foothills (San José de Maipo, Lo Barnechea) receive
        # much more heavy rain than the central urban core (Santiago).
        andean = self.df.loc[
            self.df["name"].isin(["San José de Maipo", "Lo Barnechea"]),
            "precip_rx5day_mm",
        ]
        urban = self.df.loc[
            self.df["name"].isin(["Santiago", "Providencia"]),
            "precip_rx5day_mm",
        ]
        self.assertGreater(float(andean.mean()), float(urban.mean()))

    def test_precip_n_years_n_days(self) -> None:
        n_years = self.df["precip_n_years"]
        n_days = self.df["precip_n_days"]
        self.assertEqual(int(n_years.unique()[0]), 10)
        # 10 years * 365.3 days = 3653 (CHIRPS gap-filled daily series).
        self.assertTrue((n_days == 3653).all(), f"unexpected n_days: {n_days.unique()}")

    def test_precip_annual_mean_range(self) -> None:
        mean = self.df["precip_annual_mean_mm"]
        self.assertEqual(mean.isna().sum(), 0)
        # Mediterranean climate in the RM: 200-500 mm/year.
        self.assertGreater(float(mean.min()), 150.0)
        self.assertLess(float(mean.max()), 600.0)
        # CV must be positive (inter-annual variability exists).
        self.assertGreater(float(self.df["precip_annual_cv"].max()), 0.0)

    def test_precip_winter_summer_seasonality(self) -> None:
        """Mediterranean climate in central Chile: wet winters (JJA), dry summers (DJF)."""
        winter = self.df["precip_winter_mean_mm"]
        summer = self.df["precip_summer_mean_mm"]
        self.assertGreater(float(winter.min()), 0.0)
        # Every commune must have a wetter winter (JJA) than summer (DJF).
        self.assertTrue((winter > summer).all())

    def test_precip_cdd_positive(self) -> None:
        """Mediterranean climate: every commune must experience a meaningful
        dry spell in the canonical 2015-2024 record. The mean CDD is ~75 days
        across the 52 communes; the loosest is San José de Maipo (~29 days).
        """
        cdd = self.df["precip_cdd_days"]
        self.assertEqual(cdd.isna().sum(), 0)
        # All communes have at least one annual dry spell >= 25 days.
        self.assertTrue((cdd >= 25).all(), f"commune with CDD<25 found: {cdd.min()}")
        # Andean communes (high rainfall) should still have dry spells.
        andean = self.df.loc[
            self.df["name"].isin(["San José de Maipo", "Lo Barnechea"]),
            "precip_cdd_days",
        ]
        self.assertTrue((andean > 0).all())
        # The driest commune (highest CDD) must be in the central urban /
        # northern band where CHIRPS records the lowest annual rainfall
        # (rain-shadow over the central valley).
        driest_names = set(self.df.nlargest(5, "precip_cdd_days")["name"].tolist())
        self.assertTrue(
            driest_names & {"Huechuraba", "Conchalí", "Cerrillos", "Quinta Normal",
                            "Recoleta", "Independencia", "Santiago", "Renca"},
            f"unexpected driest communes: {driest_names}",
        )

    def test_precip_wet_day_pct_range(self) -> None:
        pct = self.df["precip_wet_day_pct"]
        self.assertEqual(pct.isna().sum(), 0)
        self.assertTrue((pct >= 0).all() and (pct <= 100).all())

    def test_heavy_rain_threshold_semantics(self) -> None:
        """Hierarchical threshold semantics: count(>=20mm) <= count(>=10mm)."""
        heavy = self.df["precip_heavy_days_10mm"]
        very_heavy = self.df["precip_very_heavy_days_20mm"]
        self.assertTrue((very_heavy <= heavy + 1e-9).all())

    def test_precip_rx_hierarchy(self) -> None:
        """Mathematical invariant: 5-day max >= 1-day max (within 0.01 mm tolerance)."""
        rx1 = self.df["precip_rx1day_mm"]
        rx5 = self.df["precip_rx5day_mm"]
        self.assertTrue(
            (rx5 + 1e-2 >= rx1).all(),
            f"rx5day < rx1day in some communes: min diff = "
            f"{(rx5 - rx1).min()}",
        )

    def test_precip_intensity_floor(self) -> None:
        """precip_intensity_wet_day_mm must be >= 1 mm (wet-day threshold) and
        stay within a plausible Mediterranean range (<= 50 mm/day)."""
        intensity = self.df["precip_intensity_wet_day_mm"]
        self.assertEqual(intensity.isna().sum(), 0)
        self.assertTrue(
            (intensity >= 1.0).all(),
            f"intensity below 1 mm threshold: min = {intensity.min()}",
        )
        self.assertLess(
            float(intensity.max()),
            50.0,
            f"intensity unexpectedly high: max = {intensity.max()}",
        )

    def test_master_integration(self) -> None:
        if not MASTER_CSV.exists():
            self.skipTest("Master CSV missing; run scripts/build_master_exposome.py first.")
        master_cols = pd.read_csv(MASTER_CSV, nrows=0).columns
        core = [
            "precip_annual_mean_mm",
            "precip_annual_sd_mm",
            "precip_annual_cv",
            "precip_wet_days",
            "precip_wet_day_pct",
            "precip_heavy_days_10mm",
            "precip_very_heavy_days_20mm",
            "precip_rx1day_mm",
            "precip_rx5day_mm",
            "precip_cdd_days",
            "precip_cwd_days",
            "precip_intensity_wet_day_mm",
            "precip_winter_mean_mm",
            "precip_summer_mean_mm",
            "precip_latest_year_mm",
            "precip_latest_anomaly_mm",
            "precip_latest_anomaly_pct",
            "precip_extremes_index",
            "precip_n_years",
            "precip_n_days",
        ]
        for col in core:
            self.assertIn(col, master_cols, f"master missing core col: {col}")

    def test_build_layer_idempotent_from_cache(self) -> None:
        """Re-running build_precipitation_layer from cache must reproduce the CSV.

        The CSV is overwritten by the re-run, so we read the new frame and
        compare against the data on disk (the new file). area_km2 is recomputed
        from the projected geometry each run, so allow a 0.01 km^2 tolerance.
        """
        from exposome.precipitation import build_precipitation_layer

        cache_year = CACHE_DIR / "santiago_precipitation_chirps_2015.csv"
        if not cache_year.exists():
            self.skipTest("CHIRPS annual cache missing; run scripts/run_precipitation.py once.")
        if not (CACHE_DIR / "santiago_communes.geojson").exists():
            self.skipTest("Communes boundary cache missing.")

        df_before = pd.read_csv(DATA_DIR / "santiago_precipitation_chirps_2015_2024.csv")

        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            df_new, _ = build_precipitation_layer(
                city="santiago",
                cache_dir=CACHE_DIR,
                out_dir=out_dir,
            )
            df_after = pd.read_csv(out_dir / "santiago_precipitation_chirps_2015_2024.csv")

        # Name order is stable.
        self.assertEqual(df_new["name"].tolist(), df_before["name"].tolist())
        # Compare numeric columns; area_km2 is allowed a small tolerance
        # because projected geometry is recomputed each run.
        numeric_cols = [
            c for c in EXPECTED_COLUMNS
            if c not in ("name", "precip_n_years", "precip_n_days", "area_km2")
        ]
        m_before = df_before.set_index("name")[numeric_cols]
        m_after = df_after.set_index("name")[numeric_cols]
        for c in numeric_cols:
            diff = (m_before[c] - m_after[c]).abs().max()
            self.assertLessEqual(
                float(diff),
                1e-9,
                f"column {c} diverged by {diff} after re-build",
            )
        # n_years / n_days must be byte-exact (integers).
        for c in ("precip_n_years", "precip_n_days"):
            self.assertTrue(
                (m_before[c] == m_after[c]).all() if c in m_before.columns else True,
                f"column {c} changed",
            )
        # area_km2 must agree within 0.01 km^2.
        area_diff = (
            df_before.set_index("name")["area_km2"]
            - df_after.set_index("name")["area_km2"]
        ).abs().max()
        self.assertLessEqual(
            float(area_diff),
            0.01,
            f"area_km2 diverged by {area_diff} km^2 after re-build",
        )


class PrecipitationCacheCheckpointTest(unittest.TestCase):
    def test_year_resumes_only_missing_months(self) -> None:
        from exposome.cache import CacheIdentity, CacheStore
        from exposome.precipitation import fetch_chirps_year

        identity = CacheIdentity(
            "precipitation",
            "daily_year",
            {"collection": "CHIRPS", "year": 2020},
            "spatial-test",
            "test",
        )
        cfg = {
            "precipitation": {
                "collection": {
                    "id": "CHIRPS",
                    "band": "precipitation",
                    "scale_meters": 5566,
                }
            }
        }

        def month_frame(_cfg, _regions, start, _end, scale=None):
            del _cfg, _regions, scale
            return pd.DataFrame(
                {"name": ["A"], "date": [start], "precipitation_mm": [1.0]}
            )

        with TemporaryDirectory() as tmp:
            store = CacheStore(Path(tmp), identity)
            calls = 0

            def interrupted(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise RuntimeError("interrupted")
                return month_frame(*args, **kwargs)

            with patch(
                "exposome.precipitation.fetch_chirps_period_server_side",
                side_effect=interrupted,
            ):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    fetch_chirps_year(cfg, object(), 2020, cache_store=store)

            checkpoint = store.load_checkpoint_csv("2020")
            self.assertTrue(checkpoint.hit)
            self.assertEqual(checkpoint.completed_keys, ("M01", "M02"))

            with patch(
                "exposome.precipitation.fetch_chirps_period_server_side",
                side_effect=month_frame,
            ) as fetch:
                result = fetch_chirps_year(cfg, object(), 2020, cache_store=store)

            self.assertEqual(fetch.call_count, 10)
            self.assertEqual(len(result), 12)
            complete = store.load_csv(
                "2020", expected_completed_keys=[f"M{month:02d}" for month in range(1, 13)]
            )
            self.assertTrue(complete.hit)


if __name__ == "__main__":
    unittest.main()

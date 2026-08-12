"""Tests for the climate_openmeteo vs climate_heat dedup decision (v1.2).

In v1.2 we inspected pairwise Spearman correlations between the
24 `om_*` columns (OpenMeteo ground-station-based) and the
heat-related columns (ERA5-Land reanalysis) to determine whether
they are **duplicates** (rho > 0.95, redundant) or **complements**
(rho < 0.85, distinct sources).

Result: no pair has rho > 0.95, so the master retains BOTH sources.
The OpenMeteo and ERA5-Land reanalysis capture different aspects
of the climate signal (station-based vs gridded reanalysis) and
should not be conflated.

This test locks-in the decision by:
1. Asserting the master still contains the om_* columns (no
   accidental removal).
2. Asserting the master still contains the heat_* columns.
3. Asserting that the **maximum** pairwise correlation between
   the two sources is below 0.95, documenting that they are
   complements rather than duplicates.
"""
from __future__ import annotations

import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "processed"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"

OM_PREFIX = "om_"
HEAT_LIKE_COLS = [
    "tmax_mean_annual_c", "tmax_p95_c", "tmax_abs_c",
    "summer_tmax_mean_c",
    "heat_exposure_index", "urban_heat_anomaly_c",
    "apparent_tmax_mean_c",
]

DEDUP_THRESHOLD = 0.95


class ClimateDedupDecisionTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if MASTER_CSV.exists():
            cls.df = pd.read_csv(MASTER_CSV)
        else:
            cls.df = None

    def test_master_exists(self) -> None:
        self.assertTrue(MASTER_CSV.exists(), f"Missing: {MASTER_CSV}")

    def test_om_cols_retained(self) -> None:
        """Lock-in: the om_* columns must still be in the master.

        v1.2 dedup decision: NO om_* column was removed because no
        om_*/heat_* pair has rho > 0.95 (the dedup threshold).
        """
        if self.df is None:
            self.skipTest("master CSV not visible")
        om_cols = [c for c in self.df.columns if c.startswith(OM_PREFIX)]
        self.assertGreaterEqual(
            len(om_cols), 20,
            f"only {len(om_cols)} om_* columns; "
            "v1.2 kept the full set because no pair reached dedup threshold",
        )

    def test_heat_cols_retained(self) -> None:
        if self.df is None:
            self.skipTest("master CSV not visible")
        for col in HEAT_LIKE_COLS:
            self.assertIn(
                col, self.df.columns,
                f"heat-related column {col!r} should be in master",
            )

    def test_max_pairwise_corr_below_dedup_threshold(self) -> None:
        """Document that no om_*/heat_* pair is redundant (rho < 0.95).

        The maximum pairwise Spearman correlation should be strictly
        below the dedup threshold. If a future change pushes some
        pair above 0.95, the master should be deduplicated.
        """
        if self.df is None:
            self.skipTest("master CSV not visible")
        from scipy.stats import spearmanr
        om_cols = [c for c in self.df.columns if c.startswith(OM_PREFIX)]
        heat_cols = [c for c in HEAT_LIKE_COLS if c in self.df.columns]
        max_rho = -1.0
        max_pair: tuple[str, str] = ("", "")
        for o in om_cols:
            for h in heat_cols:
                if self.df[o].notna().sum() < 10:
                    continue
                if self.df[h].notna().sum() < 10:
                    continue
                rho, _ = spearmanr(self.df[o], self.df[h])
                if abs(rho) > max_rho:
                    max_rho = abs(rho)
                    max_pair = (o, h)
        self.assertLess(
            max_rho, DEDUP_THRESHOLD,
            f"max om_*/heat_* rho = {max_rho:.3f} "
            f"({max_pair[0]} vs {max_pair[1]}) >= {DEDUP_THRESHOLD}; "
            "consider dedup",
        )


if __name__ == "__main__":
    unittest.main()

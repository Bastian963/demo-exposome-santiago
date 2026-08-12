from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.argentina_associations import (  # noqa: E402
    benjamini_hochberg,
    evaluate_association,
)


class ArgentinaAssociationTests(unittest.TestCase):
    def test_bh_is_monotone_in_rank_order(self) -> None:
        q = benjamini_hochberg([0.01, 0.04, 0.03, 0.8])
        self.assertEqual(len(q), 4)
        self.assertTrue(all(0 <= value <= 1 for value in q))
        self.assertLessEqual(q[0], q[1])

    def test_missing_spatial_diagnostic_keeps_result_gated(self) -> None:
        rng = np.random.default_rng(7)
        n = 55
        exposure = rng.normal(size=n)
        person_years = np.full(n, 100_000.0)
        counts = rng.poisson(np.exp(-8.8 + 0.12 * exposure) * person_years)
        frame = pd.DataFrame(
            {
                "spatial_id": [f"u{i}" for i in range(n)],
                "count": counts,
                "person_years": person_years,
                "rate": counts / person_years * 100_000,
                "exposure": exposure,
                "census_pct_65_plus": rng.normal(12, 1, n),
                "census_pct_male": rng.normal(48, 1, n),
                "census_log_population_density": rng.normal(8, 0.5, n),
                "census_material_deprivation": rng.normal(size=n),
                "is_caba": np.r_[np.ones(15), np.zeros(40)],
            }
        )
        result = evaluate_association(
            frame,
            outcome_count="count",
            person_years="person_years",
            outcome_rate="rate",
            exposure="exposure",
        )
        self.assertEqual(result["release_status"], "gated")
        self.assertIn("spatial_diagnostic_missing", result["gate_reasons"])


if __name__ == "__main__":
    unittest.main()

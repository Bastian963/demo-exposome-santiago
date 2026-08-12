from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.socioeconomic import compute_nse_index, validate_against_official  # noqa: E402


class SocioeconomicTest(unittest.TestCase):
    def test_compute_nse_index_preserves_expected_orientation(self) -> None:
        df = pd.DataFrame(
            {
                "ingreso": [100, 120, 140, 160, 180, 200, 220, 240, 260, 280],
                "escolaridad": [8.0, 8.5, 9.0, 9.8, 10.5, 11.3, 12.0, 12.8, 13.5, 14.2],
                "pobreza_pct": [40, 36, 33, 29, 25, 21, 18, 14, 10, 7],
                "pobreza_multi_pct": [35, 32, 29, 26, 22, 19, 15, 12, 9, 6],
                "viv_materialidad_deficitaria_pct": [30, 28, 25, 22, 19, 16, 12, 9, 6, 4],
                "hacinamiento_phh": [4.2, 4.0, 3.8, 3.6, 3.3, 3.1, 2.9, 2.7, 2.5, 2.3],
            }
        )

        indexed, info = compute_nse_index(df)

        self.assertTrue(indexed["nse_index"].is_monotonic_increasing)
        self.assertTrue(indexed["nse_index_pca"].is_monotonic_increasing)
        self.assertEqual(indexed["nse_quintil"].value_counts().sort_index().to_dict(), {1: 2, 2: 2, 3: 2, 4: 2, 5: 2})
        self.assertGreater(info["pca_variance_explained_pc1"], 0.5)
        self.assertGreater(info["pca_loadings_pc1"]["ingreso"], 0)
        self.assertGreater(info["pca_loadings_pc1"]["escolaridad"], 0)
        self.assertGreater(info["weighting_sensitivity_spearman_rho"], 0.95)

    def test_validate_against_official_skips_missing_source(self) -> None:
        df = pd.DataFrame(
            {
                "name": ["A", "B"],
                "nse_index_pca": [1.0, -1.0],
            }
        )
        cfg = {
            "socioeconomic": {
                "validation": {
                    "sources": [
                        {
                            "name": "Missing IPS",
                            "path": "data/raw/missing_ips.csv",
                            "name_col": "comuna",
                            "value_col": "ips",
                        }
                    ]
                }
            }
        }

        with TemporaryDirectory() as tmp:
            results = validate_against_official(df, cfg, Path(tmp))

        self.assertEqual(results, [{"source": "Missing IPS", "status": "skipped", "reason": "file not found: data/raw/missing_ips.csv"}])


if __name__ == "__main__":
    unittest.main()

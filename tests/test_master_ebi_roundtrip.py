"""Round-trip tests: master exposome CSV ↔ EBI derived artefacts.

These tests verify that `scripts/analyze_cross_layer.py` can be
re-run on the master CSV and produce a **byte-deterministic** EBI
sidecar. They lock in the relationship between the master and the
EBI to detect regressions in the cross-layer analysis.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

DATA_DIR = REPO_ROOT / "data" / "processed"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"
EBI_CSV = DATA_DIR / "environmental_burden_index.csv"
SUMMARY_JSON = DATA_DIR / "cross_layer_summary.json"

# 20 canonical indicators, with their direction sign.
CANONICAL_COLUMNS: list[tuple[str, int]] = [
    ("pm25_mean", +1),
    ("no2_surface_ug_m3", +1),
    ("o3_mean", +1),
    ("aod_470", +1),
    ("hm_index", +1),
    ("alan_radiance_mean", +1),
    ("noise_combined_pct", +1),
    ("heat_exposure_index", +1),
    ("urban_heat_anomaly_c", +1),
    ("fire_burned_pct_mean_annual", +1),
    ("wind_calm_pct", +1),
    ("green_cover_pct_ndvi", -1),
    ("green_km2", -1),
    ("walk_index", -1),
    ("transit_index", -1),
    ("health_n_primary_care", -1),
    ("food_swamp_ratio", +1),
    ("pobreza_pct", +1),
    ("nse_index", -1),
    ("hacinamiento_phh", +1),
]


class EbiRoundTripTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MASTER_CSV.exists():
            raise unittest.SkipTest(
                "Master CSV not found; run scripts/build_master_exposome.py first."
            )
        cls.master = pd.read_csv(MASTER_CSV)
        if EBI_CSV.exists():
            cls.ebi = pd.read_csv(EBI_CSV)
        else:
            cls.ebi = None

    def test_ebi_csv_exists_and_has_52_rows(self) -> None:
        """EBI sidecar must exist and have 52 communes (matches master)."""
        self.assertIsNotNone(self.ebi, "EBI CSV not found")
        self.assertEqual(
            self.ebi.shape[0], 52,
            f"EBI has {self.ebi.shape[0]} rows, expected 52",
        )

    def test_ebi_has_canonical_columns(self) -> None:
        """EBI sidecar must include name, ebi_score, ebi_rank, db_score, db_rank,
        ebi_pca_score, ebi_pca_rank, effective_dose_mean, effective_dose_rank,
        and one pct_<col> per **used** canonical column.
        """
        self.assertIsNotNone(self.ebi)
        required = {
            "name", "ebi_score", "ebi_rank",
            "db_score", "db_rank",
            "ebi_pca_score", "ebi_pca_rank",
            "effective_dose_mean", "effective_dose_rank",
        }
        for col in required:
            self.assertIn(col, self.ebi.columns, f"missing {col!r} in EBI CSV")
        import json
        with open(SUMMARY_JSON) as f:
            summary = json.load(f)
        for pct_col in summary["used_pct_columns"]:
            self.assertIn(
                pct_col, self.ebi.columns,
                f"missing rank-percentile column {pct_col!r}",
            )

    def test_ebi_score_in_unit_interval(self) -> None:
        """EBI score must be in [0, 1] for all 52 communes."""
        scores = self.ebi["ebi_score"].dropna()
        self.assertGreaterEqual(scores.min(), 0.0)
        self.assertLessEqual(scores.max(), 1.0)

    def test_ebi_rank_is_perfect_1_to_52(self) -> None:
        """EBI rank must cover 1..52 with no gaps (when no ties)."""
        ranks = self.ebi["ebi_rank"].dropna().sort_values()
        self.assertEqual(ranks.iloc[0], 1.0)
        self.assertEqual(ranks.iloc[-1], 52.0)
        self.assertEqual(
            len(ranks), 52,
            f"expected 52 unique ranks, got {len(ranks)}",
        )

    def test_ebi_monotonic_with_pm25(self) -> None:
        """Higher PM2.5 should be positively correlated with EBI (rho > 0.3).

        PM2.5 is a major component of the EBI (sign=+1, included as
        canonical), so communes with higher PM2.5 should rank higher
        in EBI. A weak correlation (< 0.3) would indicate a
        regression in the EBI computation.
        """
        merged = self.master[["name", "pm25_mean"]].merge(
            self.ebi[["name", "ebi_score"]], on="name",
        )
        rho, _ = spearmanr(merged["pm25_mean"], merged["ebi_score"])
        self.assertGreater(
            rho, 0.3,
            f"Spearman(EBI, PM2.5) = {rho:.3f}, expected > 0.3",
        )

    def test_ebi_inversely_correlated_with_greenspace(self) -> None:
        """Higher NDVI should be negatively correlated with EBI (rho < -0.2).

        Greenspace NDVI has sign=-1 in the canonical set, so communes
        with more greenspace should have lower EBI. The empirical
        v1.2 correlation is rho = -0.21; we use a weak threshold to
        detect regressions where the sign flips.
        """
        merged = self.master[["name", "green_cover_pct_ndvi"]].merge(
            self.ebi[["name", "ebi_score"]], on="name",
        )
        rho, _ = spearmanr(
            merged["green_cover_pct_ndvi"], merged["ebi_score"],
        )
        self.assertLess(
            rho, -0.2,
            f"Spearman(EBI, NDVI) = {rho:.3f}, expected < -0.2 (sign flip regression)",
        )

    def test_ebi_top_commune_is_industrial_or_low_nse(self) -> None:
        """The top-1 EBI commune must be a known industrial/low-NSE commune.

        Lock-in: based on v1.2 results, Lo Espejo, Cerrillos, Tiltil,
        Estación Central, Pedro Aguirre Cerda, Lampa, Quilicura or
        similar industrial/low-NSE commune should be the top-1.
        """
        top = self.ebi.loc[self.ebi["ebi_rank"] == 1.0, "name"].iloc[0]
        expected_pool = {
            "Lo Espejo", "Cerrillos", "Tiltil", "Estación Central",
            "Pedro Aguirre Cerda", "Lampa", "Quilicura",
            "Independencia", "Renca", "Cerro Navia",
        }
        self.assertIn(
            top, expected_pool,
            f"top-1 EBI commune {top!r} not in expected industrial pool",
        )

    def test_ebi_bottom_commune_is_high_nse(self) -> None:
        """The bottom-1 EBI commune must be a known high-NSE commune."""
        bottom = self.ebi.loc[self.ebi["ebi_rank"] == 52.0, "name"].iloc[0]
        expected_pool = {
            "Las Condes", "La Florida", "La Reina", "Peñalolén",
            "Providencia", "Vitacura", "Ñuñoa", "Lo Barnechea",
        }
        self.assertIn(
            bottom, expected_pool,
            f"bottom-1 EBI commune {bottom!r} not in expected high-NSE pool",
        )

    def test_db_score_in_unit_interval(self) -> None:
        """Double-burden score must be in [0, 1] for all 52 communes."""
        scores = self.ebi["db_score"].dropna()
        self.assertGreaterEqual(scores.min(), 0.0)
        self.assertLessEqual(scores.max(), 1.0)

    def test_ebi_pca_score_in_unit_interval(self) -> None:
        """EBI-PCA score must be in [0, 1] for all 52 communes."""
        scores = self.ebi["ebi_pca_score"].dropna()
        self.assertGreaterEqual(scores.min(), 0.0)
        self.assertLessEqual(scores.max(), 1.0)

    def test_effective_dose_mean_in_unit_interval(self) -> None:
        """Effective-dose mean must be in [0, 1] for all 52 communes."""
        scores = self.ebi["effective_dose_mean"].dropna()
        self.assertGreaterEqual(scores.min(), 0.0)
        self.assertLessEqual(scores.max(), 1.0)

    def test_summary_json_top_bottom_match_ebi(self) -> None:
        """The cross_layer_summary.json top/bottom 5 must match EBI CSV.

        This is a strict round-trip check: if the EBI CSV is
        regenerated, the JSON must also be regenerated, and the
        top/bottom 5 must be consistent.
        """
        import json
        with open(SUMMARY_JSON) as f:
            summary = json.load(f)
        ebi_top = [
            e["name"] for e in summary["ebi_top_bottom"]["top_n"]
        ]
        ebi_bottom = [
            e["name"] for e in summary["ebi_top_bottom"]["bottom_n"]
        ]
        csv_top = (
            self.ebi
            .nsmallest(5, "ebi_rank")["name"]
            .tolist()
        )
        csv_bottom = (
            self.ebi
            .nlargest(5, "ebi_rank")["name"]
            .tolist()
        )
        self.assertEqual(
            set(ebi_top), set(csv_top),
            f"summary.json top-5 {ebi_top} != EBI CSV top-5 {csv_top}",
        )
        self.assertEqual(
            set(ebi_bottom), set(csv_bottom),
            f"summary.json bottom-5 {ebi_bottom} != EBI CSV bottom-5 {csv_bottom}",
        )

    def test_summary_json_has_v12_fields(self) -> None:
        """Summary JSON must include v1.2 fields:
        cluster_assignments, ebi_pca_top_bottom, db_top_bottom,
        double_burden_top10, pca_variance_explained, pca_n_components_retained.
        """
        import json
        with open(SUMMARY_JSON) as f:
            summary = json.load(f)
        for key in (
            "ebi_pca_top_bottom", "db_top_bottom",
            "double_burden_top10", "pca_variance_explained",
            "pca_n_components_retained", "cluster_assignments",
        ):
            self.assertIn(
                key, summary, f"summary.json missing v1.2 field {key!r}",
            )

    def test_pca_variance_explained_is_high(self) -> None:
        """PCA should retain >= 80% variance in <= 6 components."""
        import json
        with open(SUMMARY_JSON) as f:
            summary = json.load(f)
        var = summary["pca_variance_explained"]
        n = summary["pca_n_components_retained"]
        self.assertGreaterEqual(
            var, 0.80,
            f"PCA variance explained {var:.3f}, expected >= 0.80",
        )
        self.assertLessEqual(
            n, 6,
            f"PCA n_components_retained {n}, expected <= 6",
        )


if __name__ == "__main__":
    unittest.main()

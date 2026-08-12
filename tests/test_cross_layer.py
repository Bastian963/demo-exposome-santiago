"""Tests for the cross-layer analysis artefacts (EBI, hotspots, correlations)."""
from __future__ import annotations

import json
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "processed"
FIG_DIR = REPO_ROOT / "figures"

EBI_CSV = DATA_DIR / "environmental_burden_index.csv"
SUMMARY_JSON = DATA_DIR / "cross_layer_summary.json"
FIG_CORR = FIG_DIR / "correlation_matrix_cross_layer.png"
FIG_HOTSPOT = FIG_DIR / "socio_environmental_hotspots.png"
FIG_EBI = FIG_DIR / "environmental_burden_index.png"


class CrossLayerArtefactsTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if EBI_CSV.exists():
            cls.ebi = pd.read_csv(EBI_CSV)
        else:
            cls.ebi = None
        if SUMMARY_JSON.exists():
            cls.summary = json.loads(SUMMARY_JSON.read_text())
        else:
            cls.summary = None

    def test_ebi_csv_exists(self) -> None:
        self.assertTrue(EBI_CSV.exists(), f"Missing: {EBI_CSV}")

    def test_summary_json_exists(self) -> None:
        self.assertTrue(SUMMARY_JSON.exists(), f"Missing: {SUMMARY_JSON}")

    def test_figure_correlation_exists(self) -> None:
        self.assertTrue(FIG_CORR.exists(), f"Missing: {FIG_CORR}")
        self.assertGreater(FIG_CORR.stat().st_size, 30_000)

    def test_figure_hotspot_exists(self) -> None:
        self.assertTrue(FIG_HOTSPOT.exists(), f"Missing: {FIG_HOTSPOT}")
        self.assertGreater(FIG_HOTSPOT.stat().st_size, 30_000)

    def test_figure_ebi_exists(self) -> None:
        self.assertTrue(FIG_EBI.exists(), f"Missing: {FIG_EBI}")
        self.assertGreater(FIG_EBI.stat().st_size, 30_000)

    def test_ebi_shape(self) -> None:
        if self.ebi is None:
            self.skipTest("EBI CSV not visible")
        self.assertEqual(self.ebi.shape[0], 52)
        self.assertIn("name", self.ebi.columns)
        self.assertIn("ebi_score", self.ebi.columns)
        self.assertIn("ebi_rank", self.ebi.columns)

    def test_ebi_score_in_unit_interval(self) -> None:
        if self.ebi is None:
            self.skipTest("EBI CSV not visible")
        self.assertGreaterEqual(self.ebi["ebi_score"].min(), 0.0)
        self.assertLessEqual(self.ebi["ebi_score"].max(), 1.0)

    def test_ebi_rank_covers_52_communes(self) -> None:
        """Each of the 52 communes gets a rank; max rank equals 52.

        Ties on EBI score share an average rank, so the set of
        distinct ranks can be < 52; what matters is that every
        commune has a rank and the max equals 52.
        """
        if self.ebi is None:
            self.skipTest("EBI CSV not visible")
        ranks = self.ebi["ebi_rank"].dropna()
        self.assertEqual(len(ranks), 52)
        self.assertEqual(ranks.max(), 52.0)
        self.assertEqual(ranks.min(), 1.0)

    def test_ebi_top5_known(self) -> None:
        """Lock-in the expected high-burden communes.

        v1.3 top 5 from the 2024 master: Lo Espejo, Cerrillos,
        Pedro Aguirre Cerda, Renca, Tiltil. These are periphery
        industrial / high-deprivation communes; a change would
        suggest a master or indicator-list regression.

        Updated from v1.2 (Lo Espejo, Cerrillos, Tiltil, Estacion
        Central, Lampa) after fixing a data-labeling bug in the
        socioeconomic layer's pobreza_pct/pobreza_multi_pct (a
        third-party CSV was serving 2022 multidimensional-poverty
        values under the income-poverty label -- see
        docs/pobreza_sae_methodology.md). EBI uses both pobreza_pct
        and nse_index directly (scripts/analyze_cross_layer.py), so
        this shift is the expected effect of correcting that bug, not
        a regression.
        """
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        top = [r["name"] for r in self.summary["ebi_top_bottom"]["top_n"]]
        expected = {"Lo Espejo", "Cerrillos", "Tiltil"}
        self.assertTrue(
            expected.issubset(set(top)),
            f"Expected high-burden communes missing from top-5: "
            f"got {top}",
        )

    def test_ebi_bottom5_known(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        bot = [r["name"] for r in self.summary["ebi_bottom_bottom"]["bottom_n"]] \
            if "ebi_bottom_bottom" in self.summary["ebi_top_bottom"] \
            else [r["name"] for r in self.summary["ebi_top_bottom"]["bottom_n"]]
        expected = {"Las Condes", "La Reina"}
        self.assertTrue(
            expected.issubset(set(bot)),
            f"Expected low-burden communes missing from bottom-5: "
            f"got {bot}",
        )

    def test_hotspot_field_is_list(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        self.assertIsInstance(
            self.summary["hotspots_high_burden_and_deprivation"], list,
        )

    def test_strong_correlations_listed(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        pairs = self.summary["strong_correlations_abs_rho_ge_0.5"]
        self.assertIsInstance(pairs, list)
        self.assertGreater(len(pairs), 5, "expected many |rho|>0.5 pairs")
        for p in pairs:
            self.assertIn("indicator_a", p)
            self.assertIn("indicator_b", p)
            self.assertIn("spearman_rho", p)
            self.assertGreaterEqual(abs(p["spearman_rho"]), 0.5)

    def test_canonical_indicators_documented(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        ci = self.summary.get("canonical_indicators", [])
        self.assertGreaterEqual(len(ci), 10)
        for entry in ci:
            self.assertIn("label", entry)
            self.assertIn("column", entry)
            self.assertIn("direction", entry)
            self.assertIn(entry["direction"], (-1, +1))

    def test_db_score_in_unit_interval(self) -> None:
        if self.ebi is None:
            self.skipTest("EBI CSV not visible")
        self.assertIn("db_score", self.ebi.columns)
        self.assertGreaterEqual(self.ebi["db_score"].min(), 0.0)
        self.assertLessEqual(self.ebi["db_score"].max(), 1.0)

    def test_db_rank_covers_52_communes(self) -> None:
        if self.ebi is None:
            self.skipTest("EBI CSV not visible")
        ranks = self.ebi["db_rank"].dropna()
        self.assertEqual(len(ranks), 52)
        self.assertEqual(ranks.max(), 52.0)
        self.assertEqual(ranks.min(), 1.0)

    def test_db_score_antitonic_with_nse(self) -> None:
        """Communes with low NSE (high deprivation) tend to have
        higher double-burden score (Spearman negative)."""
        if self.ebi is None:
            self.skipTest("EBI CSV not visible")
        from scipy.stats import spearmanr
        master = pd.read_csv(DATA_DIR / "santiago_exposome_master.csv")
        m = self.ebi.merge(master[["name", "nse_index"]], on="name")
        rho, _ = spearmanr(m["nse_index"], m["db_score"])
        self.assertLess(
            rho, -0.30,
            f"db_score should be antitonically related to nse_index; "
            f"observed rho = {rho:.3f}",
        )

    def test_double_burden_top10_in_summary(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        self.assertIn("double_burden_top10", self.summary)
        self.assertIsInstance(self.summary["double_burden_top10"], list)

    def test_ebi_pca_in_unit_interval(self) -> None:
        if self.ebi is None:
            self.skipTest("EBI CSV not visible")
        self.assertIn("ebi_pca_score", self.ebi.columns)
        self.assertGreaterEqual(self.ebi["ebi_pca_score"].min(), 0.0)
        self.assertLessEqual(self.ebi["ebi_pca_score"].max(), 1.0)

    def test_pca_variance_explained_above_threshold(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        v = self.summary.get("pca_variance_explained", 0.0)
        self.assertGreater(
            v, 0.70,
            f"PCA variance explained {v:.3f} < 0.70; PC1+ may not be enough",
        )

    def test_pca_n_components_documented(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        self.assertIn("pca_n_components_retained", self.summary)
        self.assertGreater(self.summary["pca_n_components_retained"], 0)

    def test_ebi_pca_top_bottom_documented(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        self.assertIn("ebi_pca_top_bottom", self.summary)
        self.assertEqual(len(self.summary["ebi_pca_top_bottom"]["top_n"]), 5)
        self.assertEqual(len(self.summary["ebi_pca_top_bottom"]["bottom_n"]), 5)

    def test_effective_dose_columns_present(self) -> None:
        if self.ebi is None:
            self.skipTest("EBI CSV not visible")
        self.assertIn("effective_dose_mean", self.ebi.columns)
        self.assertIn("effective_dose_rank", self.ebi.columns)

    def test_effective_dose_in_unit_interval(self) -> None:
        if self.ebi is None:
            self.skipTest("EBI CSV not visible")
        s = self.ebi["effective_dose_mean"].dropna()
        self.assertGreaterEqual(s.min(), 0.0)
        self.assertLessEqual(s.max(), 1.0)

    def test_effective_dose_correlates_with_pm25(self) -> None:
        """Effective dose ~ pollutant; PM2.5 should be the main driver."""
        if self.ebi is None:
            self.skipTest("EBI CSV not visible")
        from scipy.stats import spearmanr
        master = pd.read_csv(DATA_DIR / "santiago_exposome_master.csv")
        m = self.ebi.merge(master[["name", "pm25_mean"]], on="name")
        rho, _ = spearmanr(m["pm25_mean"], m["effective_dose_mean"])
        self.assertGreater(
            rho, 0.5,
            f"effective_dose should correlate strongly with PM2.5; "
            f"observed rho = {rho:.3f}",
        )

    def test_effective_dose_correlates_with_wind_calm_winter(self) -> None:
        """Effective dose should be at least weakly correlated with
        winter calm (rho > 0). The correlation is weaker than with
        PM2.5 because winter calm has low variance (17/52 communes
        share an ERA5 pixel).
        """
        if self.ebi is None:
            self.skipTest("EBI CSV not visible")
        from scipy.stats import spearmanr
        master = pd.read_csv(DATA_DIR / "santiago_exposome_master.csv")
        m = self.ebi.merge(master[["name", "wind_calm_pct_winter"]],
                            on="name")
        rho, _ = spearmanr(
            m["wind_calm_pct_winter"], m["effective_dose_mean"],
        )
        self.assertGreater(
            rho, 0.0,
            f"effective_dose should be at least weakly positive with "
            f"winter calm; observed rho = {rho:.3f}",
        )

    def test_effective_dose_figure_exists(self) -> None:
        fig_path = FIG_DIR / "effective_dose_winter_map.png"
        self.assertTrue(fig_path.exists(), f"Missing: {fig_path}")
        self.assertGreater(fig_path.stat().st_size, 30_000)

    def test_pca_loadings_figure_exists(self) -> None:
        fig_path = FIG_DIR / "ebi_pca_loadings.png"
        self.assertTrue(fig_path.exists(), f"Missing: {fig_path}")
        self.assertGreater(fig_path.stat().st_size, 30_000)


if __name__ == "__main__":
    unittest.main()

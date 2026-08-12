"""Tests for the commune K-means clustering analysis."""
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

CLUSTERS_CSV = DATA_DIR / "commune_clusters.csv"
FIG_CLUSTERS = FIG_DIR / "commune_clusters_map.png"
SUMMARY_JSON = DATA_DIR / "cross_layer_summary.json"

EXPECTED_K_RANGE = (3, 5)


class CommuneClustersTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if CLUSTERS_CSV.exists():
            cls.df = pd.read_csv(CLUSTERS_CSV)
        else:
            cls.df = None
        if SUMMARY_JSON.exists():
            cls.summary = json.loads(SUMMARY_JSON.read_text())
        else:
            cls.summary = None

    def test_csv_exists(self) -> None:
        self.assertTrue(CLUSTERS_CSV.exists(), f"Missing: {CLUSTERS_CSV}")

    def test_figure_exists(self) -> None:
        self.assertTrue(FIG_CLUSTERS.exists(), f"Missing: {FIG_CLUSTERS}")
        self.assertGreater(FIG_CLUSTERS.stat().st_size, 30_000)

    def test_csv_shape(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(self.df.shape[0], 52)
        for col in ("name", "cluster_id", "cluster_label",
                    "cluster_size", "silhouette_global"):
            self.assertIn(col, self.df.columns, f"Missing column: {col}")

    def test_unique_names(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(self.df["name"].nunique(), 52)
        self.assertEqual(self.df["name"].isna().sum(), 0)

    def test_clusters_in_range(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        n_clusters = self.df["cluster_id"].nunique()
        self.assertGreaterEqual(
            n_clusters, EXPECTED_K_RANGE[0],
            f"only {n_clusters} clusters; expected >= {EXPECTED_K_RANGE[0]}",
        )
        self.assertLessEqual(
            n_clusters, EXPECTED_K_RANGE[1],
            f"{n_clusters} clusters; expected <= {EXPECTED_K_RANGE[1]}",
        )

    def test_silhouette_above_floor(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        s = float(self.df["silhouette_global"].iloc[0])
        self.assertGreater(
            s, 0.20,
            f"silhouette {s:.3f} too low; expected > 0.20",
        )

    def test_no_singleton_clusters(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        sizes = self.df.groupby("cluster_id").size()
        self.assertGreaterEqual(
            int(sizes.min()), 5,
            f"cluster with < 5 communes: {sizes.min()}",
        )

    def test_labels_assigned(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        # No NaN labels, and no "cluster_?" sentinel.
        for lab in self.df["cluster_label"]:
            self.assertIsInstance(lab, str)
            self.assertNotIn("?", lab, f"sentinel label: {lab!r}")

    def test_summary_includes_cluster_assignments(self) -> None:
        if self.summary is None:
            self.skipTest("summary JSON not visible")
        self.assertIn("cluster_assignments", self.summary)
        ca = self.summary["cluster_assignments"]
        self.assertIn("selected_k", ca)
        self.assertIn("clusters", ca)
        self.assertEqual(len(ca["clusters"]),
                         len({c["id"] for c in ca["clusters"]}))

    def test_known_communes_in_expected_clusters(self) -> None:
        """Lock-in the expected cluster assignments for v1.2.

        v1.2 cluster assignments (k=4, silhouette=0.407):
        - Las Condes, Vitacura, Providencia, La Reina, Nunoa
          all in the same cluster (residencial-Andes).
        - Lo Espejo, Cerrillos, Estacion Central all in the same
          cluster (industrial-periferia).
        - Alhue, Til til, Melipilla (rural) in the same cluster
          (rural-verde).
        """
        if self.df is None:
            self.skipTest("CSV not visible")
        cluster_by_name = dict(
            zip(self.df["name"], self.df["cluster_id"]),
        )
        residencial = {"Las Condes", "Vitacura", "Providencia",
                        "La Reina", "Ñuñoa"}
        industrial = {"Lo Espejo", "Cerrillos", "Estación Central",
                      "Renca"}
        rural = {"Alhué", "Tiltil", "Melipilla", "María Pinto"}
        for n in residencial:
            self.assertIn(n, cluster_by_name, f"{n} not in clusters")
        residencial_ids = {cluster_by_name[n] for n in residencial
                           if n in cluster_by_name}
        self.assertEqual(
            len(residencial_ids), 1,
            f"residencial-Andes communes split across clusters: "
            f"{[(n, cluster_by_name[n]) for n in residencial if n in cluster_by_name]}",
        )
        industrial_ids = {cluster_by_name[n] for n in industrial
                          if n in cluster_by_name}
        self.assertEqual(
            len(industrial_ids), 1,
            f"industrial-periferia communes split: "
            f"{[(n, cluster_by_name[n]) for n in industrial if n in cluster_by_name]}",
        )
        rural_ids = {cluster_by_name[n] for n in rural
                     if n in cluster_by_name}
        self.assertEqual(
            len(rural_ids), 1,
            f"rural-verde communes split: "
            f"{[(n, cluster_by_name[n]) for n in rural if n in cluster_by_name]}",
        )


if __name__ == "__main__":
    unittest.main()

"""Tests for the walkability exposome layer (OSM street network)."""
from __future__ import annotations

import json
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, box

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.walkability import _checkpoint_path, _network_stats_for_commune  # noqa: E402

DATA_DIR = REPO_ROOT / "data" / "processed"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"
MASTER_GEOJSON = DATA_DIR / "santiago_exposome_master.geojson"
FIG_DIR = REPO_ROOT / "figures"
DOC_DIR = REPO_ROOT / "docs"

EXPECTED_COLUMNS = [
    "name",
    "walk_intersection_density",
    "walk_street_density_km_km2",
    "walk_avg_street_length_m",
    "walk_streets_per_node",
    "walk_circuity",
    "walk_n_nodes",
    "walk_index",
]

KNOWN_COMMUNES = {
    "Santiago", "Providencia", "Las Condes", "Vitacura",
    "Ñuñoa", "La Granja", "Maipú", "Puente Alto",
    "Alhué", "San José de Maipo", "San Pedro",
}


class NetworkStatsFailModeTests(unittest.TestCase):
    """Offline coverage for the fail-explicit vs genuinely-sparse distinction.

    A *successful* Overpass query returning a tiny graph (< 5 nodes, e.g. a
    real rural commune with almost no mapped streets) is a legitimate sparse
    network and must not be retried. A query that never succeeds -- every
    Overpass mirror/attempt exhausted -- must raise instead of also
    returning None: those two cases used to be indistinguishable, so a full
    Overpass outage silently 0-filled every commune's walkability metrics
    and the layer "executed" successfully with fabricated data instead of
    failing (build_walkability_layer's per-commune loop deliberately does
    not catch this exception -- see the comment there).
    """

    def setUp(self) -> None:
        sleep_patch = patch("exposome.osm_fetch.time.sleep")
        sleep_patch.start()
        self.addCleanup(sleep_patch.stop)

    def test_genuinely_sparse_network_returns_none_without_retry(self) -> None:
        sparse_graph = MagicMock()
        sparse_graph.number_of_nodes.return_value = 3
        calls = {"n": 0}

        def fake_graph_from_polygon(geom, network_type):
            calls["n"] += 1
            return sparse_graph

        with patch(
            "exposome.walkability.ox.graph_from_polygon", side_effect=fake_graph_from_polygon
        ):
            result = _network_stats_for_commune(object(), area_m2=1000.0, metric_crs="EPSG:32719")

        self.assertIsNone(result)
        self.assertEqual(calls["n"], 1)

    def test_exhausted_overpass_retries_raise_instead_of_returning_none(self) -> None:
        def always_fails(geom, network_type):
            raise ConnectionError("Max retries exceeded")

        with patch("exposome.walkability.ox.graph_from_polygon", side_effect=always_fails):
            with self.assertRaises(ConnectionError):
                _network_stats_for_commune(object(), area_m2=1000.0, metric_crs="EPSG:32719")

    def test_local_highway_lines_do_not_call_overpass(self) -> None:
        geometry = box(-0.01, -0.01, 0.01, 0.01)
        roads = gpd.GeoDataFrame(
            {
                "id": ["east_west", "north_south"],
                "highway": ["residential", "residential"],
                "geometry": [
                    LineString([(-0.01, 0), (0, 0), (0.01, 0)]),
                    LineString([(0, -0.01), (0, 0), (0, 0.01)]),
                ],
            },
            crs="EPSG:4326",
        )
        with patch("exposome.walkability.ox.graph_from_polygon") as remote:
            result = _network_stats_for_commune(
                geometry,
                area_m2=1_000_000,
                metric_crs="EPSG:3857",
                local_highways=roads,
            )

        remote.assert_not_called()
        self.assertIsNotNone(result)
        assert result is not None
        self.assertGreaterEqual(result["walk_n_nodes"], 5)
        self.assertGreater(result["walk_intersection_density"], 0)


class CheckpointPathTests(unittest.TestCase):
    def test_local_extract_uses_a_separate_checkpoint_from_live_overpass(self) -> None:
        output = Path("/tmp/walkability-output")
        cache = Path("/tmp/walkability-cache")
        remote = _checkpoint_path("sao_paulo_distritos", output, cache, None)
        local = _checkpoint_path(
            "sao_paulo_distritos", output, cache, "data/raw/geofabrik/sudeste/260819/sudeste.osm.pbf"
        )

        self.assertEqual(remote, output / "sao_paulo_distritos_walkability.csv")
        self.assertEqual(local.parent, cache)
        self.assertTrue(local.name.startswith("sao_paulo_distritos_walkability_pbf_"))
        self.assertNotEqual(local, remote)


class WalkabilityLayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "santiago_walkability.csv"
        cls.geojson_path = DATA_DIR / "santiago_walkability.geojson"
        cls.metadata_path = DATA_DIR / "santiago_walkability_metadata.json"
        cls.doc_path = DOC_DIR / "walkability_methodology.md"
        cls.fig_path = FIG_DIR / "walkability_santiago_4panel.png"

        if cls.csv_path.exists():
            cls.df = pd.read_csv(cls.csv_path)
        else:
            cls.df = None
        if cls.metadata_path.exists():
            cls.metadata = json.loads(cls.metadata_path.read_text())
        else:
            cls.metadata = None

    def test_csv_exists(self) -> None:
        self.assertTrue(self.csv_path.exists(), f"Missing: {self.csv_path}")

    def test_geojson_exists(self) -> None:
        self.assertTrue(self.geojson_path.exists(), f"Missing: {self.geojson_path}")

    def test_metadata_exists(self) -> None:
        self.assertTrue(self.metadata_path.exists(), f"Missing: {self.metadata_path}")

    def test_documentation_exists(self) -> None:
        self.assertTrue(self.doc_path.exists(), f"Missing: {self.doc_path}")
        text = self.doc_path.read_text()
        self.assertGreater(len(text), 1500, "Methodology doc is too short.")

    def test_figure_exists(self) -> None:
        self.assertTrue(self.fig_path.exists(), f"Missing: {self.fig_path}")
        self.assertGreater(self.fig_path.stat().st_size, 50_000)

    def test_csv_shape(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(self.df.shape[0], 52, f"Expected 52 communes, got {self.df.shape[0]}")
        self.assertEqual(self.df.shape[1], len(EXPECTED_COLUMNS))

    def test_required_columns(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, self.df.columns, f"Missing column: {col}")

    def test_unique_names(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertEqual(self.df["name"].nunique(), 52)
        self.assertEqual(self.df["name"].isna().sum(), 0)

    def test_known_communes_present(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        names = set(self.df["name"].astype(str))
        for k in KNOWN_COMMUNES:
            self.assertIn(k, names, f"Known commune missing: {k}")

    def test_walk_index_range(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertGreaterEqual(self.df["walk_index"].min(), 0.0)
        self.assertLessEqual(self.df["walk_index"].max(), 100.0)
        self.assertGreater(self.df["walk_index"].max(), 0.0, "walk_index max must be > 0")

    def test_intersection_density_non_negative(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertGreaterEqual(self.df["walk_intersection_density"].min(), 0.0)

    def test_avg_street_length_sane(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        avg_len = self.df["walk_avg_street_length_m"]
        self.assertGreaterEqual(avg_len.min(), 0.0)
        self.assertLessEqual(avg_len.max(), 2000.0, "block length > 2 km is implausible")

    def test_circuity_sane(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        c = self.df["walk_circuity"]
        self.assertGreaterEqual(c.min(), 1.0, "circuity must be >= 1.0 (straight-line)")
        self.assertLessEqual(c.max(), 3.0, "circuity > 3.0 is implausible")

    def test_streets_per_node_sane(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        spn = self.df["walk_streets_per_node"]
        self.assertGreaterEqual(spn.min(), 1.0, "streets_per_node must be >= 1.0")
        self.assertLessEqual(spn.max(), 5.0, "streets_per_node > 5.0 is implausible")

    def test_n_nodes_positive(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        self.assertGreater(self.df["walk_n_nodes"].min(), 0)

    def test_known_extremes(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        top = self.df.nlargest(1, "walk_index").iloc[0]
        bot = self.df.nsmallest(1, "walk_index").iloc[0]
        self.assertEqual(top["name"], "La Granja", f"Top walkability must be La Granja, got {top['name']}")
        self.assertEqual(bot["name"], "San José de Maipo", f"Bottom must be San José de Maipo, got {bot['name']}")

    def test_no_nans_in_key_columns(self) -> None:
        if self.df is None:
            self.skipTest("CSV not visible")
        for col in EXPECTED_COLUMNS:
            self.assertEqual(self.df[col].isna().sum(), 0, f"NaN found in {col}")

    def test_metadata_consistent(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata file not yet visible")
        self.assertEqual(self.metadata.get("n_communes"), 52)
        self.assertEqual(self.metadata.get("network_type"), "all")
        self.assertIn("osmnx", self.metadata.get("source", "").lower())
        self.assertEqual(self.metadata.get("crs_metric"), "EPSG:32719")

    def test_top5_metadata_consistent(self) -> None:
        if self.metadata is None or self.df is None:
            self.skipTest("metadata or CSV not yet visible")
        meta_top5 = [c[0] for c in self.metadata.get("top5_most_walkable", [])]
        df_top5 = self.df.nlargest(5, "walk_index")["name"].tolist()
        self.assertEqual(meta_top5, df_top5, "top5 in metadata must match CSV ranking")

    def test_in_master_csv(self) -> None:
        if not MASTER_CSV.exists() or self.df is None:
            self.skipTest("master CSV not yet visible")
        master = pd.read_csv(MASTER_CSV, nrows=1)
        for col in ("walk_index", "walk_intersection_density"):
            self.assertIn(col, master.columns, f"Master missing column: {col}")

    def test_in_master_geojson(self) -> None:
        if not MASTER_GEOJSON.exists() or self.df is None:
            self.skipTest("master GeoJSON not yet visible")
        import geopandas as gpd
        master = gpd.read_file(MASTER_GEOJSON, rows=1)
        for col in ("walk_index", "walk_intersection_density"):
            self.assertIn(col, master.columns, f"Master GeoJSON missing column: {col}")


if __name__ == "__main__":
    unittest.main()

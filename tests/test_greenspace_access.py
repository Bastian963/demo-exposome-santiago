"""Tests for the greenspace_access layer computations.

All tests run offline — no OSM/network calls. We build minimal GeoDataFrames
in a metric CRS and verify the geometry computations produce sane values.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import Polygon

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.greenspace_access import (  # noqa: E402
    _normalize_regions,
    _region_slug,
    _unit_geometry_for_region,
    compute_access_metrics,
    compute_green_coverage,
    fetch_green_areas,
)
from exposome.osm_fetch import GREEN_TAG_MAX_TILE_SPAN_DEG, tile_grid_size_for_bbox  # noqa: E402

# Simple metric CRS (UTM zone 19S, used for Santiago)
METRIC_CRS = "EPSG:32719"


def _make_communes() -> gpd.GeoDataFrame:
    """Two 1 km x 1 km square communes side by side."""
    c1 = Polygon([(0, 0), (1000, 0), (1000, 1000), (0, 1000)])  # left
    c2 = Polygon([(1000, 0), (2000, 0), (2000, 1000), (1000, 1000)])  # right
    gdf = gpd.GeoDataFrame(
        {"name": ["ComunaA", "ComunaB"], "area_km2": [1.0, 1.0]},
        geometry=[c1, c2],
        crs=METRIC_CRS,
    )
    return gdf


def _make_green_areas(metric_crs: str) -> gpd.GeoDataFrame:
    """Two small green polygons, both inside ComunaA."""
    p1 = Polygon([(100, 100), (300, 100), (300, 300), (100, 300)])  # 0.04 km²
    p2 = Polygon([(500, 500), (600, 500), (600, 600), (500, 600)])  # 0.01 km²
    return gpd.GeoDataFrame(
        {"geometry": [p1, p2]},
        crs=metric_crs,
    )


class TestComputeGreenCoverage(unittest.TestCase):
    def setUp(self) -> None:
        self.communes = _make_communes()
        self.green = _make_green_areas(METRIC_CRS)

    def test_green_area_in_correct_commune(self) -> None:
        result = compute_green_coverage(self.communes, self.green)
        # Both green polygons are in ComunaA
        row_a = result[result["name"] == "ComunaA"].iloc[0]
        row_b = result[result["name"] == "ComunaB"].iloc[0]
        self.assertGreater(row_a["green_osm_km2"], 0)
        self.assertAlmostEqual(row_b["green_osm_km2"], 0, places=3)

    def test_green_pct_is_ratio_of_area(self) -> None:
        result = compute_green_coverage(self.communes, self.green)
        row_a = result[result["name"] == "ComunaA"].iloc[0]
        expected_pct = row_a["green_osm_km2"] / row_a["area_km2"] * 100
        self.assertAlmostEqual(row_a["green_osm_pct"], expected_pct, places=1)

    def test_polygon_count_per_commune(self) -> None:
        result = compute_green_coverage(self.communes, self.green)
        row_a = result[result["name"] == "ComunaA"].iloc[0]
        row_b = result[result["name"] == "ComunaB"].iloc[0]
        self.assertEqual(row_a["green_osm_n"], 2)
        self.assertEqual(row_b["green_osm_n"], 0)

    def test_no_nulls_in_result(self) -> None:
        result = compute_green_coverage(self.communes, self.green)
        numeric_cols = [c for c in result.columns if c not in ("name", "geometry")]
        self.assertFalse(result[numeric_cols].isna().any().any())


class TestComputeAccessMetrics(unittest.TestCase):
    def setUp(self) -> None:
        self.communes = _make_communes()
        self.green = _make_green_areas(METRIC_CRS)

    def test_dist_to_nearest_park_positive_for_commune_a(self) -> None:
        result = compute_access_metrics(self.communes, self.green, buffers_m=[500])
        row_a = result[result["name"] == "ComunaA"].iloc[0]
        # Centroid of ComunaA is at (500, 500). Green polygons are nearby.
        self.assertGreaterEqual(row_a["dist_to_nearest_park_m"], 0)

    def test_buffer_count_reflects_proximity(self) -> None:
        # With a 1000 m buffer around ComunaA (centred at commune boundary),
        # all green polygons in ComunaA should be reachable.
        result = compute_access_metrics(self.communes, self.green, buffers_m=[1000])
        row_a = result[result["name"] == "ComunaA"].iloc[0]
        self.assertGreater(row_a["green_count_within_1000m"], 0)

    def test_output_columns_present(self) -> None:
        buffers = [300, 500]
        result = compute_access_metrics(self.communes, self.green, buffers_m=buffers)
        expected_cols = {"name", "dist_to_nearest_park_m"}
        for b in buffers:
            expected_cols.add(f"green_count_within_{b}m")
            expected_cols.add(f"green_area_within_{b}m_km2")
        self.assertTrue(expected_cols.issubset(set(result.columns)))

    def test_no_nulls_in_numeric_cols(self) -> None:
        result = compute_access_metrics(self.communes, self.green, buffers_m=[300])
        numeric_cols = [c for c in result.columns if c not in ("name", "geometry")]
        self.assertFalse(result[numeric_cols].isna().any().any())


class TestTileGridSize(unittest.TestCase):
    """Bogota's rural localidades exposed a grid that stopped scaling past 2x2."""

    @staticmethod
    def _bbox(span: float) -> tuple[float, float, float, float]:
        return (-74.3, 3.7, -74.3 + span, 3.7 + span)

    @staticmethod
    def _grid(span: float) -> int:
        return tile_grid_size_for_bbox(TestTileGridSize._bbox(span), GREEN_TAG_MAX_TILE_SPAN_DEG)

    def test_no_tile_exceeds_the_span_budget(self) -> None:
        # Sumapaz (0.576) and Usme (0.276) are the units that failed against
        # Overpass; Usaquen (0.162) always succeeded as a single query.
        for span in (0.162, 0.216, 0.276, 0.576):
            with self.subTest(span=span):
                grid = self._grid(span)
                self.assertLessEqual(span / grid, GREEN_TAG_MAX_TILE_SPAN_DEG)

    def test_small_regions_stay_untiled(self) -> None:
        self.assertEqual(self._grid(GREEN_TAG_MAX_TILE_SPAN_DEG / 2), 1)

    def test_grid_grows_with_span(self) -> None:
        sumapaz = self._grid(0.576)
        usme = self._grid(0.276)
        self.assertGreater(sumapaz, usme)
        self.assertGreater(usme, 2, "the old 2x2 grid left 0.138 deg tiles that timed out")

    def test_uses_longest_side(self) -> None:
        wide = (-74.3, 3.7, -74.3 + 0.5, 3.7 + 0.01)
        self.assertEqual(
            tile_grid_size_for_bbox(wide, GREEN_TAG_MAX_TILE_SPAN_DEG),
            self._grid(0.5),
        )


class TestNormalizeRegions(unittest.TestCase):
    def test_single_string_becomes_one_item_list(self) -> None:
        self.assertEqual(_normalize_regions("Santiago, Chile"), ["Santiago, Chile"])

    def test_list_passes_through(self) -> None:
        regions = ["CABA, Argentina", "La Matanza, Argentina"]
        self.assertEqual(_normalize_regions(regions), regions)


class TestRegionSlug(unittest.TestCase):
    def test_strips_accents_and_punctuation(self) -> None:
        self.assertEqual(_region_slug("José C. Paz, Buenos Aires, Argentina"), "jose_c_paz_buenos_aires_argentina")

    def test_never_empty(self) -> None:
        self.assertEqual(_region_slug("###"), "region")

    def test_cercado_alias_matches_official_lima_unit(self) -> None:
        units = gpd.GeoDataFrame(
            {"name": ["LIMA"], "geometry": [Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])]},
            crs="EPSG:4326",
        )
        geometry = _unit_geometry_for_region("Cercado de Lima, Lima, Peru", units)
        self.assertIsNotNone(geometry)
        self.assertEqual(geometry.bounds, (0.0, 0.0, 1.0, 1.0))


def _make_cfg(region_query, tmp_path=None) -> dict:
    return {
        "greenspace": {"access": {"osm_tags": {"leisure": ["park"]}}},
        "region_query": region_query,
        "crs": {"geographic": "EPSG:4326"},
    }


class TestFetchGreenAreasChunking(unittest.TestCase):
    """Regression test: a multi-locality region_query must be downloaded one
    locality at a time with its own cache file — not as a single combined
    Overpass query. A single combined query over AMBA's 41 partidos is what
    emptied the cache in production: it timed out, and since nothing was
    cached until the very end, the retry lost every locality's data.
    """

    def setUp(self) -> None:
        # Skip the real inter-region pacing sleep in tests.
        patcher = patch("exposome.greenspace_access.time.sleep")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _polygon_gdf(self) -> gpd.GeoDataFrame:
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        return gpd.GeoDataFrame({"geometry": [poly], "name": ["x"]}, crs="EPSG:4326")

    def test_multi_locality_issues_one_call_per_region(self) -> None:
        regions = ["Region A, Argentina", "Region B, Argentina", "Region C, Argentina"]
        cfg = _make_cfg(regions)
        with patch(
            "exposome.greenspace_access._download_osm_green",
            return_value=self._polygon_gdf(),
        ) as mock_download:
            fetch_green_areas(cfg, cache_path=None)
        self.assertEqual(mock_download.call_count, len(regions))
        called_regions = [call.args[0] for call in mock_download.call_args_list]
        self.assertEqual(called_regions, regions)

    def test_failure_in_one_locality_preserves_others_cache(self) -> None:
        import tempfile

        regions = ["Region A, Argentina", "Region B, Argentina"]
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "combined_greenspace_osm.geojson"
            cfg = _make_cfg(regions)

            def side_effect(region, tags, **kwargs):
                if region == "Region B, Argentina":
                    raise ConnectionError("simulated Overpass failure")
                return self._polygon_gdf()

            with patch(
                "exposome.greenspace_access._download_osm_green",
                side_effect=side_effect,
            ):
                with self.assertRaises(ConnectionError):
                    fetch_green_areas(cfg, cache_path=cache_path)

            locality_dir = cache_path.parent / f"{cache_path.stem}_by_region"
            cached_files = list(locality_dir.glob("*.geojson"))
            self.assertEqual(len(cached_files), 1, "Region A's cache should survive Region B's failure")
            self.assertIn("region_a", cached_files[0].stem)
            # The combined cache must NOT be written when a region failed —
            # otherwise a later run would treat incomplete data as complete.
            self.assertFalse(cache_path.exists())

    def test_resume_skips_already_cached_localities(self) -> None:
        import tempfile

        regions = ["Region A, Argentina", "Region B, Argentina"]
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "combined_greenspace_osm.geojson"
            locality_dir = cache_path.parent / f"{cache_path.stem}_by_region"
            locality_dir.mkdir(parents=True)
            self._polygon_gdf().to_file(locality_dir / "region_a_argentina.geojson", driver="GeoJSON")

            cfg = _make_cfg(regions)
            with patch(
                "exposome.greenspace_access._download_osm_green",
                return_value=self._polygon_gdf(),
            ) as mock_download:
                fetch_green_areas(cfg, cache_path=cache_path)

            # Only the missing locality (Region B) should trigger a download.
            self.assertEqual(mock_download.call_count, 1)
            self.assertEqual(mock_download.call_args_list[0].args[0], "Region B, Argentina")


if __name__ == "__main__":
    unittest.main()

"""Tests for the shared OSM/Overpass endpoint-fallback + backoff helper.

Running several studies against a single hardcoded Overpass endpoint at once
saturated its per-IP connection limit (see the incident that stalled
cdmx_native/lima_distritos/bogota_localidades/valle_aburra_municipios).
``call_with_overpass_fallback`` is the fix: rotate across mirrors with
exponential backoff instead of hammering one endpoint on a fixed sleep. All
assertions here are offline -- ``time.sleep`` is mocked out so the tests run
instantly regardless of the configured backoff.
"""
from __future__ import annotations

import os
import signal
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import osmnx as ox  # noqa: E402
import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
from shapely.geometry import LineString, Point  # noqa: E402

from exposome.osm_fetch import (  # noqa: E402
    _bbox_tiles,
    call_with_overpass_fallback,
    fetch_features_from_bbox_tiled,
    fetch_features_from_local_extract,
    fetch_highway_lines_from_local_extract,
    local_extract_where,
    overpass_endpoints,
    parse_other_tags,
)
from osmnx._errors import InsufficientResponseError  # noqa: E402


class OverpassEndpointsTests(unittest.TestCase):
    def test_env_var_is_tried_first_and_deduplicated(self) -> None:
        with patch.dict(os.environ, {"OSMNX_OVERPASS_URL": "https://overpass-api.de/api/"}):
            endpoints = overpass_endpoints()
        self.assertEqual(endpoints[0], "https://overpass-api.de/api")
        self.assertEqual(len(endpoints), len(set(endpoints)))

    def test_defaults_present_without_env_var(self) -> None:
        env = dict(os.environ)
        env.pop("OSMNX_OVERPASS_URL", None)
        with patch.dict(os.environ, env, clear=True):
            endpoints = overpass_endpoints()
        self.assertIn("https://overpass-api.de/api", endpoints)
        self.assertIn("https://overpass.openstreetmap.fr/api", endpoints)


class CallWithOverpassFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_url = ox.settings.overpass_url
        sleep_patch = patch("exposome.osm_fetch.time.sleep")
        sleep_patch.start()
        self.addCleanup(sleep_patch.stop)
        self.addCleanup(setattr, ox.settings, "overpass_url", self.original_url)

    def test_rotates_endpoints_and_succeeds_on_second_mirror(self) -> None:
        seen_urls: list[str] = []

        def flaky() -> str:
            seen_urls.append(ox.settings.overpass_url)
            if ox.settings.overpass_url == "https://mirror-a/api":
                raise ConnectionError("mirror-a down")
            return "ok"

        result = call_with_overpass_fallback(
            flaky,
            endpoints=["https://mirror-a/api", "https://mirror-b/api"],
            attempts=2,
            base_sleep=0.01,
            log=lambda msg: None,
        )
        self.assertEqual(result, "ok")
        self.assertIn("https://mirror-b/api", seen_urls)
        self.assertEqual(ox.settings.overpass_url, self.original_url)

    def test_raises_connection_error_after_exhausting_all_endpoints(self) -> None:
        def always_fails() -> None:
            # osmnx itself raises a bare TypeError on malformed responses
            # from an overloaded server -- any exception must be retryable.
            raise TypeError("malformed response")

        with self.assertRaises(ConnectionError):
            call_with_overpass_fallback(
                always_fails,
                endpoints=["https://mirror-a/api", "https://mirror-b/api"],
                attempts=2,
                base_sleep=0.01,
                label="test-category",
            )
        self.assertEqual(ox.settings.overpass_url, self.original_url)

    def test_backoff_grows_exponentially_between_attempts(self) -> None:
        sleep_calls: list[float] = []
        with patch("exposome.osm_fetch.time.sleep", side_effect=sleep_calls.append):
            with self.assertRaises(ConnectionError):
                call_with_overpass_fallback(
                    lambda: (_ for _ in ()).throw(ConnectionError("down")),
                    endpoints=["https://mirror-a/api"],
                    attempts=3,
                    base_sleep=5.0,
                    backoff=3.0,
                )
        self.assertEqual(sleep_calls, [5.0, 15.0])

    def test_no_endpoints_raises_immediately(self) -> None:
        with self.assertRaises(ConnectionError):
            call_with_overpass_fallback(lambda: "unused", endpoints=[])

    @unittest.skipUnless(
        hasattr(signal, "setitimer") and hasattr(signal, "SIGALRM"),
        "POSIX wall-clock alarms are unavailable",
    )
    def test_attempt_deadline_rotates_away_from_stalled_endpoint(self) -> None:
        seen_urls: list[str] = []

        def stalls_on_first_endpoint() -> str:
            seen_urls.append(ox.settings.overpass_url)
            if ox.settings.overpass_url == "https://mirror-a/api":
                signal.pause()
            return "ok"

        result = call_with_overpass_fallback(
            stalls_on_first_endpoint,
            endpoints=["https://mirror-a/api", "https://mirror-b/api"],
            attempts=1,
            attempt_timeout_s=0.01,
            log=lambda msg: None,
        )
        self.assertEqual(result, "ok")
        self.assertEqual(
            seen_urls,
            ["https://mirror-a/api", "https://mirror-b/api"],
        )


class TiledBboxFetchTests(unittest.TestCase):
    def test_bbox_is_split_into_four_tiles(self) -> None:
        tiles = _bbox_tiles((-2, -1, 2, 1), 2)
        self.assertEqual(len(tiles), 4)
        self.assertEqual(tiles[0], (-2.0, -1.0, 0.0, 0.0))
        self.assertEqual(tiles[-1], (0.0, 0.0, 2.0, 1.0))

    def test_one_stubborn_tile_does_not_abort_the_rest_of_the_run(self) -> None:
        # Observed in production on Bogota's Usme/Sumapaz: aborting the whole
        # tile loop on the first failure meant each --resume only ever made
        # one tile of net progress before dying on the next untried tile.
        # A single stubborn tile must not block checkpointing every other
        # tile reachable in the same run.
        def feature_at(way_id: int, x: float, y: float) -> gpd.GeoDataFrame:
            index = pd.MultiIndex.from_tuples([("way", way_id)], names=["element", "id"])
            return gpd.GeoDataFrame(
                {"amenity": ["clinic"], "geometry": [Point(x, y)]},
                index=index,
                crs="EPSG:4326",
            )

        calls = 0

        def fail_only_second_tile(bbox, tags):
            del tags
            nonlocal calls
            calls += 1
            if bbox[1] < 0 and bbox[0] >= 0:  # the row=0,col=1 tile
                raise ConnectionError("simulated stuck tile")
            return feature_at(calls, bbox[0] + 0.5, bbox[1] + 0.5)

        with tempfile.TemporaryDirectory() as temporary:
            checkpoint_dir = Path(temporary)
            with patch(
                "exposome.osm_fetch.ox.features_from_bbox",
                side_effect=fail_only_second_tile,
            ):
                with self.assertRaises(ConnectionError) as ctx:
                    fetch_features_from_bbox_tiled(
                        (-1, -1, 1, 1),
                        {"amenity": ["clinic"]},
                        label="healthcare",
                        grid_size=2,
                        between_tiles_s=0,
                        checkpoint_dir=checkpoint_dir,
                        attempts=1,
                    )

            self.assertIn("1 of 4 tile(s)", str(ctx.exception))
            cached = list(checkpoint_dir.glob("query_*/tile_*.geojson"))
            self.assertEqual(len(cached), 3)  # the other three tiles still checkpointed

    def test_tile_with_zero_matching_features_is_not_treated_as_a_failure(self) -> None:
        # osmnx raises InsufficientResponseError instead of returning an empty
        # frame when a query has zero matches -- routine for sparse rural
        # tiles (e.g. Bogota's Usme/Sumapaz paramo), not a connectivity
        # problem. It must not trigger the endpoint-fallback retry loop.
        def feature_at(way_id: int, x: float, y: float) -> gpd.GeoDataFrame:
            index = pd.MultiIndex.from_tuples([("way", way_id)], names=["element", "id"])
            return gpd.GeoDataFrame(
                {"leisure": ["park"], "geometry": [Point(x, y)]},
                index=index,
                crs="EPSG:4326",
            )

        calls = 0

        def one_empty_tile(bbox, tags):
            del tags
            nonlocal calls
            calls += 1
            if bbox[0] < 0:
                raise InsufficientResponseError("No matching features.")
            return feature_at(calls, bbox[0] + 0.5, bbox[1] + 0.5)

        with patch("exposome.osm_fetch.ox.features_from_bbox", side_effect=one_empty_tile):
            with patch("exposome.osm_fetch.time.sleep"):
                result = fetch_features_from_bbox_tiled(
                    (-1, -1, 1, 1),
                    {"leisure": ["park"]},
                    label="greenspace_access",
                    grid_size=2,
                    between_tiles_s=0,
                )

        self.assertEqual(calls, 4)  # one call per tile, no retries/rotation
        self.assertEqual(len(result), 2)  # only the two tiles with real features

    def test_tiled_results_are_deduplicated_by_osm_id(self) -> None:
        index = pd.MultiIndex.from_tuples(
            [("node", 7)], names=["element", "id"]
        )

        def fake_bbox(bbox, tags):
            return gpd.GeoDataFrame(
                {"amenity": ["clinic"], "geometry": [Point(0, 0)]},
                index=index,
                crs="EPSG:4326",
            )

        with patch("exposome.osm_fetch.ox.features_from_bbox", side_effect=fake_bbox):
            with patch("exposome.osm_fetch.time.sleep"):
                result = fetch_features_from_bbox_tiled(
                    (-1, -1, 1, 1),
                    {"amenity": ["clinic"]},
                    label="healthcare",
                    grid_size=2,
                    between_tiles_s=0,
                )

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["element"], "node")
        self.assertEqual(int(result.iloc[0]["id"]), 7)

    def test_partial_tile_checkpoints_resume_without_repeating_finished_tiles(self) -> None:
        index = pd.MultiIndex.from_tuples(
            [("node", 7)], names=["element", "id"]
        )
        frame = gpd.GeoDataFrame(
            {"amenity": ["clinic"], "geometry": [Point(0, 0)]},
            index=index,
            crs="EPSG:4326",
        )
        calls = 0

        def fail_after_first_tile(bbox, tags):
            nonlocal calls
            del bbox, tags
            calls += 1
            if calls > 1:
                raise ConnectionError("simulated interrupted provider")
            return frame

        with tempfile.TemporaryDirectory() as temporary:
            checkpoint_dir = Path(temporary)
            with patch(
                "exposome.osm_fetch.ox.features_from_bbox",
                side_effect=fail_after_first_tile,
            ):
                with self.assertRaises(ConnectionError):
                    fetch_features_from_bbox_tiled(
                        (-1, -1, 1, 1),
                        {"amenity": ["clinic"]},
                        label="healthcare",
                        grid_size=2,
                        between_tiles_s=0,
                        checkpoint_dir=checkpoint_dir,
                        attempts=1,
                    )

            cached = list(checkpoint_dir.glob("query_*/tile_*.geojson"))
            self.assertEqual(len(cached), 1)

            with patch(
                "exposome.osm_fetch.ox.features_from_bbox",
                return_value=frame,
            ) as resumed:
                result = fetch_features_from_bbox_tiled(
                    (-1, -1, 1, 1),
                    {"amenity": ["clinic"]},
                    label="healthcare",
                    grid_size=2,
                    between_tiles_s=0,
                    checkpoint_dir=checkpoint_dir,
                    attempts=1,
                )

            self.assertEqual(resumed.call_count, 3)
            self.assertEqual(len(result), 1)


class ParseOtherTagsTests(unittest.TestCase):
    """GDAL's hstore blob is where every non-promoted OSM key lives."""

    def test_plain_pairs(self) -> None:
        self.assertEqual(
            parse_other_tags('"shop"=>"supermarket","access"=>"private"'),
            {"shop": "supermarket", "access": "private"},
        )

    def test_escaped_quote_inside_value(self) -> None:
        self.assertEqual(
            parse_other_tags('"name"=>"Bar \\"El Rincon\\"","amenity"=>"bar"'),
            {"name": 'Bar "El Rincon"', "amenity": "bar"},
        )

    def test_comma_inside_value_does_not_split_the_pair(self) -> None:
        # The separator and the value character are the same byte; only the
        # quoting tells them apart.
        self.assertEqual(
            parse_other_tags('"addr:street"=>"Gran Via, 42","shop"=>"convenience"'),
            {"addr:street": "Gran Via, 42", "shop": "convenience"},
        )

    def test_empty_and_non_string_inputs(self) -> None:
        for value in ("", None, float("nan"), 3):
            self.assertEqual(parse_other_tags(value), {})

    def test_unquoted_garbage_between_pairs_keeps_its_neighbours(self) -> None:
        # One odd fragment must not cost an entire region its features.
        self.assertEqual(
            parse_other_tags('"a"=>"1",garbage,"b"=>"2"'), {"a": "1", "b": "2"}
        )

    def test_unbalanced_quote_degrades_without_raising(self) -> None:
        # Documented limitation: an unbalanced quote inverts the in_quotes
        # state and desynchronises everything after it, so the pairs that
        # follow come back as junk keys. It must still not raise -- the layer
        # would lose the whole region, and the junk key matches no tag we ask
        # for, so it is dropped when the columns are materialized.
        parsed = parse_other_tags('"broken,"shop"=>"greengrocer"')
        self.assertIsInstance(parsed, dict)
        self.assertNotIn("shop", parsed)


class LocalExtractWhereTests(unittest.TestCase):
    def test_promoted_key_uses_an_in_test(self) -> None:
        where = local_extract_where({"leisure": ["park", "garden"]}, "multipolygons")
        self.assertEqual(where, "leisure IN ('park','garden')")

    def test_unpromoted_key_falls_back_to_other_tags(self) -> None:
        where = local_extract_where({"shop": ["supermarket"]}, "points")
        self.assertEqual(where, "other_tags LIKE '%\"shop\"=>\"supermarket\"%'")

    def test_single_quote_in_a_value_is_escaped_for_sql(self) -> None:
        self.assertIn("''", local_extract_where({"leisure": ["l'estany"]}, "multipolygons"))
        self.assertIn("''", local_extract_where({"shop": ["l'estany"]}, "points"))

    def test_key_without_values_selects_any_value(self) -> None:
        self.assertEqual(local_extract_where({"leisure": True}, "multipolygons"), "leisure IS NOT NULL")
        self.assertEqual(
            local_extract_where({"shop": True}, "points"), "other_tags LIKE '%\"shop\"=>%'"
        )

    def test_no_applicable_clause_returns_empty_so_the_layer_is_skipped(self) -> None:
        self.assertEqual(local_extract_where({}, "points"), "")

    def test_like_pattern_cannot_match_a_longer_key_or_value(self) -> None:
        # The pattern is quoted on both sides, which is what makes the LIKE
        # exact. Asserted here rather than re-filtering at runtime.
        pattern = local_extract_where({"shop": ["convenience"]}, "points")
        needle = pattern.split("LIKE '%", 1)[1].rsplit("%'", 1)[0]
        self.assertNotIn(needle, '"vending:shop"=>"convenience"')
        self.assertNotIn(needle, '"shop"=>"convenience_store"')
        self.assertIn(needle, '"name"=>"Q","shop"=>"convenience"')


class LocalExtractFetchTests(unittest.TestCase):
    """Column contract of the local-extract backend, without touching a .pbf."""

    def _extract_file(self) -> Path:
        handle = tempfile.NamedTemporaryFile(suffix=".osm.pbf", delete=False)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)

    def test_missing_extract_fails_loudly(self) -> None:
        with self.assertRaises(FileNotFoundError):
            fetch_features_from_local_extract(
                "/nonexistent/region.osm.pbf", {"leisure": ["park"]}, label="x", log=lambda _: None
            )

    def test_highway_lines_use_one_local_pbf_query_with_bbox(self) -> None:
        frame = gpd.GeoDataFrame(
            {
                "osm_id": ["11", "12"],
                "other_tags": ['"highway"=>"residential"', '"name"=>"No es calle"'],
                "geometry": [
                    LineString([(0, 0), (1, 0)]),
                    LineString([(0, 1), (1, 1)]),
                ],
            },
            crs="EPSG:4326",
        )
        captured: dict[str, object] = {}

        def fake_read_file(path, **kwargs):
            captured.update(kwargs)
            return frame

        with patch("exposome.osm_fetch.gpd.read_file", side_effect=fake_read_file):
            result = fetch_highway_lines_from_local_extract(
                self._extract_file(),
                bbox=(0, 0, 1, 1),
                label="walkability",
                log=lambda _: None,
            )

        self.assertEqual(result["id"].tolist(), ["11"])
        self.assertEqual(result["highway"].tolist(), ["residential"])
        self.assertEqual(captured["layer"], "lines")
        self.assertEqual(captured["bbox"], (0.0, 0.0, 1.0, 1.0))
        self.assertEqual(captured["where"], "other_tags LIKE '%\"highway\"=>%'")

    def test_extra_keys_materialize_a_column_even_when_no_feature_carries_it(self) -> None:
        # social_infrastructure reads `access` with .get(); a missing column
        # silently admits every venue it is supposed to exclude.
        frame = gpd.GeoDataFrame(
            {
                "osm_id": ["1"],
                "osm_way_id": [None],
                "name": ["Casa de cultura"],
                "amenity": ["community_centre"],
                "other_tags": ['"wheelchair"=>"yes"'],
                "geometry": [Point(0, 0)],
            },
            crs="EPSG:4326",
        )
        with patch("exposome.osm_fetch.gpd.read_file", return_value=frame):
            result = fetch_features_from_local_extract(
                self._extract_file(),
                {"amenity": ["community_centre"]},
                label="social",
                layers=("multipolygons",),
                extra_keys=("access",),
                log=lambda _: None,
            )
        self.assertIn("access", result.columns)
        self.assertTrue(result["access"].isna().all())

    def test_extra_key_is_read_from_other_tags_without_filtering_on_it(self) -> None:
        frame = gpd.GeoDataFrame(
            {
                "osm_id": ["7"],
                "osm_way_id": [None],
                "name": ["Club privado"],
                "amenity": ["social_centre"],
                "other_tags": ['"access"=>"private"'],
                "geometry": [Point(1, 1)],
            },
            crs="EPSG:4326",
        )
        captured: dict[str, str] = {}

        def fake_read_file(path, **kwargs):
            captured["where"] = kwargs["where"]
            return frame

        with patch("exposome.osm_fetch.gpd.read_file", side_effect=fake_read_file):
            result = fetch_features_from_local_extract(
                self._extract_file(),
                {"amenity": ["social_centre"]},
                label="social",
                layers=("multipolygons",),
                extra_keys=("access",),
                log=lambda _: None,
            )
        self.assertEqual(result["access"].tolist(), ["private"])
        self.assertNotIn("access", captured["where"])

    def test_empty_result_still_carries_the_full_column_contract(self) -> None:
        empty = gpd.GeoDataFrame(
            {"osm_id": [], "osm_way_id": [], "name": [], "other_tags": [], "geometry": []},
            crs="EPSG:4326",
        )
        with patch("exposome.osm_fetch.gpd.read_file", return_value=empty):
            result = fetch_features_from_local_extract(
                self._extract_file(),
                {"shop": ["supermarket"]},
                label="food",
                layers=("multipolygons",),
                extra_keys=("access",),
                log=lambda _: None,
            )
        self.assertEqual(len(result), 0)
        for column in ("element", "id", "name", "shop", "access", "geometry"):
            self.assertIn(column, result.columns)

    def test_ways_and_relations_keep_separate_ids(self) -> None:
        # osm_id and osm_way_id are distinct id spaces that overlap, and
        # _deduplicate_osm_features keys on (element, id).
        frame = gpd.GeoDataFrame(
            {
                "osm_id": ["10", "20"],
                "osm_way_id": ["99", None],
                "name": ["Parc", "Bosc"],
                "leisure": ["park", "park"],
                "geometry": [Point(0, 0), Point(1, 1)],
            },
            crs="EPSG:4326",
        )
        with patch("exposome.osm_fetch.gpd.read_file", return_value=frame):
            result = fetch_features_from_local_extract(
                self._extract_file(),
                {"leisure": ["park"]},
                label="green",
                layers=("multipolygons",),
                log=lambda _: None,
            )
        self.assertEqual(result["element"].tolist(), ["way", "relation"])
        self.assertEqual(result["id"].tolist(), ["99", "20"])
        self.assertNotIn("osm_way_id", result.columns)
        self.assertNotIn("osm_id", result.columns)

    def test_column_contract_matches_the_overpass_path(self) -> None:
        # Callers must not be able to tell the two backends apart.
        tags = {"amenity": ["clinic"]}
        overpass_frame = gpd.GeoDataFrame(
            {"element": ["node"], "id": ["1"], "name": ["CAP"], "amenity": ["clinic"],
             "geometry": [Point(0, 0)]},
            crs="EPSG:4326",
        )
        with patch("exposome.osm_fetch.ox.features_from_bbox", return_value=overpass_frame):
            via_overpass = fetch_features_from_bbox_tiled(
                (-1, -1, 1, 1), tags, label="healthcare", grid_size=1,
                between_tiles_s=0, attempts=1,
            )
        extract_frame = gpd.GeoDataFrame(
            {"osm_id": ["1"], "name": ["CAP"], "other_tags": ['"amenity"=>"clinic"'],
             "geometry": [Point(0, 0)]},
            crs="EPSG:4326",
        )
        with patch("exposome.osm_fetch.gpd.read_file", return_value=extract_frame):
            via_extract = fetch_features_from_local_extract(
                self._extract_file(), tags, label="healthcare",
                layers=("points",), log=lambda _: None,
            )
        for column in ("element", "id", "name", "amenity", "geometry"):
            self.assertIn(column, via_overpass.columns)
            self.assertIn(column, via_extract.columns)
        self.assertEqual(via_extract["element"].tolist(), ["node"])


if __name__ == "__main__":
    unittest.main()

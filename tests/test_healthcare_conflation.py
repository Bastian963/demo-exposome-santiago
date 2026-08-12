"""Column-contract checks for the OSM/official conflation step.

The empty-official branch used to skip the per-category sector columns that
``compute_counts`` aggregates over. The failure surfaced one function later as a
KeyError listing a dozen ``is_*_public``/``is_*_private`` labels, which reads
like a schema bug rather than "the official registry returned no rows for this
study" -- exactly what happened to pais_vasco_provincias on 2026-08-10.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.healthcare import _mark_as_osm_only, conflate_sources  # noqa: E402

CFG = {
    "crs": {"metric": "EPSG:32630", "geographic": "EPSG:4326"},
    "healthcare": {
        "categories": {
            "hospital": [],
            "clinic": [],
            "primary_care": [],
            "pharmacy": [],
            "laboratory": [],
            "dental": [],
            "mental_health": [],
            "all_health": [],
        },
        "official_source": {
            "conflation": {
                "buffer_m": 150,
                "strict_buffer_m": 50,
                "name_match_threshold": 0.5,
            }
        },
    },
}

SECTOR_COLUMNS = tuple(
    f"is_{category}_{sector}"
    for category in CFG["healthcare"]["categories"]
    for sector in ("public", "private")
)


def _osm_points() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"name": ["Hospital A", "Farmacia B"], "element": ["node", "node"], "id": [1, 2]},
        geometry=[Point(-2.9, 43.2), Point(-2.8, 43.3)],
        crs="EPSG:4326",
    )


def _empty_official() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {"name": [], "official_type": []}, geometry=[], crs="EPSG:4326"
    )


class EmptyOfficialSourceTests(unittest.TestCase):
    def test_empty_official_still_yields_the_sector_columns(self) -> None:
        result = conflate_sources(_empty_official(), _osm_points(), CFG)

        for column in SECTOR_COLUMNS:
            self.assertIn(column, result.columns, f"{column} missing -> KeyError in compute_counts")
            self.assertFalse(bool(result[column].any()), f"{column} must be all-False without DEIS")
        self.assertEqual(len(result), 2)
        self.assertTrue((result["source"] == "osm").all())

    def test_empty_official_matches_the_use_official_false_contract(self) -> None:
        """Both OSM-only paths must produce the same columns, or counts differ by route."""
        via_conflation = conflate_sources(_empty_official(), _osm_points(), CFG)
        via_flag = _mark_as_osm_only(_osm_points(), CFG)

        self.assertEqual(sorted(via_conflation.columns), sorted(via_flag.columns))

    def test_conflation_does_not_mutate_the_callers_frame(self) -> None:
        osm = _osm_points()
        before = sorted(osm.columns)

        conflate_sources(_empty_official(), osm, CFG)

        self.assertEqual(sorted(osm.columns), before)


if __name__ == "__main__":
    unittest.main()

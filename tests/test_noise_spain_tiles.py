from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import MultiPolygon, Polygon, box, mapping

from exposome.noise_spain_tiles import (
    MAXZOOM,
    _decoded_maxzoom_areas,
    _encode_tile,
    _generate_tiles,
    _max_window_bytes,
    _repair_after_reprojection,
    _resolved_bands,
    _select_simplification,
    _simplify,
)


class NoiseSpainVectorTileTests(unittest.TestCase):
    def _contours(self) -> gpd.GeoDataFrame:
        # Synthetic, disjoint categorical support near Barcelona in EPSG:3035.
        return gpd.GeoDataFrame(
            {
                "source_id": ["a", "a", "a", "a", "a"],
                "band_midpoint": [57.0, 62.0, 67.0, 72.0, 77.5],
                "lden_band": ["55-59", "60-64", "65-69", "70-74", "gt75"],
                "geometry": [
                    box(3656000 + index * 1200, 2060000, 3657000 + index * 1200, 2061000)
                    for index in range(5)
                ],
            },
            crs="EPSG:3035",
        )

    def test_priority_dissolve_and_simplification_keep_valid_categories(self) -> None:
        resolved = _resolved_bands(self._contours())
        simplified = _simplify(resolved)
        self.assertEqual(set(simplified["lden_band"]), {"55-59", "60-64", "65-69", "70-74", "gt75"})
        self.assertTrue(simplified.geometry.is_valid.all())

    def test_adaptive_simplification_chooses_a_passing_tolerance(self) -> None:
        resolved = _resolved_bands(self._contours())
        simplified, tolerance = _select_simplification(
            resolved,
            aoi=box(3655000, 2059000, 3663000, 2062000),
        )
        self.assertLessEqual(tolerance, 5.0)
        self.assertTrue(simplified.geometry.is_valid.all())

    def test_mvt_round_trip_preserves_band_area_and_all_zooms(self) -> None:
        simplified = _simplify(_resolved_bands(self._contours()))
        expected = {
            row.lden_band: float(row.geometry.area)
            for row in simplified.itertuples(index=False)
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inventory = _generate_tiles(simplified, root, resume=False)
            decoded = _decoded_maxzoom_areas(root, inventory)
        self.assertEqual({item["z"] for item in inventory}, set(range(11, MAXZOOM + 1)))
        self.assertTrue(all(item["gzip_bytes"] <= 500_000 for item in inventory))
        self.assertLessEqual(_max_window_bytes(inventory, columns=4, rows=4), 2_000_000)
        for band, area in expected.items():
            self.assertLessEqual(abs(decoded[band] / area - 1.0), 0.005)

    def test_subpixel_fragment_collapsing_during_quantization_is_dropped(self) -> None:
        payload = _encode_tile(
            [
                {
                    "id": 1,
                    "geometry": mapping(box(1, 1, 1.01, 1.01)),
                    "properties": {"lden_band": "55-59"},
                }
            ],
            (0, 0, 4096, 4096),
        )
        self.assertGreater(len(payload), 0)

    def test_multipolygon_parts_are_encodable_when_one_part_is_subpixel(self) -> None:
        payload = _encode_tile(
            [
                {
                    "id": 1,
                    "geometry": mapping(
                        MultiPolygon([box(100, 100, 200, 200), box(1, 1, 1.01, 1.01)])
                    ),
                    "properties": {"lden_band": "55-59"},
                }
            ],
            (0, 0, 4096, 4096),
        )
        self.assertGreater(len(payload), 0)


class ReprojectionSeamTests(unittest.TestCase):
    """Validity does not survive a CRS change, and the tile pipeline crosses twice.

    `_simplify` asserts validity in EPSG:3035 and that gate held, but
    `_generate_tiles` converts to EPSG:3857 and `_decoded_maxzoom_areas` converts
    back, and neither crossing re-checked. Measured on 2026-08-11 for
    pais_vasco_provincias: 13 of 9052 parts valid in 3035 came back invalid in
    3857, and both crossings then died inside GEOS with `TopologyException: side
    location conflict at <x> <y>` -- a message naming a coordinate but neither
    the band, the agglomeration nor the CRS.
    """

    def _bowtie(self) -> gpd.GeoDataFrame:
        """A self-intersecting ring: the shape reprojection produces by accident."""
        return gpd.GeoDataFrame(
            {
                "band_midpoint": [57.0],
                "lden_band": ["55-59"],
                "geometry": [Polygon([(0, 0), (10, 10), (10, 0), (0, 10), (0, 0)])],
            },
            crs="EPSG:3857",
        )

    def test_invalid_geometry_is_repaired_rather_than_raising(self) -> None:
        frame = self._bowtie()
        self.assertFalse(frame.geometry.is_valid.all())

        repaired = _repair_after_reprojection(frame, "EPSG:3857, prueba")

        self.assertTrue(repaired.geometry.is_valid.all())
        self.assertFalse(repaired.empty)
        # A repaired bowtie must still intersect without GEOS raising, which is
        # the operation that actually crashed in _tile_features.
        repaired.geometry.intersection(box(-1, -1, 11, 11))

    def test_valid_geometry_is_returned_untouched(self) -> None:
        frame = gpd.GeoDataFrame(
            {"band_midpoint": [57.0], "geometry": [box(0, 0, 10, 10)]},
            crs="EPSG:3857",
        )

        repaired = _repair_after_reprojection(frame, "EPSG:3857, prueba")

        self.assertIs(repaired, frame)  # no copy when there is nothing to fix

    def test_repair_preserves_area_within_the_published_gate(self) -> None:
        """The build's own area gate is what bounds this repair; keep it honest."""
        frame = self._bowtie()

        repaired = _repair_after_reprojection(frame, "EPSG:3857, prueba")

        # make_valid on a bowtie yields the two triangles: half the naive bbox,
        # which is the correct reading of a self-intersecting ring.
        self.assertAlmostEqual(repaired.geometry.area.sum(), 50.0, places=6)


if __name__ == "__main__":
    unittest.main()

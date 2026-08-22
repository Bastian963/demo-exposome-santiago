"""Tests for the greenspace_multisource layer.

Pure-logic tests mock `ee` (no GEE calls). The output-contract test reads the
real processed CSV if it has been generated and is skipped otherwise, so CI
stays offline-safe.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

PROCESSED = REPO_ROOT / "data" / "processed"
# Canonical study-scoped output (not the flat legacy `santiago_greenspace_multisource.csv`,
# which predates the spatial_id/spatial_name fix and is not what master.py resolves).
MULTISOURCE_CSV = (
    PROCESSED / "cl" / "santiago" / "santiago_communes" / "greenspace_multisource"
    / "santiago_communes_greenspace_multisource.csv"
)
OSM_CSV = PROCESSED / "santiago_greenspace_access.csv"

PCT_COLS = ["green_total_pct", "tree_pct", "grass_pct", "canopy_cover_pct"]
ALL_COLS = ["spatial_id", "spatial_name", "name", "area_km2", *PCT_COLS, "canopy_mean_height_m"]


def _load_module(test: unittest.TestCase):
    """Import greenspace_multisource with a mocked `ee` and deps.

    Restores the pre-mock sys.modules entries via addCleanup so this doesn't
    leak a MagicMock `exposome.config`/`exposome.boundaries`/`exposome.gee`
    into later tests in the same process (silent test-order-dependent
    corruption — MagicMock's `__float__`/`__getitem__` fabricate plausible
    values instead of failing loudly).
    """
    deps = ["ee", "exposome.boundaries", "exposome.config", "exposome.gee"]
    saved = {dep: sys.modules.get(dep) for dep in deps}

    def _restore() -> None:
        for dep, original in saved.items():
            if original is None:
                sys.modules.pop(dep, None)
            else:
                sys.modules[dep] = original

    test.addCleanup(_restore)

    sys.modules["ee"] = MagicMock()
    for dep in ["exposome.boundaries", "exposome.config", "exposome.gee"]:
        sys.modules[dep] = MagicMock()
    sys.modules.pop("exposome.greenspace_multisource", None)
    import exposome.greenspace_multisource as mod

    return mod


class TestDynamicWorldClasses(unittest.TestCase):
    def test_band_order_matches_dynamic_world(self) -> None:
        mod = _load_module(self)
        # Official Dynamic World V1 band order — the class index is load-bearing
        # for the argmax masks.
        self.assertEqual(mod.DW_CLASSES[0], "water")
        self.assertEqual(mod.DW_CLASSES[1], "trees")
        self.assertEqual(mod.DW_CLASSES[2], "grass")
        self.assertEqual(mod.DW_CLASSES[5], "shrub_and_scrub")
        self.assertEqual(mod.DW_CLASSES[6], "built")
        self.assertEqual(len(mod.DW_CLASSES), 9)
        self.assertEqual(mod._DW_INDEX["trees"], 1)


class TestSeasonFilter(unittest.TestCase):
    def test_wraparound_season_uses_or(self) -> None:
        mod = _load_module(self)
        import ee  # the mock

        ee.Filter.reset_mock()
        mod._season_filter([10, 11, 12, 1, 2, 3])
        # Oct-Mar wraps the year, so it must be expressed as an OR of ranges,
        # never a single calendarRange(1, 12) (which would select all months).
        self.assertTrue(ee.Filter.Or.called)
        called_ranges = [c.args for c in ee.Filter.calendarRange.call_args_list]
        self.assertIn((10, 12, "month"), called_ranges)
        self.assertIn((1, 3, "month"), called_ranges)

    def test_full_year_is_all_months(self) -> None:
        mod = _load_module(self)
        import ee

        ee.Filter.reset_mock()
        mod._season_filter(list(range(1, 13)))
        ee.Filter.calendarRange.assert_called_once_with(1, 12, "month")
        self.assertFalse(ee.Filter.Or.called)


class TestCanopyProjection(unittest.TestCase):
    def test_canopy_mosaic_inherits_a_source_tile_projection(self) -> None:
        """A tiled mosaic must be projected before native reduction uses it."""
        mod = _load_module(self)
        import ee

        roi = MagicMock(name="roi")
        collection = ee.ImageCollection.return_value.filterBounds.return_value.select.return_value
        source_image = MagicMock(name="source_image")
        source_band = MagicMock(name="source_band")
        source_projection = MagicMock(name="source_projection")
        ee.Image.return_value = source_image
        collection.first.return_value = MagicMock(name="first_tile")
        source_image.select.return_value = source_band
        source_band.projection.return_value = source_projection

        mosaic = MagicMock(name="mosaic")
        projected_mosaic = MagicMock(name="projected_mosaic")
        canopy = MagicMock(name="canopy")
        collection.mosaic.return_value = mosaic
        mosaic.setDefaultProjection.return_value = projected_mosaic
        projected_mosaic.select.return_value = canopy

        result = mod.build_canopy_image(
            roi,
            collection_id="meta/canopy",
            band="cover_code",
            min_height_m=3,
        )

        ee.ImageCollection.assert_called_once_with("meta/canopy")
        ee.ImageCollection.return_value.filterBounds.assert_called_once_with(roi)
        mosaic.setDefaultProjection.assert_called_once_with(source_projection)
        self.assertIsNotNone(result)


class TestAdaptiveZoneScale(unittest.TestCase):
    def test_small_zone_keeps_configured_scale(self) -> None:
        mod = _load_module(self)
        self.assertEqual(mod._adaptive_zone_scale(30, 10), 30)

    def test_large_zone_uses_deterministic_coarser_scale(self) -> None:
        mod = _load_module(self)
        # 20,000 km² would contain ~22.2M 30-m pixels. The bounded request
        # samples at 100 m, limiting the reduction to 2M pixels.
        self.assertEqual(mod._adaptive_zone_scale(30, 20_000), 100)

    def test_negative_area_is_rejected(self) -> None:
        mod = _load_module(self)
        with self.assertRaises(ValueError):
            mod._adaptive_zone_scale(30, -1)


@unittest.skipUnless(MULTISOURCE_CSV.exists(), "run scripts/run_greenspace_multisource.py first")
class TestOutputContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import pandas as pd

        cls.df = pd.read_csv(MULTISOURCE_CSV)

    def test_row_count_and_columns(self) -> None:
        self.assertEqual(len(self.df), 52)
        for col in ALL_COLS:
            self.assertIn(col, self.df.columns)

    def test_no_missing_values(self) -> None:
        self.assertFalse(self.df[[c for c in ALL_COLS if c != "name"]].isna().any().any())

    def test_percent_columns_in_range(self) -> None:
        for col in PCT_COLS:
            self.assertTrue(self.df[col].between(0, 100).all(), f"{col} out of [0,100]")

    def test_canopy_height_non_negative(self) -> None:
        self.assertTrue((self.df["canopy_mean_height_m"] >= 0).all())

    def test_canopy_exceeds_dw_green_in_dense_urban(self) -> None:
        # Non-tautological complement signal: in the dense urban core Dynamic
        # World's 10 m argmax reads ~0 green (built dominates every 10 m pixel),
        # yet the 1 m canopy still detects street trees. So among communes with
        # near-zero DW green, canopy cover should be materially higher — this is
        # the "green OSM and the 10 m argmax both miss" story, and it is an
        # empirical property of the two products (canopy could have been ~0 too).
        dense = self.df[self.df["green_total_pct"] < 2.0]
        self.assertGreaterEqual(len(dense), 3)
        gap = dense["canopy_cover_pct"] - dense["green_total_pct"]
        self.assertTrue((gap > 0).all(), "canopy does not exceed DW green in dense-urban communes")
        self.assertGreater(gap.mean(), 2.0, "dense-urban canopy complement is not material")


if __name__ == "__main__":
    unittest.main()

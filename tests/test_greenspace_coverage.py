"""Tests for greenspace_satellite layer logic.

All tests run offline — no GEE calls. The EVI sanitisation and column assembly
are the main things under test.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
import numpy as np
from shapely.geometry import Point

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


class TestEviSanitation(unittest.TestCase):
    """Verify that the EVI mask logic is applied correctly.

    We mock the `ee` module so no GEE init is needed, then reload the module
    under test so we can inspect that _add_indices calls updateMask on EVI.
    """

    def _load_module(self) -> object:
        """Import greenspace_satellite with a mocked `ee`.

        Restores the pre-mock sys.modules entries via addCleanup so this
        doesn't leak a MagicMock `exposome.config`/`exposome.boundaries`/
        `exposome.gee` into later tests in the same process (silent
        test-order-dependent corruption — MagicMock's `__float__`/
        `__getitem__` fabricate plausible values instead of failing loudly).
        """
        deps = ["ee", "exposome.boundaries", "exposome.config", "exposome.gee"]
        saved = {dep: sys.modules.get(dep) for dep in deps}

        def _restore() -> None:
            for dep, original in saved.items():
                if original is None:
                    sys.modules.pop(dep, None)
                else:
                    sys.modules[dep] = original

        self.addCleanup(_restore)

        ee_mock = MagicMock()
        sys.modules["ee"] = ee_mock
        # Also need to mock dependencies pulled in at import time
        for dep in ["exposome.boundaries", "exposome.config", "exposome.gee"]:
            sys.modules[dep] = MagicMock()
        if "exposome.greenspace_satellite" in sys.modules:
            del sys.modules["exposome.greenspace_satellite"]
        import exposome.greenspace_satellite as mod
        return mod, ee_mock

    def test_evi_updateMask_is_called(self) -> None:
        """_add_indices must call updateMask after building EVI."""
        mod, ee_mock = self._load_module()

        image = MagicMock()
        ndvi_mock = MagicMock()
        evi_mock = MagicMock()
        evi_masked = MagicMock()
        green_ndvi_mock = MagicMock()
        green_evi_mock = MagicMock()

        image.normalizedDifference.return_value.rename.return_value = ndvi_mock
        image.expression.return_value.rename.return_value = evi_mock
        evi_mock.gte.return_value.And.return_value = MagicMock()
        evi_mock.updateMask.return_value = evi_masked
        ndvi_mock.gte.return_value.rename.return_value = green_ndvi_mock
        evi_masked.gte.return_value.rename.return_value = green_evi_mock
        image.addBands.return_value = MagicMock()

        mod._add_indices(image, ndvi_threshold=0.20, evi_threshold=0.15)

        # updateMask must have been called on the original EVI image
        evi_mock.updateMask.assert_called_once()

    def test_green_evi_uses_masked_evi(self) -> None:
        """green_evi must be derived from the masked EVI, not the raw EVI."""
        mod, ee_mock = self._load_module()

        image = MagicMock()
        ndvi_mock = MagicMock()
        evi_mock = MagicMock()
        evi_masked = MagicMock()

        image.normalizedDifference.return_value.rename.return_value = ndvi_mock
        image.expression.return_value.rename.return_value = evi_mock
        evi_mock.gte.return_value.And.return_value = MagicMock()
        evi_mock.updateMask.return_value = evi_masked
        evi_masked.gte.return_value.rename.return_value = MagicMock()
        ndvi_mock.gte.return_value.rename.return_value = MagicMock()
        image.addBands.return_value = MagicMock()

        mod._add_indices(image, ndvi_threshold=0.20, evi_threshold=0.15)

        # evi_masked.gte must have been called (not evi_mock.gte for threshold)
        evi_masked.gte.assert_called_once_with(0.15)


class TestEviRangeNumpyAnalog(unittest.TestCase):
    """Numpy-level check: values outside [-1, 1] should be masked (NaN)."""

    def test_evi_values_clipped_to_valid_range(self) -> None:
        # Simulate raw EVI values including anomalous spikes
        raw_evi = np.array([0.5, -0.2, 2872.5, -5.0, 0.3, 1.1])
        masked = np.where((raw_evi >= -1) & (raw_evi <= 1), raw_evi, np.nan)
        valid = masked[~np.isnan(masked)]
        self.assertTrue(np.all(valid >= -1))
        self.assertTrue(np.all(valid <= 1))
        self.assertTrue(np.isnan(masked[2]))  # 2872.5 → NaN
        self.assertTrue(np.isnan(masked[3]))  # -5.0 → NaN
        self.assertAlmostEqual(valid.max(), 0.5)


class TestSeasonFilter(unittest.TestCase):
    def test_october_to_march_does_not_expand_to_full_year(self) -> None:
        helper = TestEviSanitation()
        helper.addCleanup = self.addCleanup
        mod, ee_mock = helper._load_module()
        ee_mock.Filter.reset_mock()

        mod._season_filter([10, 11, 12, 1, 2, 3])

        ranges = [call.args for call in ee_mock.Filter.calendarRange.call_args_list]
        self.assertIn((1, 3, "month"), ranges)
        self.assertIn((10, 12, "month"), ranges)
        self.assertTrue(ee_mock.Filter.Or.called)
        self.assertNotIn((1, 12, "month"), ranges)


class TestZonalStatsCaching(unittest.TestCase):
    """build_greenspace_coverage_layer must cache the single zonal
    reduceRegions call to cache/ and skip GEE entirely on a cached re-run
    (crash-safety / resume contract, same idea as pm25's per-step cache)."""

    def _load_module(self) -> object:
        deps = ["ee", "exposome.boundaries", "exposome.config", "exposome.gee"]
        saved = {dep: sys.modules.get(dep) for dep in deps}

        def _restore() -> None:
            for dep, original in saved.items():
                if original is None:
                    sys.modules.pop(dep, None)
                else:
                    sys.modules[dep] = original

        self.addCleanup(_restore)

        ee_mock = MagicMock()
        sys.modules["ee"] = ee_mock
        for dep in ["exposome.boundaries", "exposome.config", "exposome.gee"]:
            sys.modules[dep] = MagicMock()
        if "exposome.greenspace_satellite" in sys.modules:
            del sys.modules["exposome.greenspace_satellite"]
        import exposome.greenspace_satellite as mod
        return mod

    def _fixture_cfg_and_communes(self) -> tuple[dict, "gpd.GeoDataFrame"]:
        communes = gpd.GeoDataFrame(
            {"name": ["A"], "area_km2": [10.0]},
            geometry=[Point(-70.6, -33.5).buffer(0.05)],
            crs="EPSG:4326",
        )
        cfg = {
            "greenspace": {
                "satellite": {
                    "years": [2024],
                    "season_months": [12, 1, 2],
                    "ndvi_threshold": 0.2,
                    "evi_threshold": 0.15,
                }
            },
            "expected_communes": 1,
            "crs": {"geographic": "EPSG:4326"},
        }
        return cfg, communes

    def test_cached_zonal_stats_skip_gee_call_on_rerun(self) -> None:
        mod = self._load_module()
        cfg, communes = self._fixture_cfg_and_communes()
        stats = {
            "A": {
                "name": "A",
                "NDVI_mean": 0.3,
                "NDVI_max": 0.5,
                "EVI_mean": 0.25,
                "EVI_max": 0.4,
                "green_ndvi_mean": 0.6,
                "green_evi_mean": 0.5,
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "cache"
            out_dir = Path(tmp) / "out"
            figures_dir = Path(tmp) / "figures"

            with (
                patch.object(mod.config, "load_config", return_value=cfg),
                patch.object(mod.boundaries, "get_communes", return_value=communes),
                patch.object(mod, "build_landsat_composite", return_value=MagicMock()),
                patch.object(mod, "_write_coverage_figure"),
            ):
                with patch.object(
                    mod, "_zonal_stats_combined", return_value=stats
                ) as fetch_mock:
                    mod.build_greenspace_coverage_layer(
                        city="testcity",
                        cache_dir=cache_dir,
                        out_dir=out_dir,
                        figures_dir=figures_dir,
                    )
                    fetch_mock.assert_called_once()

                cache_files = list(cache_dir.rglob("zonal.*.csv"))
                self.assertEqual(len(cache_files), 1)
                self.assertEqual(len(list(cache_dir.rglob("zonal.cache.json"))), 1)

                # Re-run with the same cache_dir: the GEE zonal call must not
                # happen again — this is the crash-safety guarantee.
                with patch.object(
                    mod,
                    "_zonal_stats_combined",
                    side_effect=AssertionError("GEE zonal call should have been cached"),
                ):
                    mod.build_greenspace_coverage_layer(
                        city="testcity",
                        cache_dir=cache_dir,
                        out_dir=out_dir,
                        figures_dir=figures_dir,
                    )


if __name__ == "__main__":
    unittest.main()

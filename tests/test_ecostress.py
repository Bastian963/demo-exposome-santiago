from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.climate import fetch_ecostress as fe  # noqa: E402
from exposome.layers import load_layer_catalog  # noqa: E402
from exposome.native import NATIVE_LAYER_SPECS, RASTER_KINDS  # noqa: E402

SANTIAGO_LON = -70.65


class SolarHourTests(unittest.TestCase):
    def test_longitude_offset_not_civil_timezone(self):
        # 18:00 UTC at lon -70.65 is 18 - 4.71 = 13.29 local solar.
        hour = fe.local_solar_hour(
            datetime(2023, 1, 15, 18, 0, tzinfo=timezone.utc), SANTIAGO_LON
        )
        self.assertAlmostEqual(hour, 13.29, places=2)

    def test_wraps_past_midnight(self):
        hour = fe.local_solar_hour(
            datetime(2023, 1, 15, 4, 0, tzinfo=timezone.utc), SANTIAGO_LON
        )
        self.assertAlmostEqual(hour, 23.29, places=2)
        self.assertTrue(0 <= hour < 24)

    def test_naive_datetime_treated_as_utc(self):
        naive = fe.local_solar_hour(datetime(2023, 1, 15, 18, 0), SANTIAGO_LON)
        aware = fe.local_solar_hour(
            datetime(2023, 1, 15, 18, 0, tzinfo=timezone.utc), SANTIAGO_LON
        )
        self.assertAlmostEqual(naive, aware, places=9)

    def test_day_window(self):
        self.assertEqual(fe.window_for_hour(13.3), "day")

    def test_night_window_wraps(self):
        self.assertEqual(fe.window_for_hour(23.3), "night")
        self.assertEqual(fe.window_for_hour(2.0), "night")

    def test_transition_hours_are_dropped(self):
        # A transition-hour mean would mix heating and cooling regimes, so
        # these acquisitions must fall in no window at all.
        for hour in (9.9, 16.0, 21.9, 5.0):
            self.assertIsNone(fe.window_for_hour(hour), hour)


class GranuleIdTests(unittest.TestCase):
    granule = "ECOv002_L2T_LSTE_26543_007_19HCC_20230115T143052_0712_01"

    def test_parses_tile_and_time(self):
        info = fe.parse_granule_id(self.granule)
        self.assertEqual(info["tile"], "19HCC")
        self.assertEqual(info["orbit"], "26543")
        self.assertEqual(
            info["acquired_utc"],
            datetime(2023, 1, 15, 14, 30, 52, tzinfo=timezone.utc),
        )

    def test_rejects_unrecognised_id(self):
        with self.assertRaises(ValueError):
            fe.parse_granule_id("MOD11A1.A2023015.h12v12.061")

    def test_accepts_collection_3_prefix(self):
        info = fe.parse_granule_id(
            "ECOv003_L2T_LSTE_26543_007_18HYG_20230115T143052_0712_01"
        )
        self.assertEqual(info["tile"], "18HYG")


class DecodeAndMaskTests(unittest.TestCase):
    def test_fill_becomes_nan_and_scaling_applied(self):
        raw = np.array([[fe.LST_FILL, 14000]], dtype="uint16")
        out = fe.decode_lst(raw)
        self.assertTrue(np.isnan(out[0, 0]))
        # 14000 * 0.02 = 280 K -> 6.85 degC
        self.assertAlmostEqual(float(out[0, 1]), 6.85, places=2)

    def test_integer_storage_gets_packed_scale(self):
        # rasterio reports scales == (1.0,) both for genuinely unscaled data
        # and for a missing tag, so dtype is the discriminator.  Getting this
        # wrong yields a plausible-looking but 50x-wrong temperature field.
        self.assertEqual(fe.resolve_lst_scaling(np.dtype("uint16"), (1.0,)), (0.02, 0.0))
        self.assertEqual(fe.resolve_lst_scaling(np.dtype("uint16"), None), (0.02, 0.0))

    def test_declared_scale_wins_for_integers(self):
        self.assertEqual(fe.resolve_lst_scaling(np.dtype("uint16"), (0.01,)), (0.01, 0.0))

    def test_float_storage_is_already_kelvin(self):
        self.assertEqual(fe.resolve_lst_scaling(np.dtype("float32"), (1.0,)), (1.0, 0.0))

    def test_mask_drops_cloud_water_and_bad_qc(self):
        lst = np.array([[20.0, 21.0, 22.0, 23.0]], dtype="float32")
        cloud = np.array([[0, 1, 0, 0]], dtype="uint8")
        water = np.array([[0, 0, 1, 0]], dtype="uint8")
        qc = np.array([[0, 0, 0, 0b11]], dtype="uint16")
        keep = fe.quality_mask(lst_c=lst, cloud=cloud, water=water, qc=qc)
        self.assertEqual(keep.tolist(), [[True, False, False, False]])

    def test_mask_drops_implausible_temperatures(self):
        lst = np.array([[-99.0, 20.0, 200.0]], dtype="float32")
        keep = fe.quality_mask(lst_c=lst)
        self.assertEqual(keep.tolist(), [[False, True, False]])

    def test_mask_survives_missing_ancillary_bands(self):
        lst = np.array([[20.0, np.nan]], dtype="float32")
        keep = fe.quality_mask(lst_c=lst)
        self.assertEqual(keep.tolist(), [[True, False]])


class AccumulatorTests(unittest.TestCase):
    def test_mean_ignores_masked_pixels(self):
        acc = fe.WindowAccumulator(shape=(1, 2))
        acc.update(np.array([[10.0, 30.0]]), np.array([[True, False]]))
        acc.update(np.array([[20.0, 40.0]]), np.array([[True, True]]))
        self.assertEqual(acc.count.tolist(), [[2, 1]])
        np.testing.assert_allclose(acc.mean(), [[15.0, 40.0]])
        np.testing.assert_allclose(acc.peak(), [[20.0, 40.0]])

    def test_never_observed_pixel_is_nan_not_zero(self):
        acc = fe.WindowAccumulator(shape=(1, 1))
        acc.update(np.array([[10.0]]), np.array([[False]]))
        self.assertTrue(np.isnan(acc.mean()[0, 0]))
        self.assertTrue(np.isnan(acc.peak()[0, 0]))

    def test_shape_mismatch_is_rejected(self):
        acc = fe.WindowAccumulator(shape=(2, 2))
        with self.assertRaises(ValueError):
            acc.update(np.zeros((1, 2)), np.ones((1, 2), dtype=bool))

    def test_checkpoint_roundtrip_preserves_resume_state(self):
        acc = fe.AccumulatorSet(shape=(2, 2))
        acc.update("day", np.full((2, 2), 25.0), np.ones((2, 2), dtype=bool))
        acc.update("night", np.full((2, 2), 12.0), np.ones((2, 2), dtype=bool))
        acc.mark_processed("granule-a")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ckpt.npz"
            acc.save(path)
            restored = fe.AccumulatorSet.load(path)
        self.assertEqual(restored.processed, {"granule-a"})
        self.assertEqual([w.name for w in restored.windows], ["day", "night"])
        np.testing.assert_allclose(restored.accumulators["day"].mean(), np.full((2, 2), 25.0))
        np.testing.assert_allclose(restored.accumulators["night"].mean(), np.full((2, 2), 12.0))

    def test_resumed_accumulator_keeps_accumulating(self):
        acc = fe.AccumulatorSet(shape=(1, 1))
        acc.update("day", np.array([[10.0]]), np.array([[True]]))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ckpt.npz"
            acc.save(path)
            restored = fe.AccumulatorSet.load(path)
        restored.update("day", np.array([[20.0]]), np.array([[True]]))
        np.testing.assert_allclose(restored.accumulators["day"].mean(), [[15.0]])


class GranuleSelectionTests(unittest.TestCase):
    @staticmethod
    def _granule(native_id: str):
        return {"meta": {"native-id": native_id}}

    def test_skips_already_processed_and_out_of_window(self):
        granules = [
            # 18:00Z -> 13.29 local solar -> day
            self._granule("ECOv003_L2T_LSTE_1_001_19HCC_20230115T180000_0712_01"),
            # 04:00Z -> 23.29 local solar -> night
            self._granule("ECOv003_L2T_LSTE_2_001_19HCC_20230115T040000_0712_01"),
            # 14:30Z -> 9.79 local solar -> transition, dropped
            self._granule("ECOv003_L2T_LSTE_3_001_19HCC_20230115T143000_0712_01"),
            self._granule("already-done"),
        ]
        selected = list(
            fe.iter_granule_windows(
                granules, SANTIAGO_LON, skip={"already-done"}
            )
        )
        self.assertEqual([info["window"] for _, info in selected], ["day", "night"])

    def test_all_tiles_of_one_overpass_share_a_window(self):
        # Santiago spans UTM zones 18 and 19; binning per-tile centroid could
        # split one overpass across windows and stitch the mosaic from
        # different diurnal regimes.
        granules = [
            self._granule("ECOv003_L2T_LSTE_9_001_18HYG_20230115T180000_0712_01"),
            self._granule("ECOv003_L2T_LSTE_9_001_19HDD_20230115T180000_0712_01"),
        ]
        selected = list(fe.iter_granule_windows(granules, SANTIAGO_LON))
        self.assertEqual({info["window"] for _, info in selected}, {"day"})

    def test_unparseable_granules_are_skipped_not_fatal(self):
        granules = [self._granule("garbage"), self._granule(
            "ECOv003_L2T_LSTE_1_001_19HCC_20230115T180000_0712_01"
        )]
        selected = list(fe.iter_granule_windows(granules, SANTIAGO_LON))
        self.assertEqual(len(selected), 1)


class GridTests(unittest.TestCase):
    def test_grid_snaps_outward_to_resolution(self):
        grid = fe.build_study_grid((100.0, 200.0, 240.0, 300.0), "EPSG:32719", 70.0)
        self.assertEqual(grid.shape, (grid.height, grid.width))
        # Bounds are snapped out, so the grid always covers the request.
        west, north = grid.transform.c, grid.transform.f
        self.assertLessEqual(west, 100.0)
        self.assertGreaterEqual(north, 300.0)

    def test_reproject_same_crs_is_identity_on_aligned_grid(self):
        grid = fe.build_study_grid((0.0, 0.0, 210.0, 140.0), "EPSG:32719", 70.0)
        source = np.arange(grid.height * grid.width, dtype="float32").reshape(grid.shape)
        out = fe.reproject_to_grid(source, grid.transform, "EPSG:32719", grid)
        np.testing.assert_allclose(out, source)

    def test_reproject_marks_uncovered_area_as_nan(self):
        from rasterio.transform import from_origin

        grid = fe.build_study_grid((0.0, 0.0, 700.0, 700.0), "EPSG:32719", 70.0)
        # A small source tile in one corner leaves most of the grid unobserved.
        source = np.ones((2, 2), dtype="float32")
        out = fe.reproject_to_grid(
            source, from_origin(0.0, 700.0, 70.0, 70.0), "EPSG:32719", grid
        )
        self.assertTrue(np.isnan(out).any())
        self.assertEqual(int(np.nansum(out)), 4)


class AssetUrlTests(unittest.TestCase):
    class _Granule:
        def data_links(self):
            return [
                "https://x/ECOv003_L2T_LSTE_1_001_19HCC_20230115T180000_0712_01_LST.tif",
                "https://x/ECOv003_L2T_LSTE_1_001_19HCC_20230115T180000_0712_01_cloud.tif",
                "https://x/ECOv003_L2T_LSTE_1_001_19HCC_20230115T180000_0712_01_QC.tif",
                "https://x/ECOv003_L2T_LSTE_1_001_19HCC_20230115T180000_0712_01.h5",
            ]

    def test_maps_bands_and_ignores_non_tif(self):
        urls = fe.granule_asset_urls(self._Granule())
        self.assertEqual(sorted(urls), ["LST", "QC", "cloud"])
        self.assertTrue(urls["LST"].endswith("_LST.tif"))


class ReadGranuleTests(unittest.TestCase):
    """read_granule_to_grid with a stub opener -- no network, no credentials."""

    class _Dataset:
        def __init__(self, array, transform, scales=(1.0,)):
            self._array = array
            self.transform = transform
            self.crs = "EPSG:32719"
            self.scales = scales

        def read(self, _index):
            return self._array

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def test_masks_then_reprojects(self):
        from rasterio.transform import from_origin

        grid = fe.build_study_grid((0.0, 0.0, 140.0, 140.0), "EPSG:32719", 70.0)
        transform = from_origin(0.0, 140.0, 70.0, 70.0)
        # 15000 DN -> 26.85 degC; one pixel is fill, one is clouded.
        lst = np.array([[15000, 15000], [fe.LST_FILL, 15000]], dtype="uint16")
        cloud = np.array([[0, 1], [0, 0]], dtype="uint8")

        datasets = {
            "LST": self._Dataset(lst, transform),
            "cloud": self._Dataset(cloud, transform),
        }

        def opener(url):
            return datasets[url]

        values, mask = fe.read_granule_to_grid(
            {"LST": "LST", "cloud": "cloud"}, grid, opener=opener
        )
        self.assertEqual(mask.sum(), 2)
        np.testing.assert_allclose(values[mask], [26.85, 26.85], atol=1e-2)

    def test_missing_lst_band_is_an_error(self):
        grid = fe.build_study_grid((0.0, 0.0, 70.0, 70.0), "EPSG:32719", 70.0)
        with self.assertRaises(KeyError):
            fe.read_granule_to_grid({"cloud": "c"}, grid, opener=lambda url: None)


class UnitSummaryTests(unittest.TestCase):
    """Label-grid aggregation in the layer builder."""

    @staticmethod
    def _runner():
        from exposome.climate import ecostress_layer

        return ecostress_layer

    labels = np.array([[1, 1, 1], [0, 0, 0], [2, 2, 2]], dtype="int32")
    values = np.array(
        [[10.0, 20.0, 30.0], [99.0, 99.0, 99.0], [5.0, 7.0, 9.0]], dtype="float32"
    )

    def test_background_excluded_and_mask_respected(self):
        mask = np.array([[1, 1, 0], [1, 1, 1], [1, 1, 1]], dtype=bool)
        rows = self._runner().unit_summaries(
            self.values, mask, self.labels, ["A", "B"], "spatial_id"
        )
        # Unit A keeps 10 and 20 (30 is masked); the background 99s must never
        # leak into any unit.
        self.assertEqual(rows[0]["n_pixels"], 2)
        self.assertAlmostEqual(rows[0]["lst_mean_c"], 15.0)
        self.assertAlmostEqual(rows[0]["lst_max_c"], 20.0)
        self.assertEqual(rows[1]["n_pixels"], 3)
        self.assertAlmostEqual(rows[1]["lst_mean_c"], 7.0)

    def test_fully_masked_granule_reports_none_not_zero(self):
        rows = self._runner().unit_summaries(
            self.values,
            np.zeros(self.labels.shape, dtype=bool),
            self.labels,
            ["A", "B"],
            "spatial_id",
        )
        for row in rows:
            self.assertEqual(row["n_pixels"], 0)
            self.assertIsNone(row["lst_mean_c"])
            self.assertIsNone(row["lst_max_c"])


class CollectionVersionTests(unittest.TestCase):
    def test_default_collection_is_v002_not_v003(self):
        # The NASA catalog advertises v003 as covering 2018-07-09 to present,
        # but that is the intended extent: reprocessing is still rolling
        # forward.  Measured CMR counts over Santiago (2026-08-02) were
        # v003 = 0 granules for 2021/2023/2024 against v002 = 1826/2825/1198.
        # Defaulting to v003 would silently produce a near-empty composite for
        # the whole historical period.
        self.assertEqual(fe.DEFAULT_VERSION, "002")

    def test_config_and_code_agree_on_the_collection_version(self):
        import yaml

        settings = yaml.safe_load(
            (ROOT / "config" / "layers" / "climate_lst_ecostress.yaml").read_text(
                encoding="utf-8"
            )
        )["settings"]["collection"]
        self.assertEqual(str(settings["version"]), fe.DEFAULT_VERSION)
        self.assertEqual(settings["short_name"], fe.SHORT_NAME)

    def test_lst_error_band_does_not_shadow_the_lst_band(self):
        # Real granules ship both `..._LST.tif` and `..._LST_err.tif`; the
        # suffix parser must keep them distinct or the error band would
        # overwrite the measurement.
        class _G:
            def data_links(self):
                base = "https://x/ECOv002_L2T_LSTE_1_001_19HCC_20230115T180000_0712_01"
                return [f"{base}_LST.tif", f"{base}_LST_err.tif"]

        urls = fe.granule_asset_urls(_G())
        self.assertTrue(urls["LST"].endswith("_LST.tif"))
        self.assertEqual(urls["err"], urls["err"])
        self.assertNotEqual(urls["LST"], urls.get("err"))


class RegistrationTests(unittest.TestCase):
    def test_native_spec_uses_the_provider_neutral_raster_kind(self):
        spec = NATIVE_LAYER_SPECS["climate_lst_ecostress"]
        self.assertEqual(spec.kind, "raster")
        self.assertEqual(spec.native_resolution_m, 70)
        self.assertIn(spec.kind, RASTER_KINDS)
        # Consumers must treat it exactly like a GEE raster on disk.
        self.assertIn("gee_raster", RASTER_KINDS)

    def test_catalog_entry_matches_the_native_spec(self):
        spec = load_layer_catalog().layers["climate_lst_ecostress"]
        self.assertEqual(spec.native_resolution_m, 70)
        self.assertIn("earthdata", spec.requirements["capabilities"])

    def test_layer_is_not_advertised_as_a_pilot_layer(self):
        # Portability is unproven where cloud cover is persistent.
        catalog = load_layer_catalog()
        self.assertNotIn("climate_lst_ecostress", catalog.pilot_layers)


if __name__ == "__main__":
    unittest.main()

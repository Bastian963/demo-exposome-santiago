from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import Point
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[1]


class NativeStudyTests(unittest.TestCase):
    def test_heat_native_temporal_support_uses_reference_year(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.native import native_temporal_support

        self.assertEqual(
            native_temporal_support(
                {"study_period": {"reference_year": 2022}},
                "climate_heat",
            ),
            {
                "kind": "year",
                "year": "2022",
                "source_label": "ERA5-Land",
            },
        )
        self.assertEqual(
            native_temporal_support(
                {"pm25": {"years": [2015, 2016, 2022]}},
                "air_quality_pm25",
            ),
            {
                "kind": "period",
                "start_year": "2015",
                "end_year": "2022",
                "aggregation": "mean",
                "source_label": "ACAG V6.GL.02",
            },
        )
        self.assertIsNone(native_temporal_support({}, "wind"))

    def test_caba_native_uses_aoi_without_analysis_units(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.native import load_native_aoi
        from exposome.studies import load_study

        context = load_study("caba_native", repo_root_path=ROOT)
        self.assertTrue(context.is_native)
        self.assertEqual(context.mode, "native")
        aoi = load_native_aoi(context)
        self.assertEqual(len(aoi), 1)
        with self.assertRaisesRegex(ValueError, "is native"):
            context.load_spatial_units()

    def test_santiago_native_uses_aoi_without_analysis_units(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.native import load_native_aoi
        from exposome.studies import load_study

        context = load_study("santiago_native", repo_root_path=ROOT)
        self.assertTrue(context.is_native)
        self.assertEqual(context.mode, "native")
        aoi = load_native_aoi(context)
        self.assertEqual(len(aoi), 1)
        self.assertIn(aoi.geometry.iloc[0].geom_type, {"Polygon", "MultiPolygon"})
        with self.assertRaisesRegex(ValueError, "is native"):
            context.load_spatial_units()

    def test_santiago_native_dissolved_aoi_covers_communes_bbox(self) -> None:
        """The dissolved Gran Santiago AOI must not be a stray/degenerate shape."""
        import sys

        sys.path.insert(0, str(ROOT / "src"))

        communes = gpd.read_file(
            ROOT / "data" / "reference" / "cl" / "santiago" / "santiago_communes"
            / "spatial_units.geojson"
        )
        aoi = gpd.read_file(
            ROOT / "data" / "reference" / "cl" / "santiago" / "santiago_native" / "aoi.geojson"
        )
        commune_bounds = communes.total_bounds
        aoi_bounds = aoi.total_bounds
        for i in (0, 1):  # min corner
            self.assertAlmostEqual(commune_bounds[i], aoi_bounds[i], places=3)
        for i in (2, 3):  # max corner
            self.assertAlmostEqual(commune_bounds[i], aoi_bounds[i], places=3)

    def test_cdmx_native_uses_aoi_without_analysis_units(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.native import load_native_aoi
        from exposome.studies import load_study

        context = load_study("cdmx_native", repo_root_path=ROOT)
        self.assertTrue(context.is_native)
        self.assertEqual(context.mode, "native")
        aoi = load_native_aoi(context)
        self.assertEqual(len(aoi), 1)
        self.assertIn(aoi.geometry.iloc[0].geom_type, {"Polygon", "MultiPolygon"})
        with self.assertRaisesRegex(ValueError, "is native"):
            context.load_spatial_units()

    def test_cdmx_native_dissolved_aoi_covers_alcaldias_bbox(self) -> None:
        """The dissolved Ciudad de Mexico AOI must not be a stray/degenerate shape."""
        import sys

        sys.path.insert(0, str(ROOT / "src"))

        alcaldias = gpd.read_file(
            ROOT / "data" / "reference" / "mx" / "cdmx" / "cdmx_alcaldias"
            / "spatial_units.geojson"
        )
        aoi = gpd.read_file(
            ROOT / "data" / "reference" / "mx" / "cdmx" / "cdmx_native" / "aoi.geojson"
        )
        alcaldia_bounds = alcaldias.total_bounds
        aoi_bounds = aoi.total_bounds
        for i in (0, 1):  # min corner
            self.assertAlmostEqual(alcaldia_bounds[i], aoi_bounds[i], places=3)
        for i in (2, 3):  # max corner
            self.assertAlmostEqual(alcaldia_bounds[i], aoi_bounds[i], places=3)

    def test_native_preflight_does_not_derive_polygon_resolution(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.layers import PreflightStatus, build_run_plan
        from exposome.studies import load_study

        context = load_study("caba_native", repo_root_path=ROOT)
        plans = build_run_plan(context, layer_ids=("climate_heat",))
        self.assertEqual(plans[0].preflight.status, PreflightStatus.READY)
        self.assertIsNone(plans[0].preflight.unit_resolution_m)

    def test_native_execution_identity_invalidates_pre_grid_contract_exports(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.layers import layer_execution_identity, load_layer_catalog
        from exposome.studies import load_study

        context = load_study("santiago_native", repo_root_path=ROOT)
        identity = layer_execution_identity(context, load_layer_catalog().get("alan"))
        self.assertTrue(identity.algorithm_version.endswith("native-grid-contract-v3"))

    def test_native_execution_does_not_call_subprocess_or_boundary_cache(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.layers import build_run_plan, execute_run_plan
        from exposome.studies import load_study

        context = load_study("caba_native", repo_root_path=ROOT)
        plans = build_run_plan(context, layer_ids=("climate_heat",))
        with patch("exposome.native.export_native_layer", return_value=()):
            with patch("exposome.layers.subprocess.run") as runner:
                results = execute_run_plan(context, plans)
        runner.assert_not_called()
        self.assertEqual(results[0].action, "executed")


class NativeOsmExportTests(unittest.TestCase):
    def test_gpkg_frame_sanitizes_osm_field_names_and_container_values(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.native import _prepare_gpkg_frame

        raw = gpd.GeoDataFrame(
            {
                "currency:MXN": ["yes"],
                "currency_MXN": ["collision"],
                "payment:coins": [["MXN", "USD"]],
                "geometry": [Point(-99.13, 19.43)],
            },
            index=pd.MultiIndex.from_tuples(
                [("node", 42)], names=["element", "id"]
            ),
            crs="EPSG:4326",
        )

        prepared = _prepare_gpkg_frame(raw)

        self.assertIn("currency_MXN", prepared.columns)
        self.assertIn("currency_MXN_2", prepared.columns)
        self.assertNotIn("currency:MXN", prepared.columns)
        self.assertEqual(prepared.iloc[0]["payment_coins"], '["MXN", "USD"]')
        self.assertEqual(prepared.iloc[0]["element"], "node")


class NativeAirQualitySatelliteTests(unittest.TestCase):
    """air_quality_satellite native export: NO2 band only (Hallazgo 3)."""

    def test_gee_image_exports_no2_band_only_at_its_own_scale(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.native import _gee_image
        from exposome.config import load_config

        cfg = load_config("caba_native")
        roi = MagicMock(name="roi")

        with patch("exposome.air_quality._annual_no2_image") as mock_image_fn:
            no2_image = MagicMock(name="no2_image")
            clipped = MagicMock(name="clipped")
            no2_image.clip.return_value = clipped
            mock_image_fn.return_value = no2_image

            image, scale, bands = _gee_image(cfg, "air_quality_satellite", roi)

        mock_image_fn.assert_called_once_with(
            dict(cfg), cfg["air_quality"]["start_date"], cfg["air_quality"]["end_date"]
        )
        no2_image.clip.assert_called_once_with(roi)
        self.assertIs(image, clipped)
        self.assertEqual(scale, 1113.0)
        self.assertEqual(bands, "tropospheric_NO2_column_number_density")
        # Only the NO2 band is exported; O3/AOD/BLH must not be touched here
        # (bundling them would force one export scale and oversample the
        # coarser bands — see docs/resolution_manifest.md Hallazgo 3).
        self.assertNotIn("O3", bands)
        self.assertNotIn("Optical_Depth", bands)

    def test_native_layer_specs_declares_no2_native_resolution(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.native import NATIVE_LAYER_SPECS

        spec = NATIVE_LAYER_SPECS["air_quality_satellite"]
        self.assertEqual(spec.kind, "gee_raster")
        self.assertEqual(spec.native_resolution_m, 1113)

    def test_canopy_native_spec_preserves_source_and_analysis_distinction(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.native import NATIVE_LAYER_SPECS

        spec = NATIVE_LAYER_SPECS["greenspace_multisource"]
        self.assertEqual(spec.native_resolution_m, 1)
        self.assertIn("30 m", spec.description)


class NativePrecipitationTests(unittest.TestCase):
    def test_native_precipitation_casts_annual_components_before_cross_year_mean(self) -> None:
        """365- and 366-day annual count bands must share one EE numeric type."""
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.native import _gee_image

        ee = MagicMock()
        daily = ee.ImageCollection.return_value
        daily.filterDate.return_value.select.return_value = daily
        daily.sum.return_value.rename.return_value.toFloat.return_value = MagicMock()
        daily.map.return_value.sum.return_value.rename.return_value.toFloat.return_value = MagicMock()
        ee.Image.return_value.select.return_value.rename.return_value.toFloat.return_value = MagicMock()

        cfg = {
            "precipitation": {
                "collection": {
                    "id": "UCSB-CHG/CHIRPS/DAILY",
                    "band": "precipitation",
                    "scale_meters": 5566,
                },
                "years": [2015, 2016],
                "thresholds": {"wet_day_mm": 1, "heavy_day_mm": 10},
            }
        }
        with patch.dict(sys.modules, {"ee": ee}):
            _gee_image(cfg, "precipitation", MagicMock(name="roi"))

        # One cast for every annual total, heavy-day count and CDD image.
        self.assertEqual(
            daily.sum.return_value.rename.return_value.toFloat.call_count,
            2,
        )
        self.assertEqual(
            daily.map.return_value.sum.return_value.rename.return_value.toFloat.call_count,
            2,
        )
        self.assertEqual(
            ee.Image.return_value.select.return_value.rename.return_value.toFloat.call_count,
            2,
        )


class NativeGeeExportDownloadTests(unittest.TestCase):
    """export_gee_native_layer's download call (Hallazgo 3b).

    Covers two things: (1) it calls geemap.download_ee_image (not the old
    ee_export_image, which had a synchronous 48 MB cap) with the inspected
    source CRS/affine grid rather than a replacement scale; (2) the tif.exists()
    guard raises loudly instead of
    silently writing success metadata for a .tif that was never created —
    the second, independent bug found in the same production run.
    """

    def _context(self) -> MagicMock:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        context = MagicMock()
        context.study.id = "santiago_native"
        context.location.geographic_crs = "EPSG:4326"
        return context

    def test_wildfire_exports_each_component_on_its_own_grid(self) -> None:
        """Mixed-grid wildfire is no longer rejected: MODIS burned area (500 m)
        and FIRMS fire activity (1 km) are exported as separate products, each
        on its own native grid, never fused into one oversampled TIFF."""
        import contextlib
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        import exposome.native as native
        from shapely.geometry import box

        components = [
            ("burned_area", MagicMock(name="burned"), 500.0, "burned_any"),
            ("active_fire", MagicMock(name="fires"), 1000.0, "fire_brightness_max"),
        ]
        written: list[tuple[str, float]] = []

        def fake_verify(geemap, image, tif, ee_roi, *, layer_id, scale):
            Path(tif).write_bytes(b"fake-tif")
            written.append((Path(tif).name, scale))
            return ({"crs": "EPSG:4326"}, {"resolution": {"x": 1, "y": 1, "unit": "m"}})

        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            tmp_dir = Path(tmp)
            stack.enter_context(patch.object(native, "load_native_aoi", return_value=MagicMock()))
            stack.enter_context(patch.object(native, "aoi_geometry", return_value=box(0, 0, 1, 1)))
            stack.enter_context(patch("exposome.config.load_config", return_value={}))
            stack.enter_context(patch("ee.Initialize"))
            stack.enter_context(patch("ee.Geometry", return_value=MagicMock()))
            stack.enter_context(patch.object(native, "native_output_dir", return_value=tmp_dir))
            stack.enter_context(
                patch.object(native, "_gee_component_images", return_value=components)
            )
            stack.enter_context(
                patch.object(native, "_download_and_verify_gee_image", side_effect=fake_verify)
            )
            mock_meta = stack.enter_context(
                patch.object(native, "write_native_metadata", return_value=tmp_dir / "metadata.json")
            )
            result = native.export_gee_native_layer(self._context(), "wildfire")

        # One .tif per component, each named and scaled for its own grid.
        self.assertEqual(
            written,
            [
                ("wildfire_burned_area_native.tif", 500.0),
                ("wildfire_active_fire_native.tif", 1000.0),
            ],
        )
        # Two tifs followed by the metadata path.
        self.assertEqual(len(result), 3)
        mock_meta.assert_called_once()
        outputs = [Path(item).name for item in mock_meta.call_args.kwargs["outputs"]]
        self.assertEqual(
            outputs,
            ["wildfire_burned_area_native.tif", "wildfire_active_fire_native.tif"],
        )

    def test_greenspace_coverage_pins_source_projection(self) -> None:
        """Regression for the 111 320 m fallback: build_landsat_composite's
        .median() drops the 30 m projection, so the native branch must pin it
        back with setDefaultProjection (the sibling precip/wind/heat branches
        already did; greenspace_coverage was the one that was missed)."""
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome import native

        composite = MagicMock(name="composite")
        projection = MagicMock(name="landsat_projection")
        cfg = {
            "greenspace": {
                "satellite": {
                    "years": [2020],
                    "season_months": [1, 2, 12],
                    "ndvi_threshold": 0.3,
                    "evi_threshold": 0.2,
                    "scale_meters": 30,
                }
            }
        }
        with (
            patch(
                "exposome.greenspace_satellite.build_landsat_composite",
                return_value=composite,
            ),
            patch(
                "exposome.greenspace_satellite.landsat_source_projection",
                return_value=projection,
            ),
        ):
            image, scale, bands = native._gee_image(
                cfg, "greenspace_coverage", MagicMock(name="roi")
            )

        composite.setDefaultProjection.assert_called_once_with(projection)
        self.assertEqual(image, composite.setDefaultProjection.return_value)
        self.assertEqual(scale, 30.0)
        self.assertEqual(bands, "NDVI,EVI,green_ndvi,green_evi")

    def test_wildfire_component_scales_match_earth_engine_grid(self) -> None:
        """The strict native grid check rejects a >5% scale mismatch. MODIS
        'BurnDate' is 463.31 m and FIRMS 'T21' is 926.63 m in Earth Engine, not
        the nominal 500/1000 labels, so the component scales must be the real
        nominalScale (native_scale_meters). Ties the config to the code: drop
        that field and the fallback to scale_meters (500/1000) fails here."""
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome import config as legacy_config
        from exposome import native

        cfg = legacy_config.load_config("santiago_native")
        ee = MagicMock()
        with patch.dict(sys.modules, {"ee": ee}):
            components = native._gee_component_images(cfg, "wildfire", MagicMock(name="roi"))

        scales = {component: scale for component, _image, scale, _bands in components}
        self.assertAlmostEqual(scales["burned_area"], 463.3127, places=3)
        self.assertAlmostEqual(scales["active_fire"], 926.6254, places=3)

    def test_grid_signature_uses_provider_affine_transform(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.native import _gee_grid_signature

        image = MagicMock()
        image.select.return_value.projection.return_value.getInfo.return_value = {
            "crs": "EPSG:4326",
            "transform": [1 / 240, 0, -70, 0, -1 / 240, -33],
        }
        signature = _gee_grid_signature(image)
        self.assertEqual(signature["crs"], "EPSG:4326")
        self.assertAlmostEqual(signature["resolution"]["x"], 1 / 240)
        self.assertEqual(signature["resolution"]["unit"], "degree")

    def test_grid_contract_rejects_earth_engine_one_degree_fallback(self) -> None:
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        from exposome.native import _validate_export_grid

        with self.assertRaisesRegex(ValueError, "lost its provider projection"):
            _validate_export_grid(
                "climate_heat",
                {
                    "crs": "EPSG:4326",
                    "resolution": {"x": 1, "y": 1, "unit": "degree"},
                },
                expected_resolution_m=11132,
            )
        _validate_export_grid(
            "climate_heat",
            {
                "crs": "EPSG:4326",
                "resolution": {"x": 0.1, "y": 0.1, "unit": "degree"},
            },
            expected_resolution_m=11132,
        )

    def _apply_patches(self, stack, native, tmp_dir: Path, download_side_effect):
        from shapely.geometry import box

        stack.enter_context(patch.object(native, "load_native_aoi", return_value=MagicMock()))
        stack.enter_context(patch.object(native, "aoi_geometry", return_value=box(0, 0, 1, 1)))
        stack.enter_context(patch("exposome.config.load_config", return_value={}))
        stack.enter_context(patch("ee.Initialize"))
        stack.enter_context(patch("ee.Geometry", return_value=MagicMock()))
        stack.enter_context(
            patch.object(native, "_gee_image", return_value=(MagicMock(), 30.0, "NDVI,EVI"))
        )
        stack.enter_context(
            patch.object(
                native,
                "_gee_grid_signature",
                return_value={
                    "crs": "EPSG:4326",
                    "transform": [30 / 111_320, 0, -70, 0, -30 / 111_320, -33],
                    "resolution": {"x": 30 / 111_320, "y": 30 / 111_320, "unit": "degree"},
                },
            )
        )
        stack.enter_context(patch.object(native, "native_output_dir", return_value=tmp_dir))
        mock_download = stack.enter_context(
            patch("geemap.download_ee_image", side_effect=download_side_effect)
        )
        mock_meta = stack.enter_context(
            patch.object(native, "write_native_metadata", return_value=tmp_dir / "metadata.json")
        )
        stack.enter_context(
            patch(
                "exposome.spatial_detail.raster_grid_signature",
                return_value={
                    "crs": "EPSG:4326",
                    "resolution": {
                        "x": 30 / 111_320,
                        "y": 30 / 111_320,
                        "unit": "degree",
                    },
                },
            )
        )
        return mock_download, mock_meta

    def test_success_calls_download_ee_image_and_writes_metadata(self) -> None:
        import contextlib
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        import exposome.native as native

        def fake_download(image, filename, **kwargs):
            Path(filename).write_bytes(b"fake-tif-bytes")

        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            tmp_dir = Path(tmp)
            mock_download, mock_meta = self._apply_patches(stack, native, tmp_dir, fake_download)
            tif, metadata = native.export_gee_native_layer(
                self._context(), "greenspace_coverage"
            )

            mock_download.assert_called_once()
            call_kwargs = mock_download.call_args.kwargs
            self.assertEqual(call_kwargs["crs"], "EPSG:4326")
            self.assertEqual(
                call_kwargs["crs_transform"],
                [30 / 111_320, 0, -70, 0, -30 / 111_320, -33],
            )
            self.assertNotIn("scale", call_kwargs)
            self.assertEqual(call_kwargs["resampling"], "near")
            # Multi-tile downloads must be serialized to survive Earth Engine
            # Restricted Mode's concurrency ceiling (greenspace_coverage's
            # 84-tile export failed at ~17 tiles otherwise, Lima 2026-07-22).
            self.assertEqual(call_kwargs["num_threads"], 1)
            self.assertEqual(call_kwargs["max_requests"], 1)
            self.assertTrue(tif.exists())
            mock_meta.assert_called_once()

    def test_raises_and_skips_metadata_when_download_produces_no_file(self) -> None:
        """The tif.exists() guard: fail loudly, never write success metadata
        for a .tif that download_ee_image failed to create (Hallazgo 3b's
        second bug — this is exactly what happened in production before the
        guard existed)."""
        import contextlib
        import sys

        sys.path.insert(0, str(ROOT / "src"))
        import exposome.native as native

        def silent_failure(image, filename, **kwargs):
            return None  # no file written, no exception — the old failure mode

        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            tmp_dir = Path(tmp)
            _, mock_meta = self._apply_patches(stack, native, tmp_dir, silent_failure)
            with self.assertRaisesRegex(RuntimeError, "did not produce"):
                native.export_gee_native_layer(self._context(), "greenspace_coverage")

        mock_meta.assert_not_called()


class NativeSamplingTests(unittest.TestCase):
    def test_raster_sampling_uses_nearest_native_pixel(self) -> None:
        # The sampler moved out of scripts/query_exposome.py into an importable
        # module so the CLI, the extract-points command and the web bundle share
        # one implementation.  The script is now only a CLI surface.
        from exposome.point_query import raster_values

        import pandas as pd

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "value.tif"
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                height=2,
                width=2,
                count=1,
                dtype="float32",
                crs="EPSG:4326",
                transform=from_origin(-58.5, -34.5, 0.1, 0.1),
            ) as dst:
                dst.write(np.array([[1, 2], [3, 4]], dtype="float32"), 1)
            result = raster_values(
                path, pd.DataFrame([{"query_id": "p", "lon": -58.46, "lat": -34.54}]), "pm25"
            )
        self.assertEqual(result.loc[0, "pm25_band_1"], 1.0)


if __name__ == "__main__":
    unittest.main()

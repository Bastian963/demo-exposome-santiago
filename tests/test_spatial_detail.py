from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import geopandas as gpd
from rasterio.transform import from_origin
from shapely.geometry import box


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.spatial_detail import (  # noqa: E402
    NATIVE_RASTER_INDICATORS,
    build_aligned_metric_grid,
    build_cog,
    raster_grid_signature,
    _cached_detail_matches_source,
)


class SpatialDetailCogTests(unittest.TestCase):
    def test_cached_detail_requires_identical_source_hash_and_band(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.tif"
            source.write_bytes(b"source-one")
            sidecar = root / "detail.metadata.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "source_path": "alan/alan_native.tif",
                        "source_band": 1,
                        "source_sha256": "not-a-real-hash",
                    }
                ),
                encoding="utf-8",
            )
            self.assertFalse(
                _cached_detail_matches_source(
                    sidecar,
                    source=source,
                    source_band=1,
                    source_relative_path="alan/alan_native.tif",
                )
            )

    def test_cached_heat_detail_requires_matching_temporal_support(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.tif"
            source.write_bytes(b"heat-2024")
            import hashlib

            sidecar = root / "detail.metadata.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "source_path": "climate_heat/climate_heat_native.tif",
                        "source_band": 1,
                        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    }
                ),
                encoding="utf-8",
            )
            self.assertFalse(
                _cached_detail_matches_source(
                    sidecar,
                    source=source,
                    source_band=1,
                    source_relative_path="climate_heat/climate_heat_native.tif",
                    temporal_support={
                        "kind": "year",
                        "year": "2024",
                        "source_label": "ERA5-Land",
                    },
                )
            )
    def test_physical_climate_components_map_to_explicit_native_bands(self) -> None:
        self.assertEqual(NATIVE_RASTER_INDICATORS["heat_summer_tmax"].source_band, 1)
        self.assertEqual(NATIVE_RASTER_INDICATORS["heat_hot_days"].source_band, 2)
        self.assertEqual(NATIVE_RASTER_INDICATORS["heat_tropical_nights"].source_band, 3)
        self.assertEqual(NATIVE_RASTER_INDICATORS["rain_annual"].source_band, 1)
        self.assertEqual(NATIVE_RASTER_INDICATORS["rain_dry_spell"].source_band, 2)
        self.assertEqual(NATIVE_RASTER_INDICATORS["rain_heavy"].source_band, 3)

    def test_build_cog_reprojects_without_interpolating_source_values(self) -> None:
        import rasterio

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.tif"
            output = root / "detail.tif"
            values = np.array([[1, 2], [3, 4]], dtype="float32")
            with rasterio.open(
                source,
                "w",
                driver="GTiff",
                height=2,
                width=2,
                count=1,
                dtype="float32",
                crs="EPSG:4326",
                transform=from_origin(-70, -33, 0.01, 0.01),
                nodata=-9999,
            ) as dataset:
                dataset.write(values, 1)

            metadata = build_cog(source, output)

            self.assertTrue(output.is_file())
            self.assertEqual(metadata["crs"], "EPSG:3857")
            self.assertEqual(metadata["resampling"], "nearest")
            self.assertEqual(metadata["storage_grid"]["crs"], "EPSG:3857")
            self.assertEqual(metadata["statistics"]["min"], 1.0)
            self.assertEqual(metadata["statistics"]["max"], 4.0)
            with rasterio.open(output) as dataset:
                self.assertEqual(dataset.crs.to_string(), "EPSG:3857")
                self.assertIn(dataset.driver, {"GTiff", "COG"})

    def test_grid_signature_comes_from_the_raster_not_sidecar_claims(self) -> None:
        import rasterio

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "grid.tif"
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                height=2,
                width=2,
                count=1,
                dtype="float32",
                crs="EPSG:4326",
                transform=from_origin(-70, -33, 1 / 240, 1 / 240),
            ) as dataset:
                dataset.write(np.ones((2, 2), dtype="float32"), 1)
            signature = raster_grid_signature(path)
        self.assertEqual(signature["crs"], "EPSG:4326")
        self.assertEqual(signature["resolution"]["unit"], "degree")
        self.assertAlmostEqual(signature["resolution"]["x"], 1 / 240)

    def test_build_cog_can_publish_one_exact_source_band(self) -> None:
        import rasterio

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-multiband.tif"
            output = root / "hot-days.tif"
            with rasterio.open(
                source,
                "w",
                driver="GTiff",
                height=2,
                width=2,
                count=3,
                dtype="float32",
                crs="EPSG:4326",
                transform=from_origin(-70, -33, 0.1, 0.1),
            ) as dataset:
                dataset.write(np.full((2, 2), 11, dtype="float32"), 1)
                dataset.write(np.full((2, 2), 22, dtype="float32"), 2)
                dataset.write(np.full((2, 2), 33, dtype="float32"), 3)

            metadata = build_cog(source, output, source_bands=(2,))

            self.assertEqual(metadata["count"], 1)
            self.assertEqual(metadata["statistics"]["min"], 22.0)
            self.assertEqual(metadata["statistics"]["max"], 22.0)

    def test_metadata_is_json_serializable(self) -> None:
        payload = {"statistics": {"p02": 1.2, "p98": 9.8}, "count": 12}
        self.assertIsInstance(json.dumps(payload), str)

    def test_grid_phase_is_identical_when_communes_are_dissolved_or_split(self) -> None:
        dissolved = gpd.GeoDataFrame(geometry=[box(0, 0, 2500, 1800)], crs="EPSG:3857")
        split = gpd.GeoDataFrame(
            geometry=[box(0, 0, 1200, 1800), box(1200, 0, 2500, 1800)],
            crs="EPSG:3857",
        )
        one = build_aligned_metric_grid(dissolved, spacing_m=1000, metric_crs="EPSG:3857")
        many = build_aligned_metric_grid(split, spacing_m=1000, metric_crs="EPSG:3857")
        self.assertEqual(one["cell_id"].tolist(), many["cell_id"].tolist())
        self.assertEqual(
            [geom.wkt for geom in one["sample_geometry"]],
            [geom.wkt for geom in many["sample_geometry"]],
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from rasterio.transform import from_origin


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.spatial_audit import audit_spatial_contract, published_bundle_paths  # noqa: E402
from exposome.spatial_support import indicators_for_bundle  # noqa: E402
from exposome.spatial_support import NOISE_LDEN_BANDS  # noqa: E402
from exposome.noise_spain_tiles import _generate_tiles, _resolved_bands, _simplify  # noqa: E402
import geopandas as gpd  # noqa: E402
from shapely.geometry import box  # noqa: E402


class SpatialAuditTests(unittest.TestCase):
    def _write_vector_bundle(self, root: Path) -> Path:
        palette = json.loads((ROOT / "webapp" / "public" / "palette.json").read_text())
        palette_path = root / "palette.json"
        palette_path.write_text(json.dumps(palette), encoding="utf-8")
        contours = gpd.GeoDataFrame(
            {
                "source_id": ["a"] * 5,
                "band_midpoint": [57.0, 62.0, 67.0, 72.0, 77.5],
                "lden_band": ["55-59", "60-64", "65-69", "70-74", "gt75"],
                "geometry": [
                    box(3656000 + index * 1200, 2060000, 3657000 + index * 1200, 2061000)
                    for index in range(5)
                ],
            },
            crs="EPSG:3035",
        )
        simplified = _simplify(_resolved_bands(contours))
        tile_root = root / "detail" / "noise_lden"
        inventory = _generate_tiles(simplified, tile_root, resume=False)
        digest = "a" * 64
        report = {
            "schema_version": 1,
            "source_manifest_sha256": digest,
            "source_assets": [{"path": "cataluna/barcelona.zip", "sha256": digest}],
            "source_support_preserved": True,
            "minzoom": 11,
            "maxzoom": 15,
            "quantization_invalid_geometry": "polygonal_make_valid_or_drop",
            "geometry_sha256": "b" * 64,
            "topology": {
                "resolved_valid": True,
                "simplified_valid": True,
                "bands_disjoint": True,
                "within_aoi": True,
            },
            "area_checks": {
                band["value"]: {
                    "source_to_resolved_fraction": 0.0,
                    "resolved_to_simplified_fraction": 0.0,
                    "simplified_to_tiled_fraction": 0.0,
                }
                for band in NOISE_LDEN_BANDS
            },
            "initial_visible_gzip_bytes": {
                "desktop_4x4": sum(item["gzip_bytes"] for item in inventory if item["z"] == 11),
                "mobile_3x5": sum(item["gzip_bytes"] for item in inventory if item["z"] == 11),
            },
            "tiles": inventory,
        }
        validation_path = root / "detail" / "noise_lden.vector_contours.validation.json"
        validation_path.write_text(json.dumps(report), encoding="utf-8")
        descriptor = {
            "schema_version": 1,
            "type": "vector_contours",
            "tiles": ["detail/noise_lden/{z}/{x}/{y}.pbf"],
            "minzoom": 11,
            "maxzoom": 15,
            "bounds": [2.0, 41.0, 2.3, 41.6],
            "source_layer": "noise_lden",
            "bands": list(NOISE_LDEN_BANDS),
            "source_manifest_sha256": digest,
            "source_assets": [{"path": "cataluna/barcelona.zip", "sha256": digest}],
            "source_sha256": digest,
            "source_support_preserved": True,
            "validation": {
                "path": "detail/noise_lden.vector_contours.validation.json",
                "sha256": hashlib.sha256(validation_path.read_bytes()).hexdigest(),
            },
        }
        descriptor_path = root / "detail" / "noise_lden.vector_contours.json"
        descriptor_path.write_text(json.dumps(descriptor), encoding="utf-8")
        records = indicators_for_bundle(
            ["detail/noise_lden.vector_contours.json"],
            vector_contour_metadata={"noise_lden": descriptor},
            administrative_unit_label="distrito",
        )
        (root / "manifest.json").write_text(
            json.dumps({"schema_version": 3, "spatial_indicators": records}),
            encoding="utf-8",
        )
        return palette_path

    def test_strict_mode_accepts_verified_vector_contours(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            palette = self._write_vector_bundle(root)
            result = audit_spatial_contract(palette, bundle_path=root, strict=True)
        self.assertTrue(result.ok, result.issues)

    def test_strict_mode_ignores_macos_appledouble_tile_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            palette = self._write_vector_bundle(root)
            tile = next((root / "detail" / "noise_lden").rglob("*.pbf"))
            tile.with_name(f"._{tile.name}").write_bytes(b"not an MVT")
            result = audit_spatial_contract(palette, bundle_path=root, strict=True)
        self.assertTrue(result.ok, result.issues)

    def test_strict_mode_rejects_tampered_vector_tile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            palette = self._write_vector_bundle(root)
            tile = next((root / "detail" / "noise_lden").rglob("*.pbf"))
            tile.write_bytes(tile.read_bytes() + b"tampered")
            result = audit_spatial_contract(palette, bundle_path=root, strict=True)
        self.assertFalse(result.ok)
        self.assertTrue(any("tile hash differs" in issue for issue in result.issues))

    def test_repository_palette_has_complete_support_coverage(self) -> None:
        result = audit_spatial_contract(ROOT / "webapp" / "public" / "palette.json")
        self.assertTrue(result.ok, result.issues)
        # noise_lden is part of the published Spain noise integration.
        self.assertEqual(result.checked_indicators, 47)

    def test_bundle_rejects_advertised_missing_detail(self) -> None:
        palette = json.loads((ROOT / "webapp" / "public" / "palette.json").read_text())
        records = indicators_for_bundle([])
        records["pm25"]["detail"] = {
            "type": "cog",
            "path": "detail/pm25.tif",
            "band": 1,
            "color_domain": {"min": 1, "max": 2},
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            palette_path = root / "palette.json"
            palette_path.write_text(json.dumps(palette), encoding="utf-8")
            (root / "manifest.json").write_text(
                json.dumps({"schema_version": 2, "spatial_indicators": records}),
                encoding="utf-8",
            )
            result = audit_spatial_contract(palette_path, bundle_path=root)
        self.assertFalse(result.ok)
        self.assertTrue(any("pm25: advertised detail asset is missing" in issue for issue in result.issues))

    def test_all_bundle_discovery_ignores_nested_layer_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "v1" / "cl" / "santiago" / "study"
            layer = bundle / "layers" / "pm25"
            layer.mkdir(parents=True)
            (bundle / "manifest.json").write_text("{}", encoding="utf-8")
            (layer / "manifest.json").write_text("{}", encoding="utf-8")
            self.assertEqual(published_bundle_paths(root), [bundle / "manifest.json"])

    def test_strict_mode_requires_inspected_grid_provenance(self) -> None:
        import rasterio

        palette = json.loads((ROOT / "webapp" / "public" / "palette.json").read_text())
        records = indicators_for_bundle([])
        records["pm25"].update(
            {
                "detail": {
                    "type": "cog",
                    "path": "detail/pm25.tif",
                    "band": 1,
                    "canonical_resolution_verified": True,
                    "source_native_resolution_m": 1113.0,
                    "color_domain": {"min": 1, "max": 2},
                },
                "rendered": {
                    "kind": "cog",
                    "label": "píxel ACAG nativo",
                    "resolution": {"value": 1113, "unit": "m"},
                },
                "boundary_role": "mask_only",
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            palette_path = root / "palette.json"
            palette_path.write_text(json.dumps(palette), encoding="utf-8")
            detail = root / "detail"
            detail.mkdir()
            with rasterio.open(
                detail / "pm25.tif",
                "w",
                driver="GTiff",
                height=1,
                width=1,
                count=1,
                dtype="float32",
                crs="EPSG:3857",
                transform=from_origin(0, 0, 1000, 1000),
            ) as dataset:
                dataset.write(np.array([[1]], dtype="float32"), 1)
            (detail / "pm25.metadata.json").write_text(
                json.dumps(
                    {
                        "source_native_study": "native",
                        "source_path": "pm25/pm25_native.tif",
                        "source_support_preserved": True,
                        "source_native_resolution_m": 1113.0,
                    }
                ),
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                json.dumps({"schema_version": 3, "spatial_indicators": records}),
                encoding="utf-8",
            )
            result = audit_spatial_contract(palette_path, bundle_path=root, strict=True)
        self.assertFalse(result.ok)
        self.assertTrue(any("lacks inspected source grid" in issue for issue in result.issues))

    def test_strict_mode_rejects_rounded_alan_grid(self) -> None:
        import rasterio

        palette = json.loads((ROOT / "webapp" / "public" / "palette.json").read_text())
        records = indicators_for_bundle([])
        records["alan"].update(
            {
                "detail": {
                    "type": "cog",
                    "path": "detail/alan.tif",
                    "band": 1,
                    "canonical_resolution_verified": True,
                    "source_native_resolution_m": 463.83,
                    "color_domain": {"min": 1, "max": 2},
                },
                "rendered": {
                    "kind": "cog",
                    "label": "radiancia VIIRS nativa",
                    "resolution": {"value": 463.83, "unit": "m"},
                },
                "boundary_role": "mask_only",
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            palette_path = root / "palette.json"
            palette_path.write_text(json.dumps(palette), encoding="utf-8")
            detail = root / "detail"
            detail.mkdir()
            with rasterio.open(
                detail / "alan.tif",
                "w",
                driver="GTiff",
                height=1,
                width=1,
                count=1,
                dtype="float32",
                crs="EPSG:3857",
                transform=from_origin(0, 0, 500, 500),
            ) as dataset:
                dataset.write(np.array([[1]], dtype="float32"), 1)
            (detail / "alan.metadata.json").write_text(
                json.dumps(
                    {
                        "source_native_study": "native",
                        "source_path": "alan/alan_native.tif",
                        "source_support_preserved": True,
                        "source_native_resolution_m": 463.83,
                        "source_grid": {
                            "crs": "EPSG:4326",
                            "resolution": {"x": 0.0044916, "y": 0.0044916, "unit": "degree"},
                        },
                        "storage_grid": {
                            "crs": "EPSG:3857",
                            "resolution": {"x": 500, "y": 500, "unit": "m"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                json.dumps({"schema_version": 3, "spatial_indicators": records}),
                encoding="utf-8",
            )
            result = audit_spatial_contract(palette_path, bundle_path=root, strict=True)
        self.assertFalse(result.ok)
        self.assertTrue(any("does not meet the canonical provider grid" in issue for issue in result.issues))

    def test_temporal_cog_must_match_year_and_shared_color_domain(self) -> None:
        palette = json.loads((ROOT / "webapp" / "public" / "palette.json").read_text())
        records = indicators_for_bundle([])
        domain = {"min": 10.0, "max": 35.0}
        detail_record = {
            "type": "cog",
            "path": "annual/detail/pm25_2015.tif",
            "band": 1,
            "canonical_resolution_verified": True,
            "source_native_resolution_m": 1113.0,
            "source_support_preserved": True,
            "source_sha256": "a" * 64,
            "color_domain": {"min": 11.0, "max": 30.0},
            "temporal_support": {
                "kind": "year",
                "year": "2016",
                "source_label": "ACAG V6.GL.02",
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            palette_path = root / "palette.json"
            palette_path.write_text(json.dumps(palette), encoding="utf-8")
            annual_detail = root / "annual" / "detail"
            annual_detail.mkdir(parents=True)
            (annual_detail / "pm25_2015.tif").write_bytes(b"advertised-test-asset")
            (annual_detail / "pm25_2015.metadata.json").write_text(
                json.dumps(
                    {
                        "source_sha256": "a" * 64,
                        "source_support_preserved": True,
                        "source_native_resolution_m": 1113.0,
                        "series_color_domain": domain,
                        "temporal_support": detail_record["temporal_support"],
                    }
                ),
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 3,
                        "spatial_indicators": records,
                        "temporal_indicators": {
                            "pm25": {
                                "color_domain": domain,
                                "years": {"2015": {"detail": detail_record}},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = audit_spatial_contract(palette_path, bundle_path=root)
        self.assertFalse(result.ok)
        self.assertTrue(any("temporal support does not match" in issue for issue in result.issues))
        self.assertTrue(any("does not use the series color domain" in issue for issue in result.issues))

    def test_documented_exception_lets_strict_audit_pass(self) -> None:
        import rasterio

        palette = json.loads((ROOT / "webapp" / "public" / "palette.json").read_text())
        records = indicators_for_bundle([])
        domain = {"min": 10.0, "max": 35.0}
        detail_record = {
            "type": "cog",
            "path": "annual/detail/pm25_2016.tif",
            "band": 1,
            "canonical_resolution_verified": True,
            "source_native_resolution_m": 1113.0,
            "source_support_preserved": True,
            "source_sha256": "a" * 64,
            "color_domain": domain,
            "temporal_support": {
                "kind": "year",
                "year": "2016",
                "source_label": "ACAG V6.GL.02",
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            palette_path = root / "palette.json"
            palette_path.write_text(json.dumps(palette), encoding="utf-8")
            annual_detail = root / "annual" / "detail"
            annual_detail.mkdir(parents=True)
            with rasterio.open(
                annual_detail / "pm25_2016.tif",
                "w",
                driver="GTiff",
                height=1,
                width=1,
                count=1,
                dtype="float32",
                crs="EPSG:3857",
                transform=from_origin(0, 0, 1113, 1113),
            ) as dataset:
                dataset.write(np.array([[1]], dtype="float32"), 1)
            (annual_detail / "pm25_2016.metadata.json").write_text(
                json.dumps(
                    {
                        "source_sha256": "a" * 64,
                        "source_support_preserved": True,
                        "source_native_resolution_m": 1113.0,
                        "series_color_domain": domain,
                        "temporal_support": detail_record["temporal_support"],
                        "source_grid": {
                            "crs": "EPSG:4326",
                            "resolution": {"x": 0.01, "y": 0.01, "unit": "degree"},
                        },
                        "storage_grid": {
                            "crs": "EPSG:3857",
                            "resolution": {"x": 1113, "y": 1113, "unit": "m"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 3,
                        "spatial_indicators": records,
                        "temporal_indicators": {
                            "pm25": {
                                "expected_years": ["2015", "2016"],
                                "excepted_years": ["2015"],
                                "exceptions": [
                                    {
                                        "year": "2015",
                                        "reason": "Deterministic provider gap.",
                                        "doc": "docs/x.md",
                                    }
                                ],
                                "color_domain": domain,
                                "years": {"2016": {"detail": detail_record}},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = audit_spatial_contract(palette_path, bundle_path=root, strict=True)
        self.assertTrue(result.ok, result.issues)

    def test_undeclared_missing_year_still_fails_despite_an_unrelated_exception(self) -> None:
        palette = json.loads((ROOT / "webapp" / "public" / "palette.json").read_text())
        records = indicators_for_bundle([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            palette_path = root / "palette.json"
            palette_path.write_text(json.dumps(palette), encoding="utf-8")
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 3,
                        "spatial_indicators": records,
                        "temporal_indicators": {
                            "pm25": {
                                "expected_years": ["2015", "2016"],
                                "excepted_years": ["2015"],
                                "exceptions": [
                                    {
                                        "year": "2015",
                                        "reason": "Deterministic provider gap.",
                                        "doc": "docs/x.md",
                                    }
                                ],
                                "years": {},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = audit_spatial_contract(palette_path, bundle_path=root, strict=True)
        self.assertFalse(result.ok)
        self.assertTrue(
            any("missing years ['2016']" in issue for issue in result.issues)
        )
        self.assertFalse(any("'2015'" in issue for issue in result.issues))

    def test_exception_year_outside_expected_years_is_rejected(self) -> None:
        palette = json.loads((ROOT / "webapp" / "public" / "palette.json").read_text())
        records = indicators_for_bundle([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            palette_path = root / "palette.json"
            palette_path.write_text(json.dumps(palette), encoding="utf-8")
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 3,
                        "spatial_indicators": records,
                        "temporal_indicators": {
                            "pm25": {
                                "expected_years": ["2015", "2016"],
                                "excepted_years": ["2019"],
                                "exceptions": [
                                    {
                                        "year": "2019",
                                        "reason": "Deterministic provider gap.",
                                        "doc": "docs/x.md",
                                    }
                                ],
                                "years": {},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = audit_spatial_contract(palette_path, bundle_path=root, strict=True)
        self.assertFalse(result.ok)
        self.assertTrue(
            any("excepted_years ['2019'] are not in expected_years" in issue for issue in result.issues)
        )

    def test_exception_without_a_reason_is_rejected(self) -> None:
        palette = json.loads((ROOT / "webapp" / "public" / "palette.json").read_text())
        records = indicators_for_bundle([])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            palette_path = root / "palette.json"
            palette_path.write_text(json.dumps(palette), encoding="utf-8")
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 3,
                        "spatial_indicators": records,
                        "temporal_indicators": {
                            "pm25": {
                                "expected_years": ["2015", "2016"],
                                "excepted_years": ["2015"],
                                "exceptions": [],
                                "years": {},
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = audit_spatial_contract(palette_path, bundle_path=root, strict=True)
        self.assertFalse(result.ok)
        self.assertTrue(
            any(
                "excepted_years ['2015'] have no documented reason" in issue
                for issue in result.issues
            )
        )


if __name__ == "__main__":
    unittest.main()

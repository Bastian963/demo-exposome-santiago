from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.spatial_coverage import audit_spatial_coverage, coverage_for_manifest  # noqa: E402
from exposome.spatial_support import indicators_for_bundle  # noqa: E402


class SpatialCoverageTests(unittest.TestCase):
    def _manifest(self, *, mode: str = "aggregate") -> dict:
        records = indicators_for_bundle([])
        # Focus each fixture on ALAN; the remaining cards are valid but outside
        # the assertion's target scope.
        for indicator_id, record in records.items():
            if indicator_id != "alan":
                record["publication_target"]["required_for_production"] = False
        return {
            "study_id": "example",
            "mode": mode,
            "layers": {"alan": {"available": True}},
            "spatial_indicators": records,
        }

    def test_missing_native_alan_is_honest_preview_not_production(self) -> None:
        coverage = coverage_for_manifest(self._manifest())
        self.assertEqual(coverage.status, "partial")
        self.assertEqual(coverage.publication_tier, "preview")
        self.assertEqual(coverage.missing, ("alan",))

    def test_verified_detail_completes_required_indicator(self) -> None:
        manifest = self._manifest()
        alan = manifest["spatial_indicators"]["alan"]
        alan["detail"] = {
            "type": "cog",
            "path": "detail/alan.tif",
            "canonical_resolution_verified": True,
            "source_grid": {
                "crs": "EPSG:4326",
                "resolution": {"x": 1 / 240, "y": 1 / 240, "unit": "degree"},
            },
        }
        alan["rendered"] = {
            "kind": "cog",
            "label": "radiancia VIIRS nativa",
            "resolution": {"value": 463.83, "unit": "m"},
        }
        alan["boundary_role"] = "mask_only"
        coverage = coverage_for_manifest(manifest)
        self.assertEqual(coverage.status, "complete")
        self.assertEqual(coverage.publication_tier, "production")
        self.assertEqual(coverage.complete, 1)

    def test_false_one_degree_detail_is_reported_as_missing(self) -> None:
        manifest = self._manifest()
        alan = manifest["spatial_indicators"]["alan"]
        alan["detail"] = {
            "type": "cog",
            "path": "detail/alan.tif",
            "canonical_resolution_verified": True,
            "source_grid": {
                "crs": "EPSG:4326",
                "resolution": {"x": 1, "y": 1, "unit": "degree"},
            },
        }
        alan["rendered"] = {"kind": "cog"}
        coverage = coverage_for_manifest(manifest)
        self.assertEqual(coverage.missing, ("alan",))
        self.assertEqual(coverage.indicators["alan"]["reason"], "source_grid_mismatch")

    def test_required_annual_series_is_missing_when_one_year_has_no_detail(self) -> None:
        manifest = self._manifest()
        alan = manifest["spatial_indicators"]["alan"]
        alan["detail"] = {
            "type": "cog",
            "path": "detail/alan.tif",
            "canonical_resolution_verified": True,
            "source_grid": {
                "crs": "EPSG:4326",
                "resolution": {"x": 1 / 240, "y": 1 / 240, "unit": "degree"},
            },
        }
        alan["rendered"] = {"kind": "cog"}
        manifest["temporal_indicators"] = {
            "alan": {
                "expected_years": ["2023", "2024"],
                "spatial_target": {
                    "kind": "native_raster",
                    "required_for_production": True,
                },
                "years": {
                    "2023": {
                        "detail": {
                            "type": "cog",
                            "canonical_resolution_verified": True,
                            "source_support_preserved": True,
                            "temporal_support": {"kind": "year", "year": "2023"},
                        }
                    },
                    "2024": {"asset": {"path": "annual/alan_2024.json"}},
                },
            }
        }
        coverage = coverage_for_manifest(manifest)
        self.assertEqual(coverage.missing, ("alan",))
        self.assertEqual(coverage.indicators["alan"]["reason"], "annual_detail_incomplete")
        self.assertEqual(coverage.indicators["alan"]["missing_years"], ["2024"])

    def test_documented_exception_still_leaves_the_series_incomplete(self) -> None:
        # spatial_coverage.py deliberately does not read excepted_years/exceptions
        # (ADR 0008): a documented, permanent gap lets `publish` and
        # `spatial-audit --strict` pass, but resolution-coverage must keep
        # reporting the indicator as missing so the study stays at `preview`
        # instead of silently re-earning `production`.
        manifest = self._manifest()
        alan = manifest["spatial_indicators"]["alan"]
        alan["detail"] = {
            "type": "cog",
            "path": "detail/alan.tif",
            "canonical_resolution_verified": True,
            "source_grid": {
                "crs": "EPSG:4326",
                "resolution": {"x": 1 / 240, "y": 1 / 240, "unit": "degree"},
            },
        }
        alan["rendered"] = {"kind": "cog"}
        manifest["temporal_indicators"] = {
            "alan": {
                "expected_years": ["2023", "2024"],
                "excepted_years": ["2024"],
                "exceptions": [
                    {
                        "year": "2024",
                        "reason": "Deterministic provider gap.",
                        "doc": "docs/x.md",
                    }
                ],
                "spatial_target": {
                    "kind": "native_raster",
                    "required_for_production": True,
                },
                "years": {
                    "2023": {
                        "detail": {
                            "type": "cog",
                            "canonical_resolution_verified": True,
                            "source_support_preserved": True,
                            "temporal_support": {"kind": "year", "year": "2023"},
                        }
                    },
                },
            }
        }
        coverage = coverage_for_manifest(manifest)
        self.assertEqual(coverage.missing, ("alan",))
        self.assertEqual(coverage.publication_tier, "preview")
        self.assertEqual(coverage.indicators["alan"]["reason"], "annual_detail_incomplete")
        self.assertEqual(coverage.indicators["alan"]["missing_years"], ["2024"])

    def test_native_companion_is_not_a_standalone_production_map(self) -> None:
        coverage = coverage_for_manifest(self._manifest(mode="native"))
        self.assertEqual(coverage.status, "complete")
        self.assertEqual(coverage.publication_tier, "preview")
        self.assertEqual(coverage.required, 0)

    def test_explicit_unavailability_wins_over_layer_presence(self) -> None:
        manifest = self._manifest()
        manifest["spatial_indicators"]["alan"]["availability"] = {
            "status": "unavailable",
            "reason": "country_not_supported",
            "supported_countries": ["AR"],
        }
        coverage = coverage_for_manifest(manifest)
        self.assertEqual(coverage.required, 0)
        self.assertEqual(coverage.missing, ())
        self.assertFalse(coverage.indicators["alan"]["layer_available"])

    def test_bundle_audit_reads_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            bundle.joinpath("manifest.json").write_text(
                json.dumps(self._manifest()), encoding="utf-8"
            )
            result = audit_spatial_coverage(bundle)
        self.assertEqual(result.study_id, "example")
        self.assertIn("alan", result.missing)

    def test_legacy_manifest_uses_current_target_not_stale_raster_claim(self) -> None:
        records = indicators_for_bundle([])
        legacy_heat_index = dict(records["heat_index"])
        legacy_heat_index.pop("publication_target")
        # Simulate a pre-target manifest whose old declaration called the
        # city-relative z-score a raster. The current contract must not demand
        # an invented COG for it.
        legacy_heat_index["downloaded"] = {"kind": "raster_grid"}
        legacy_heat_index["analysis"] = {"kind": "regular_grid"}
        coverage = coverage_for_manifest(
            {
                "study_id": "legacy",
                "mode": "aggregate",
                "layers": {"climate_heat": {"available": True}},
                "spatial_indicators": {"heat_index": legacy_heat_index},
            }
        )
        self.assertEqual(coverage.required, 0)
        self.assertEqual(coverage.missing, ())


if __name__ == "__main__":
    unittest.main()

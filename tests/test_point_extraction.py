"""Contracts for the published, indicator-keyed extraction path.

The offline tests build a miniature bundle in a temp dir.  The tests that read
the real ``webapp/public/data`` bundle are gated behind
``EXPOSOME_RUN_ARTIFACT_TESTS=1`` like the rest of the artifact suite.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from exposome.point_extraction import (
    FLAG_NOT_PUBLISHED,
    FLAG_OUT_OF_COVERAGE,
    FLAG_UNSUPPORTED,
    BundleStudy,
    detail_asset,
    extract_points,
    load_bundle_catalog,
    study_for_point,
)

ARTIFACTS = os.environ.get("EXPOSOME_RUN_ARTIFACT_TESTS") == "1"
REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_BUNDLE = REPO_ROOT / "webapp" / "public" / "data"

SANTIAGO_LON = -70.65
SANTIAGO_LAT = -33.45


def _study(study_id: str, bbox, *, hidden: bool = False) -> dict:
    return {
        "study_id": study_id,
        "city": study_id,
        "country_code": "cl",
        "bundle": f"v1/{study_id}",
        "bbox": list(bbox),
        "available": True,
        "hidden": hidden,
        "unit_type": "commune",
    }


class CatalogTest(unittest.TestCase):
    def _catalog(self, tmp: Path, studies) -> Path:
        (tmp / "catalog.json").write_text(json.dumps({"studies": studies}))
        return tmp

    def test_smallest_bbox_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._catalog(Path(tmp), [
                _study("wide", (-72, -35, -69, -32)),
                _study("narrow", (-70.8, -33.6, -70.5, -33.3)),
            ])
            studies = load_bundle_catalog(root)
            match = study_for_point(studies, SANTIAGO_LON, SANTIAGO_LAT)
            self.assertEqual(match.study_id, "narrow")

    def test_hidden_studies_are_not_resolution_targets(self) -> None:
        # buenos_aires_comunas is hidden and has a smaller bbox than
        # buenos_aires_amba; routing a CABA address to it would lose the COGs.
        with tempfile.TemporaryDirectory() as tmp:
            root = self._catalog(Path(tmp), [
                _study("visible", (-72, -35, -69, -32)),
                _study("hidden_small", (-70.8, -33.6, -70.5, -33.3), hidden=True),
            ])
            studies = load_bundle_catalog(root)
            self.assertEqual([s.study_id for s in studies], ["visible"])
            match = study_for_point(studies, SANTIAGO_LON, SANTIAGO_LAT)
            self.assertEqual(match.study_id, "visible")

    def test_hidden_can_be_opted_into(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._catalog(Path(tmp), [
                _study("visible", (-72, -35, -69, -32)),
                _study("hidden_small", (-70.8, -33.6, -70.5, -33.3), hidden=True),
            ])
            studies = load_bundle_catalog(root, include_hidden=True)
            self.assertEqual(len(studies), 2)

    def test_unavailable_studies_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = _study("planned", (-72, -35, -69, -32))
            record["available"] = False
            root = self._catalog(Path(tmp), [record])
            self.assertEqual(load_bundle_catalog(root), [])

    def test_point_outside_every_study(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._catalog(Path(tmp), [_study("wide", (-72, -35, -69, -32))])
            studies = load_bundle_catalog(root)
            self.assertIsNone(study_for_point(studies, 0.0, 0.0))


class DetailAssetTest(unittest.TestCase):
    def _bundle(self, tmp: Path, manifest: dict) -> BundleStudy:
        root = tmp / "bundle"
        root.mkdir(parents=True)
        (root / "manifest.json").write_text(json.dumps(manifest))
        (root / "palette.json").write_text(json.dumps({"exposomes": {}}))
        return BundleStudy("s", "c", "cl", "bundle", (-1, -1, 1, 1), "commune", root)

    def test_current_epoch_asset_comes_from_spatial_indicators(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            study = self._bundle(Path(tmp), {
                "spatial_indicators": {
                    "pm25": {"detail": {"type": "cog", "path": "detail/pm25.tif"}}
                }
            })
            self.assertEqual(detail_asset(study, "pm25")["path"], "detail/pm25.tif")

    def test_year_scoped_asset_comes_from_temporal_indicators(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            study = self._bundle(Path(tmp), {
                "temporal_indicators": {
                    "pm25": {"years": {
                        "2020": {"detail": {"type": "cog",
                                            "path": "annual/detail/pm25_2020.tif"}}
                    }}
                }
            })
            asset = detail_asset(study, "pm25", 2020)
            self.assertEqual(asset["path"], "annual/detail/pm25_2020.tif")

    def test_absent_indicator_has_no_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            study = self._bundle(Path(tmp), {"spatial_indicators": {}})
            self.assertIsNone(detail_asset(study, "pm25"))


@unittest.skipUnless(ARTIFACTS, "set EXPOSOME_RUN_ARTIFACT_TESTS=1")
class PublishedBundleTest(unittest.TestCase):
    """End-to-end against the real bundle.  Read-only, no network."""

    POINTS = pd.DataFrame([
        {"query_id": "santiago", "lon": SANTIAGO_LON, "lat": SANTIAGO_LAT},
        {"query_id": "ocean", "lon": -90.0, "lat": -40.0},
    ])

    @classmethod
    def setUpClass(cls) -> None:
        if not (REAL_BUNDLE / "catalog.json").exists():
            raise unittest.SkipTest("no published bundle on disk")
        cls.frame = extract_points(
            cls.POINTS, ["pm25", "canopy", "no2", "green", "nse"],
            radii=[0, 300, 1000], data_root=REAL_BUNDLE,
        )

    def _rows(self, exposome: str, query_id: str = "santiago") -> pd.DataFrame:
        return self.frame[
            (self.frame["exposome_id"] == exposome) & (self.frame["query_id"] == query_id)
        ]

    def test_point_resolves_to_its_city(self) -> None:
        self.assertEqual(self._rows("pm25")["study_id"].iloc[0], "santiago_communes")

    def test_point_outside_every_study_is_flagged_not_dropped(self) -> None:
        ocean = self.frame[self.frame["query_id"] == "ocean"]
        self.assertFalse(ocean.empty)
        self.assertEqual(ocean["quality_flag"].iloc[0], FLAG_OUT_OF_COVERAGE)

    def test_no2_never_emits_a_within_buffer_sd(self) -> None:
        # Its observation footprint is 7 km, so no offered radius resolves.
        rows = self._rows("no2")
        self.assertTrue(rows["sd_within_buffer"].isna().all())
        self.assertTrue((rows["radius_status"] == "sub_observation").all())

    def test_canopy_resolves_and_reports_spread(self) -> None:
        resolved = self._rows("canopy").query("radius_m == 300")
        self.assertEqual(resolved["radius_status"].iloc[0], "resolved")
        self.assertTrue(np.isfinite(resolved["sd_within_buffer"].iloc[0]))
        self.assertGreater(resolved["n_cells"].iloc[0], 100)

    def test_green_is_declared_unsupported_not_404(self) -> None:
        # green's detail is subcomuna/green.geojson, not a COG.
        rows = self._rows("green")
        self.assertEqual(rows["quality_flag"].iloc[0], FLAG_UNSUPPORTED)

    def test_administrative_value_has_no_radius(self) -> None:
        rows = self._rows("nse")
        self.assertEqual(len(rows), 1)
        self.assertTrue(pd.isna(rows["radius_m"].iloc[0]))
        self.assertEqual(rows["radius_status"].iloc[0], "not_applicable")
        self.assertIsNotNone(rows["spatial_id"].iloc[0])

    def test_support_is_never_finer_than_the_product(self) -> None:
        raster = self.frame[self.frame["estimand_kind"] == "raster_block"].dropna(
            subset=["support_m", "observation_support_m"]
        )
        self.assertFalse(raster.empty)
        self.assertTrue((raster["support_m"] >= raster["observation_support_m"]).all())

    def test_interior_point_has_full_coverage(self) -> None:
        # Guards the window-rounding bug that reported 0.21 for a 300 m buffer.
        interior = self._rows("pm25").dropna(subset=["coverage_fraction"])
        self.assertTrue((interior["coverage_fraction"] > 0.99).all())

    def test_chile_only_indicator_is_absent_elsewhere(self) -> None:
        lima = extract_points(
            pd.DataFrame([{"query_id": "lima", "lon": -77.03, "lat": -12.05}]),
            ["nse"], radii=[0], data_root=REAL_BUNDLE,
        )
        self.assertEqual(lima["quality_flag"].iloc[0], FLAG_NOT_PUBLISHED)


if __name__ == "__main__":
    unittest.main()

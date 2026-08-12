"""Contracts for the extraction bundle: manifest, checkpoints and the pivot."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from exposome.point_artifacts import (
    LONG_CSV,
    MANIFEST,
    METHOD_VERSION,
    METHODOLOGY,
    WIDE_CSV,
    extraction_plan,
    run_extraction,
    sha256_file,
    to_wide,
)

ARTIFACTS = os.environ.get("EXPOSOME_RUN_ARTIFACT_TESTS") == "1"
REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_BUNDLE = REPO_ROOT / "webapp" / "public" / "data"

POINTS = pd.DataFrame([
    {"query_id": "santiago", "lon": -70.65, "lat": -33.45},
    {"query_id": "lima", "lon": -77.03, "lat": -12.05},
    {"query_id": "ocean", "lon": -90.0, "lat": -40.0},
])


class ToWideTest(unittest.TestCase):
    FRAME = pd.DataFrame([
        {"query_id": "a", "lon": 1.0, "lat": 2.0, "study_id": "s",
         "exposome_id": "pm25", "radius_m": 0.0, "year": None, "value": 10.0},
        {"query_id": "a", "lon": 1.0, "lat": 2.0, "study_id": "s",
         "exposome_id": "pm25", "radius_m": 1000.0, "year": None, "value": 11.0},
        {"query_id": "a", "lon": 1.0, "lat": 2.0, "study_id": "s",
         "exposome_id": "nse", "radius_m": None, "year": None, "value": 1.5},
    ])

    def test_pivot_selects_one_radius(self) -> None:
        wide = to_wide(self.FRAME, radius_m=1000.0)
        self.assertEqual(len(wide), 1)
        self.assertEqual(wide["pm25"].iloc[0], 11.0)

    def test_radius_free_rows_are_carried_into_every_slice(self) -> None:
        # An administrative value has no radius, so it belongs in each pivot.
        wide = to_wide(self.FRAME, radius_m=0.0)
        self.assertEqual(wide["pm25"].iloc[0], 10.0)
        self.assertEqual(wide["nse"].iloc[0], 1.5)

    def test_empty_input_gives_empty_output(self) -> None:
        self.assertTrue(to_wide(pd.DataFrame()).empty)


@unittest.skipUnless(ARTIFACTS, "set EXPOSOME_RUN_ARTIFACT_TESTS=1")
class BundleTest(unittest.TestCase):
    """End-to-end write against the real published bundle.  No network."""

    @classmethod
    def setUpClass(cls) -> None:
        if not (REAL_BUNDLE / "catalog.json").exists():
            raise unittest.SkipTest("no published bundle on disk")

    def _run(self, tmp: Path, **kwargs):
        return run_extraction(
            POINTS, ["pm25", "nse"], output_dir=tmp / "out",
            radii=[0, 1000], data_root=REAL_BUNDLE, repo_root=REPO_ROOT, **kwargs
        )

    def test_writes_the_four_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._run(Path(tmp), wide_radius=1000.0)
            out = Path(tmp) / "out"
            for name in (LONG_CSV, WIDE_CSV, MANIFEST, METHODOLOGY):
                with self.subTest(artifact=name):
                    self.assertTrue((out / name).exists())

    def test_manifest_digests_match_the_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(Path(tmp))
            manifest = json.loads(Path(result["manifest"]).read_text())
            out = Path(tmp) / "out"
            self.assertEqual(manifest["method_version"], METHOD_VERSION)
            for entry in manifest["outputs"]:
                with self.subTest(path=entry["path"]):
                    self.assertEqual(sha256_file(out / entry["path"]), entry["sha256"])

    def test_manifest_pins_the_source_bundles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(Path(tmp))
            manifest = json.loads(Path(result["manifest"]).read_text())
            studies = manifest["source"]["studies"]
            self.assertTrue(studies)
            for study in studies:
                with self.subTest(study=study["study_id"]):
                    self.assertIsNotNone(study["release_manifest_sha256"])

    def test_manifest_states_the_estimand(self) -> None:
        # A downloaded table must carry what its numbers mean.
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(Path(tmp))
            manifest = json.loads(Path(result["manifest"]).read_text())
            self.assertIn("B(x, r)", manifest["estimand"])

    def test_checkpoints_are_reused_and_parameter_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "cache"
            first = self._run(Path(tmp), cache_dir=cache)
            self.assertEqual(first["reused_checkpoints"], 0)

            second = self._run(Path(tmp), cache_dir=cache)
            self.assertEqual(second["reused_checkpoints"], len(POINTS))

            # A different radius set is a different question, so the cache key
            # must change (ADR 0005: cache identity includes the parameters).
            third = run_extraction(
                POINTS, ["pm25", "nse"], output_dir=Path(tmp) / "out",
                radii=[0, 500], data_root=REAL_BUNDLE, repo_root=REPO_ROOT,
                cache_dir=cache,
            )
            self.assertEqual(third["reused_checkpoints"], 0)

    def test_plan_reports_sub_observation_without_reading_pixels(self) -> None:
        plan = extraction_plan(POINTS, ["no2", "canopy"], [0, 300, 1000],
                               data_root=REAL_BUNDLE)
        no2 = plan[plan["exposome_id"] == "no2"]
        self.assertTrue((no2["radius_status"] == "sub_observation").all())
        canopy = plan[(plan["exposome_id"] == "canopy") & (plan["radius_m"] == 300)]
        self.assertTrue((canopy["radius_status"] == "resolved").all())

    def test_plan_reports_the_declared_unavailability_reason(self) -> None:
        # nse is Chile-only; Lima's manifest says country_not_supported.
        plan = extraction_plan(POINTS, ["nse"], [0], data_root=REAL_BUNDLE)
        lima = plan[plan["study_id"] == "lima_distritos"]
        self.assertEqual(lima["availability"].iloc[0], "country_not_supported")


if __name__ == "__main__":
    unittest.main()

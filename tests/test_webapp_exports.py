"""Tests for the 4 webapp export scripts.

Verifies that each export script produces the expected output
artefacts with the right shape, file count, and data integrity.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
SCRIPTS = REPO_ROOT / "scripts"
WEBAPP_DATA = REPO_ROOT / "webapp" / "public" / "data"
PROFILES_DIR = WEBAPP_DATA / "profiles"
METHODOLOGY_DIR = WEBAPP_DATA / "methodology"
SUBCOMUNA_DIR = WEBAPP_DATA / "subcomuna"


def _run(script_name: str) -> None:
    """Run a script as a subprocess and assert it succeeds."""
    script = SCRIPTS / script_name
    if not script.exists():
        raise FileNotFoundError(f"Script not found: {script}")
    res = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"{script_name} failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"
        )


class WebappExportsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Re-run all 4 export scripts to ensure outputs are fresh.
        _run("export_webapp_master.py")
        _run("export_webapp_profiles.py")
        _run("export_webapp_sources.py")
        _run("export_webapp_methodology.py")
        _run("export_webapp_zipcodes.py")

    def test_master_geojson_exists_and_is_slim(self) -> None:
        """master.geojson must exist, have 52 features, < 1 MB."""
        path = WEBAPP_DATA / "master.geojson"
        self.assertTrue(path.exists(), f"missing: {path}")
        size_kb = path.stat().st_size / 1024
        self.assertLess(
            size_kb, 1024,
            f"master.geojson is {size_kb:.1f} KB, expected < 1 MB",
        )
        with open(path) as f:
            data = json.load(f)
        self.assertEqual(data["type"], "FeatureCollection")
        self.assertEqual(
            len(data["features"]), 52,
            f"master has {len(data['features'])} features, expected 52",
        )

    def test_master_geojson_has_slug_and_pm25(self) -> None:
        """Each feature must have a slug + pm25_mean property."""
        with open(WEBAPP_DATA / "master.geojson") as f:
            data = json.load(f)
        for f in data["features"]:
            props = f["properties"]
            self.assertIn("slug", props, "feature missing slug")
            self.assertIn("pm25_mean", props, "feature missing pm25_mean")
            self.assertIn("social_index", props, "feature missing social_index")
            self.assertIn("noise_combined_pct", props, "feature missing noise_combined_pct")
            self.assertIn("noise_in_gsu_map", props, "feature missing noise_in_gsu_map")
            self.assertIsInstance(
                props["slug"], str,
                f"slug must be string, got {type(props['slug'])}",
            )
            self.assertGreater(
                len(props["slug"]), 0,
                "slug must be non-empty",
            )

    def test_profiles_count_is_52(self) -> None:
        """There must be exactly 52 profile files."""
        profiles = list(PROFILES_DIR.glob("*.json"))
        self.assertEqual(
            len(profiles), 52,
            f"found {len(profiles)} profiles, expected 52",
        )

    def test_profile_schema(self) -> None:
        """Each profile must have the expected keys + numeric indicators."""
        profiles = list(PROFILES_DIR.glob("*.json"))
        sample = json.loads(profiles[0].read_text())
        for key in (
            "name", "slug", "cluster", "lisa_quadrant",
            "nse_quintil", "indicators", "ebi", "neuro_outcomes",
        ):
            self.assertIn(key, sample, f"profile missing {key!r}")
        self.assertIsInstance(sample["indicators"], dict)
        self.assertGreater(
            len(sample["indicators"]), 50,
            f"only {len(sample['indicators'])} indicators, expected 50+",
        )
        for profile in profiles:
            data = json.loads(profile.read_text())
            indicators = data["indicators"]
            self.assertIn("social_index", indicators, f"{profile.name} missing social_index")
            self.assertIn("noise_combined_pct", indicators, f"{profile.name} missing noise_combined_pct")
            self.assertIn("noise_in_gsu_map", indicators, f"{profile.name} missing noise_in_gsu_map")

    def test_sources_json_has_six_entries(self) -> None:
        """sources.json must have at least the 6 v0.5 entries."""
        path = WEBAPP_DATA / "sources.json"
        self.assertTrue(path.exists(), f"missing: {path}")
        with open(path) as f:
            data = json.load(f)
        for key in (
            "pm25",
            "no2",
            "alan",
            "heat",
            "green",
            "ebi",
            "nse",
            "social_infrastructure",
            "noise",
        ):
            self.assertIn(key, data, f"sources.json missing {key!r}")
        # pm25 is primary for v0.5
        self.assertTrue(data["pm25"].get("primary", False))
        self.assertIn("CASEN", data["nse"]["name"])
        self.assertEqual(data["nse"]["spatial_resolution"], "1 commune = 1 value")
        self.assertIn("OpenStreetMap", data["social_infrastructure"]["name"])
        self.assertEqual(
            data["social_infrastructure"]["spatial_resolution"],
            "1 commune = 1 value",
        )
        self.assertIn("MMA", data["noise"]["name"])
        self.assertIn("GSU", data["noise"]["spatial_resolution"])
        self.assertIn("noise_in_gsu_map", data["noise"]["coverage_note"])

    def test_zipcodes_json_is_explicit_about_reference_status(self) -> None:
        path = WEBAPP_DATA / "zipcodes.json"
        self.assertTrue(path.exists(), f"missing: {path}")
        data = json.loads(path.read_text())
        self.assertIn(data["status"], ("ready", "missing_reference"))
        self.assertIn("records", data)
        self.assertIsInstance(data["records"], list)
        if data["status"] == "missing_reference":
            self.assertEqual(data["records"], [])
            self.assertIn("postal", data.get("message", ""))
        else:
            sample = data["records"][0]
            for key in ("zipcode", "lat", "lon", "commune_slug"):
                self.assertIn(key, sample)

    def test_methodology_files_present(self) -> None:
        """All 6 methodology files must be present."""
        for expo in (
            "pm25",
            "no2",
            "alan",
            "heat",
            "green",
            "ebi",
            "nse",
            "social_infrastructure",
            "noise",
        ):
            path = METHODOLOGY_DIR / f"{expo}.json"
            self.assertTrue(path.exists(), f"missing methodology: {path}")
            data = json.loads(path.read_text())
            self.assertIn("sections", data, f"{expo}.json missing sections")
            self.assertGreater(
                len(data["sections"]), 1,
                f"{expo}.json has only {len(data['sections'])} sections",
            )

    def test_pm25_methodology_contains_key_concepts(self) -> None:
        """PM2.5 methodology should mention ACAG or PM2.5 in raw text."""
        path = METHODOLOGY_DIR / "pm25.json"
        data = json.loads(path.read_text())
        raw_lower = data.get("raw", "").lower()
        self.assertTrue(
            "pm2.5" in raw_lower or "pm25" in raw_lower,
            "pm25 methodology must mention PM2.5",
        )

    def test_alan_subcomuna_file_is_real(self) -> None:
        path = SUBCOMUNA_DIR / "alan.geojson"
        self.assertTrue(path.exists(), f"missing: {path}")
        data = json.loads(path.read_text())
        self.assertEqual(data.get("exposome"), "alan")
        self.assertFalse(data.get("is_synthetic", True))
        self.assertGreater(len(data.get("features", [])), 1000)
        self.assertEqual(data.get("grid_alignment"), "native_lonlat_rectangles")
        self.assertGreater(data.get("pixel_width_deg", 0), 0.001)
        self.assertGreater(data.get("pixel_height_deg", 0), 0.001)

    def test_alan_subcomuna_features_have_pixel_ids_and_rectangles(self) -> None:
        data = json.loads((SUBCOMUNA_DIR / "alan.geojson").read_text())
        for feature in data["features"][:250]:
            props = feature["properties"]
            self.assertIn("pixel_id", props)
            ring = feature["geometry"]["coordinates"][0]
            self.assertEqual(len(ring), 5)
            xs = sorted({round(pt[0], 5) for pt in ring[:-1]})
            ys = sorted({round(pt[1], 5) for pt in ring[:-1]})
            self.assertEqual(len(xs), 2, f"expected rectangle x coords, got {xs}")
            self.assertEqual(len(ys), 2, f"expected rectangle y coords, got {ys}")
            self.assertEqual(ring[0], ring[-1], "polygon ring must be closed")


if __name__ == "__main__":
    unittest.main()

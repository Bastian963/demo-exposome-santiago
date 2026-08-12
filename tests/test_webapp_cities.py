"""Tests for the cities.json export script and webapp data structure."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
WEBAPP_DATA = REPO_ROOT / "webapp" / "public" / "data"
CITIES_JSON = WEBAPP_DATA / "cities.json"
CATALOG_JSON = WEBAPP_DATA / "catalog.json"


def _run(script_name: str) -> None:
    res = subprocess.run(
        [sys.executable, str(SCRIPTS / script_name)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"{script_name} failed:\n{res.stdout}\n{res.stderr}"
        )


class CitiesJsonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _run("export_webapp_cities.py")
        with open(CITIES_JSON) as f:
            cls.data = json.load(f)
        with open(CATALOG_JSON) as f:
            cls.catalog = json.load(f)

    def test_cities_file_exists(self) -> None:
        self.assertTrue(CITIES_JSON.exists(), f"missing: {CITIES_JSON}")

    def test_cities_has_at_least_1(self) -> None:
        self.assertGreaterEqual(
            len(self.data["cities"]), 1,
            f"only {len(self.data['cities'])} cities, expected >= 1",
        )

    def test_santiago_is_available(self) -> None:
        """Santiago must be the available city in v0.5."""
        santiago = next(
            (c for c in self.data["cities"] if c["slug"] == "santiago"),
            None,
        )
        self.assertIsNotNone(santiago, "santiago missing")
        self.assertTrue(
            santiago["available"],
            "santiago must be available in v0.5",
        )
        self.assertEqual(santiago["n_communes"], 52)
        catalog_santiago = next(
            c for c in self.catalog["cities"] if c["slug"] == "santiago"
        )
        self.assertEqual(santiago["n_layers"], catalog_santiago["n_layers"])
        self.assertIsNone(santiago["n_indicators"])

    def test_all_listed_cities_are_available(self) -> None:
        """Every city shipped in the globe's list must have real data."""
        for city in self.data["cities"]:
            self.assertTrue(
                city["available"],
                f"{city['slug']} is listed but not available",
            )
            self.assertTrue(
                city["data_url"],
                f"{city['slug']} is available but has no data_url",
            )

    def test_default_center_latam(self) -> None:
        """default_center must be in LATAM region."""
        c = self.data["default_center"]
        self.assertGreater(c[0], -75)
        self.assertLess(c[0], -55)
        self.assertGreater(c[1], -40)
        self.assertLess(c[1], -10)

    def test_default_zoom_is_continental(self) -> None:
        """default_zoom should be 2-4 (continental view)."""
        z = self.data["default_zoom"]
        self.assertGreaterEqual(z, 2)
        self.assertLessEqual(z, 4)


if __name__ == "__main__":
    unittest.main()

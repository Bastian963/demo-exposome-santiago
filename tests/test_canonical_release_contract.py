"""Acceptance checks for a materialized canonical Santiago release."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.layers import load_layer_catalog  # noqa: E402
from exposome.studies import load_study  # noqa: E402
from exposome.verification import verify_release  # noqa: E402


@unittest.skipUnless(
    os.environ.get("EXPOSOME_RUN_ARTIFACT_TESTS") == "1",
    "requires EXPOSOME_RUN_ARTIFACT_TESTS=1 and a materialized Santiago release",
)
class CanonicalSantiagoReleaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.context = load_study("santiago_communes", repo_root_path=ROOT)
        cls.catalog = load_layer_catalog()
        cls.root = cls.context.paths.processed
        cls.master = pd.read_csv(cls.root / "master.csv", dtype={"spatial_id": str})

    def test_release_checksums_and_enabled_layer_manifests(self) -> None:
        result = verify_release(self.context)
        self.assertTrue(result.ok, result.issues)
        self.assertGreaterEqual(result.checked_assets, len(self.context.enabled_layers) * 2)
        for requested_id in self.context.enabled_layers:
            layer_id = self.catalog.resolve_id(requested_id)
            self.assertTrue((self.root / layer_id / "manifest.json").is_file(), layer_id)

    def test_master_has_stable_ids_and_compatibility_name(self) -> None:
        self.assertEqual(len(self.master), 52)
        self.assertTrue(self.master["spatial_id"].str.fullmatch(r"13\d{3}").all())
        self.assertFalse(self.master["spatial_id"].duplicated().any())
        self.assertEqual(self.master["name"].tolist(), self.master["spatial_name"].tolist())

    def test_catalogued_master_columns_are_integrated(self) -> None:
        for requested_id in self.context.enabled_layers:
            spec = self.catalog.get(requested_id)
            master = spec.master or {}
            if not master.get("include", False):
                continue
            expected = [master.get("rename", {}).get(column, column) for column in master.get("required_columns", ())]
            with self.subTest(layer=spec.id):
                self.assertTrue(set(expected).issubset(self.master.columns))


if __name__ == "__main__":
    unittest.main()

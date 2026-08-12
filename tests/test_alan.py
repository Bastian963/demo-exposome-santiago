from __future__ import annotations

import json
import sys
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import audit_exposome_status as audit  # noqa: E402
from exposome.alan import _annual_radiance_image, alan_cache_namespace  # noqa: E402
from exposome.config import load_config  # noqa: E402


class AlanContractTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = REPO_ROOT / "data" / "processed" / "santiago_alan_viirs_2024.csv"
        cls.meta_path = REPO_ROOT / "data" / "processed" / "santiago_alan_viirs_2024_metadata.json"
        cls.master_path = REPO_ROOT / "data" / "processed" / "santiago_exposome_master.csv"
        cls.df = pd.read_csv(cls.csv_path)
        cls.master = pd.read_csv(cls.master_path)
        cls.meta = json.loads(cls.meta_path.read_text(encoding="utf-8"))

    def test_config_uses_explicit_exclusive_annual_window(self) -> None:
        cfg = load_config("santiago")

        self.assertEqual(cfg["alan"]["start_date"], "2024-01-01")
        self.assertEqual(cfg["alan"]["end_date"], "2025-01-01")

    def test_master_builder_requires_population_weighted_alan(self) -> None:
        specs = audit.load_layer_specs()
        alan = next(spec for spec in specs if spec["name"] == "alan")

        self.assertIn("alan_radiance_pop_weighted", alan["columns"])
        self.assertNotIn("optional_columns", alan)

    def test_processed_output_is_complete_and_nonnegative(self) -> None:
        expected_columns = {
            "name",
            "area_km2",
            "alan_radiance_mean",
            "alan_radiance_median",
            "alan_radiance_sd",
            "alan_radiance_max",
            "alan_radiance_pop_weighted",
        }

        self.assertEqual(len(self.df), 52)
        self.assertEqual(set(self.df.columns), expected_columns)
        self.assertEqual(self.df["name"].nunique(), 52)
        self.assertFalse(self.df.isna().any().any())
        self.assertTrue((self.df["alan_radiance_mean"] >= 0).all())
        self.assertTrue((self.df["alan_radiance_median"] >= 0).all())
        self.assertTrue((self.df["alan_radiance_sd"] >= 0).all())
        self.assertTrue((self.df["alan_radiance_max"] >= 0).all())
        self.assertTrue((self.df["alan_radiance_pop_weighted"] >= 0).all())

    def test_metadata_documents_window_cache_and_population_source(self) -> None:
        self.assertEqual(self.meta["year"], 2024)
        self.assertEqual(self.meta["start_date"], "2024-01-01")
        self.assertEqual(self.meta["end_date_exclusive"], "2025-01-01")
        self.assertEqual(self.meta["units"], "nW/cm^2/sr")
        self.assertEqual(self.meta["sources"]["viirs_dnb"]["cloud_free_band"], "cf_cvg")
        self.assertEqual(self.meta["sources"]["population"]["resolution_m"], 100)
        self.assertIn("radiance_stats", self.meta["cache_files"])
        self.assertIn("population_weighted", self.meta["cache_files"])
        self.assertEqual(self.meta["population_weighted_fallback"]["fallback_metric"], "alan_radiance_mean")

    def test_master_contains_identical_alan_columns(self) -> None:
        alan_cols = [
            "alan_radiance_mean",
            "alan_radiance_median",
            "alan_radiance_sd",
            "alan_radiance_max",
            "alan_radiance_pop_weighted",
        ]
        merged = self.master[["name", *alan_cols]].merge(
            self.df[["name", *alan_cols]],
            on="name",
            how="outer",
            suffixes=("_master", "_layer"),
            indicator=True,
        )

        merge_counts = merged["_merge"].value_counts().to_dict()
        self.assertEqual(merge_counts.get("both"), 52)
        self.assertEqual(merge_counts.get("left_only", 0), 0)
        self.assertEqual(merge_counts.get("right_only", 0), 0)
        for col in alan_cols:
            diff = (merged[f"{col}_master"] - merged[f"{col}_layer"]).abs().max()
            self.assertEqual(diff, 0.0, msg=col)


class AlanCacheNamespaceTest(unittest.TestCase):
    def test_annual_composite_preserves_monthly_viirs_projection(self) -> None:
        collection = MagicMock()
        first = MagicMock()
        source_band = MagicMock()
        projection = MagicMock()
        mean = MagicMock()
        projected = MagicMock()
        result = MagicMock()
        collection.filterDate.return_value = collection
        collection.select.return_value.mean.return_value = mean
        collection.first.return_value = first
        source_band.projection.return_value = projection
        mean.setDefaultProjection.return_value = projected
        projected.rename.return_value.max.return_value = result
        with patch("exposome.alan.ee") as ee_mock:
            ee_mock.ImageCollection.return_value = collection
            ee_mock.Image.return_value.select.return_value = source_band
            actual = _annual_radiance_image(
                {
                    "alan": {
                        "collection": {
                            "id": "NOAA/VIIRS/DNB/MONTHLY_V1/VCMSLCFG",
                            "band": "avg_rad",
                        }
                    }
                },
                "2024-01-01",
                "2025-01-01",
            )
        self.assertIs(actual, result)
        mean.setDefaultProjection.assert_called_once_with(projection)

    def test_namespace_changes_when_collection_scale_changes(self) -> None:
        cfg = load_config("lima_distritos")["alan"]
        current = alan_cache_namespace(cfg)
        legacy = json.loads(json.dumps(cfg))
        legacy["collection"]["scale_meters"] = 500
        self.assertNotEqual(current, alan_cache_namespace(legacy))

    def test_namespace_is_stable_for_equivalent_settings(self) -> None:
        cfg = load_config("medellin_comunas")["alan"]
        self.assertEqual(alan_cache_namespace(cfg), alan_cache_namespace(dict(cfg)))


if __name__ == "__main__":
    unittest.main()

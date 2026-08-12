from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from exposome.cache import CacheIdentity, CacheStore, spatial_fingerprint


def _identity(**updates: object) -> CacheIdentity:
    values = {
        "layer_id": "pm25",
        "operation": "area_mean",
        "parameters": {"collection": "acag-v6", "scale": 1113, "years": [2020]},
        "spatial_fingerprint": "spatial-a",
        "algorithm_version": "1",
    }
    values.update(updates)
    return CacheIdentity(**values)  # type: ignore[arg-type]


class CacheIdentityTests(unittest.TestCase):
    def test_mapping_order_does_not_change_digest(self) -> None:
        left = _identity(parameters={"band": "pm25", "scale": 1113})
        right = _identity(parameters={"scale": 1113, "band": "pm25"})
        self.assertEqual(left.digest, right.digest)

    def test_material_parameter_changes_digest(self) -> None:
        left = _identity(parameters={"scale": 1113})
        right = _identity(parameters={"scale": 1000})
        self.assertNotEqual(left.digest, right.digest)

    def test_spatial_change_changes_digest(self) -> None:
        self.assertNotEqual(
            _identity(spatial_fingerprint="a").digest,
            _identity(spatial_fingerprint="b").digest,
        )

    def test_spatial_fingerprint_is_order_stable_and_geometry_sensitive(self) -> None:
        frame = gpd.GeoDataFrame(
            {"spatial_id": ["b", "a"]},
            geometry=[Point(2, 2), Point(1, 1)],
            crs="EPSG:4326",
        )
        reordered = frame.iloc[::-1].reset_index(drop=True)
        changed = frame.copy()
        changed.loc[changed["spatial_id"] == "a", "geometry"] = Point(1.1, 1)
        self.assertEqual(spatial_fingerprint(frame), spatial_fingerprint(reordered))
        self.assertNotEqual(spatial_fingerprint(frame), spatial_fingerprint(changed))


class CacheStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = CacheStore(self.root, _identity())
        self.frame = pd.DataFrame({"spatial_id": ["a", "b"], "value": [1.0, 2.0]})

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_complete_entry_round_trips_with_validation(self) -> None:
        written = self.store.write_csv_atomic("annual", self.frame, completed_keys=["2020"])
        loaded = self.store.load_csv(
            "annual",
            required_columns=["spatial_id", "value"],
            expected_completed_keys=["2020"],
        )
        self.assertTrue(written.hit)
        self.assertTrue(loaded.hit)
        pd.testing.assert_frame_equal(loaded.frame, self.frame)

    def test_missing_sidecar_is_a_cache_miss(self) -> None:
        record = self.store.load_csv("annual")
        self.assertFalse(record.hit)
        self.assertEqual(record.reason, "sidecar missing")

    def test_tampered_data_is_a_cache_miss(self) -> None:
        written = self.store.write_csv_atomic("annual", self.frame)
        assert written.data_path is not None
        written.data_path.write_text("spatial_id,value\na,99\n", encoding="utf-8")
        record = self.store.load_csv("annual")
        self.assertFalse(record.hit)
        self.assertIn("mismatch", record.reason)

    def test_required_columns_are_validated_before_read(self) -> None:
        self.store.write_csv_atomic("annual", self.frame)
        record = self.store.load_csv("annual", required_columns=["missing"])
        self.assertFalse(record.hit)
        self.assertIn("required columns missing", record.reason)

    def test_partial_checkpoint_is_resumable_but_not_complete(self) -> None:
        self.store.checkpoint_csv("daily", self.frame, completed_keys=["01", "02"])
        complete = self.store.load_csv("daily")
        checkpoint = self.store.load_checkpoint_csv("daily")
        self.assertFalse(complete.hit)
        self.assertEqual(complete.reason, "cache entry is partial")
        self.assertTrue(checkpoint.hit)
        self.assertEqual(checkpoint.completed_keys, ("01", "02"))

    def test_other_identity_cannot_read_checkpoint(self) -> None:
        self.store.checkpoint_csv("daily", self.frame, completed_keys=["01"])
        other = CacheStore(self.root, _identity(parameters={"scale": 1000}))
        self.assertFalse(other.load_checkpoint_csv("daily").hit)

    def test_failed_sidecar_publish_keeps_previous_generation_valid(self) -> None:
        first = self.store.write_csv_atomic("annual", self.frame)
        replacement = pd.DataFrame({"spatial_id": ["a"], "value": [7.0]})
        with patch("exposome.cache._atomic_json", side_effect=OSError("simulated")):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.store.write_csv_atomic("annual", replacement)
        loaded = self.store.load_csv("annual")
        self.assertTrue(loaded.hit)
        self.assertEqual(loaded.data_path, first.data_path)
        pd.testing.assert_frame_equal(loaded.frame, self.frame)

    def test_sidecar_identity_payload_is_persisted(self) -> None:
        written = self.store.write_csv_atomic("annual", self.frame)
        payload = json.loads(written.sidecar_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["identity"], self.store.identity.payload)
        self.assertEqual(payload["identity_digest"], self.store.identity.digest)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from exposome.raw_sources import (
    RawSnapshotStore,
    build_raw_source_asset,
    load_source_manifest,
    write_source_manifest,
)
from exposome.heavy_metals import resolve_retc_source_files
from scripts.migrations.migrate_retc_raw import inventory_retc, migrate_retc


class RawSourceManifestTests(unittest.TestCase):
    def test_manifest_roundtrip_and_idempotency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "retc_efp_2020.csv"
            source.write_text("a,b\n1,2\n", encoding="utf-8")
            asset = build_raw_source_asset(
                root,
                source,
                url="https://example.test/retc.csv",
                resource_id="resource-1",
                year=2020,
            )
            first = write_source_manifest(
                root,
                provider="mma",
                dataset="retc-air-point-sources",
                version="snapshot-a",
                license_name="CC-BY",
                assets=[asset],
            )
            second = write_source_manifest(
                root,
                provider="mma",
                dataset="retc-air-point-sources",
                version="snapshot-a",
                license_name="CC-BY",
                assets=[asset],
            )
            snapshot = load_source_manifest(root)
            self.assertEqual(first, second)
            self.assertEqual(snapshot.assets[0].year, 2020)

    def test_manifest_refuses_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "retc.csv"
            source.write_text("old", encoding="utf-8")
            first = build_raw_source_asset(root, source, url="https://example.test", year=2020)
            write_source_manifest(
                root,
                provider="mma",
                dataset="retc",
                version="v1",
                license_name="CC-BY",
                assets=[first],
            )
            source.write_text("new", encoding="utf-8")
            second = build_raw_source_asset(root, source, url="https://example.test", year=2020)
            with self.assertRaisesRegex(ValueError, "Refusing to mutate"):
                write_source_manifest(
                    root,
                    provider="mma",
                    dataset="retc",
                    version="v1",
                    license_name="CC-BY",
                    assets=[second],
                )

    def test_tampered_asset_fails_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "retc.csv"
            source.write_text("old", encoding="utf-8")
            asset = build_raw_source_asset(root, source, url="https://example.test", year=2020)
            write_source_manifest(
                root,
                provider="mma",
                dataset="retc",
                version="v1",
                license_name="CC-BY",
                assets=[asset],
            )
            source.write_text("changed", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "mismatch"):
                load_source_manifest(root)

    def test_manifest_can_verify_payloads_on_an_external_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_root = root / "repo" / "data" / "raw" / "provider" / "dataset" / "v1"
            payload_root = root / "external" / "provider" / "dataset" / "v1"
            payload_root.mkdir(parents=True)
            source = payload_root / "payload.csv"
            source.write_text("a,b\n1,2\n", encoding="utf-8")
            asset = build_raw_source_asset(payload_root, source, url="https://example.test/payload")
            write_source_manifest(
                manifest_root,
                provider="provider",
                dataset="dataset",
                version="v1",
                license_name="CC-BY",
                assets=[asset],
                payload_root=payload_root,
            )
            store = RawSnapshotStore(manifest_root=manifest_root, payload_root=payload_root)
            snapshot = store.load()
            self.assertEqual(snapshot.asset_path(snapshot.assets[0]), source)
            source.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "mismatch"):
                store.load()


class RetcMigrationTests(unittest.TestCase):
    def test_inventory_rejects_disagreeing_copies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            (left / "retc_efp_2020.csv").write_text("left", encoding="utf-8")
            (right / "retc_efp_2020.csv").write_text("right", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "disagree"):
                inventory_retc([left, right], [2020])

    def test_dry_run_does_not_create_destination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "cache"
            source_root.mkdir()
            source = source_root / "retc_efp_2020.csv"
            source.write_text("a,b\n1,2\n", encoding="utf-8")
            destination = root / "raw"
            messages = migrate_retc(
                {2020: source}, destination, version="ckan-2026-06", write=False
            )
            self.assertFalse(destination.exists())
            self.assertTrue(any("WOULD COPY" in message for message in messages))

    def test_write_copies_and_manifests_without_deleting_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "cache"
            source_root.mkdir()
            source = source_root / "retc_efp_2020.csv"
            source.write_text("a,b\n1,2\n", encoding="utf-8")
            destination = root / "raw"
            migrate_retc({2020: source}, destination, version="ckan-2026-06", write=True)
            self.assertTrue(source.is_file())
            self.assertTrue((destination / source.name).is_file())
            manifest = json.loads(
                (destination / "source_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["assets"][0]["year"], 2020)


class RetcSourceResolutionTests(unittest.TestCase):
    def test_canonical_resolution_requires_and_verifies_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "retc_efp_2020.csv"
            source.write_text("a,b\n1,2\n", encoding="utf-8")
            asset = build_raw_source_asset(
                root,
                source,
                url="https://example.test/retc.csv",
                year=2020,
            )
            write_source_manifest(
                root,
                provider="mma",
                dataset="retc-air-point-sources",
                version="snapshot-a",
                license_name="CC-BY",
                assets=[asset],
            )
            resolved, snapshot = resolve_retc_source_files(root, [2020])
            self.assertEqual(resolved, {2020: source})
            self.assertIsNotNone(snapshot)

    def test_strict_resolution_does_not_scan_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "retc_efp_2020.csv").write_text("cached", encoding="utf-8")
            with self.assertRaisesRegex(FileNotFoundError, "manifest not found"):
                resolve_retc_source_files(root / "raw", [2020])

    def test_legacy_fallback_is_explicit_and_warns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "cache"
            cache.mkdir()
            source = cache / "retc_efp_2020.csv"
            source.write_text("cached", encoding="utf-8")
            with self.assertWarns(DeprecationWarning):
                resolved, snapshot = resolve_retc_source_files(
                    root / "raw",
                    [2020],
                    legacy_cache_dir=cache,
                )
            self.assertEqual(resolved, {2020: source})
            self.assertIsNone(snapshot)


if __name__ == "__main__":
    unittest.main()

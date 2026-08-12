from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from exposome.artifact_contract import load_layer_bundle, load_release, write_study_release
from exposome.artifacts import write_layer_manifest
from exposome.layers import load_layer_catalog
from exposome.settings import resolve_settings
from exposome.studies import load_study
from scripts.migrations.upgrade_artifact_manifests_v2 import upgrade_release


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class ManifestV2MigrationTests(unittest.TestCase):
    def test_explicit_rebind_accepts_a_stale_v2_release_settings_index(self) -> None:
        original = load_study("buenos_aires_comunas")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = replace(
                original,
                study=replace(original.study, enabled_layers=("pm25",)),
                paths=replace(original.paths, processed=root),
            )
            layer_dir = root / "air_quality_pm25"
            layer_dir.mkdir()
            table = layer_dir / "pm25.csv"
            table.write_text(
                "spatial_id,pm25_mean,pm25_pop_weighted,pm25_who_ratio\n1,10,11,2\n",
                encoding="utf-8",
            )
            write_layer_manifest(
                context,
                load_layer_catalog().get("pm25"),
                layer_dir,
                [table],
            )
            bundle = load_layer_bundle(context, "air_quality_pm25")
            master_csv = root / "master.csv"
            master_geo = root / "master.geojson"
            master_csv.write_text("spatial_id\n1\n", encoding="utf-8")
            master_geo.write_text(
                json.dumps({"type": "FeatureCollection", "features": []}),
                encoding="utf-8",
            )
            release_path = write_study_release(
                context,
                [bundle],
                [("master_csv", master_csv), ("master_geojson", master_geo)],
                expected_layer_ids=("air_quality_pm25",),
            )
            payload = json.loads(release_path.read_text(encoding="utf-8"))
            payload["settings_fingerprint"] = "stale-after-config-change"
            release_path.write_text(json.dumps(payload), encoding="utf-8")

            messages = upgrade_release(
                context,
                write=True,
                allow_stale_settings=True,
            )
            migrated = load_release(
                context,
                expected_layer_ids=("air_quality_pm25",),
            )

            self.assertTrue(any("WRITE complete" in message for message in messages))
            self.assertEqual(
                migrated.settings_fingerprint,
                resolve_settings(context).fingerprint,
            )

    def test_verified_v1_release_upgrades_atomically(self) -> None:
        original = load_study("buenos_aires_comunas")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = replace(
                original,
                study=replace(original.study, enabled_layers=("pm25",)),
                paths=replace(original.paths, processed=root),
            )
            layer_dir = root / "air_quality_pm25"
            layer_dir.mkdir()
            table = layer_dir / "pm25.csv"
            table.write_text(
                "spatial_id,pm25_mean,pm25_pop_weighted,pm25_who_ratio\n"
                "1,10,11,2\n",
                encoding="utf-8",
            )
            layer_manifest = layer_dir / "manifest.json"
            layer_manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "layer_id": "air_quality_pm25",
                        "study_id": context.study.id,
                        "mode": "aggregate",
                        "assets": [
                            {
                                "path": table.name,
                                "role": "primary_table",
                                "bytes": table.stat().st_size,
                                "sha256": _sha(table),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            master_csv = root / "master.csv"
            master_geo = root / "master.geojson"
            master_csv.write_text("spatial_id\n1\n", encoding="utf-8")
            master_geo.write_text(
                json.dumps({"type": "FeatureCollection", "features": []}),
                encoding="utf-8",
            )
            release = root / "release_manifest.json"
            release.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "study_id": context.study.id,
                        "settings_fingerprint": resolve_settings(context).fingerprint,
                        "layers": [
                            {
                                "layer_id": "air_quality_pm25",
                                "path": "air_quality_pm25/manifest.json",
                                "sha256": _sha(layer_manifest),
                            }
                        ],
                        "master_assets": [
                            {
                                "role": "csv",
                                "path": "master.csv",
                                "bytes": master_csv.stat().st_size,
                                "sha256": _sha(master_csv),
                            },
                            {
                                "role": "geojson",
                                "path": "master.geojson",
                                "bytes": master_geo.stat().st_size,
                                "sha256": _sha(master_geo),
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            dry_run = upgrade_release(context, write=False)
            self.assertTrue(any("READY release" in message for message in dry_run))
            upgrade_release(context, write=True)
            migrated = load_release(
                context,
                expected_layer_ids=("air_quality_pm25",),
            )

            self.assertEqual(migrated.study_id, context.study.id)
            self.assertTrue((root / "release_manifest.v1.json").is_file())
            self.assertTrue((layer_dir / "manifest.v1.json").is_file())

    def test_mixed_recovery_can_retain_a_verified_v2_layer(self) -> None:
        original = load_study("buenos_aires_comunas")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = replace(
                original,
                study=replace(original.study, enabled_layers=("pm25",)),
                paths=replace(original.paths, processed=root),
            )
            layer_dir = root / "air_quality_pm25"
            layer_dir.mkdir()
            table = layer_dir / "pm25.csv"
            table.write_text(
                "spatial_id,pm25_mean,pm25_pop_weighted,pm25_who_ratio\n1,10,11,2\n",
                encoding="utf-8",
            )
            write_layer_manifest(context, load_layer_catalog().get("pm25"), layer_dir, [table])
            master_csv = root / "master.csv"
            master_geo = root / "master.geojson"
            master_csv.write_text("spatial_id\n1\n", encoding="utf-8")
            master_geo.write_text(
                json.dumps({"type": "FeatureCollection", "features": []}),
                encoding="utf-8",
            )
            release = root / "release_manifest.json"
            release.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "study_id": context.study.id,
                        "settings_fingerprint": "stale-after-partial-recovery",
                        "layers": [
                            {
                                "layer_id": "air_quality_pm25",
                                "path": "air_quality_pm25/manifest.json",
                                "sha256": "outdated-v1-reference",
                            }
                        ],
                        "master_assets": [
                            {"role": "csv", "path": "master.csv", "bytes": master_csv.stat().st_size, "sha256": _sha(master_csv)},
                            {"role": "geojson", "path": "master.geojson", "bytes": master_geo.stat().st_size, "sha256": _sha(master_geo)},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            messages = upgrade_release(context, write=True, allow_stale_settings=True)
            migrated = load_release(context, expected_layer_ids=("air_quality_pm25",))

            self.assertTrue(any(message.startswith("RETAIN v2") for message in messages))
            self.assertEqual(migrated.study_id, context.study.id)

    def test_explicit_recovery_accepts_a_stale_v1_release_index_but_checks_assets(self) -> None:
        original = load_study("buenos_aires_comunas")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = replace(
                original,
                study=replace(original.study, enabled_layers=("pm25",)),
                paths=replace(original.paths, processed=root),
            )
            layer_dir = root / "air_quality_pm25"
            layer_dir.mkdir()
            table = layer_dir / "pm25.csv"
            table.write_text(
                "spatial_id,pm25_mean,pm25_pop_weighted,pm25_who_ratio\n1,10,11,2\n",
                encoding="utf-8",
            )
            layer_manifest = layer_dir / "manifest.json"
            layer_manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "layer_id": "air_quality_pm25",
                        "study_id": context.study.id,
                        "mode": "aggregate",
                        "assets": [{"path": table.name, "role": "primary_table", "bytes": table.stat().st_size, "sha256": _sha(table)}],
                    }
                ),
                encoding="utf-8",
            )
            master_csv = root / "master.csv"
            master_geo = root / "master.geojson"
            master_csv.write_text("spatial_id\n1\n", encoding="utf-8")
            master_geo.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
            (root / "release_manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "study_id": context.study.id,
                        "settings_fingerprint": "stale-after-partial-recovery",
                        "layers": [{"layer_id": "air_quality_pm25", "path": "air_quality_pm25/manifest.json", "sha256": "stale-index"}],
                        "master_assets": [
                            {"role": "csv", "path": "master.csv", "bytes": master_csv.stat().st_size, "sha256": "stale-index"},
                            {"role": "geojson", "path": "master.geojson", "bytes": master_geo.stat().st_size, "sha256": "stale-index"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            upgrade_release(context, write=True, allow_stale_settings=True)
            migrated = load_release(context, expected_layer_ids=("air_quality_pm25",))

            self.assertEqual(migrated.study_id, context.study.id)


if __name__ == "__main__":
    unittest.main()

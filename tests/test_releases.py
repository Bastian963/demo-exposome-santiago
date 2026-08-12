from __future__ import annotations

from dataclasses import replace
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.artifacts import write_layer_manifest  # noqa: E402
from exposome.layers import load_layer_catalog  # noqa: E402
from exposome.releases import write_release_manifest  # noqa: E402
from exposome.studies import load_study  # noqa: E402
from exposome.verification import verify_release  # noqa: E402


def _isolated_context(processed: Path):
    original = load_study("buenos_aires_comunas", repo_root_path=ROOT)
    study = replace(original.study, enabled_layers=("pm25",))
    paths = replace(original.paths, processed=processed)
    return replace(original, study=study, paths=paths)


def _write_bundle_and_master(context):
    spec = load_layer_catalog().get("pm25")
    layer_dir = context.paths.layer_processed("air_quality_pm25")
    layer_dir.mkdir(parents=True)
    table = layer_dir / "pm25.csv"
    table.write_text(
        "spatial_id,pm25_mean,pm25_pop_weighted,pm25_who_ratio\n1,2,2,0.4\n",
        encoding="utf-8",
    )
    write_layer_manifest(context, spec, layer_dir, [table])
    master_csv = context.paths.processed / "master.csv"
    master_geojson = context.paths.processed / "master.geojson"
    master_csv.write_text("spatial_id,pm25_mean\n1,2\n", encoding="utf-8")
    master_geojson.write_text(
        json.dumps({"type": "FeatureCollection", "features": []}),
        encoding="utf-8",
    )
    master = SimpleNamespace(paths={"csv": master_csv, "geojson": master_geojson})
    return table, master


class ReleaseManifestTests(unittest.TestCase):
    def test_release_links_master_and_layer_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = _isolated_context(Path(tmp))
            _table, master = _write_bundle_and_master(context)
            path = write_release_manifest(context, master)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["study_id"], "buenos_aires_comunas")
        self.assertEqual(payload["layers"][0]["path"], "air_quality_pm25/manifest.json")
        roles = {asset["role"]: asset["path"] for asset in payload["assets"]}
        self.assertEqual(roles["master_csv"], "master.csv")
        self.assertEqual(roles["master_geojson"], "master.geojson")
        self.assertEqual(len(payload["settings_fingerprint"]), 64)

    def test_verification_detects_changed_layer_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = _isolated_context(Path(tmp))
            table, master = _write_bundle_and_master(context)
            write_release_manifest(context, master)

            verified = verify_release(context)
            self.assertTrue(verified.ok, verified.issues)
            self.assertEqual(verified.checked_assets, 4)

            table.write_text(
                "spatial_id,pm25_mean,pm25_pop_weighted,pm25_who_ratio\n1,999,2,0.4\n",
                encoding="utf-8",
            )
            tampered = verify_release(context)

        self.assertFalse(tampered.ok)
        self.assertTrue(any("mismatch" in issue for issue in tampered.issues))


if __name__ == "__main__":
    unittest.main()

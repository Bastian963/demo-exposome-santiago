from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from exposome.artifact_contract import (
    load_layer_bundle,
    load_release,
    write_layer_bundle_manifest,
    write_study_release,
)
from exposome.execution import LayerBuildResult, ProducedAsset
from exposome.studies import load_study


ROOT = Path(__file__).resolve().parents[1]


class ArtifactContractTests(unittest.TestCase):
    def _context(self, root: Path):
        context = load_study("buenos_aires_comunas", repo_root_path=ROOT)
        paths = replace(context.paths, processed=root)
        return replace(context, paths=paths)

    def _write_bundle(self, context, layer_id: str = "air_quality_pm25"):
        output = context.paths.layer_processed(layer_id)
        output.mkdir(parents=True)
        table = output / "pm25.csv"
        geometry = output / "pm25.geojson"
        table.write_text("spatial_id,pm25\n1,2\n", encoding="utf-8")
        geometry.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        spec = SimpleNamespace(
            id=layer_id,
            master={"include": True, "required_columns": ["pm25"]},
        )
        result = LayerBuildResult(
            (
                ProducedAsset(table, "primary_table"),
                ProducedAsset(geometry, "primary_geometry"),
            )
        )
        write_layer_bundle_manifest(
            context,
            spec,
            output,
            result,
            execution_fingerprint="fingerprint-a",
        )
        return spec, load_layer_bundle(context, layer_id, spec=spec)

    def test_layer_bundle_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = self._context(Path(tmp))
            _, bundle = self._write_bundle(context)
            self.assertEqual(bundle.layer_id, "air_quality_pm25")
            self.assertEqual(bundle.primary_table.name, "pm25.csv")

    def test_layer_bundle_rejects_stale_execution_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = self._context(Path(tmp))
            spec, _ = self._write_bundle(context)
            with self.assertRaisesRegex(ValueError, "stale"):
                load_layer_bundle(
                    context,
                    "air_quality_pm25",
                    spec=spec,
                    expected_execution_fingerprint="fingerprint-b",
                )

    def test_layer_bundle_rejects_unsafe_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = self._context(Path(tmp))
            spec, bundle = self._write_bundle(context)
            payload = json.loads(bundle.manifest_path.read_text(encoding="utf-8"))
            payload["assets"][0]["path"] = "../escape.csv"
            bundle.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                load_layer_bundle(context, "air_quality_pm25", spec=spec)

    def test_tampered_layer_asset_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = self._context(Path(tmp))
            spec, bundle = self._write_bundle(context)
            bundle.primary_table.write_text("spatial_id,pm25\n1,99\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "mismatch"):
                load_layer_bundle(context, "air_quality_pm25", spec=spec)

    def test_release_requires_exact_layer_set_and_roundtrips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = self._context(Path(tmp))
            spec, bundle = self._write_bundle(context)
            master_csv = context.paths.processed / "master.csv"
            master_geojson = context.paths.processed / "master.geojson"
            master_csv.write_text("spatial_id,pm25\n1,2\n", encoding="utf-8")
            master_geojson.write_text(
                '{"type":"FeatureCollection","features":[]}', encoding="utf-8"
            )
            write_study_release(
                context,
                [bundle],
                [("master_csv", master_csv), ("master_geojson", master_geojson)],
                expected_layer_ids=["air_quality_pm25"],
            )
            release = load_release(
                context,
                expected_layer_ids=["air_quality_pm25"],
                specs={"air_quality_pm25": spec},
            )
            self.assertEqual(set(release.layers), {"air_quality_pm25"})
            with self.assertRaisesRegex(ValueError, "exact enabled Layer set"):
                load_release(context, expected_layer_ids=["air_quality_pm25", "alan"])


if __name__ == "__main__":
    unittest.main()

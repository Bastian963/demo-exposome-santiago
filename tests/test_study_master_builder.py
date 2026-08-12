"""Focused tests for the study-level master builder."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from exposome.master import build_study_master, discover_layer_outputs  # noqa: E402


def _boundaries() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "postal_code": ["1000", "1001", "1002"],
            "label": ["Centro", "Norte", "Sur"],
        },
        geometry=[box(-58.5, -34.7, -58.4, -34.6),
                  box(-58.4, -34.7, -58.3, -34.6),
                  box(-58.5, -34.8, -58.4, -34.7)],
        crs="EPSG:4326",
    )


class StudyMasterBuilderTest(unittest.TestCase):
    def test_manifest_merge_writes_outputs_and_reports_partial_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pd.DataFrame(
                {"spatial_id": ["1000", "1001", "1002"], "pm25": [8.1, 9.2, 7.0]}
            ).to_csv(root / "pm25.csv", index=False)
            pd.DataFrame(
                {"spatial_id": ["1000", "1001", "9999"], "ndvi": [0.2, None, 0.9]}
            ).to_csv(root / "green.csv", index=False)
            (root / "pm25_metadata.json").write_text(
                json.dumps({"provider": "test satellite", "period": "2024"})
            )

            result = build_study_master(
                "buenos_aires_postal",
                boundaries=_boundaries(),
                id_column="postal_code",
                name_column="label",
                expected_units=3,
                layers_dir=root,
                output_dir=root / "master_output",
                layer_outputs={
                    "pm25": {
                        "path": "pm25.csv",
                        "metadata_path": "pm25_metadata.json",
                        "required_columns": ["pm25"],
                    },
                    "green": {
                        "path": "green.csv",
                        "columns": ["ndvi"],
                        "rename": {"ndvi": "ndvi_mean"},
                    },
                },
            )

            self.assertEqual(result.master["spatial_id"].tolist(), ["1000", "1001", "1002"])
            self.assertEqual(result.master["spatial_name"].tolist(), ["Centro", "Norte", "Sur"])
            self.assertEqual(result.master.loc[0, "pm25"], 8.1)
            self.assertIn("ndvi_mean", result.master.columns)
            green = result.coverage.set_index("layer_id").loc["green"]
            self.assertEqual(green["status"], "partial_with_extra_ids")
            self.assertEqual(green["matched_units"], 2)
            self.assertEqual(json.loads(green["missing_spatial_ids"]), ["1002"])
            self.assertEqual(json.loads(green["extra_spatial_ids"]), ["9999"])
            self.assertEqual(result.metadata["n_spatial_units"], 3)
            self.assertEqual(
                result.metadata["layers"][0]["source_metadata"]["provider"],
                "test satellite",
            )
            for path in result.paths.values():
                self.assertTrue(path.exists(), path)

            written = pd.read_csv(result.paths["csv"], dtype={"spatial_id": "string"})
            self.assertEqual(written.shape, result.master.shape)

    def test_study_context_does_not_discover_unmanifested_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layer_dir = root / "pm25"
            layer_dir.mkdir()
            pd.DataFrame(
                {"spatial_id": ["1000", "1001", "1002"], "pm25": [1.0, 2.0, 3.0]}
            ).to_csv(layer_dir / "pm25.csv", index=False)

            context = SimpleNamespace(
                repo_root=root,
                study=SimpleNamespace(
                    id="ba",
                    id_column="postal_code",
                    name_column="label",
                ),
                spatial_path=root / "unused.geojson",
                expected_units=3,
                enabled_layers=("pm25", "alan"),
                paths=SimpleNamespace(processed=root),
            )
            with self.assertRaisesRegex(ValueError, "does not discover CSVs"):
                build_study_master(
                    context,
                    boundaries=_boundaries(),
                    strict_required=False,
                    write=False,
                )

    def test_duplicate_spatial_ids_fail_before_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate.csv"
            pd.DataFrame(
                {"spatial_id": ["1000", "1000"], "value": [1, 2]}
            ).to_csv(path, index=False)

            with self.assertRaisesRegex(ValueError, "duplicate spatial IDs"):
                build_study_master(
                    "duplicate_test",
                    boundaries=_boundaries(),
                    id_column="postal_code",
                    name_column="label",
                    layer_outputs={"duplicate": path},
                    write=False,
                )

    def test_required_missing_output_fails_but_optional_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.csv"
            kwargs = {
                "boundaries": _boundaries(),
                "id_column": "postal_code",
                "name_column": "label",
                "write": False,
            }
            with self.assertRaisesRegex(FileNotFoundError, "Required layer"):
                build_study_master(
                    "required_test",
                    layer_outputs={"pm25": {"path": missing, "required": True}},
                    **kwargs,
                )

            result = build_study_master(
                "optional_test",
                layer_outputs={"pm25": {"path": missing, "required": False}},
                **kwargs,
            )
            self.assertEqual(result.coverage.loc[0, "status"], "missing_output")

    def test_catalog_manifest_rejects_layer_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layer_dir = root / "pm25"
            layer_dir.mkdir()
            optional_dir = root / "alan"
            optional_dir.mkdir()
            pd.DataFrame(
                {"spatial_id": ["1000", "1001", "1002"], "raw": [1, 2, 3]}
            ).to_csv(layer_dir / "pm25.csv", index=False)
            pd.DataFrame(
                {"spatial_id": ["1000", "1001", "1002"], "annual": [4, 5, 6]}
            ).to_csv(layer_dir / "pm25_annual.csv", index=False)
            diagnostics = layer_dir / "diagnostics"
            diagnostics.mkdir()
            pd.DataFrame(
                {"spatial_id": ["1000"], "raw": [99]}
            ).to_csv(diagnostics / "ranking.csv", index=False)

            with self.assertRaisesRegex(ValueError, "verified bundle manifest"):
                build_study_master(
                    "catalog_test",
                    boundaries=_boundaries(),
                    id_column="postal_code",
                    name_column="label",
                    layer_outputs={
                        "layers": {
                            "pm25": {
                                "path": layer_dir,
                                "master": {
                                    "include": True,
                                    "required_columns": ["raw"],
                                },
                            },
                        }
                    },
                    write=False,
                )

    def test_discovery_rejects_ambiguous_primary_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            layer_dir = Path(tmp) / "pm25"
            layer_dir.mkdir()
            for name in ("annual.csv", "chronic.csv"):
                pd.DataFrame(
                    {"spatial_id": ["1000"], "value": [1]}
                ).to_csv(layer_dir / name, index=False)
            with self.assertRaisesRegex(ValueError, "explicit layer manifest"):
                discover_layer_outputs(tmp, layer_ids=["pm25"])

    def test_legacy_script_reexports_new_api_without_replacing_build_master(self) -> None:
        import build_master_exposome as builder

        self.assertIs(builder.build_study_master, build_study_master)
        self.assertNotEqual(builder.build_master, builder.build_study_master)


if __name__ == "__main__":
    unittest.main()

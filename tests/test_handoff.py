from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from exposome.handoff import (
    HANDOFF_SCHEMA_VERSION,
    MANIFEST_NAME,
    export_handoff,
    import_handoff,
    validate_handoff,
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class HandoffTests(unittest.TestCase):
    def _handoff(
        self,
        root: Path,
        *,
        path: str = "data/processed/example.txt",
        value: bytes = b"ok",
        studies: list[dict[str, object]] | None = None,
        role: str = "test",
    ) -> Path:
        asset = root / path
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(value)
        payload = {
            "schema_version": HANDOFF_SCHEMA_VERSION,
            "handoff_id": "node/run",
            "studies": studies or [],
            "artifacts": [{"path": path, "role": role, "study_id": "example", "size_bytes": len(value), "sha256": _sha(value)}],
        }
        (root / MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")
        return root

    def test_import_stages_then_promotes_a_verified_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff = self._handoff(root / "handoff")
            repo = root / "repo"
            repo.mkdir()
            report = import_handoff(handoff=handoff, repo_root=repo, staging_root=root / "staging")
            self.assertEqual(report["accepted"], ["data/processed/example.txt"])
            self.assertFalse((repo / "data/processed/example.txt").exists())
            report = import_handoff(handoff=handoff, repo_root=repo, staging_root=root / "another", promote=True)
            self.assertEqual(report["promoted"], ["data/processed/example.txt"])
            self.assertEqual((repo / "data/processed/example.txt").read_bytes(), b"ok")

    def test_checksum_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handoff = self._handoff(Path(tmp) / "handoff")
            (handoff / "data/processed/example.txt").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                validate_handoff(handoff)

    def test_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "handoff"
            root.mkdir()
            (root / MANIFEST_NAME).write_text(json.dumps({
                "schema_version": HANDOFF_SCHEMA_VERSION,
                "handoff_id": "node/run",
                "artifacts": [{"path": "../secret", "size_bytes": 0, "sha256": "0"}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unsafe handoff path"):
                validate_handoff(root)

    def test_utc_run_identifier_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            handoff = self._handoff(Path(tmp) / "handoff")
            payload = json.loads((handoff / MANIFEST_NAME).read_text(encoding="utf-8"))
            payload["handoff_id"] = "node/20260813T165626Z-6bd13eb"
            (handoff / MANIFEST_NAME).write_text(json.dumps(payload), encoding="utf-8")
            validate_handoff(handoff)

    def test_content_collision_blocks_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff = self._handoff(root / "handoff")
            repo = root / "repo"
            target = repo / "data/processed/example.txt"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"different")
            with self.assertRaisesRegex(ValueError, "collisions"):
                import_handoff(handoff=handoff, repo_root=repo, staging_root=root / "staging", promote=True)

    def test_configuration_fingerprint_must_match_central_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            study = repo / "config/studies/example.yaml"
            location = repo / "config/locations/example.yaml"
            study.parent.mkdir(parents=True)
            location.parent.mkdir(parents=True)
            study.write_text("id: example\n", encoding="utf-8")
            location.write_text("id: example\n", encoding="utf-8")
            fingerprints = {
                "study": {"path": "config/studies/example.yaml", "sha256": _sha(study.read_bytes())},
                "location": {"path": "config/locations/example.yaml", "sha256": _sha(location.read_bytes())},
            }
            handoff = self._handoff(root / "handoff", studies=[{"study_id": "example", "configurations": fingerprints}])
            import_handoff(handoff=handoff, repo_root=repo, staging_root=root / "staging")
            study.write_text("id: changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Configuration mismatch"):
                import_handoff(handoff=handoff, repo_root=repo, staging_root=root / "other")

    def test_operation_summary_is_staged_but_never_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            handoff = self._handoff(
                root / "handoff", path="operations/summary.md", role="operation_summary"
            )
            repo = root / "repo"
            report = import_handoff(handoff=handoff, repo_root=repo, staging_root=root / "staging", promote=True)
            self.assertEqual(report["accepted"], [])
            self.assertFalse((repo / "operations/summary.md").exists())

    def test_export_freezes_verified_closure_with_default_utc_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            output = Path(tmp) / "handoffs"
            asset = root / "data/processed/co/example/example_urban/release.txt"
            study_config = root / "config/studies/example_urban.yaml"
            location_config = root / "config/locations/co/example.yaml"
            spatial = root / "data/reference/co/example/example_urban/spatial_units.geojson"
            for path, value in ((asset, "release"), (study_config, "id: example_urban\n"), (location_config, "id: example\n"), (spatial, "{}")):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value, encoding="utf-8")
            context = SimpleNamespace(
                repo_root=root,
                study=SimpleNamespace(id="example_urban", config_path=study_config, spatial_path=spatial, aoi_path=None),
                location=SimpleNamespace(config_path=location_config),
            )

            def fake_run(command, **_kwargs):
                stdout = "a" * 40 if "rev-parse" in command else "runner/multicity-2026-08-12"
                return SimpleNamespace(stdout=stdout + "\n")

            with (
                patch("exposome.handoff.load_study", return_value=context),
                patch("exposome.handoff._release_records", return_value=[(asset, "release_manifest")]),
                patch("exposome.handoff.canonical_enabled_layers", return_value=("wind",)),
                patch("exposome.handoff.subprocess.run", side_effect=fake_run),
            ):
                destination = export_handoff(
                    node_id="node", studies=["example_urban"], output_root=output, repo_root=root,
                )
            manifest = validate_handoff(destination)
            self.assertRegex(manifest["handoff_id"], r"^node/\d{8}T\d{6}Z-[a-f0-9]{8}$")
            self.assertEqual(manifest["studies"][0]["configurations"]["study"]["path"], "config/studies/example_urban.yaml")
            self.assertTrue((destination / "data/processed/co/example/example_urban/release.txt").is_file())


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from exposome.handoff import HANDOFF_SCHEMA_VERSION, MANIFEST_NAME, import_handoff, validate_handoff


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


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.gemma_handoff import create_handoff, import_handoff, inspect_handoff  # noqa: E402


class GemmaHandoffTests(unittest.TestCase):
    def _bundle(self, data: Path, *, value: str = "one") -> Path:
        bundle = data / "v1" / "br" / "sao_paulo" / "sao_paulo_distritos"
        bundle.mkdir(parents=True)
        (bundle / "manifest.json").write_text(json.dumps({"study_id": "sao_paulo_distritos"}), encoding="utf-8")
        (bundle / "master.csv").write_text(f"name,value\\nA,{value}\\n", encoding="utf-8")
        return bundle

    def test_package_inspect_and_import(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_data = root / "source-data"
            bundle = self._bundle(source_data)
            archive = root / "sao-paulo.tar"
            create_handoff(bundle, archive, data_root=source_data)
            handoff = inspect_handoff(archive)
            self.assertEqual(handoff["study_id"], "sao_paulo_distritos")
            destination_data = root / "gemma-data"
            result = import_handoff(archive, data_root=destination_data, repo_root=ROOT)
            self.assertTrue(result["installed"])
            self.assertTrue((destination_data / handoff["bundle"] / "master.csv").is_file())
            self.assertTrue((destination_data / "catalog.json").is_file())
            repeat = import_handoff(archive, data_root=destination_data, repo_root=ROOT)
            self.assertFalse(repeat["installed"])

    def test_refuses_corrupted_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_data = root / "source-data"
            archive = root / "bundle.tar"
            create_handoff(self._bundle(source_data), archive, data_root=source_data)
            corrupted = root / "corrupt.tar"
            with tarfile.open(archive) as original, tarfile.open(corrupted, "w") as target:
                for member in original.getmembers():
                    content = original.extractfile(member).read() if member.isfile() else None
                    if member.name == "bundle/master.csv":
                        content = b"tampered"
                        member.size = len(content)
                    target.addfile(member, io.BytesIO(content) if content is not None else None)
            with self.assertRaisesRegex(ValueError, "integrity check failed"):
                inspect_handoff(corrupted)

    def test_refuses_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "unsafe.tar"
            with tarfile.open(archive, "w") as target:
                payload = json.dumps({"schema_version": 1, "study_id": "x", "bundle": "v1/x/y/z", "files": []}).encode()
                info = tarfile.TarInfo("handoff.json")
                info.size = len(payload)
                target.addfile(info, io.BytesIO(payload))
                data = b"no"
                evil = tarfile.TarInfo("bundle/../../outside")
                evil.size = len(data)
                target.addfile(evil, io.BytesIO(data))
            with self.assertRaisesRegex(ValueError, "unsafe relative path"):
                inspect_handoff(archive)

    def test_refuses_different_existing_bundle_without_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_data = root / "source-data"
            archive = root / "bundle.tar"
            create_handoff(self._bundle(source_data, value="new"), archive, data_root=source_data)
            destination = root / "gemma-data"
            self._bundle(destination, value="old")
            with self.assertRaises(FileExistsError):
                import_handoff(archive, data_root=destination, repo_root=ROOT)
            result = import_handoff(archive, data_root=destination, repo_root=ROOT, replace=True)
            self.assertTrue(result["installed"])
            installed = destination / "v1" / "br" / "sao_paulo" / "sao_paulo_distritos" / "master.csv"
            self.assertIn("new", installed.read_text(encoding="utf-8"))

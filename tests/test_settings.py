from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome import config  # noqa: E402
from exposome.settings import resolve_settings  # noqa: E402
from exposome.studies import StudyConfigError, load_study  # noqa: E402


class ResolvedSettingsTests(unittest.TestCase):
    def test_buenos_aires_has_no_santiago_config_dependency(self) -> None:
        context = load_study("buenos_aires_comunas", repo_root_path=ROOT)
        self.assertIsNone(context.legacy_config)

        resolved = resolve_settings(context)
        self.assertEqual(resolved.country_code, "AR")
        self.assertIn("pm25", resolved.values)
        self.assertFalse(resolved.layer("healthcare")["official_source"]["enabled"])
        self.assertFalse(resolved.layer("wildfire")["official"]["enabled"])
        self.assertFalse(any("cities/santiago.yaml" in str(path) for path in resolved.sources))

    def test_study_loader_uses_resolved_layer_defaults(self) -> None:
        cfg = config.load_config("buenos_aires_comunas")
        self.assertEqual(cfg["country_code"], "AR")
        self.assertEqual(cfg["alan"]["population"]["country"], "ARG")
        self.assertFalse(cfg["healthcare"]["official_source"]["enabled"])

    def test_summer_is_derived_from_the_study_hemisphere(self) -> None:
        self.assertEqual(
            config.load_config("santiago_native")["climate"]["seasons"]["summer"],
            [12, 1, 2],
        )
        self.assertEqual(
            config.load_config("cdmx_native")["climate"]["seasons"]["summer"],
            [6, 7, 8],
        )

    def test_layer_schema_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            layers = root / "config" / "layers"
            layers.mkdir(parents=True)
            (layers / "pm25.yaml").write_text(
                "schema_version: 1\nid: pm25\nsettings: {}\nunknown: true\n",
                encoding="utf-8",
            )
            copied = ROOT / "config" / "countries"
            (root / "config" / "countries").mkdir()
            for source in copied.glob("*.yaml"):
                (root / "config" / "countries" / source.name).write_text(
                    source.read_text(encoding="utf-8"), encoding="utf-8"
                )
            context = load_study("buenos_aires_comunas", repo_root_path=ROOT)
            # Recreate the context only with a fake repo root; settings are the
            # object under test and need no filesystem mutation outside tmp.
            from dataclasses import replace

            with self.assertRaisesRegex(StudyConfigError, "unknown keys"):
                resolve_settings(replace(context, repo_root=root))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.layer_info import (  # noqa: E402
    build_bibtex,
    build_methodology_json,
    build_sources_entry,
    expand_aliases,
    format_paper,
    load_layer_info_registry,
    resolve_layer_info,
)
from exposome.studies import StudyConfigError  # noqa: E402


VALID_ENTRY = """\
schema_version: 1
layer_id: fake_layer
webapp_keys: [fake]
source:
  name: "Fake Provider"
  url: "https://example.org"
  license: "Open"
citation:
  authors: "Doe, Jane and others"
  year: 2020
  title: "A Fake Dataset"
  journal: "Fake Journal"
  doi: "10.1234/fake.1"
specs:
  spatial_resolution: "~1 km"
  temporal_coverage: "2015-2020"
  validation: "R2 > 0.9"
limitations:
  - "Registry limitation."
methodology_doc: docs/fake_methodology.md
countries:
  AR:
    source:
      name: "Fake Provider AR"
studies:
  fake_study:
    specs:
      temporal_coverage: "2018 only"
"""


class RegistryLoaderTests(unittest.TestCase):
    def _write_registry(self, tmp: Path, name: str = "fake_layer", body: str = VALID_ENTRY) -> Path:
        registry_dir = tmp / "config" / "layer_info"
        registry_dir.mkdir(parents=True, exist_ok=True)
        (registry_dir / f"{name}.yaml").write_text(body, encoding="utf-8")
        return tmp

    def test_loads_valid_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            registry = load_layer_info_registry(self._write_registry(Path(tmp)))
            self.assertIn("fake_layer", registry)
            self.assertEqual(registry["fake_layer"]["source"]["name"], "Fake Provider")

    def test_filename_must_match_layer_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write_registry(Path(tmp), name="wrong_name")
            with self.assertRaises(StudyConfigError):
                load_layer_info_registry(Path(tmp))

    def test_unknown_key_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write_registry(Path(tmp), body=VALID_ENTRY + "extra_key: 1\n")
            with self.assertRaises(StudyConfigError):
                load_layer_info_registry(Path(tmp))

    def test_malformed_doi_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write_registry(
                Path(tmp), body=VALID_ENTRY.replace("10.1234/fake.1", "not-a-doi")
            )
            with self.assertRaises(StudyConfigError):
                load_layer_info_registry(Path(tmp))

    def test_not_assigned_doi_status_is_valid_without_doi(self) -> None:
        body = VALID_ENTRY.replace('  doi: "10.1234/fake.1"\n', "  doi_status: not_assigned\n")
        with tempfile.TemporaryDirectory() as tmp:
            registry = load_layer_info_registry(self._write_registry(Path(tmp), body=body))
        self.assertEqual(
            registry["fake_layer"]["citation"]["doi_status"], "not_assigned"
        )

    def test_not_assigned_doi_status_conflicts_with_doi(self) -> None:
        body = VALID_ENTRY.replace(
            '  doi: "10.1234/fake.1"\n',
            '  doi: "10.1234/fake.1"\n  doi_status: not_assigned\n',
        )
        with tempfile.TemporaryDirectory() as tmp:
            self._write_registry(Path(tmp), body=body)
            with self.assertRaises(StudyConfigError):
                load_layer_info_registry(Path(tmp))

    def test_malformed_override_doi_rejected(self) -> None:
        body = VALID_ENTRY.replace(
            "    source:\n      name: \"Fake Provider AR\"\n",
            "    source:\n      name: \"Fake Provider AR\"\n    citation:\n      doi: bad\n",
        )
        with tempfile.TemporaryDirectory() as tmp:
            self._write_registry(Path(tmp), body=body)
            with self.assertRaises(StudyConfigError):
                load_layer_info_registry(Path(tmp))

    def test_real_registry_loads(self) -> None:
        registry = load_layer_info_registry(ROOT)
        self.assertGreaterEqual(len(registry), 30)
        self.assertEqual(
            registry["air_quality_pm25"]["citation"]["doi"], "10.1289/EHP7394"
        )


class PrecedenceMergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        registry_dir = tmp / "config" / "layer_info"
        registry_dir.mkdir(parents=True)
        (registry_dir / "fake_layer.yaml").write_text(VALID_ENTRY, encoding="utf-8")
        self.entry = load_layer_info_registry(tmp)["fake_layer"]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_default_resolution(self) -> None:
        info = resolve_layer_info(self.entry)
        self.assertEqual(info["source"]["name"], "Fake Provider")
        self.assertNotIn("countries", info)

    def test_country_override_wins(self) -> None:
        info = resolve_layer_info(self.entry, country_code="AR")
        self.assertEqual(info["source"]["name"], "Fake Provider AR")
        # untouched sibling fields survive the deep merge
        self.assertEqual(info["source"]["url"], "https://example.org")

    def test_study_override_wins_over_country(self) -> None:
        info = resolve_layer_info(self.entry, country_code="AR", study_id="fake_study")
        self.assertEqual(info["source"]["name"], "Fake Provider AR")
        self.assertEqual(info["specs"]["temporal_coverage"], "2018 only")


class BuildersTests(unittest.TestCase):
    CITATION = {
        "authors": "Doe, Jane and others",
        "year": 2020,
        "title": "A Fake Dataset",
        "journal": "Fake Journal",
        "doi": "10.1234/fake.1",
    }

    def test_format_paper_composes_reference(self) -> None:
        self.assertEqual(format_paper(self.CITATION), "Doe et al. (2020) Fake Journal")

    def test_explicit_paper_wins(self) -> None:
        citation = dict(self.CITATION, paper="Custom reference string")
        self.assertEqual(format_paper(citation), "Custom reference string")

    def test_bibtex_contains_all_fields(self) -> None:
        bibtex = build_bibtex(self.CITATION, "fake_layer")
        self.assertIn("@article{doe2020", bibtex)
        self.assertIn("doi = {10.1234/fake.1}", bibtex)
        self.assertIn("title = {A Fake Dataset}", bibtex)

    def test_bibtex_requires_title_and_year(self) -> None:
        self.assertIsNone(build_bibtex({"paper": "prose only"}, "fake_layer"))

    def test_sources_entry_merges_sidecar_facts(self) -> None:
        info = {
            "layer_id": "fake_layer",
            "source": {"name": "Fake Provider", "url": "u", "license": "l"},
            "citation": self.CITATION,
            "specs": {"spatial_resolution": "", "temporal_coverage": "", "validation": "v"},
        }
        entry = build_sources_entry(info, {"years": [2016, 2015, 2019], "resolution_m": 500})
        self.assertEqual(entry["years"], [2015, 2019])
        self.assertEqual(entry["temporal_coverage"], "2015-2019")
        self.assertEqual(entry["spatial_resolution"], "~500 m")
        self.assertEqual(entry["resolution_m"], 500)
        self.assertEqual(entry["doi"], "10.1234/fake.1")
        self.assertEqual(entry["doi_status"], "verified")

    def test_sources_entry_emits_explicit_not_assigned_doi(self) -> None:
        info = {
            "layer_id": "fake_layer",
            "source": {"name": "Fake Provider", "url": "u", "license": "l"},
            "citation": {"paper": "Official report", "doi_status": "not_assigned"},
            "specs": {"spatial_resolution": "admin", "temporal_coverage": "2024", "validation": "v"},
        }
        entry = build_sources_entry(info)
        self.assertNotIn("doi", entry)
        self.assertEqual(entry["doi_status"], "not_assigned")

    def test_curated_specs_beat_sidecar(self) -> None:
        info = {
            "layer_id": "fake_layer",
            "source": {"name": "n"},
            "specs": {
                "spatial_resolution": "~1 km",
                "temporal_coverage": "2015-2020 (annual)",
                "validation": "v",
            },
        }
        entry = build_sources_entry(info, {"years": [2018], "resolution_m": 500})
        self.assertEqual(entry["spatial_resolution"], "~1 km")
        self.assertEqual(entry["temporal_coverage"], "2015-2020 (annual)")

    def test_methodology_appends_limitations_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            doc = Path(tmp) / "docs" / "fake_methodology.md"
            doc.parent.mkdir(parents=True)
            doc.write_text("# Titulo\n\nCuerpo.\n", encoding="utf-8")
            info = {
                "methodology_doc": "docs/fake_methodology.md",
                "limitations": ["Registry limitation."],
            }
            payload = build_methodology_json(
                "fake_layer", info, tmp, extra_limitations=["Sidecar limitation."]
            )
            self.assertEqual(payload["id"], "fake_layer")
            last = payload["sections"][-1]
            self.assertEqual(last["title"], "Limitaciones")
            self.assertIn("- Registry limitation.", last["body"])
            self.assertIn("- Sidecar limitation.", last["body"])

    def test_missing_methodology_doc_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                build_methodology_json(
                    "fake_layer", {"methodology_doc": "docs/nope.md"}, tmp
                )

    def test_fallback_markdown_used_without_doc(self) -> None:
        payload = build_methodology_json(
            "fake_layer", {}, ".", fallback_markdown="Native method prose."
        )
        self.assertEqual(payload["raw"], "Native method prose.")

    def test_expand_aliases_duplicates_under_webapp_keys(self) -> None:
        registry = {"fake_layer": {"webapp_keys": ["fake", "fake2"]}}
        entries = {"fake_layer": {"layer_id": "fake_layer", "name": "n"}}
        expanded = expand_aliases(entries, registry)
        self.assertIs(expanded["fake"], entries["fake_layer"])
        self.assertIs(expanded["fake2"], entries["fake_layer"])

    def test_expand_aliases_rejects_collisions(self) -> None:
        registry = {
            "layer_a": {"webapp_keys": ["shared"]},
            "layer_b": {"webapp_keys": ["shared"]},
        }
        entries = {
            "layer_a": {"layer_id": "layer_a"},
            "layer_b": {"layer_id": "layer_b"},
        }
        with self.assertRaises(StudyConfigError):
            expand_aliases(entries, registry)


class RegistryPaletteContractTests(unittest.TestCase):
    """The real registry must cover the real palette (the validator's core)."""

    def test_registry_validation_has_no_errors(self) -> None:
        from exposome.info_validation import validate_registry

        errors, warnings = validate_registry(ROOT)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()

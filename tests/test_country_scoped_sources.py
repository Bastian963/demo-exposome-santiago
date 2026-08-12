"""Guards against country-scoped official sub-sources leaking into other countries.

Some global layers carry an *optional* national sub-source that only exists for
one country: `healthcare.official_source` is Chile's MINSAL/DEIS registry and
`wildfire.official` is Chile's CONAF fire statistics. The layer itself is global
(OSM, MODIS), so it cannot be gated with `countries:` in config/layers.yaml the
way a genuinely Chile-only layer like `demography` is -- that would kill the
layer everywhere.

That leaves the per-country override files as the only real defense, and on
2026-08-10 that defense turned out to be one missing file wide: there was no
config/countries/es.yaml, `resolve_settings` treats a missing country file as a
silent no-op, and healthcare for pais_vasco_provincias downloaded the Chilean
DEIS registry into a Spanish study.

These tests sweep *every* study rather than spot-checking one, and assert that
every country a study lives in actually has an override file.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.settings import resolve_settings  # noqa: E402
from exposome.studies import load_study  # noqa: E402

# (layer id, path to the `enabled` flag inside that layer's settings, owning country)
CHILE_SCOPED_SUBSOURCES = (
    ("healthcare", ("official_source", "enabled"), "CL"),
    ("wildfire", ("official", "enabled"), "CL"),
)


def _study_ids() -> list[str]:
    return sorted(path.stem for path in (ROOT / "config" / "studies").glob("*.yaml"))


def _flag(resolved, layer_id: str, path: tuple[str, ...]):
    node = resolved.layer(layer_id)
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


class CountryScopedSubSourceTests(unittest.TestCase):
    """Config-resolution guards. Offline: these only read YAML."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.resolved = {}
        for study_id in _study_ids():
            context = load_study(study_id, repo_root_path=ROOT)
            cls.resolved[study_id] = (context.country_code, resolve_settings(context))

    def test_no_study_inherits_another_countrys_official_source(self) -> None:
        leaks = []
        for study_id, (country, resolved) in self.resolved.items():
            for layer_id, path, owner in CHILE_SCOPED_SUBSOURCES:
                if country == owner:
                    continue
                if _flag(resolved, layer_id, path):
                    leaks.append(f"{study_id} ({country}): {layer_id}.{'.'.join(path)} is enabled")
        self.assertEqual(
            leaks,
            [],
            "A study resolved a country-scoped official sub-source belonging to another "
            "country. Add the opt-out to config/countries/<iso2>.yaml:\n  " + "\n  ".join(leaks),
        )

    def test_the_owning_country_still_gets_its_official_source(self) -> None:
        """The opt-out must not be 'disable it everywhere' -- Chile still needs DEIS/CONAF."""
        for layer_id, path, owner in CHILE_SCOPED_SUBSOURCES:
            owned = [s for s, (cc, _) in self.resolved.items() if cc == owner]
            self.assertTrue(owned, f"no {owner} study found to check {layer_id}")
            for study_id in owned:
                _, resolved = self.resolved[study_id]
                self.assertTrue(
                    _flag(resolved, layer_id, path),
                    f"{study_id} ({owner}) lost its own {layer_id}.{'.'.join(path)}",
                )

    def test_every_country_with_a_study_has_an_override_file(self) -> None:
        """The root cause: settings.py skips a missing country file without complaining."""
        countries = {country for country, _ in self.resolved.values()}
        missing = sorted(
            country
            for country in countries
            if not (ROOT / "config" / "countries" / f"{country.lower()}.yaml").is_file()
        )
        self.assertEqual(
            missing,
            [],
            "These countries have studies but no config/countries/<iso2>.yaml. A missing "
            "file is a silent no-op, so they inherit every global layer default, including "
            f"country-specific ones: {missing}",
        )


@unittest.skipUnless(
    os.environ.get("EXPOSOME_RUN_ARTIFACT_TESTS") == "1",
    "requires EXPOSOME_RUN_ARTIFACT_TESTS=1 and materialized releases",
)
class MaterializedArtifactTests(unittest.TestCase):
    """Checks what actually landed on disk, not just what the config says."""

    def test_only_chilean_healthcare_artifacts_used_the_official_registry(self) -> None:
        offenders = []
        for path in sorted((ROOT / "data" / "processed").glob("*/*/*/healthcare/*metadata*.json")):
            # macOS leaves AppleDouble sidecars (`._name`) on the FUSE/NTFS cache
            # volume; they are not UTF-8 and are not ours.
            if path.name.startswith("._"):
                continue
            country = path.relative_to(ROOT / "data" / "processed").parts[0]
            payload = json.loads(path.read_text())
            if "use_official_source" not in payload:
                continue  # native studies carry a different metadata contract
            if payload["use_official_source"] and country != "cl":
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(
            offenders,
            [],
            f"non-Chilean healthcare artifacts built with the Chilean DEIS registry: {offenders}",
        )


if __name__ == "__main__":
    unittest.main()

"""Every picker-visible aggregate study must be able to publish native detail.

`docs/resolution_manifest.md` states the rule plainly: an administrative unit is
only a mask over a native asset. On 2026-08-11 that rule turned out to be
unenforced. `pais_vasco_provincias` shipped to GEMMA with 1 of 14 spatial
indicators complete -- its 3 provinces were *defining* the painted value instead
of only clipping it -- because nothing ever checked the one declaration that
makes native detail possible.

The chain is short and entirely config-level:

    no `detail.native_study` in the study yaml
      -> no companion native study to collect native rasters
      -> `exposome detail` (local post-processing) has nothing to convert
      -> no detail/*.tif
      -> spatial_coverage marks every raster indicator `missing`
      -> publication_tier: preview

`spatial_plan.py` already emits the prerequisite as prose ("declare
detail.native_study with a validated dissolved AOI"), but only when someone asks
it for a recovery plan. Nothing on the publish path did.

These tests fail loudly at config time instead, which is the point: the cost of
the miss was a full native collection run discovered one day before a delivery.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.studies import load_study  # noqa: E402

STUDY_DIR = ROOT / "config" / "studies"

# Single-layer vector deliveries whose detail is MVT `vector_contours`, not a
# native raster. They have no raster indicator to source from a native study, so
# requiring one would be noise. Keep this list short and justified -- it is the
# only way to opt out of the contract.
VECTOR_ONLY_STUDIES = {
    "barcelona_districts_noise",
    "barcelones_noise_pilot",
}

# Studies that are configured but deliberately not executable, so they never
# reach the picker with real data.
NON_EXECUTABLE_STUDIES = {
    "buenos_aires_zipcodes",  # the 2026-07 cohort delivery has no postal codes
}


def _study_ids() -> list[str]:
    return sorted(path.stem for path in STUDY_DIR.glob("*.yaml"))


def _visible_aggregate_studies() -> list[str]:
    """Aggregate studies a browser user can actually select."""
    selected = []
    for study_id in _study_ids():
        if study_id in VECTOR_ONLY_STUDIES or study_id in NON_EXECUTABLE_STUDIES:
            continue
        context = load_study(study_id)
        if context.is_native or context.study.hidden:
            continue
        selected.append(study_id)
    return selected


class NativeDetailDeclarationTests(unittest.TestCase):
    def test_every_visible_aggregate_study_declares_a_native_companion(self) -> None:
        missing = []
        for study_id in _visible_aggregate_studies():
            raw_detail = load_study(study_id).study.raw.get("detail")
            native_study = (
                raw_detail.get("native_study") if isinstance(raw_detail, dict) else None
            )
            if not native_study:
                missing.append(study_id)

        self.assertEqual(
            missing,
            [],
            "picker-visible studies without `detail.native_study` publish as "
            "publication_tier=preview and paint flat administrative units: "
            f"{missing}. Declare the companion study (see "
            "config/studies/pais_vasco_native.yaml) or add the study to "
            "VECTOR_ONLY_STUDIES with a reason.",
        )

    def test_each_declared_native_study_exists_and_is_native(self) -> None:
        for study_id in _study_ids():
            raw_detail = load_study(study_id).study.raw.get("detail")
            if not isinstance(raw_detail, dict):
                continue
            native_study = raw_detail.get("native_study")
            if not native_study:
                continue
            with self.subTest(study=study_id):
                config_path = STUDY_DIR / f"{native_study}.yaml"
                self.assertTrue(
                    config_path.is_file(),
                    f"{study_id} points detail.native_study at {native_study}, "
                    f"which has no config at {config_path}",
                )
                self.assertTrue(
                    load_study(native_study).is_native,
                    f"{study_id}'s detail.native_study {native_study} is not "
                    "`mode: native`; exposome detail would find no native rasters",
                )

    def test_declared_native_studies_have_a_readable_aoi(self) -> None:
        """A native study without its AOI file fails only once GEE is already open."""
        for study_id in _study_ids():
            context = load_study(study_id)
            if not context.is_native:
                continue
            with self.subTest(study=study_id):
                aoi_path = context.aoi_path or context.spatial_path
                self.assertIsNotNone(aoi_path, f"{study_id} declares neither aoi nor spatial path")
                self.assertTrue(
                    Path(aoi_path).is_file(),
                    f"{study_id}'s AOI is missing: {aoi_path}. Rebuild it with "
                    "scripts/migrations/build_native_aoi.py",
                )


if __name__ == "__main__":
    unittest.main()

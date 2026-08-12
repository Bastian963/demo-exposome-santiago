"""Column -> exposome catalog join in the distributions exporter.

The analytics panel's rail is the webapp exposome catalog itself, so the only
fragile step -- mapping a ``master.csv`` column to the exposome id the picker
shows -- lives once, here, in ``registry_by_column``. These tests pin that join
against the committed ``webapp/public/palette.json`` (an offline file read; no
bundle or raster is touched).

Loads scripts/export_webapp_distributions.py by path (it is a CLI script, not
an installed package).
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "export_webapp_distributions", ROOT / "scripts" / "export_webapp_distributions.py"
)
exp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(exp)


class RegistryByColumnTest(unittest.TestCase):
    def setUp(self) -> None:
        self.palette = exp.load_palette()
        self.by_column = exp.registry_by_column(self.palette)
        self.exposomes = self.palette["exposomes"]

    def test_headline_columns_map_to_their_exposome(self) -> None:
        cases = {
            "pm25_mean": "pm25",
            "nse_index": "nse",
            "social_index": "social_infrastructure",
            "mean_nearest_health_m": "healthcare",
            "walk_index": "walkability",
        }
        for column, exposome_id in cases.items():
            self.assertIn(column, self.by_column, column)
            self.assertEqual(self.by_column[column][0], exposome_id, column)

    def test_group_shared_column_resolves_to_child_not_parent(self) -> None:
        # `heat` (status:group) and its child `heat_index` both declare
        # `heat_exposure_index`; `rain`/`rain_index` share `precip_extremes_index`.
        # The concrete child must win so the analytics indicator keys the leaf
        # the picker would drill into, never the aggregation parent.
        self.assertEqual(self.by_column["heat_exposure_index"][0], "heat_index")
        self.assertEqual(self.by_column["precip_extremes_index"][0], "rain_index")

    def test_group_parents_are_never_a_mapping_target(self) -> None:
        group_ids = {
            eid for eid, e in self.exposomes.items() if e.get("status") == "group"
        }
        self.assertTrue(group_ids, "expected at least one group parent in the catalog")
        mapped_ids = {eid for eid, _ in self.by_column.values()}
        self.assertEqual(group_ids & mapped_ids, set())

    def test_detail_columns_are_not_headline_columns(self) -> None:
        # The derived/detail columns the picker hides must not be catalog
        # headline columns -- otherwise they would leak back into the rail.
        for column in (
            "ndvi_mean",
            "evi_mean",
            "green_cover_pct_ndvi",
            "pm25_who_ratio",
            "pm25_pop_weighted",
            "alan_radiance_median",
            "precip_rx1day_mm",
            "spi_3_mean",
            "tmax_p95_c",
            "aod_mean",
        ):
            self.assertNotIn(column, self.by_column, column)

    def test_every_mapped_id_exists_in_the_catalog(self) -> None:
        for _, (exposome_id, entry) in self.by_column.items():
            self.assertIn(exposome_id, self.exposomes)
            self.assertEqual(entry.get("status"), self.exposomes[exposome_id].get("status"))


class FineWinsTest(unittest.TestCase):
    def test_supported_fine_exposomes_are_declared(self) -> None:
        for fine in ("pm25", "no2", "alan", "wind", "green"):
            self.assertIn(fine, exp.FINE_INDICATOR_LABELS, fine)

    def test_fine_pm25_would_shadow_its_admin_column(self) -> None:
        # pm25_mean maps to "pm25"; since "pm25" is a fine sample, the admin
        # column is intentionally not exported as a separate indicator.
        by_column = exp.registry_by_column(exp.load_palette())
        self.assertEqual(by_column["pm25_mean"][0], "pm25")
        self.assertIn("pm25", exp.FINE_INDICATOR_LABELS)


class PublishedDetailGateTest(unittest.TestCase):
    def _bundle(self, detail: dict, sidecar: dict | None = None) -> tuple[Path, dict]:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        bundle = Path(temp.name)
        asset = bundle / "detail" / "pm25.tif"
        asset.parent.mkdir()
        asset.write_bytes(b"test")
        if sidecar is not None:
            asset.with_suffix(".metadata.json").write_text(json.dumps(sidecar))
        manifest = {
            "schema_version": 3,
            "spatial_indicators": {"pm25": {"detail": detail}},
        }
        return bundle, manifest

    def test_verified_cog_requires_matching_sidecar_scale(self) -> None:
        detail = {
            "type": "cog",
            "path": "detail/pm25.tif",
            "canonical_resolution_verified": True,
            "source_native_resolution_m": 1113.0,
        }
        bundle, manifest = self._bundle(
            detail,
            {"source_support_preserved": True, "source_native_resolution_m": 1113.0},
        )
        self.assertIsNotNone(
            exp._verified_published_detail(bundle, manifest, "pm25", "cog")
        )

    def test_stale_or_unverified_cog_is_rejected(self) -> None:
        detail = {
            "type": "cog",
            "path": "detail/pm25.tif",
            "canonical_resolution_verified": True,
            "source_native_resolution_m": 1113.0,
        }
        bundle, manifest = self._bundle(
            detail,
            {"source_support_preserved": True, "source_native_resolution_m": 9000.0},
        )
        self.assertIsNone(
            exp._verified_published_detail(bundle, manifest, "pm25", "cog")
        )
        manifest["spatial_indicators"]["pm25"]["detail"][
            "canonical_resolution_verified"
        ] = False
        self.assertIsNone(
            exp._verified_published_detail(bundle, manifest, "pm25", "cog")
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome import boundaries, config  # noqa: E402
from exposome.studies import load_study  # noqa: E402


PILOT_CONFIG_KEYS = {
    "pm25",
    "alan",
    "greenspace",
    "precipitation",
    "climate_heat",
    "climate",
    "wind",
    "wildfire",
    "healthcare",
    "social_infrastructure",
    "food_environment",
}


class StudyLayerBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = config.load_config("santiago_communes")

    def test_study_config_exposes_legacy_layer_settings(self) -> None:
        self.assertTrue(PILOT_CONFIG_KEYS.issubset(self.cfg))
        self.assertEqual(self.cfg["name"], "santiago_communes")
        self.assertEqual(self.cfg["expected_units"], 52)
        self.assertEqual(self.cfg["expected_communes"], 52)
        self.assertEqual(self.cfg["spatial_unit_type"], "commune")

    def test_worldpop_country_follows_location(self) -> None:
        self.assertEqual(self.cfg["country_code3"], "CHL")
        self.assertEqual(self.cfg["alan"]["population"]["country"], "CHL")

    def test_boundaries_preserve_canonical_and_legacy_keys(self) -> None:
        units = boundaries.get_communes(self.cfg)
        self.assertEqual(len(units), 52)
        self.assertTrue(
            {"spatial_id", "spatial_name", "name", "area_km2", "geometry"}.issubset(
                units.columns
            )
        )
        self.assertFalse(units["spatial_id"].duplicated().any())
        self.assertFalse(units["name"].duplicated().any())

    def test_metric_crs_is_resolved(self) -> None:
        self.assertNotEqual(self.cfg["crs"]["metric"], "auto")
        self.assertEqual(self.cfg["crs"]["metric"], "EPSG:32719")

    def test_runner_injected_config_keeps_legacy_location_query(self) -> None:
        context = load_study("santiago_communes", repo_root_path=REPO_ROOT)
        cfg = context.resolved_config()
        self.assertEqual(cfg["location_id"], "santiago")
        self.assertEqual(cfg["region_query"], "Santiago, Chile")

    def test_external_study_path_and_period_reach_legacy_runners(self) -> None:
        polygons = (
            REPO_ROOT
            / "data"
            / "reference"
            / "cl"
            / "santiago"
            / "santiago_communes"
            / "spatial_units.geojson"
        )
        with tempfile.TemporaryDirectory() as tmp:
            study_path = Path(tmp) / "external_study.yaml"
            study_path.write_text(
                "\n".join(
                    [
                        "id: external_study",
                        "location: cl/santiago",
                        "spatial:",
                        f"  path: {polygons}",
                        "  id_column: spatial_id",
                        "  name_column: spatial_name",
                        "  unit_type: commune",
                        "  expected_units: 52",
                        "layers: [pm25, alan, precipitation]",
                        "period:",
                        '  start_date: "2020-01-01"',
                        '  end_date: "2021-12-31"',
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(
                "os.environ", {"EXPOSOME_STUDY_CONFIG": str(study_path)}
            ):
                cfg = config.load_config("external_study")

        self.assertEqual(cfg["study_period"]["reference_year"], 2021)
        self.assertEqual(cfg["pm25"]["years"], [2020, 2021])
        self.assertEqual(cfg["alan"]["year"], 2021)
        self.assertEqual(cfg["precipitation"]["years"], [2020, 2021])

    def test_partial_calendar_period_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "complete calendar years"):
            config._apply_study_period(  # type: ignore[attr-defined]
                {},
                {"start_date": "2020-06-01", "end_date": "2021-05-31"},
            )


if __name__ == "__main__":
    unittest.main()

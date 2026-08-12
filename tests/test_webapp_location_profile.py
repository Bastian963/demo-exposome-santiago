"""Tests for the local ZIP/marker exposome profile.

The local profile is a relative, intra-city radar. It must not invent
postal-code geocoding, must not treat EBI as a raw exposure axis, and
must only use fine layers when the exposome declares that resolution.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEBAPP = REPO_ROOT / "webapp"
AXES_JSON = WEBAPP / "public" / "data" / "location_profile_axes.json"
ZIPCODES_JSON = WEBAPP / "public" / "data" / "zipcodes.json"
LOCATION_JS = WEBAPP / "src" / "location-profile.js"
INDEX_HTML = WEBAPP / "index.html"
MAIN_JS = WEBAPP / "src" / "main.js"
URL_STATE_JS = WEBAPP / "src" / "utils" / "url-state.js"
CITY_PANEL_JS = WEBAPP / "src" / "panels" / "city-overview.js"
STYLE_CSS = WEBAPP / "src" / "style.css"
EXPORT_SCRIPT = REPO_ROOT / "scripts" / "export_webapp_zipcodes.py"


class LocationProfileContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.axes = json.loads(AXES_JSON.read_text())
        cls.zipcodes = json.loads(ZIPCODES_JSON.read_text())
        cls.location_src = LOCATION_JS.read_text()
        cls.index_html = INDEX_HTML.read_text()
        cls.main_src = MAIN_JS.read_text()
        cls.url_src = URL_STATE_JS.read_text()
        cls.city_panel_src = CITY_PANEL_JS.read_text()
        cls.style_src = STYLE_CSS.read_text()

    def test_axis_file_has_eight_family_axes(self) -> None:
        axes = self.axes["axes"]
        self.assertEqual(
            [a["id"] for a in axes],
            ["pm25", "no2", "heavy_metals", "alan", "noise", "heat", "rain", "nse_low", "social_low"],
        )
        self.assertEqual(len(axes), 9)

    def test_axis_file_does_not_use_ebi_or_duplicate_heat_rain_sublayers(self) -> None:
        axes = self.axes["axes"]
        axis_ids = {a["id"] for a in axes}
        exposomes = {a["exposome"] for a in axes}
        self.assertNotIn("ebi", axis_ids)
        self.assertNotIn("ebi", exposomes)
        self.assertEqual([a["exposome"] for a in axes if a["id"] == "heat"], ["heat_index"])
        self.assertEqual([a["exposome"] for a in axes if a["id"] == "rain"], ["rain_index"])

    def test_axis_directions_are_methodologically_oriented(self) -> None:
        by_id = {a["id"]: a for a in self.axes["axes"]}
        for burden_axis in ("pm25", "no2", "alan", "noise", "heat", "rain"):
            self.assertEqual(by_id[burden_axis]["direction"], 1)
        self.assertEqual(by_id["nse_low"]["direction"], -1)
        self.assertEqual(by_id["social_low"]["direction"], -1)

    def test_noise_axis_has_coverage_gap_guard(self) -> None:
        by_id = {a["id"]: a for a in self.axes["axes"]}
        self.assertEqual(by_id["noise"]["coverage_column"], "noise_in_gsu_map")
        self.assertEqual(by_id["noise"]["coverage_missing_value"], 0)

    def test_zipcodes_default_is_missing_reference_not_fake_data(self) -> None:
        self.assertEqual(self.zipcodes["status"], "missing_reference")
        self.assertEqual(self.zipcodes["records"], [])
        self.assertIn("postal", self.zipcodes["message"])

    def test_index_has_location_profile_ui_mounts(self) -> None:
        for element_id in (
            "locationProfileWidget",
            "locationZipInput",
            "locationPickButton",
            "locationProfileAvatar",
            "locationProfileCard",
        ):
            self.assertIn(f'id="{element_id}"', self.index_html)

    def test_url_state_supports_loc_and_zip(self) -> None:
        self.assertIn("loc: null", self.url_src)
        self.assertIn("zip: null", self.url_src)
        self.assertIn('params.get("loc")', self.url_src)
        self.assertIn('params.get("zip")', self.url_src)

    def test_main_wires_city_overview_and_restore(self) -> None:
        self.assertIn("openLocationProfilePicker", self.main_src)
        self.assertIn("restoreLocationProfileFromState(_appState)", self.main_src)
        self.assertIn("openLocationProfile: true", self.main_src)
        self.assertIn("destroyLocationProfile()", self.main_src)

    def test_city_overview_has_local_profile_action(self) -> None:
        self.assertIn("_onOpenLocationProfile", self.city_panel_src)
        self.assertIn("cityLocalProfileButton", self.city_panel_src)
        self.assertIn("Radar relativo", self.city_panel_src)
        self.assertIn('data-mode="switch"', self.style_src)
        self.assertIn(".city-overview-panel[data-mode=\"switch\"] .city-local-profile-action", self.style_src)

    def test_location_profile_uses_only_local_data_and_declared_fine_layers(self) -> None:
        self.assertIn("assetUrl(\"location_profile_axes.json\")", self.location_src)
        self.assertIn("assetUrl(\"zipcodes.json\")", self.location_src)
        # In manifest schema v2, a study's actual declared detail asset is
        # authoritative; a global palette flag would falsely advertise detail
        # for cities that have not published it yet.
        self.assertIn("studyHasFineLayer(axis.exposome)", self.location_src)
        self.assertIn("studyDetailAsset(axis.exposome)", self.location_src)
        self.assertNotIn("expo.has_fine_layer", self.location_src)
        self.assertIn("/data/subcomuna/${exposomeId}.geojson", self.location_src)
        self.assertNotIn("https://", self.location_src)
        self.assertNotIn("nominatim", self.location_src.lower())
        self.assertNotIn("geocode", self.location_src.lower())

    def test_location_profile_exports_expected_functions(self) -> None:
        for name in (
            "initLocationProfile",
            "openLocationProfilePicker",
            "restoreLocationProfileFromState",
            "setLocationFromZipcode",
            "setLocationPoint",
            "normalizeZipcode",
            "rankPercentile",
        ):
            self.assertTrue(
                f"export function {name}" in self.location_src
                or f"export async function {name}" in self.location_src,
                f"missing export: {name}",
            )

    def test_export_zipcodes_script_is_local_only(self) -> None:
        src = EXPORT_SCRIPT.read_text()
        self.assertIn("postal_code_reference.csv", src)
        self.assertIn("zipcodes_rm.geojson", src)
        self.assertIn("missing_reference", src)
        self.assertNotIn("requests", src)
        self.assertNotIn("https://", src)


if __name__ == "__main__":
    unittest.main()

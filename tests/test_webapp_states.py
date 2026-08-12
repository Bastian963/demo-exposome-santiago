"""Tests for the state machine in main.js.

Verifies the LATAM <-> COMMUNE state transitions and their wiring.
"""
from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_JS = REPO_ROOT / "webapp" / "src" / "main.js"
LATAM_JS = REPO_ROOT / "webapp" / "src" / "states" / "latam.js"
COMMUNE_JS = REPO_ROOT / "webapp" / "src" / "states" / "commune.js"


class StateMachineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main = MAIN_JS.read_text()
        cls.latam = LATAM_JS.read_text()
        cls.commune = COMMUNE_JS.read_text()

    def test_main_imports_both_states(self) -> None:
        self.assertIn('from "./states/latam.js"', self.main)
        self.assertIn('from "./states/commune.js"', self.main)

    def test_main_has_state_constants(self) -> None:
        self.assertIn('LATAM: "latam"', self.main)
        self.assertIn('COMMUNE: "commune"', self.main)

    def test_transition_to_commune_function(self) -> None:
        self.assertIn("transitionToCommune", self.main)

    def test_transition_to_latam_function(self) -> None:
        self.assertIn("transitionToLatam", self.main)

    def test_back_button_setup(self) -> None:
        self.assertIn("setupBackButton", self.main)
        self.assertIn("backButton", self.main)

    def test_loading_overlay(self) -> None:
        self.assertIn("loadingOverlay", self.main)
        self.assertIn("showLoading", self.main)

    def test_city_selection_is_not_gated_by_globe_tween(self) -> None:
        select_idx = self.latam.index("function selectCity(slug)")
        select_end = self.latam.index("\n}\n", select_idx) + 2
        select_block = self.latam[select_idx:select_end]
        self.assertIn("void focusCity(slug);", select_block)
        self.assertIn("_onCityClick(slug)", select_block)
        self.assertNotIn("focusCity(slug).then", select_block)

    def test_city_navigation_commits_only_after_manifest_load(self) -> None:
        transition_idx = self.main.index("async function transitionToCity")
        transition_end = self.main.index("\n}\n\nfunction showCityLoadError", transition_idx)
        transition_block = self.main[transition_idx:transition_end]
        self.assertLess(
            transition_block.index("await selectStudy(city.study_id)"),
            transition_block.index("setURLState(_appState)"),
        )
        self.assertIn("_cityNavigationGeneration", transition_block)

    def test_city_load_errors_offer_recovery(self) -> None:
        self.assertIn("function showCityLoadError", self.main)
        self.assertIn("retry:", self.main)
        self.assertIn("back:", self.main)

    def test_latam_state_has_world_view(self) -> None:
        self.assertIn("DEFAULT_LON", self.latam)
        self.assertIn("DEFAULT_ZOOM", self.latam)

    def test_commune_state_has_santiago(self) -> None:
        self.assertIn("getStudyManifest", self.commune)
        self.assertIn("fitToStudy", self.commune)

    def test_commune_state_loads_master(self) -> None:
        self.assertIn("loadMaster", self.commune)
        self.assertIn("addChoropleth", self.commune)

    def test_commune_click_handler(self) -> None:
        """Commune state must wire click handler."""
        self.assertIn("onCommuneClick", self.commune)
        self.assertIn("getCentroid", self.commune)


if __name__ == "__main__":
    unittest.main()

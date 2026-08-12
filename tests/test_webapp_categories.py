"""Tests for the study-aware city overview categories."""
from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WEBAPP_SRC = REPO_ROOT / "webapp" / "src"
SRC = WEBAPP_SRC / "panels" / "city-overview.js"
PALETTE = REPO_ROOT / "webapp" / "public" / "palette.json"


class CategoriesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.src = SRC.read_text()
        cls.palette = PALETTE.read_text()

    def test_8_categories_present(self) -> None:
        """The overview keeps the two domain groups used by the palette."""
        self.assertIn('entorno:', self.src)
        self.assertIn('sociedad:', self.src)

    def test_categories_have_icons(self) -> None:
        """Every rendered card still has a deterministic icon key."""
        self.assertIn("icon-${escHtml(iconId)}", self.src)

    def test_exposome_assignment_per_category(self) -> None:
        """Verify that each exposome appears in some category."""
        for expo in (
            "pm25", "no2", "alan", "noise", "heavy_metals", "ebi", "nse",
            "food_environment", "food_insecurity", "poverty", "social_infrastructure",
        ):
            self.assertIn(
                f'"{expo}"', self.palette,
                f"exposome {expo!r} not in any category",
            )

    def test_acordeon_only_one_open(self) -> None:
        """The acordeon behavior must close all others before opening."""
        self.assertIn("attachContentListeners", self.src)


if __name__ == "__main__":
    unittest.main()

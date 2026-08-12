"""Tests for the hybrid monitor scale engine.

The chamber's visual intensity used to clamp to a hand-tuned domain
(chamber.visual_min_value/visual_max_value) that was calibrated to
Santiago's data range, which left it dead (AMBA pm25) or saturated (AMBA
heat_tropical_nights) for any other city. This is now hybrid: the active
study's own data range wins when available (choropleth.js computes it,
controller.js caches it, scaling.js applies it), falling back to the
palette's domain only when no study data is loaded yet or the exposome
opts out via `chamber.domain: "absolute"`.
"""
from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHOROPLETH_JS = REPO_ROOT / "webapp" / "src" / "choropleth.js"
CONTROLLER_JS = REPO_ROOT / "webapp" / "src" / "components" / "exposomeAnimations" / "controller.js"
SCALING_JS = REPO_ROOT / "webapp" / "src" / "components" / "exposomeAnimations" / "scaling.js"
INDEX_JS = REPO_ROOT / "webapp" / "src" / "components" / "exposomeAnimations" / "index.js"
AIRCHAMBER_JS = REPO_ROOT / "webapp" / "src" / "visualizations" / "airchamber.js"


class StudyDomainWiringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.choropleth_src = CHOROPLETH_JS.read_text()
        cls.controller_src = CONTROLLER_JS.read_text()
        cls.scaling_src = SCALING_JS.read_text()
        cls.index_src = INDEX_JS.read_text()
        cls.airchamber_src = AIRCHAMBER_JS.read_text()

    def test_choropleth_computes_and_pushes_study_domain(self) -> None:
        self.assertIn("function computeStudyDomain", self.choropleth_src)
        self.assertIn("m.setStudyDomain(computeStudyDomain(values))", self.choropleth_src)
        # Robust bounds: p5/p95 clamp outliers instead of raw min/max alone.
        self.assertIn("quantileSorted(sorted, 0.05)", self.choropleth_src)
        self.assertIn("quantileSorted(sorted, 0.95)", self.choropleth_src)

    def test_study_domain_exported_end_to_end(self) -> None:
        for src, name in (
            (self.controller_src, "controller.js"),
            (self.index_src, "index.js"),
            (self.airchamber_src, "airchamber.js"),
        ):
            self.assertIn("setStudyDomain", src, f"setStudyDomain missing from {name}")

    def test_controller_resets_study_domain_on_destroy(self) -> None:
        destroy_idx = self.controller_src.index("export function destroy()")
        next_export = self.controller_src.index("export function", destroy_idx + 1)
        destroy_block = self.controller_src[destroy_idx:next_export]
        self.assertIn("_baseDomain = null", destroy_block)
        self.assertIn("_previewContext = null", destroy_block)

    def test_controller_forwards_study_domain_to_scaling(self) -> None:
        self.assertIn(
            "valueToVisualState(value, _expo || defaultExpo(), activeDomain())",
            self.controller_src,
        )


class ScalingPrecedenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scaling_src = SCALING_JS.read_text()

    def test_resolve_study_bounds_prefers_percentiles_over_minmax(self) -> None:
        idx = self.scaling_src.index("function resolveStudyBounds")
        end = self.scaling_src.index("\n}", idx) + 2
        block = self.scaling_src[idx:end]
        p5_idx = block.index("p95 > p5")
        minmax_idx = block.index("max > min")
        self.assertLess(p5_idx, minmax_idx, "p5/p95 must be tried before min/max")

    def test_study_domain_wins_over_palette_chamber_domain(self) -> None:
        self.assertIn("studyBounds ? studyBounds.vmin : chamber.visual_min_value", self.scaling_src)
        self.assertIn("studyBounds ? studyBounds.vmax : chamber.visual_max_value", self.scaling_src)

    def test_absolute_domain_escape_hatch(self) -> None:
        self.assertIn('chamber.domain === "absolute"', self.scaling_src)

    def test_value_to_visual_state_accepts_study_domain_param(self) -> None:
        self.assertIn(
            "export function valueToVisualState(value, expo = {}, studyDomain = null)",
            self.scaling_src,
        )


class WhoCategoryStaysAbsoluteTest(unittest.TestCase):
    """The chamber's visual intensity is hybrid (per-study), but the
    health category label must mean the same thing in every city."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.controller_src = CONTROLLER_JS.read_text()

    def test_who_category_accepts_optional_expo_thresholds(self) -> None:
        self.assertIn(
            "export function whoCategory(value, expo = null)",
            self.controller_src,
        )
        self.assertIn("const thresholds = expo?.thresholds || WHO_THRESHOLDS", self.controller_src)


if __name__ == "__main__":
    unittest.main()

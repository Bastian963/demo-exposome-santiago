"""Pin the radius gate against the declared spatial supports.

These tests are the guard that stops a point extraction from advertising more
resolution than a product has (ADR 0012 §2-§4).  The expected numbers come from
``INDICATOR_SUPPORT`` itself, so a change to a declared support has to be made
deliberately here too.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from exposome.point_support import (
    ADMINISTRATIVE_UNIT,
    COMPOSITE,
    DEFAULT_RADII,
    NOT_APPLICABLE,
    RASTER_BLOCK,
    RESOLVED,
    SUB_OBSERVATION,
    VECTOR_QUERY,
    UnknownIndicator,
    analysis_support_m,
    delivered_support_m,
    effective_support_m,
    emits_within_buffer_sd,
    estimand_kind,
    observation_support_m,
    radius_status,
    resolution_metres,
)
from exposome.spatial_support import INDICATOR_SUPPORT

SANTIAGO_LAT = -33.45


class EstimandKindTest(unittest.TestCase):
    def test_every_declared_indicator_maps_to_exactly_one_kind(self) -> None:
        kinds = {RASTER_BLOCK, ADMINISTRATIVE_UNIT, VECTOR_QUERY, COMPOSITE}
        for indicator_id in INDICATOR_SUPPORT:
            with self.subTest(indicator=indicator_id):
                self.assertIn(estimand_kind(indicator_id), kinds)

    def test_known_classifications(self) -> None:
        self.assertEqual(estimand_kind("pm25"), RASTER_BLOCK)
        self.assertEqual(estimand_kind("nse"), ADMINISTRATIVE_UNIT)
        self.assertEqual(estimand_kind("greenspace_access"), VECTOR_QUERY)
        self.assertEqual(estimand_kind("ebi"), COMPOSITE)

    def test_unknown_indicator_is_explicit(self) -> None:
        with self.assertRaises(UnknownIndicator):
            estimand_kind("not_an_indicator")


class ResolutionConversionTest(unittest.TestCase):
    def test_degree_grid_uses_the_repo_constant(self) -> None:
        # INDICATOR_SUPPORT declares a 0.01 degree product as 1113.2 m, so the
        # conversion has to reproduce that exact number.
        metres = resolution_metres({"x": 0.01, "y": 0.01, "unit": "degree"}, SANTIAGO_LAT)
        self.assertAlmostEqual(metres, 1113.2, places=1)

    def test_anisotropic_footprint_takes_the_long_axis(self) -> None:
        metres = resolution_metres(
            {"x": 3500, "y": 5500, "y_max": 7000, "unit": "m"}, SANTIAGO_LAT
        )
        self.assertEqual(metres, 7000.0)

    def test_vector_resolution_is_not_a_number(self) -> None:
        self.assertIsNone(resolution_metres({"value": None, "unit": "vector"}, SANTIAGO_LAT))

    def test_absent_resolution_is_none(self) -> None:
        self.assertIsNone(resolution_metres(None, SANTIAGO_LAT))


class EffectiveSupportTest(unittest.TestCase):
    def test_no2_is_bound_by_its_observation_footprint(self) -> None:
        # Downloaded on a 1113 m grid, but one TROPOMI observation covers
        # 3.5 x 5.5-7 km.  The footprint binds.
        self.assertAlmostEqual(analysis_support_m("no2", SANTIAGO_LAT), 1113.2, places=1)
        self.assertEqual(observation_support_m("no2", SANTIAGO_LAT), 7000.0)
        self.assertEqual(effective_support_m("no2", SANTIAGO_LAT), 7000.0)

    def test_canopy_is_bound_by_its_analysis_grid(self) -> None:
        # The 1 m source is canopy *height*; what is published is a canopy
        # *fraction* on a 30 m grid.  Advertising 1 m would overclaim by 30x.
        self.assertEqual(observation_support_m("canopy", SANTIAGO_LAT), 1.0)
        self.assertEqual(analysis_support_m("canopy", SANTIAGO_LAT), 30.0)
        self.assertEqual(effective_support_m("canopy", SANTIAGO_LAT), 30.0)

    def test_symmetric_products_agree(self) -> None:
        self.assertAlmostEqual(effective_support_m("alan", SANTIAGO_LAT), 463.83, places=2)
        self.assertAlmostEqual(effective_support_m("pm25", SANTIAGO_LAT), 1113.2, places=1)
        self.assertEqual(effective_support_m("wind", SANTIAGO_LAT), 11132.0)

    def test_administrative_indicators_have_no_metric_support(self) -> None:
        self.assertIsNone(effective_support_m("nse", SANTIAGO_LAT))


class RadiusStatusTest(unittest.TestCase):
    """The four cases named in the plan, plus the boundary condition."""

    def test_no2_never_resolves_at_any_offered_radius(self) -> None:
        for radius in DEFAULT_RADII:
            with self.subTest(radius=radius):
                self.assertEqual(
                    radius_status("no2", radius, SANTIAGO_LAT), SUB_OBSERVATION
                )

    def test_alan_resolves_at_500_m(self) -> None:
        self.assertEqual(radius_status("alan", 500, SANTIAGO_LAT), RESOLVED)

    def test_pm25_needs_a_kilometre(self) -> None:
        self.assertEqual(radius_status("pm25", 300, SANTIAGO_LAT), SUB_OBSERVATION)
        self.assertEqual(radius_status("pm25", 500, SANTIAGO_LAT), SUB_OBSERVATION)
        self.assertEqual(radius_status("pm25", 1000, SANTIAGO_LAT), RESOLVED)

    def test_canopy_resolves_at_300_m(self) -> None:
        self.assertEqual(radius_status("canopy", 300, SANTIAGO_LAT), RESOLVED)

    def test_containing_cell_never_resolves_a_buffer(self) -> None:
        for indicator in ("pm25", "alan", "canopy"):
            with self.subTest(indicator=indicator):
                self.assertEqual(radius_status(indicator, 0, SANTIAGO_LAT), SUB_OBSERVATION)

    def test_boundary_is_inclusive(self) -> None:
        # 2r == support counts as resolved.
        support = effective_support_m("alan", SANTIAGO_LAT)
        self.assertEqual(radius_status("alan", support / 2, SANTIAGO_LAT), RESOLVED)

    def test_non_raster_estimands_are_not_applicable(self) -> None:
        for indicator in ("nse", "ebi", "greenspace_access"):
            with self.subTest(indicator=indicator):
                self.assertEqual(
                    radius_status(indicator, 500, SANTIAGO_LAT), NOT_APPLICABLE
                )


class DeliveredSupportTest(unittest.TestCase):
    def test_support_never_drops_below_the_product(self) -> None:
        # A 300 m buffer on an 11 km product still has 11 km of support.
        self.assertEqual(delivered_support_m("wind", 300, SANTIAGO_LAT), 11132.0)

    def test_a_resolving_buffer_widens_the_support(self) -> None:
        self.assertEqual(delivered_support_m("alan", 1000, SANTIAGO_LAT), 2000.0)

    def test_containing_cell_reports_the_product_support(self) -> None:
        self.assertAlmostEqual(delivered_support_m("pm25", 0, SANTIAGO_LAT), 1113.2, places=1)


class WithinBufferSdTest(unittest.TestCase):
    def test_suppressed_when_the_radius_does_not_resolve(self) -> None:
        # Every contributing cell would sit inside one observation footprint,
        # so the SD collapses to ~0 and would read as high confidence.
        self.assertFalse(emits_within_buffer_sd("no2", 1000, SANTIAGO_LAT))
        self.assertFalse(emits_within_buffer_sd("pm25", 300, SANTIAGO_LAT))

    def test_emitted_when_the_radius_resolves(self) -> None:
        self.assertTrue(emits_within_buffer_sd("alan", 500, SANTIAGO_LAT))
        self.assertTrue(emits_within_buffer_sd("canopy", 300, SANTIAGO_LAT))

    def test_never_emitted_for_administrative_values(self) -> None:
        self.assertFalse(emits_within_buffer_sd("nse", 1000, SANTIAGO_LAT))


class ParityFixtureTest(unittest.TestCase):
    """One fixture, two implementations.

    The webapp mirrors this gate in JavaScript because the tab computes it in
    the browser.  Both sides assert against ``point_support_parity.json``, so a
    change here fails until the mirror is updated too -- which is the only thing
    stopping the same address from getting two different answers depending on
    whether it was asked through the tab or the CLI.
    """

    FIXTURE = Path(__file__).resolve().parent / "fixtures" / "point_support_parity.json"

    def test_python_still_matches_the_fixture(self) -> None:
        document = json.loads(self.FIXTURE.read_text())
        for case in document["cases"]:
            with self.subTest(indicator=case["indicator"], radius=case["radius_m"]):
                latitude = case["latitude"]
                indicator = case["indicator"]
                radius = case["radius_m"]
                self.assertEqual(
                    effective_support_m(indicator, latitude),
                    case["effective_support_m"],
                )
                self.assertEqual(
                    radius_status(indicator, radius, latitude), case["radius_status"]
                )
                self.assertEqual(
                    delivered_support_m(indicator, radius, latitude),
                    case["delivered_support_m"],
                )
                self.assertEqual(
                    emits_within_buffer_sd(indicator, radius, latitude), case["emits_sd"]
                )

    def test_fixture_covers_the_discriminating_cases(self) -> None:
        document = json.loads(self.FIXTURE.read_text())
        indicators = {case["indicator"] for case in document["cases"]}
        # no2 (footprint-bound) and canopy (analysis-bound) are the two cases
        # that a naive gate gets wrong in opposite directions.
        self.assertIn("no2", indicators)
        self.assertIn("canopy", indicators)


class LatitudeTest(unittest.TestCase):
    def test_degree_products_do_not_vary_with_latitude(self) -> None:
        # The north-south extent of a degree cell bounds it, and that does not
        # depend on latitude.  A latitude-dependent answer here would mean the
        # gate silently loosens near the equator.
        for latitude in (-33.45, -12.05, 4.7, 19.43, 43.26):
            with self.subTest(latitude=latitude):
                self.assertAlmostEqual(
                    effective_support_m("pm25", latitude), 1113.2, places=1
                )


if __name__ == "__main__":
    unittest.main()

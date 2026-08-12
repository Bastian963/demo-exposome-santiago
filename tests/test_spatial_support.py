from __future__ import annotations

import sys
import unittest
import json
from inspect import signature
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.spatial_support import (  # noqa: E402
    NOISE_LDEN_BANDS,
    administrative_unit_label,
    apply_indicator_availability,
    indicators_for_bundle,
    validate_palette_coverage,
    validate_indicator_records,
)


class SpatialSupportContractTests(unittest.TestCase):
    @staticmethod
    def _degree_grid(value: float) -> dict:
        return {
            "crs": "EPSG:4326",
            "resolution": {"x": value, "y": value, "unit": "degree"},
        }

    def test_administrative_unit_labels_are_public_facing_spanish(self) -> None:
        self.assertEqual(administrative_unit_label("comuna_corregimiento"), "comuna o corregimiento")
        self.assertEqual(administrative_unit_label("alcaldia"), "alcaldía")

    def test_no_detail_is_not_advertised_just_because_the_source_is_fine(self) -> None:
        records = indicators_for_bundle([], administrative_unit_label="distrito")
        pm25 = records["pm25"]
        self.assertEqual(pm25["boundary_role"], "analysis_unit")
        self.assertIsNone(pm25["detail"])
        self.assertEqual(pm25["rendered"]["kind"], "administrative_polygon")
        self.assertEqual(pm25["rendered"]["label"], "distrito")

    def test_spain_noise_declares_vector_source_and_administrative_rendering(self) -> None:
        noise = indicators_for_bundle([], administrative_unit_label="comarca")["noise_lden"]
        self.assertEqual(noise["layer_id"], "noise_spain")
        self.assertEqual(noise["downloaded"]["kind"], "vector_features")
        self.assertEqual(noise["analysis"]["kind"], "administrative_unit")
        self.assertEqual(noise["boundary_role"], "analysis_unit")
        self.assertIsNone(noise["detail"])
        self.assertEqual(noise["rendered"]["kind"], "administrative_polygon")
        self.assertEqual(noise["publication_target"]["kind"], "native_vector")
        self.assertTrue(noise["publication_target"]["required_for_production"])

    def test_spain_noise_accepts_verified_vector_contours_without_raster_resolution(self) -> None:
        digest = "a" * 64
        descriptor = {
            "schema_version": 1,
            "type": "vector_contours",
            "tiles": ["detail/noise_lden/{z}/{x}/{y}.pbf"],
            "minzoom": 11,
            "maxzoom": 15,
            "bounds": [2.0, 41.0, 2.3, 41.6],
            "source_layer": "noise_lden",
            "bands": list(NOISE_LDEN_BANDS),
            "source_manifest_sha256": digest,
            "source_assets": [{"path": "cataluna/barcelona.zip", "sha256": digest}],
            "source_sha256": digest,
            "source_support_preserved": True,
            "validation": {
                "path": "detail/noise_lden.vector_contours.validation.json",
                "sha256": digest,
            },
        }
        noise = indicators_for_bundle(
            ["detail/noise_lden.vector_contours.json"],
            vector_contour_metadata={"noise_lden": descriptor},
            administrative_unit_label="distrito",
        )["noise_lden"]
        self.assertEqual(noise["detail"]["type"], "vector_contours")
        self.assertEqual(noise["rendered"]["kind"], "vector_contours")
        self.assertIsNone(noise["rendered"]["resolution"])
        self.assertEqual(noise["boundary_role"], "mask_only")
        self.assertEqual(validate_indicator_records({"noise_lden": noise}), [])

    def test_spain_noise_rejects_unproven_vector_descriptor(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid vector-contour detail"):
            indicators_for_bundle(
                ["detail/noise_lden.vector_contours.json"],
                vector_contour_metadata={"noise_lden": {"type": "vector_contours"}},
            )

    def test_native_bundle_without_detail_keeps_aoi_as_mask_but_advertises_no_map(self) -> None:
        pm25 = indicators_for_bundle([], is_native=True)["pm25"]
        self.assertEqual(pm25["boundary_role"], "mask_only")
        self.assertEqual(pm25["rendered"]["kind"], "unavailable")
        self.assertIsNone(pm25["detail"])

    def test_cog_detail_is_study_local_and_preferred(self) -> None:
        records = indicators_for_bundle(
            ["subcomuna/pm25.geojson", "detail/pm25.tif", "detail/pm25.metadata.json"],
            detail_metadata={
                "pm25": {
                    "source_native_resolution_m": 1113,
                    "source_grid": self._degree_grid(0.01),
                    "statistics": {"p02": 1, "p98": 9},
                }
            },
        )
        pm25 = records["pm25"]
        self.assertEqual(pm25["detail"]["type"], "cog")
        self.assertEqual(pm25["detail"]["path"], "detail/pm25.tif")
        self.assertEqual(pm25["detail"]["color_domain"], {"min": 1, "max": 9})
        self.assertEqual(pm25["detail"]["source_grid"]["resolution"]["x"], 0.01)
        self.assertEqual(pm25["rendered"]["kind"], "cog")

    def test_no2_detail_keeps_native_column_units(self) -> None:
        no2 = indicators_for_bundle(
            ["detail/no2.tif"],
            detail_metadata={
                "no2": {
                    "source_native_resolution_m": 1113,
                    "source_grid": self._degree_grid(0.01),
                    "statistics": {"p02": 1, "p98": 9},
                }
            },
        )["no2"]
        self.assertEqual(no2["detail"]["unit"], "mol/m²")
        self.assertEqual(no2["detail"]["metric_label"], "NO₂ columna troposférica")
        self.assertIn("BLH", no2["notes"])

    def test_physical_heat_metric_can_publish_its_own_native_band(self) -> None:
        detail = indicators_for_bundle(
            ["detail/heat_hot_days.tif"],
            detail_metadata={
                "heat_hot_days": {
                    "source_native_resolution_m": 11132,
                    "source_grid": self._degree_grid(0.10),
                    "source_band": 2,
                    "temporal_support": {
                        "kind": "year",
                        "year": "2024",
                        "source_label": "ERA5-Land",
                    },
                    "statistics": {"p02": 1, "p98": 9},
                }
            },
        )["heat_hot_days"]
        self.assertEqual(detail["detail"]["type"], "cog")
        self.assertEqual(detail["detail"]["band"], 1)
        self.assertEqual(
            detail["detail"]["temporal_support"]["source_label"],
            "ERA5-Land",
        )
        self.assertEqual(detail["rendered"]["kind"], "cog")

    def test_physical_heat_detail_requires_one_declared_source_year(self) -> None:
        with self.assertRaisesRegex(ValueError, "temporal_support"):
            indicators_for_bundle(
                ["detail/heat_summer_tmax.tif"],
                detail_metadata={
                    "heat_summer_tmax": {
                        "source_native_resolution_m": 11132,
                        "source_grid": self._degree_grid(0.10),
                        "statistics": {"p02": 1, "p98": 9},
                    }
                },
            )

    def test_physical_rain_metric_can_publish_its_own_native_band(self) -> None:
        detail = indicators_for_bundle(
            ["detail/rain_dry_spell.tif"],
            detail_metadata={
                "rain_dry_spell": {
                    "source_native_resolution_m": 5566,
                    "source_grid": self._degree_grid(0.05),
                    "source_band": 2,
                    "statistics": {"p02": 1, "p98": 9},
                }
            },
        )["rain_dry_spell"]
        self.assertEqual(detail["detail"]["type"], "cog")
        self.assertEqual(detail["rendered"]["kind"], "cog")

    def test_canopy_keeps_one_metre_source_and_thirty_metre_rendered_support(self) -> None:
        detail = indicators_for_bundle(
            ["detail/canopy.tif"],
            detail_metadata={
                "canopy": {
                    "source_native_resolution_m": 1,
                    "analysis_resolution_m": 30,
                    "source_grid": {
                        "crs": "EPSG:3857",
                        "resolution": {"x": 30, "y": 30, "unit": "m"},
                    },
                    "statistics": {"p02": 1, "p98": 9},
                }
            },
        )["canopy"]
        self.assertEqual(detail["detail"]["source_native_resolution_m"], 1.0)
        self.assertEqual(detail["rendered"]["resolution"]["value"], 30)

    def test_legacy_green_requires_shared_aoi_grid_provenance(self) -> None:
        old = indicators_for_bundle(
            ["subcomuna/green.geojson"],
            geojson_detail_metadata={"green": {"is_synthetic": False}},
        )
        valid = indicators_for_bundle(
            ["subcomuna/green.geojson"],
            geojson_detail_metadata={
                "green": {
                    "is_synthetic": False,
                    "grid_alignment": "study_aoi_metric_grid",
                }
            },
        )
        self.assertIsNone(old["green"]["detail"])
        self.assertEqual(valid["green"]["detail"]["type"], "geojson")

    def test_healthcare_grid_requires_same_real_grid_provenance(self) -> None:
        detail = indicators_for_bundle(
            ["subcomuna/healthcare.geojson"],
            geojson_detail_metadata={
                "healthcare": {
                    "is_synthetic": False,
                    "grid_alignment": "study_aoi_metric_grid",
                }
            },
        )["healthcare"]
        self.assertEqual(detail["detail"]["type"], "geojson")
        self.assertEqual(detail["detail"]["unit"], "m")

    def test_admin_sources_remain_source_unit(self) -> None:
        admin = indicators_for_bundle([])["poverty_income"]
        self.assertEqual(admin["boundary_role"], "source_unit")
        self.assertEqual(admin["rendered"]["kind"], "administrative_polygon")

    def test_availability_distinguishes_country_scope_and_coming_soon(self) -> None:
        records = apply_indicator_availability(
            indicators_for_bundle([]),
            enabled_layers=("air_quality_pm25",),
            available_layers=("air_quality_pm25",),
            country_code="CL",
            layer_countries={"community_safety": ("AR",)},
            palette_statuses={"ebi": "coming_soon"},
        )
        self.assertEqual(records["pm25"]["availability"]["status"], "available")
        self.assertEqual(
            records["community_safety"]["availability"],
            {
                "status": "unavailable",
                "reason": "country_not_supported",
                "supported_countries": ["AR"],
            },
        )
        self.assertEqual(records["community_safety"]["rendered"]["kind"], "unavailable")
        self.assertEqual(records["ebi"]["availability"]["reason"], "coming_soon")

    def test_osm_support_matches_each_actual_analysis_method(self) -> None:
        records = indicators_for_bundle([])
        self.assertEqual(records["healthcare"]["analysis"]["kind"], "regular_grid")
        self.assertEqual(records["healthcare"]["analysis"]["resolution"]["value"], 1000)
        self.assertEqual(records["healthcare"]["boundary_role"], "analysis_unit")
        self.assertEqual(records["social_infrastructure"]["boundary_role"], "component_specific")
        self.assertFalse(
            records["social_infrastructure"]["publication_target"]["required_for_production"]
        )
        self.assertEqual(records["walkability"]["analysis"]["kind"], "administrative_unit")
        self.assertIsNone(records["walkability"]["analysis"]["resolution"])
        self.assertEqual(records["food_environment"]["boundary_role"], "analysis_unit")

    def test_contract_rejects_detail_with_administrative_source_role(self) -> None:
        records = indicators_for_bundle(
            ["detail/pm25.tif"],
            detail_metadata={
                "pm25": {
                    "source_native_resolution_m": 1113,
                    "source_grid": self._degree_grid(0.01),
                    "statistics": {"p02": 1, "p98": 9},
                }
            },
        )
        records["pm25"]["boundary_role"] = "source_unit"
        issues = validate_indicator_records(records)
        self.assertTrue(any("pm25" in issue for issue in issues))

    def test_one_degree_reducer_fallback_is_never_advertised(self) -> None:
        cases = {
            "pm25": (1113, 1),
            "no2": (1113, 1),
            "heat_hot_days": (11132, 1),
            "rain_annual": (5566, 1),
            "wind": (11132, 1),
        }
        for indicator_id, (native_m, bad_degree) in cases.items():
            with self.subTest(indicator_id=indicator_id):
                record = indicators_for_bundle(
                    [f"detail/{indicator_id}.tif"],
                    detail_metadata={
                        indicator_id: {
                            "source_native_resolution_m": native_m,
                            "source_grid": self._degree_grid(bad_degree),
                            "statistics": {"p02": 1, "p98": 9},
                            "statistics_by_band": {"3": {"p02": 1, "p98": 9}},
                        }
                    },
                )[indicator_id]
                self.assertIsNone(record["detail"])

    def test_contract_rejects_mask_only_for_an_administrative_map(self) -> None:
        records = indicators_for_bundle([])
        records["pm25"]["boundary_role"] = "mask_only"
        issues = validate_indicator_records(records)
        self.assertTrue(any("administrative rendering" in issue for issue in issues))

    def test_stale_native_scale_is_not_advertised(self) -> None:
        records = indicators_for_bundle(
            ["detail/wind.tif"],
            detail_metadata={
                "wind": {
                    "source_native_resolution_m": 9000,
                    "statistics_by_band": {"3": {"p02": 1, "p98": 9}},
                }
            },
        )
        self.assertIsNone(records["wind"]["detail"])
        self.assertEqual(records["wind"]["rendered"]["kind"], "administrative_polygon")

    def test_alan_requires_the_actual_viirs_15_arcsecond_grid(self) -> None:
        old = indicators_for_bundle(
            ["detail/alan.tif"],
            detail_metadata={
                "alan": {
                    "source_native_resolution_m": 463.83,
                    "source_grid": {
                        "crs": "EPSG:4326",
                        "resolution": {"x": 0.004491576, "y": 0.004491576, "unit": "degree"},
                    },
                    "statistics": {"p02": 1, "p98": 9},
                }
            },
        )["alan"]
        canonical = indicators_for_bundle(
            ["detail/alan.tif"],
            detail_metadata={
                "alan": {
                    "source_native_resolution_m": 463.83,
                    "source_grid": {
                        "crs": "EPSG:4326",
                        "resolution": {"x": 1 / 240, "y": 1 / 240, "unit": "degree"},
                    },
                    "statistics": {"p02": 1, "p98": 9},
                }
            },
        )["alan"]
        self.assertIsNone(old["detail"])
        self.assertEqual(canonical["detail"]["type"], "cog")
        self.assertEqual(canonical["detail"]["source_grid"]["crs"], "EPSG:4326")

    def test_declared_native_scales_fix_known_overstatement(self) -> None:
        records = indicators_for_bundle([])
        self.assertEqual(records["alan"]["source"]["resolution"]["value"], 463.83)
        self.assertEqual(records["wind"]["source"]["resolution"]["value"], 11132)
        self.assertEqual(records["green"]["analysis"]["resolution"]["value"], 1000)

    def test_every_indicator_declares_its_publication_target(self) -> None:
        records = indicators_for_bundle([])
        self.assertTrue(records["alan"]["publication_target"]["required_for_production"])
        self.assertTrue(records["healthcare"]["publication_target"]["required_for_production"])
        self.assertFalse(records["poverty_income"]["publication_target"]["required_for_production"])

    def test_city_relative_heat_and_rain_indices_do_not_claim_pixel_support(self) -> None:
        records = indicators_for_bundle([])
        for indicator_id in ("heat", "heat_index", "rain", "rain_index"):
            self.assertEqual(records[indicator_id]["boundary_role"], "component_specific")
            self.assertFalse(
                records[indicator_id]["publication_target"]["required_for_production"]
            )

    def test_spi_stays_administrative_until_its_pixel_time_series_is_built(self) -> None:
        spi = indicators_for_bundle([])["precipitation_spi"]
        self.assertEqual(spi["boundary_role"], "source_unit")
        self.assertFalse(spi["publication_target"]["required_for_production"])

    def test_every_browser_card_has_a_spatial_contract(self) -> None:
        palette = json.loads((ROOT / "webapp" / "public" / "palette.json").read_text())
        self.assertEqual(validate_palette_coverage(palette["exposomes"]), [])

    def test_era5_land_fallback_never_reverts_to_nine_km(self) -> None:
        from exposome.climate.fetch_era5land import (  # noqa: PLC0415
            fetch_era5land_month_server_side,
            fetch_era5land_year,
        )

        self.assertEqual(signature(fetch_era5land_month_server_side).parameters["scale"].default, 11_132)
        self.assertEqual(signature(fetch_era5land_year).parameters["scale"].default, 11_132)

    def test_era5_land_month_windows_stay_under_the_query_abort(self) -> None:
        from exposome.climate.fetch_era5land import _month_date_windows  # noqa: PLC0415

        # 31-day month: contiguous exclusive-end windows covering every day,
        # none longer than 11 days (a full month trips GEE's 5000-element abort).
        windows = _month_date_windows(2015, 1)
        self.assertEqual(
            windows,
            [
                ("2015-01-01", "2015-01-12"),
                ("2015-01-12", "2015-01-23"),
                ("2015-01-23", "2015-02-01"),
            ],
        )
        # December's last window must roll over to January 1st of the next year.
        self.assertEqual(_month_date_windows(2015, 12)[-1][1], "2016-01-01")
        # Leap February covers day 29.
        self.assertEqual(_month_date_windows(2020, 2)[-1], ("2020-02-23", "2020-03-01"))

    def test_global_sources_keep_the_same_native_scale_in_santiago_and_amba(self) -> None:
        from exposome.studies import load_study  # noqa: PLC0415

        scales = {}
        for study_id in ("santiago_communes", "buenos_aires_amba"):
            context = load_study(study_id)
            cfg = context.resolved_config(spatial_units=context.load_spatial_units())
            scales[study_id] = {
                "pm25": cfg["pm25"]["collection"]["scale_meters"],
                "no2": cfg["air_quality"]["collections"]["no2"]["scale_meters"],
                "alan": cfg["alan"]["collection"]["scale_meters"],
                "wind": cfg["wind"]["scale_meters"],
                "rain": cfg["precipitation"]["collection"]["scale_meters"],
            }
        self.assertEqual(scales["santiago_communes"], scales["buenos_aires_amba"])
        self.assertEqual(scales["santiago_communes"], {
            "pm25": 1113,
            "no2": 1113,
            "alan": 463.83,
            "wind": 11132,
            "rain": 5566,
        })


if __name__ == "__main__":
    unittest.main()

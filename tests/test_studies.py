from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.studies import (  # noqa: E402
    StudyConfigError,
    TemporalException,
    load_location,
    load_study,
)
from exposome.studies import _parse_temporal_exceptions  # noqa: E402


class StudyConfigTest(unittest.TestCase):
    def test_new_santiago_study_resolves_location_legacy_and_paths(self) -> None:
        context = load_study("santiago_communes", repo_root_path=REPO_ROOT)

        self.assertEqual(context.study.id, "santiago_communes")
        self.assertEqual(context.city, "santiago")
        self.assertEqual(context.country_code, "CL")
        self.assertEqual(context.expected_units, 52)
        self.assertEqual(context.study.id_column, "spatial_id")
        self.assertEqual(context.study.name_column, "spatial_name")
        self.assertIsNone(context.location.metric_crs)
        self.assertIn("pm25", context.enabled_layers)
        self.assertIsNone(context.legacy_config)
        self.assertIn("air_quality", context.config)
        self.assertFalse(context.study.hidden)
        self.assertEqual(
            context.paths.processed,
            REPO_ROOT / "data" / "processed" / "cl" / "santiago" / "santiago_communes",
        )
        self.assertEqual(
            context.paths.layer_cache("pm25"),
            REPO_ROOT / "cache" / "cl" / "santiago" / "santiago_communes" / "pm25",
        )
        self.assertEqual(
            context.paths.reference,
            REPO_ROOT / "data" / "reference" / "cl" / "santiago" / "santiago_communes",
        )
        self.assertEqual(
            context.paths.provider_raw("acag", "pm25", "v6"),
            REPO_ROOT / "data" / "raw" / "acag" / "pm25" / "v6",
        )
        self.assertEqual(context.config["expected_communes"], 52)
        self.assertEqual(context.config["crs"]["metric"], "auto")

    def test_provider_snapshot_uses_configured_external_payload_root(self) -> None:
        context = load_study("santiago_communes", repo_root_path=REPO_ROOT)
        with patch.dict("os.environ", {"GEMMA_RAW_PAYLOAD_ROOT": "/tmp/gemma-payloads"}):
            store = context.paths.provider_snapshot("acag", "pm25", "v6")
        self.assertEqual(
            store.manifest_root,
            REPO_ROOT / "data" / "raw" / "acag" / "pm25" / "v6",
        )
        self.assertEqual(
            store.payload_root,
            Path("/tmp/gemma-payloads/acag/pm25/v6"),
        )

    def test_buenos_aires_study_accepts_user_provided_variable_unit_count(self) -> None:
        context = load_study("buenos_aires_zipcodes", repo_root_path=REPO_ROOT)

        self.assertEqual(context.country_code, "AR")
        self.assertEqual(context.study.unit_type, "postal_code")
        self.assertIsNone(context.expected_units)
        self.assertEqual(context.study.spatial_source, "user_provided")
        self.assertEqual(context.study.spatial_license, "document_before_execution")
        self.assertTrue(
            str(context.spatial_path).endswith(
                "data/reference/ar/buenos_aires/buenos_aires_zipcodes/"
                "spatial_units.geojson"
            )
        )

    def test_barcelones_noise_pilot_is_one_explicit_partial_unit(self) -> None:
        context = load_study("barcelones_noise_pilot", repo_root_path=REPO_ROOT)
        self.assertEqual(context.location.name, "Barcelonès — piloto MER 2022")
        self.assertEqual(context.expected_units, 1)
        self.assertEqual(context.study.raw["noise_spain"]["source_region"], "cataluna")
        self.assertEqual(context.study.raw["noise_spain"]["coverage"], "partial")
        self.assertEqual(
            context.layer_inputs("noise_spain")["source_manifest"].name,
            "source_manifest.json",
        )

    def test_location_short_name_prefers_new_location_over_legacy_city(self) -> None:
        location = load_location("santiago", repo_root_path=REPO_ROOT)

        self.assertIn("config/locations/cl/santiago.yaml", location.config_path.as_posix())
        self.assertIsNone(location.metric_crs)

    def test_caba_native_study_is_hidden_from_the_city_picker(self) -> None:
        context = load_study("caba_native", repo_root_path=REPO_ROOT)

        self.assertTrue(context.study.hidden)

    def test_sao_paulo_visible_study_has_a_hidden_native_companion(self) -> None:
        visible = load_study("sao_paulo_distritos", repo_root_path=REPO_ROOT)
        native = load_study("sao_paulo_native", repo_root_path=REPO_ROOT)

        self.assertEqual(visible.study.raw["detail"]["native_study"], "sao_paulo_native")
        self.assertTrue(native.is_native)
        self.assertTrue(native.study.hidden)
        self.assertEqual(native.location.id, visible.location.id)
        self.assertEqual(native.aoi_path, visible.spatial_path)

    def test_legacy_city_config_is_a_valid_transitional_study(self) -> None:
        context = load_study("santiago", repo_root_path=REPO_ROOT)

        self.assertEqual(context.study.id, "santiago")
        self.assertEqual(context.expected_units, 52)
        self.assertEqual(context.study.id_column, "name")
        self.assertEqual(context.location.metric_crs, "EPSG:32719")
        self.assertEqual(context.config["region_query"], "Región Metropolitana de Santiago, Chile")

    def test_bogota_localidades_declares_the_los_martires_2019_exception(self) -> None:
        context = load_study("bogota_localidades", repo_root_path=REPO_ROOT)

        self.assertEqual(len(context.study.temporal_exceptions), 1)
        exception = context.study.temporal_exceptions[0]
        self.assertEqual(exception.layer_id, "greenspace_multisource")
        self.assertEqual(exception.indicator, "green")
        self.assertEqual(exception.years, (2019,))
        self.assertTrue(exception.reason)
        self.assertTrue(exception.doc)

    def test_colombia_download_node_studies_share_one_official_urban_unit(self) -> None:
        for aggregate_id, native_id, code in (
            ("santa_marta_urban", "santa_marta_native", "47001"),
            ("cartagena_urban", "cartagena_native", "13001"),
            ("pasto_urban", "pasto_native", "52001"),
        ):
            with self.subTest(study=aggregate_id):
                aggregate = load_study(aggregate_id, repo_root_path=REPO_ROOT)
                native = load_study(native_id, repo_root_path=REPO_ROOT)
                self.assertEqual(aggregate.expected_units, 1)
                self.assertEqual(aggregate.study.unit_type, "dane_cabecera_municipal")
                self.assertEqual(aggregate.study.raw["detail"]["native_study"], native_id)
                self.assertTrue(native.is_native)
                self.assertTrue(native.study.hidden)
                self.assertEqual(native.aoi_path, aggregate.spatial_path)
                self.assertIn(code, aggregate.study.spatial_source)


class TemporalExceptionParsingTest(unittest.TestCase):
    ENABLED = ("greenspace_multisource", "pm25")

    def _entry(self, **overrides: object) -> dict[str, object]:
        entry = {
            "layer_id": "greenspace_multisource",
            "indicator": "green",
            "years": [2019],
            "reason": "Deterministic Dynamic World gap for one locality/year.",
            "doc": "docs/greenspace_multisource_methodology.md#limitations",
        }
        entry.update(overrides)
        return entry

    def test_none_or_empty_yields_no_exceptions(self) -> None:
        self.assertEqual(
            _parse_temporal_exceptions(None, self.ENABLED, Path("study.yaml")), ()
        )

    def test_valid_entry_parses_to_a_temporal_exception(self) -> None:
        result = _parse_temporal_exceptions(
            [self._entry()], self.ENABLED, Path("study.yaml")
        )
        self.assertEqual(
            result,
            (
                TemporalException(
                    layer_id="greenspace_multisource",
                    indicator="green",
                    years=(2019,),
                    reason="Deterministic Dynamic World gap for one locality/year.",
                    doc="docs/greenspace_multisource_methodology.md#limitations",
                ),
            ),
        )

    def test_layer_not_enabled_is_rejected(self) -> None:
        entry = self._entry(layer_id="climate_heat")
        with self.assertRaisesRegex(StudyConfigError, "not enabled"):
            _parse_temporal_exceptions([entry], self.ENABLED, Path("study.yaml"))

    def test_missing_reason_is_rejected(self) -> None:
        entry = self._entry(reason="")
        with self.assertRaisesRegex(StudyConfigError, "reason"):
            _parse_temporal_exceptions([entry], self.ENABLED, Path("study.yaml"))

    def test_missing_doc_is_rejected(self) -> None:
        entry = self._entry(doc="")
        with self.assertRaisesRegex(StudyConfigError, "doc"):
            _parse_temporal_exceptions([entry], self.ENABLED, Path("study.yaml"))

    def test_non_four_digit_year_is_rejected(self) -> None:
        entry = self._entry(years=[19])
        with self.assertRaisesRegex(StudyConfigError, "4-digit"):
            _parse_temporal_exceptions([entry], self.ENABLED, Path("study.yaml"))

    def test_empty_years_list_is_rejected(self) -> None:
        entry = self._entry(years=[])
        with self.assertRaisesRegex(StudyConfigError, "non-empty 'years'"):
            _parse_temporal_exceptions([entry], self.ENABLED, Path("study.yaml"))

    def test_non_list_payload_is_rejected(self) -> None:
        with self.assertRaisesRegex(StudyConfigError, "must be a list"):
            _parse_temporal_exceptions({"layer_id": "x"}, self.ENABLED, Path("study.yaml"))


if __name__ == "__main__":
    unittest.main()

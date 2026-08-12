"""Offline tests for input classification and the geocoding adapter.

The transport is always stubbed.  Nothing in this file may touch the network:
a test that silently reaches Nominatim would violate its usage policy and make
the suite depend on someone else's uptime.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from exposome.geocoding import (
    KIND_ADDRESS,
    KIND_EMPTY,
    KIND_LATLON,
    KIND_POSTAL,
    PRECISION_EXACT,
    PRECISION_LOCALITY,
    PRECISION_ROOFTOP,
    PRECISION_STREET,
    NominatimGeocoder,
    classify_input,
    geocode_lines,
    resolve_postal_code,
)

MAIPU = "Manuel Rodriguez 1085, Maipu, Santiago, Chile"

NOMINATIM_HOUSE = [{
    "lon": "-70.7580", "lat": "-33.5110",
    "class": "place", "type": "house", "addresstype": "house",
    "display_name": "1085, Manuel Rodriguez, Maipu, Santiago, Chile",
    "boundingbox": ["-33.5111", "-33.5109", "-70.7581", "-70.7579"],
}]


class ClassifyTest(unittest.TestCase):
    def test_address_is_the_default(self) -> None:
        result = classify_input(MAIPU)
        self.assertEqual(result.kind, KIND_ADDRESS)

    def test_lat_lon_pair(self) -> None:
        result = classify_input("-33.45, -70.65")
        self.assertEqual(result.kind, KIND_LATLON)
        self.assertAlmostEqual(result.lat, -33.45)
        self.assertAlmostEqual(result.lon, -70.65)

    def test_lat_lon_accepts_whitespace_separator(self) -> None:
        self.assertEqual(classify_input("-33.45 -70.65").kind, KIND_LATLON)

    def test_out_of_range_pair_is_not_coordinates(self) -> None:
        result = classify_input("999.0, 999.0")
        self.assertEqual(result.kind, KIND_ADDRESS)
        self.assertIsNotNone(result.note)

    def test_empty_line(self) -> None:
        self.assertEqual(classify_input("   ").kind, KIND_EMPTY)

    def test_postal_needs_a_declared_country(self) -> None:
        # Five digits alone is ambiguous between MX, ES and PE.
        self.assertEqual(classify_input("06700").kind, KIND_ADDRESS)
        self.assertEqual(classify_input("06700", postal_country="MX").kind, KIND_POSTAL)

    def test_country_prefix_declares_it_inline(self) -> None:
        result = classify_input("MX 06700")
        self.assertEqual(result.kind, KIND_POSTAL)
        self.assertEqual(result.country, "MX")
        self.assertEqual(result.postal_code, "06700")

    def test_chilean_seven_digit_code(self) -> None:
        result = classify_input("CL 7500000")
        self.assertEqual(result.kind, KIND_POSTAL)
        self.assertEqual(result.postal_code, "7500000")

    def test_argentine_cpa(self) -> None:
        result = classify_input("AR C1425DKE")
        self.assertEqual(result.kind, KIND_POSTAL)
        self.assertEqual(result.postal_code, "C1425DKE")

    def test_brazilian_cep_with_and_without_dash(self) -> None:
        for code in ("01310-100", "01310100"):
            with self.subTest(code=code):
                self.assertEqual(classify_input(f"BR {code}").kind, KIND_POSTAL)

    def test_wrong_shape_for_the_country_is_an_address(self) -> None:
        # Five digits is not a Chilean postal code, so it is not silently one.
        self.assertEqual(classify_input("12345", postal_country="CL").kind, KIND_ADDRESS)


class PostalResolutionTest(unittest.TestCase):
    def test_no_vendored_reference_means_unsupported(self) -> None:
        outcome = resolve_postal_code("7500000", "CL")
        self.assertEqual(outcome["status"], "unsupported_country")

    def test_unknown_country(self) -> None:
        self.assertEqual(resolve_postal_code("1234", "ZZ")["status"], "unsupported_country")

    def test_resolves_from_a_local_reference(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tmp:
            reference = Path(tmp) / "mx"
            reference.mkdir()
            (reference / "postal_units.json").write_text(json.dumps({
                "records": {"06700": {"spatial_id": "09015", "spatial_name": "Cuauhtemoc"}}
            }))
            outcome = resolve_postal_code("06700", "MX", reference_dir=Path(tmp))
            self.assertEqual(outcome["status"], "resolved")
            self.assertEqual(outcome["spatial_id"], "09015")
            # A postal code resolves to an areal unit, never to a point.
            self.assertEqual(outcome["support"], "administrative_unit")

    def test_absent_code_is_not_found_not_unsupported(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as tmp:
            reference = Path(tmp) / "mx"
            reference.mkdir()
            (reference / "postal_units.json").write_text(json.dumps({"records": {}}))
            outcome = resolve_postal_code("06700", "MX", reference_dir=Path(tmp))
            self.assertEqual(outcome["status"], "not_found")


class NominatimTest(unittest.TestCase):
    def _geocoder(self, payload, *, cache_dir=None, calls=None):
        def transport(url, params, headers):
            self.assertIn("User-Agent", headers)  # required by the usage policy
            if calls is not None:
                calls.append(params)
            return payload

        return NominatimGeocoder(
            transport=transport, cache_dir=cache_dir, min_interval_s=0
        )

    def test_house_match_is_rooftop(self) -> None:
        result = self._geocoder(NOMINATIM_HOUSE).geocode(MAIPU)
        self.assertEqual(result.precision, PRECISION_ROOFTOP)
        self.assertAlmostEqual(result.lat, -33.5110)
        self.assertIsNotNone(result.matched_address)

    def test_accuracy_comes_from_the_provider_bounding_box(self) -> None:
        result = self._geocoder(NOMINATIM_HOUSE).geocode(MAIPU)
        # A ~20 m box should not claim kilometre accuracy.
        self.assertLess(result.accuracy_m, 100)
        self.assertGreater(result.accuracy_m, 0)

    def test_street_and_locality_precision(self) -> None:
        street = [{**NOMINATIM_HOUSE[0], "addresstype": "road"}]
        locality = [{**NOMINATIM_HOUSE[0], "addresstype": "city"}]
        self.assertEqual(self._geocoder(street).geocode("x").precision, PRECISION_STREET)
        self.assertEqual(
            self._geocoder(locality).geocode("x").precision, PRECISION_LOCALITY
        )

    def test_no_match_is_data_not_an_exception(self) -> None:
        result = self._geocoder([]).geocode("nowhere")
        self.assertIsNone(result.lon)
        self.assertEqual(result.error, "no_match")

    def test_transport_failure_is_captured(self) -> None:
        def failing(url, params, headers):
            raise OSError("connection reset")

        geocoder = NominatimGeocoder(transport=failing, min_interval_s=0)
        result = geocoder.geocode("x")
        self.assertIsNone(result.lon)
        self.assertIn("connection reset", result.error)

    def test_country_and_viewbox_narrow_the_query(self) -> None:
        calls: list[dict] = []
        geocoder = self._geocoder(NOMINATIM_HOUSE, calls=calls)
        geocoder.geocode(MAIPU, country_code="cl", viewbox=(-71.8, -34.5, -69.8, -32.9))
        self.assertEqual(calls[0]["countrycodes"], "cl")
        self.assertEqual(calls[0]["bounded"], "1")

    def test_repeated_queries_hit_the_cache(self) -> None:
        calls: list[dict] = []
        with tempfile.TemporaryDirectory() as tmp:
            geocoder = self._geocoder(NOMINATIM_HOUSE, cache_dir=Path(tmp), calls=calls)
            first = geocoder.geocode(MAIPU)
            second = geocoder.geocode(MAIPU)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first.lat, second.lat)


class GeocodeLinesTest(unittest.TestCase):
    def test_coordinates_need_no_network(self) -> None:
        rows = geocode_lines(["-33.45, -70.65"])
        self.assertEqual(rows[0]["status"], "ok")
        self.assertEqual(rows[0]["geocode_precision"], PRECISION_EXACT)
        self.assertEqual(rows[0]["geocode_accuracy_m"], 0.0)

    def test_addresses_are_refused_until_opted_in(self) -> None:
        rows = geocode_lines([MAIPU])
        self.assertEqual(rows[0]["status"], "geocoding_not_enabled")
        self.assertIsNone(rows[0]["lon"])

    def test_addresses_resolve_once_enabled(self) -> None:
        geocoder = NominatimGeocoder(
            transport=lambda url, params, headers: NOMINATIM_HOUSE, min_interval_s=0
        )
        rows = geocode_lines([MAIPU], geocoder=geocoder, allow_network=True)
        self.assertEqual(rows[0]["status"], "ok")
        self.assertEqual(rows[0]["geocode_precision"], PRECISION_ROOFTOP)

    def test_mixed_batch_keeps_row_order_and_ids(self) -> None:
        rows = geocode_lines(
            ["-33.45, -70.65", "CL 7500000", MAIPU, ""], postal_country=None
        )
        self.assertEqual([row["input_kind"] for row in rows],
                         [KIND_LATLON, KIND_POSTAL, KIND_ADDRESS, KIND_EMPTY])
        self.assertEqual(rows[0]["query_id"], "point_0001")
        self.assertEqual(rows[3]["query_id"], "point_0004")

    def test_postal_lines_report_why_they_failed(self) -> None:
        rows = geocode_lines(["CL 7500000"])
        self.assertEqual(rows[0]["status"], "unsupported_country")


if __name__ == "__main__":
    unittest.main()

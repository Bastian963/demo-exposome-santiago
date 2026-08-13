from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "migrations" / "build_colombia_urban_references.py"
SPEC = importlib.util.spec_from_file_location("build_colombia_urban_references", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _feature_collection(city_spec) -> dict:
    west, south = -74.25, 11.20
    east, north = -74.15, 11.30
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "dpto_ccdgo": city_spec.dane_code[:2],
                    "mpio_ccdgo": city_spec.dane_code[2:],
                    "mpio_cdpmp": city_spec.dane_code,
                    "clas_ccdgo": "1",
                    "zu_ccdgo": "000",
                    "zu_cdivi": f"{city_spec.dane_code}000",
                    "zu_cnmbre": city_spec.name.upper(),
                    "zu_ccnct": f"{city_spec.dane_code}100000000",
                    "zu_narea": 123.0,
                    "zu_naltd": 5.0,
                    "zu_nano": 2024,
                    "Categoria": "Cabecera Municipal",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [west, south],
                            [east, south],
                            [east, north],
                            [west, north],
                            [west, south],
                        ]
                    ],
                },
            }
        ],
    }


def _populated_center(city_spec) -> dict:
    feature = json.loads(json.dumps(_feature_collection(city_spec)["features"][0]))
    feature["properties"].update(
        {
            "clas_ccdgo": "2",
            "zu_ccdgo": "001",
            "zu_cdivi": f"{city_spec.dane_code}001",
            "zu_cnmbre": "CENTRO POBLADO",
            "zu_ccnct": f"{city_spec.dane_code}200000001",
            "Categoria": "Centro Poblado",
        }
    )
    return feature


def _discovery_response(city_spec) -> dict:
    return {
        "features": [
            {
                "attributes": {
                    "OBJECTID": 100,
                    "mpio_cdpmp": city_spec.dane_code,
                    "clas_ccdgo": "2",
                    "Categoria": "Centro Poblado",
                }
            },
            {
                "attributes": {
                    "OBJECTID": 7418,
                    "mpio_cdpmp": city_spec.dane_code,
                    "clas_ccdgo": "1",
                    "Categoria": "Cabecera Municipal",
                }
            },
        ]
    }


class ColombiaUrbanReferenceTests(unittest.TestCase):
    def test_declares_three_distinct_official_codes(self) -> None:
        self.assertEqual(
            {spec.slug: spec.dane_code for spec in module.CITY_SPECS},
            {"santa_marta": "47001", "cartagena": "13001", "pasto": "52001"},
        )

    def test_all_official_fallbacks_use_feature_server_geometry(self) -> None:
        self.assertTrue(all("/FeatureServer/305/query" in url for url in module.SERVICE_URLS))

    def test_payload_rejects_wrong_municipality(self) -> None:
        spec = module.CITY_BY_SLUG["santa_marta"]
        payload = _feature_collection(spec)
        payload["features"][0]["properties"]["mpio_cdpmp"] = "13001"
        with self.assertRaisesRegex(ValueError, "found 0"):
            module._validate_payload(payload, spec)

    def test_query_uses_spatial_envelope_without_quoted_sql(self) -> None:
        spec = module.CITY_BY_SLUG["santa_marta"]
        params = module._discovery_query_params(spec)

        self.assertEqual(params["where"], "1=1")
        self.assertEqual(params["geometry"], "-74.36,11.06,-74.05,11.39")
        self.assertEqual(params["geometryType"], "esriGeometryEnvelope")
        self.assertEqual(params["returnGeometry"], "false")
        self.assertNotIn("'", params["where"])

    def test_discovery_selects_only_the_official_cabecera_object_id(self) -> None:
        spec = module.CITY_BY_SLUG["santa_marta"]

        object_id = module._select_object_id(_discovery_response(spec), spec)

        self.assertEqual(object_id, "7418")
        params = module._feature_query_params(object_id)
        self.assertEqual(params["objectIds"], "7418")
        self.assertEqual(params["returnGeometry"], "true")
        self.assertEqual(params["returnTrueCurves"], "false")

    def test_payload_accepts_nearby_non_cabecera_features(self) -> None:
        spec = module.CITY_BY_SLUG["santa_marta"]
        payload = _feature_collection(spec)
        payload["features"].insert(0, _populated_center(spec))

        selected = module._validate_payload(payload, spec)

        self.assertEqual(selected["properties"]["clas_ccdgo"], "1")

    def test_download_falls_back_to_second_official_dane_service(self) -> None:
        spec = module.CITY_BY_SLUG["santa_marta"]
        discovery = Mock()
        discovery.json.return_value = _discovery_response(spec)
        discovery.raise_for_status.return_value = None
        response = Mock()
        response.json.return_value = _feature_collection(spec)
        response.raise_for_status.return_value = None
        response.url = module._prepared_url(
            spec,
            module.SERVICE_URLS[1],
            object_id="7418",
        )
        with patch.object(
            module.requests,
            "get",
            side_effect=[
                module.requests.ConnectTimeout("primary down"),
                discovery,
                response,
            ],
        ) as get:
            result = module._download_source(
                spec,
                connect_timeout_seconds=1,
                read_timeout_seconds=2,
                attempts_per_service=1,
                retry_wait_seconds=0,
            )

        self.assertIs(result, response)
        self.assertEqual(get.call_count, 3)
        self.assertEqual(get.call_args_list[0].args[0], module.SERVICE_URLS[0])
        self.assertEqual(get.call_args_list[1].args[0], module.SERVICE_URLS[1])
        self.assertEqual(get.call_args_list[2].args[0], module.SERVICE_URLS[1])
        self.assertEqual(get.call_args_list[2].kwargs["params"]["objectIds"], "7418")
        self.assertEqual(get.call_args_list[0].kwargs["timeout"], (1, 2))

    def test_build_reference_is_offline_and_resume_safe(self) -> None:
        spec = module.CITY_BY_SLUG["santa_marta"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = module._snapshot_root(root, spec)
            source = snapshot / "zona_urbana.geojson"
            source.parent.mkdir(parents=True)
            payload = _feature_collection(spec)
            payload["features"].insert(0, _populated_center(spec))
            source.write_text(json.dumps(payload), encoding="utf-8")
            asset = module.build_raw_source_asset(
                snapshot,
                source,
                url=module._prepared_url(spec),
            )
            manifest = module.write_source_manifest(
                snapshot,
                provider="dane",
                dataset=f"mgn-zona-urbana-{spec.dane_code}",
                version=module.SOURCE_VERSION,
                license_name=module.SOURCE_LICENSE,
                assets=[asset],
            )

            first = module._build_reference(root, spec, source, manifest)
            first_bytes = first.read_bytes()
            second = module._build_reference(root, spec, source, manifest)

            self.assertEqual(first, second)
            self.assertEqual(first_bytes, second.read_bytes())
            collection = json.loads(first.read_text(encoding="utf-8"))
            properties = collection["features"][0]["properties"]
            self.assertEqual(properties["unit_id"], "47001")
            self.assertEqual(properties["unit_name"], "Santa Marta")
            metadata = json.loads((first.parent / "metadata.json").read_text())
            self.assertEqual(metadata["unit_count"], 1)
            self.assertEqual(metadata["source_geometry_sha256"], module._sha256(source))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


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


class ColombiaUrbanReferenceTests(unittest.TestCase):
    def test_declares_three_distinct_official_codes(self) -> None:
        self.assertEqual(
            {spec.slug: spec.dane_code for spec in module.CITY_SPECS},
            {"santa_marta": "47001", "cartagena": "13001", "pasto": "52001"},
        )

    def test_payload_rejects_wrong_municipality(self) -> None:
        spec = module.CITY_BY_SLUG["santa_marta"]
        payload = _feature_collection(spec)
        payload["features"][0]["properties"]["mpio_cdpmp"] = "13001"
        with self.assertRaisesRegex(ValueError, "code mismatch"):
            module._validate_payload(payload, spec)

    def test_build_reference_is_offline_and_resume_safe(self) -> None:
        spec = module.CITY_BY_SLUG["santa_marta"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = module._snapshot_root(root, spec)
            source = snapshot / "zona_urbana.geojson"
            source.parent.mkdir(parents=True)
            source.write_text(json.dumps(_feature_collection(spec)), encoding="utf-8")
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

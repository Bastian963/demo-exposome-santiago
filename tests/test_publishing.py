from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.publishing import (  # noqa: E402
    _relative_assets,
    _vector_contour_metadata,
    aggregate_provenance_issues,
    build_catalog,
    publish_study,
    write_catalog,
    _write_temporal_assets,
)
from exposome.artifact_contract import write_layer_bundle_manifest  # noqa: E402
from exposome.execution import LayerBuildResult, ProducedAsset  # noqa: E402
from exposome.layers import load_layer_catalog  # noqa: E402
from exposome.studies import TemporalException, load_study  # noqa: E402
from exposome.temporal_exposomes import TemporalIndicatorSpec, TemporalSpec  # noqa: E402


RUN_ARTIFACT_TESTS = os.environ.get("EXPOSOME_RUN_ARTIFACT_TESTS") == "1"


class PublishingContractTests(unittest.TestCase):
    def test_vector_tile_tree_uses_descriptor_without_bloating_public_file_list(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            detail = bundle / "detail"
            tile = detail / "noise_lden" / "11" / "1080" / "760.pbf"
            tile.parent.mkdir(parents=True)
            tile.write_bytes(b"mvt")
            descriptor = detail / "noise_lden.vector_contours.json"
            descriptor.write_text(json.dumps({"type": "vector_contours"}), encoding="utf-8")
            record = _relative_assets(detail, bundle, "detail")
            metadata = _vector_contour_metadata(detail)
        self.assertEqual(record["type"], "directory")
        self.assertIn("noise_lden.vector_contours.json", record["files"])
        self.assertNotIn("noise_lden/11/1080/760.pbf", record["files"])
        self.assertEqual(metadata["noise_lden"]["type"], "vector_contours")

    def test_production_blocks_incomplete_required_annual_spatial_series(self) -> None:
        indicator = TemporalIndicatorSpec(
            exposome_id="alan",
            value_column="alan_radiance_mean",
            detail_kind="native_raster",
            detail_required_for_production=True,
        )
        spec = TemporalSpec(
            "alan", "alan", 2023, 2024, "VIIRS", (indicator,)
        )
        context = SimpleNamespace(
            study=SimpleNamespace(
                id="example",
                period={"start_date": "2023-01-01", "end_date": "2024-12-31"},
                temporal_exceptions=(),
            )
        )
        with tempfile.TemporaryDirectory() as tmp, patch(
            "exposome.temporal_exposomes.completed_annual_products",
            return_value=[],
        ), patch(
            "exposome.temporal_exposomes.discover_temporal_specs",
            return_value=(spec,),
        ):
            with self.assertRaisesRegex(ValueError, "Annual spatial publication is incomplete"):
                _write_temporal_assets(context, Path(tmp))

    def test_documented_exception_lets_publish_skip_the_declared_year(self) -> None:
        indicator = TemporalIndicatorSpec(
            exposome_id="green",
            value_column="green_total_pct",
            detail_required_for_production=True,
        )
        spec = TemporalSpec(
            "greenspace_multisource",
            "greenspace_multisource",
            2023,
            2024,
            "Dynamic World",
            (indicator,),
        )
        exception = TemporalException(
            layer_id="greenspace_multisource",
            indicator="green",
            years=(2023,),
            reason="Deterministic Dynamic World gap for one locality/year.",
            doc="docs/greenspace_multisource_methodology.md#limitations",
        )
        context = SimpleNamespace(
            study=SimpleNamespace(
                id="example",
                period={"start_date": "2023-01-01", "end_date": "2024-12-31"},
                temporal_exceptions=(exception,),
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            year_dir = tmp_path / "source" / "2024"
            year_dir.mkdir(parents=True)
            table_path = year_dir / "annual.csv"
            pd.DataFrame(
                {
                    "spatial_id": ["001", "002"],
                    "spatial_name": ["A", "B"],
                    "year": [2024, 2024],
                    "green_total_pct": [10.5, 20.5],
                }
            ).to_csv(table_path, index=False)
            (year_dir / "manifest.json").write_text("{}", encoding="utf-8")

            with patch(
                "exposome.temporal_exposomes.completed_annual_products",
                return_value=[(spec, 2024, {"sha256": "deadbeef"}, table_path)],
            ), patch(
                "exposome.temporal_exposomes.discover_temporal_specs",
                return_value=(spec,),
            ):
                _, temporal = _write_temporal_assets(context, tmp_path / "bundle")

        record = temporal["green"]
        self.assertEqual(record["expected_years"], ["2023", "2024"])
        self.assertEqual(record["excepted_years"], ["2023"])
        self.assertEqual(
            record["exceptions"],
            [
                {
                    "year": "2023",
                    "reason": "Deterministic Dynamic World gap for one locality/year.",
                    "doc": "docs/greenspace_multisource_methodology.md#limitations",
                }
            ],
        )
        self.assertEqual(sorted(record["years"].keys()), ["2024"])

    def test_exception_does_not_waive_other_missing_years(self) -> None:
        indicator = TemporalIndicatorSpec(
            exposome_id="green",
            value_column="green_total_pct",
            detail_required_for_production=True,
        )
        spec = TemporalSpec(
            "greenspace_multisource",
            "greenspace_multisource",
            2022,
            2024,
            "Dynamic World",
            (indicator,),
        )
        exception = TemporalException(
            layer_id="greenspace_multisource",
            indicator="green",
            years=(2023,),
            reason="Deterministic Dynamic World gap for one locality/year.",
            doc="docs/greenspace_multisource_methodology.md#limitations",
        )
        context = SimpleNamespace(
            study=SimpleNamespace(
                id="example",
                period={"start_date": "2022-01-01", "end_date": "2024-12-31"},
                temporal_exceptions=(exception,),
            )
        )
        with tempfile.TemporaryDirectory() as tmp, patch(
            "exposome.temporal_exposomes.completed_annual_products",
            return_value=[],
        ), patch(
            "exposome.temporal_exposomes.discover_temporal_specs",
            return_value=(spec,),
        ):
            with self.assertRaises(ValueError) as raised:
                _write_temporal_assets(context, Path(tmp))
        message = str(raised.exception)
        self.assertIn("2022", message)
        self.assertIn("2024", message)
        self.assertNotIn("2023", message)

    @unittest.skipUnless(RUN_ARTIFACT_TESTS, "requires a materialized Santiago release")
    def test_santiago_bundle_is_namespaced_and_self_describing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = publish_study(
                load_study("santiago_communes"), output_root=tmp, clean=True
            )
            expected = Path(tmp) / "v1" / "cl" / "santiago" / "santiago_communes"
            self.assertEqual(result.path, expected)
            manifest = json.loads((expected / "manifest.json").read_text())
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(manifest["study_id"], "santiago_communes")
            self.assertEqual(manifest["mode"], "aggregate")
            self.assertIn("master_geojson", manifest["assets"])
            self.assertIn("release_manifest", manifest["assets"])
            self.assertIn("air_quality_pm25", manifest["layers"])
            self.assertTrue(manifest["layers"]["air_quality_pm25"]["available"])
            self.assertNotIn("pm25", manifest["layers"])
            master = expected / manifest["assets"]["master_geojson"]["path"]
            self.assertTrue(master.exists())
            self.assertTrue(
                (expected / manifest["assets"]["release_manifest"]["path"]).exists()
            )
            self.assertEqual(
                manifest["assets"]["master_geojson"]["sha256"],
                __import__("hashlib").sha256(master.read_bytes()).hexdigest(),
            )
            pm25 = manifest["spatial_indicators"]["pm25"]
            self.assertEqual(pm25["boundary_role"], "mask_only")
            if pm25["detail"] and pm25["detail"]["type"] == "cog":
                self.assertIn("color_domain", pm25["detail"])

    @unittest.skipUnless(RUN_ARTIFACT_TESTS, "requires a materialized Santiago release")
    def test_catalog_separates_native_and_postal_studies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            publish_study(load_study("santiago_communes"), output_root=tmp)
            catalog = build_catalog(repo_root=ROOT, output_root=tmp)
            path = write_catalog(catalog, tmp)
            self.assertTrue(path.exists())
            records = {record["study_id"]: record for record in catalog["studies"]}
            self.assertTrue(records["santiago_communes"]["available"])
            self.assertFalse(records["buenos_aires_zipcodes"]["available"])
            self.assertEqual(records["caba_native"]["mode"], "native")
            self.assertEqual(catalog["cities"][0]["continent"], "south_america")

    def test_aggregate_study_without_master_cannot_be_published(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                publish_study(load_study("buenos_aires_zipcodes"), output_root=tmp)

    def test_provider_sidecars_must_match_resolved_settings(self) -> None:
        context = load_study("lima_distritos")
        with tempfile.TemporaryDirectory() as tmp:
            processed = Path(tmp) / "processed"
            catalog = load_layer_catalog()

            def write_bundle(layer_id: str, metadata: dict) -> None:
                layer_dir = processed / layer_id
                layer_dir.mkdir(parents=True, exist_ok=True)
                metadata_path = layer_dir / f"{layer_id}_metadata.json"
                metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
                spec = catalog.get(layer_id)
                required = list((spec.master or {}).get("required_columns", ()))
                table = layer_dir / f"{layer_id}.csv"
                table.write_text(
                    ",".join(["spatial_id", *required])
                    + "\n"
                    + ",".join(["1", *(["0"] * len(required))])
                    + "\n",
                    encoding="utf-8",
                )
                write_layer_bundle_manifest(
                    isolated,
                    spec,
                    layer_dir,
                    LayerBuildResult(
                        (
                            ProducedAsset(table, "primary_table"),
                            ProducedAsset(metadata_path, "metadata"),
                        )
                    ),
                    execution_fingerprint="test-fingerprint",
                )

            isolated = replace(
                context,
                paths=replace(context.paths, processed=processed),
            )
            for layer_id, source in (
                ("climate_heat", "openmeteo"),
                ("wind", "ECMWF/ERA5/HOURLY via GEE"),
                ("alan", "VIIRS DNB"),
            ):
                write_bundle(
                    layer_id,
                    {
                        "source": source,
                        "resolution_m": 500 if layer_id == "alan" else None,
                    },
                )
            issues = aggregate_provenance_issues(isolated)
            self.assertTrue(any("climate_heat" in issue for issue in issues))
            self.assertTrue(any("wind" in issue for issue in issues))
            self.assertTrue(any("alan" in issue for issue in issues))

            write_bundle("climate_heat", {"source": "era5land"})
            write_bundle("wind", {"source": "ECMWF/ERA5_LAND/HOURLY via GEE"})
            write_bundle("alan", {"source": "VIIRS DNB", "resolution_m": 463.83})
            self.assertEqual(aggregate_provenance_issues(isolated), [])


@unittest.skipUnless(RUN_ARTIFACT_TESTS, "requires a materialized Santiago release")
class SantiagoBundleContentTests(unittest.TestCase):
    """Publish Santiago once and inspect the resulting bundle contents.

    A single publish is shared across assertions because copying the
    (gitignored) subcomuna/ compatibility assets is not cheap.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        result = publish_study(
            load_study("santiago_communes"), output_root=cls._tmp.name, clean=True
        )
        cls.bundle = result.path
        cls.manifest = json.loads((cls.bundle / "manifest.json").read_text())

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_published_master_features_have_web_identity(self) -> None:
        master = json.loads((self.bundle / "master.geojson").read_text())
        slugs = set()
        for feature in master["features"]:
            props = feature["properties"]
            self.assertIn("slug", props)
            self.assertIn("name", props)
            slugs.add(props["slug"])
        profile_stems = {p.stem for p in (self.bundle / "profiles").glob("*.json")}
        self.assertEqual(slugs, profile_stems)
        for expected in ("nunoa", "penalolen", "estacion_central"):
            self.assertIn(expected, slugs)

    def test_published_manifest_lists_master_columns(self) -> None:
        columns = self.manifest["columns"]
        for expected in ("pm25_mean", "nse_index", "slug"):
            self.assertIn(expected, columns)

    def test_bundle_uses_the_canonical_master_release(self) -> None:
        canonical = ROOT / "data" / "processed" / "cl" / "santiago" / "santiago_communes"
        self.assertEqual(
            (canonical / "master.csv").read_bytes(),
            (self.bundle / "master.csv").read_bytes(),
        )
        self.assertTrue((self.bundle / "release_manifest.json").is_file())

    def test_santiago_bundle_includes_subcomuna_and_zipcodes(self) -> None:
        self.assertTrue((self.bundle / "subcomuna" / "pm25.geojson").exists())
        self.assertTrue((self.bundle / "zipcodes.json").exists())

    def test_sources_follow_the_canonical_info_panel_schema(self) -> None:
        payload = json.loads((self.bundle / "sources.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 2)
        sources = payload["sources"]
        # entries are emitted under the layer_id AND its webapp alias
        self.assertIn("air_quality_pm25", sources)
        self.assertIn("pm25", sources)
        self.assertEqual(sources["pm25"]["layer_id"], "air_quality_pm25")
        for key, entry in sources.items():
            for field in ("name", "url", "license", "spatial_resolution",
                          "temporal_coverage", "validation"):
                self.assertIsInstance(entry.get(field), str, f"{key}.{field}")
            self.assertFalse(
                entry["name"].startswith("{"), f"{key}.name is a stringified dict"
            )
        self.assertIn("bibtex", sources["pm25"])
        self.assertEqual(sources["pm25"]["doi"], "10.1289/EHP7394")

    def test_methodology_published_under_layer_id_and_alias(self) -> None:
        methodology = self.bundle / "methodology"
        # main.js requests exposomeDataId('pm25') = air_quality_pm25
        self.assertTrue((methodology / "air_quality_pm25.json").is_file())
        self.assertTrue((methodology / "pm25.json").is_file())
        payload = json.loads(
            (methodology / "air_quality_pm25.json").read_text(encoding="utf-8")
        )
        self.assertEqual(payload["id"], "air_quality_pm25")
        self.assertTrue(payload["sections"])
        titles = [section["title"] for section in payload["sections"]]
        self.assertIn("Limitaciones", titles)

    def test_published_bundle_passes_info_panel_validation(self) -> None:
        from exposome.info_validation import validate_bundle

        errors, warnings = validate_bundle(self.bundle)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


class NonSantiagoAggregateProfilesTests(unittest.TestCase):
    @unittest.skipUnless(RUN_ARTIFACT_TESTS, "requires a materialized Buenos Aires release")
    def test_non_santiago_bundle_publishes_profiles_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = publish_study(load_study("buenos_aires_comunas"), output_root=tmp, clean=True)
            bundle = result.path
            manifest = json.loads((bundle / "manifest.json").read_text())
            self.assertIn("profiles", manifest["assets"])
            profile_files = list((bundle / "profiles").glob("*.json"))
            self.assertEqual(len(profile_files), 15)
            master = json.loads((bundle / "master.geojson").read_text())
            slugs = {f["properties"]["slug"] for f in master["features"]}
            profile_stems = {p.stem for p in profile_files}
            self.assertEqual(slugs, profile_stems)


class AmbaOutcomePublishingTests(unittest.TestCase):
    @unittest.skipUnless(RUN_ARTIFACT_TESTS, "requires materialized AMBA local layers")
    def test_amba_bundle_separates_outcomes_and_uses_local_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = publish_study(load_study("buenos_aires_amba"), output_root=tmp, clean=True)
            manifest = json.loads((result.path / "manifest.json").read_text())
            self.assertIn("outcomes_catalog", manifest["assets"])
            self.assertIn("outcome_layers", manifest["assets"])
            self.assertGreaterEqual(
                len([column for column in manifest["columns"] if column.startswith("crime_")]),
                54,
            )
            sources = (result.path / "sources.json").read_text(encoding="utf-8").lower()
            axes = (result.path / "location_profile_axes.json").read_text(encoding="utf-8").lower()
            self.assertNotIn("santiago", sources)
            self.assertNotIn("santiago", axes)
            self.assertTrue(manifest["layers"]["community_violence"]["available"])
            for layer_id in ("community_safety", "community_violence"):
                methodology = result.path / "methodology" / f"{layer_id}.json"
                self.assertTrue(methodology.is_file())
                payload = json.loads(methodology.read_text(encoding="utf-8"))
                self.assertTrue(payload["sections"])
            for outcome in ("suicide_mortality", "road_traffic_mortality"):
                layer = json.loads((result.path / "outcomes" / f"{outcome}.geojson").read_text())
                columns = set(layer["features"][0]["properties"])
                self.assertFalse(any("count" in column or "person" in column for column in columns))
                self.assertTrue((result.path / "methodology" / f"{outcome}.json").is_file())


class MultiLocationCatalogTests(unittest.TestCase):
    def test_two_studies_in_different_locations_get_two_catalog_cities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            locations_dir = root / "config" / "locations" / "zz"
            studies_dir = root / "config" / "studies"
            locations_dir.mkdir(parents=True)
            studies_dir.mkdir(parents=True)
            for city_id, name in (("cityone", "City One"), ("citytwo", "City Two")):
                (locations_dir / f"{city_id}.yaml").write_text(
                    f"id: {city_id}\n"
                    f"name: {name}\n"
                    "country: Testland\n"
                    "country_code: ZZ\n"
                    "bbox:\n"
                    "  west: 0\n"
                    "  south: 0\n"
                    "  east: 1\n"
                    "  north: 1\n",
                    encoding="utf-8",
                )
                (studies_dir / f"{city_id}_study.yaml").write_text(
                    f"id: {city_id}_study\n"
                    f"location: zz/{city_id}\n"
                    "mode: aggregate\n"
                    "spatial:\n"
                    "  path: fake.geojson\n"
                    "  expected_units: 1\n"
                    "layers: []\n",
                    encoding="utf-8",
                )
            output_root = root / "published"
            for study_id in ("cityone_study", "citytwo_study"):
                bundle = output_root / "v1" / "zz" / study_id.replace("_study", "") / study_id
                bundle.mkdir(parents=True)
                (bundle / "manifest.json").write_text(json.dumps({"layers": {}}), encoding="utf-8")

            catalog = build_catalog(repo_root=root, output_root=output_root)

            city_slugs = sorted(city["slug"] for city in catalog["cities"])
            self.assertEqual(city_slugs, ["cityone", "citytwo"])
            self.assertTrue(all(city["available"] for city in catalog["cities"]))


class HiddenStudyCatalogTests(unittest.TestCase):
    def test_catalog_places_spain_in_europe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            locations_dir = root / "config" / "locations" / "es"
            studies_dir = root / "config" / "studies"
            locations_dir.mkdir(parents=True)
            studies_dir.mkdir(parents=True)
            (locations_dir / "testcity.yaml").write_text(
                "id: testcity\n"
                "name: Test City\n"
                "country: España\n"
                "country_code: ES\n"
                "bbox:\n"
                "  west: 0\n"
                "  south: 0\n"
                "  east: 1\n"
                "  north: 1\n",
                encoding="utf-8",
            )
            (studies_dir / "testcity_study.yaml").write_text(
                "id: testcity_study\n"
                "location: es/testcity\n"
                "mode: aggregate\n"
                "spatial:\n"
                "  path: fake.geojson\n"
                "  expected_units: 1\n"
                "layers: []\n",
                encoding="utf-8",
            )
            output_root = root / "published"
            bundle = output_root / "v1" / "es" / "testcity" / "testcity_study"
            bundle.mkdir(parents=True)
            (bundle / "manifest.json").write_text(json.dumps({"layers": {}}), encoding="utf-8")

            catalog = build_catalog(repo_root=root, output_root=output_root)

            self.assertEqual(catalog["cities"][0]["continent"], "europe")
            self.assertEqual(catalog["studies"][0]["continent"], "europe")

    def test_hidden_study_is_excluded_from_catalog_cities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            locations_dir = root / "config" / "locations" / "zz"
            studies_dir = root / "config" / "studies"
            locations_dir.mkdir(parents=True)
            studies_dir.mkdir(parents=True)
            (locations_dir / "testcity.yaml").write_text(
                "id: testcity\n"
                "name: Test City\n"
                "country: Testland\n"
                "country_code: ZZ\n"
                "bbox:\n"
                "  west: 0\n"
                "  south: 0\n"
                "  east: 1\n"
                "  north: 1\n",
                encoding="utf-8",
            )
            (studies_dir / "testcity_primary.yaml").write_text(
                "id: testcity_primary\n"
                "location: zz/testcity\n"
                "mode: aggregate\n"
                "spatial:\n"
                "  path: fake.geojson\n"
                "  expected_units: 1\n"
                "layers: []\n",
                encoding="utf-8",
            )
            (studies_dir / "testcity_secondary.yaml").write_text(
                "id: testcity_secondary\n"
                "location: zz/testcity\n"
                "mode: aggregate\n"
                "hidden: true\n"
                "spatial:\n"
                "  path: fake.geojson\n"
                "  expected_units: 1\n"
                "layers: []\n",
                encoding="utf-8",
            )
            output_root = root / "published"
            for study_id in ("testcity_primary", "testcity_secondary"):
                bundle = output_root / "v1" / "zz" / "testcity" / study_id
                bundle.mkdir(parents=True)
                (bundle / "manifest.json").write_text(
                    json.dumps({"layers": {}}), encoding="utf-8"
                )

            catalog = build_catalog(repo_root=root, output_root=output_root)

            city_slugs = [city["slug"] for city in catalog["cities"]]
            self.assertEqual(city_slugs, ["testcity"])
            by_id = {study["study_id"]: study for study in catalog["studies"]}
            self.assertFalse(by_id["testcity_primary"]["hidden"])
            self.assertTrue(by_id["testcity_secondary"]["hidden"])
            self.assertTrue(by_id["testcity_secondary"]["available"])


if __name__ == "__main__":
    unittest.main()

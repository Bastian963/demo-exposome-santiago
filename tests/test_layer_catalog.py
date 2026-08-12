from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.layers import (  # noqa: E402
    LayerCategory,
    PreflightStatus,
    build_master_manifest,
    build_run_plan,
    execute_run_plan,
    load_layer_catalog,
    normalize_layer_outputs,
    preflight_layers,
    prepare_boundary_cache,
    render_layer_command,
)
from exposome.runners import collect_legacy_assets, has_importable_runner  # noqa: E402


def _context(
    root: Path,
    *,
    country: str = "AR",
    enabled_layers: tuple[str, ...] = ("pm25",),
    nominal_resolution_m: int = 1000,
) -> SimpleNamespace:
    spatial_path = root / "units.geojson"
    spatial_path.touch()
    study = SimpleNamespace(
        id="test_zipcodes",
        spatial_path=spatial_path,
        spatial_layer=None,
        id_column="code",
        name_column="label",
        unit_type="postal_code",
        expected_units=2,
        enabled_layers=enabled_layers,
        raw={"spatial": {"nominal_resolution_m": nominal_resolution_m}},
        config_path=root / "study.yaml",
    )
    location = SimpleNamespace(
        id="test_city",
        name="Test City",
        country="Argentina" if country == "AR" else "Chile",
        country_code=country,
        timezone="America/Argentina/Buenos_Aires",
        geographic_crs="EPSG:4326",
        metric_crs="EPSG:32721",
        bbox=None,
    )
    paths = SimpleNamespace(
        raw=root / "raw",
        interim=root / "interim",
        processed=root / "processed",
        cache=root / "cache",
    )
    paths.layer_processed = lambda layer_id: paths.processed / layer_id
    return SimpleNamespace(
        study=study,
        location=location,
        paths=paths,
        spatial_path=spatial_path,
        expected_units=2,
        enabled_layers=enabled_layers,
        country_code=country,
        city="test_city",
    )


def _write_polygons(context: SimpleNamespace) -> None:
    gdf = gpd.GeoDataFrame(
        {
            "code": ["A-01", "A-02"],
            "label": ["Area Norte", "Área Sur"],
            "geometry": [box(-58.50, -34.65, -58.49, -34.64), box(-58.48, -34.65, -58.47, -34.64)],
        },
        crs="EPSG:4326",
    )
    gdf.to_file(context.spatial_path, driver="GeoJSON")


class LayerCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_layer_catalog()

    def test_catalog_preserves_audit_inventory_and_country_layers(self) -> None:
        # climate_heat_by_year / precipitation_by_year are internal per-year
        # sub-layers consumed by scripts/build_master_exposome.py (webapp year
        # sliders); they are audited (present in LAYER_SPECS) but are not
        # standalone, user-selectable catalog entries in config/layers.yaml.
        non_catalog_audited = {"climate_heat_by_year", "precipitation_by_year"}
        with (ROOT / "docs" / "exposome_status.csv").open(encoding="utf-8") as handle:
            audited = {row["layer_id"] for row in csv.DictReader(handle)}
        self.assertEqual(
            len(audited - {"food_insecurity", "pobreza_sae"} - non_catalog_audited), 27
        )
        self.assertTrue((audited - non_catalog_audited).issubset(self.catalog.layers))
        # 34 since noise_spain (SICA MER administrative summary) joined after
        # climate_lst_ecostress (ECOSTRESS 70 m LST). climate_lst_ecostress is
        # still deliberately absent from exposome_status.csv: that dashboard
        # tracks layers with real outputs to review, and it has not been run for
        # any study yet. noise_spain earned its row on 2026-08-10, when it was
        # materialized for both Spanish studies -- hence 27 above, not 26. The
        # subset assertion is one-directional precisely so a catalog entry can
        # exist before it has anything to audit.
        self.assertEqual(len(self.catalog.layers), 34)
        self.assertIn("food_insecurity", self.catalog.layers)
        self.assertIn("pobreza_sae", self.catalog.layers)
        self.assertIn("community_safety", self.catalog.layers)
        self.assertIn("community_violence", self.catalog.layers)
        self.assertIn("suicide_mortality", self.catalog.layers)
        self.assertIn("road_traffic_mortality", self.catalog.layers)

    def test_exact_thirteen_layer_pilot(self) -> None:
        self.assertEqual(
            self.catalog.pilot_layers,
            (
                "air_quality_pm25",
                "alan",
                "greenspace_coverage",
                "greenspace_multisource",
                "precipitation",
                "climate_heat",
                "wind",
                "wildfire",
                "greenspace_access",
                "walkability",
                "social_infrastructure",
                "food_environment",
                "healthcare",
            ),
        )
        self.assertEqual(sum(spec.pilot for spec in self.catalog.layers.values()), 13)
        self.assertTrue(all(has_importable_runner(layer_id) for layer_id in self.catalog.pilot_layers))

    def test_existing_builders_are_registered_without_script_subprocesses(self) -> None:
        for layer_id in (
            "socioeconomic", "air_quality", "heavy_metals", "air_quality_satellite",
            "sleep_context", "precipitation_spi", "noise", "public_transport",
            "demography", "food_insecurity", "pobreza_sae", "noise_spain",
        ):
            with self.subTest(layer=layer_id):
                self.assertTrue(has_importable_runner(layer_id))

    def test_all_portability_classes_are_present(self) -> None:
        self.assertEqual(
            {spec.category for spec in self.catalog.layers.values()},
            set(LayerCategory),
        )
        self.assertEqual(self.catalog.get("pm25").id, "air_quality_pm25")

    def test_every_layer_declares_provider_command_and_master_contract(self) -> None:
        for spec in self.catalog.layers.values():
            with self.subTest(layer=spec.id):
                self.assertTrue(spec.provider)
                self.assertTrue(spec.command)
                self.assertIn("include", spec.master)


class PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_layer_catalog()
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_ready_resolution_warning_unavailable_and_missing_input(self) -> None:
        context = _context(
            self.root,
            enabled_layers=("healthcare", "wind", "food_insecurity", "precipitation_spi"),
        )
        results = {
            result.layer_id: result
            for result in preflight_layers(
                context,
                catalog=self.catalog,
                layer_ids=("healthcare", "wind", "food_insecurity", "precipitation_spi"),
            )
        }
        self.assertEqual(results["healthcare"].status, PreflightStatus.READY)
        self.assertEqual(results["wind"].status, PreflightStatus.RESOLUTION_WARNING)
        self.assertEqual(results["food_insecurity"].status, PreflightStatus.UNAVAILABLE)
        self.assertEqual(results["precipitation_spi"].status, PreflightStatus.MISSING_INPUT)

    def test_capabilities_are_checked_only_when_supplied(self) -> None:
        context = _context(self.root, enabled_layers=("pm25",), nominal_resolution_m=5000)
        unchecked = preflight_layers(context, catalog=self.catalog)[0]
        checked = preflight_layers(
            context,
            catalog=self.catalog,
            available_capabilities={"network"},
        )[0]
        self.assertEqual(unchecked.status, PreflightStatus.READY)
        self.assertEqual(checked.status, PreflightStatus.MISSING_INPUT)
        self.assertIn("gee", " ".join(checked.reasons))

    def test_command_uses_study_id_and_country_provider_args(self) -> None:
        context = _context(self.root, enabled_layers=("healthcare",))
        command = render_layer_command(context, self.catalog.get("healthcare"))
        self.assertIn("test_zipcodes", command)
        self.assertNotIn("test_city", command)
        self.assertIn("--no-official", command)

    def test_build_run_plan_does_not_create_directories(self) -> None:
        context = _context(self.root, enabled_layers=("pm25",), nominal_resolution_m=5000)
        plans = build_run_plan(context, catalog=self.catalog)
        self.assertEqual(len(plans), 1)
        self.assertFalse(context.paths.processed.exists())
        self.assertFalse(context.paths.cache.exists())

    def test_resume_ignores_auxiliary_normalized_csv(self) -> None:
        context = _context(self.root, enabled_layers=("pm25",), nominal_resolution_m=5000)
        output = context.paths.processed / "air_quality_pm25"
        output.mkdir(parents=True)
        pd.DataFrame(
            {
                "spatial_id": ["A-01"],
                "spatial_name": ["Area Norte"],
                "date": ["2024-01-01"],
            }
        ).to_csv(output / "daily_auxiliary.csv", index=False)
        plan = build_run_plan(context, catalog=self.catalog, resume=True)[0]
        self.assertFalse(plan.skip)

    def test_resume_rejects_bare_csv_even_when_recompute_inputs_are_missing(self) -> None:
        context = _context(self.root, enabled_layers=("precipitation_spi",))
        _write_polygons(context)
        output = context.paths.processed / "precipitation_spi"
        output.mkdir(parents=True)
        pd.DataFrame(
            {
                "spatial_id": ["A-01", "A-02"],
                "spatial_name": ["Area Norte", "Área Sur"],
                "drought_months_pct": [10.0, 20.0],
                "drought_severe_months_pct": [1.0, 2.0],
                "drought_max_duration_months": [2, 3],
                "precip_trend_mm_per_decade": [5.0, -4.0],
                "spi_12_latest": [0.1, -0.2],
                "spi_3_mean": [0.1, -0.2],
                "spi_3_std": [1.0, 1.1],
                "spi_6_mean": [0.1, -0.2],
                "spi_12_mean": [0.1, -0.2],
            }
        ).to_csv(output / "spi.csv", index=False)
        plan = build_run_plan(context, catalog=self.catalog, resume=True)[0]
        self.assertFalse(plan.preflight.runnable)
        self.assertFalse(plan.skip)

    def test_blocked_plan_renders_missing_study_input_without_execution(self) -> None:
        context = _context(self.root, enabled_layers=("climate_openmeteo",))
        plan = build_run_plan(context, catalog=self.catalog)[0]
        self.assertEqual(plan.preflight.status, PreflightStatus.MISSING_INPUT)
        self.assertIn("<missing:input_daily_csv>", plan.command)

    def test_self_fetch_study_input_is_runnable_even_when_file_is_missing(self) -> None:
        # climate_openmeteo's daily_csv is declared self-fetching (run_climate_metrics.py
        # downloads it from Open-Meteo when absent), so preflight must not block a
        # brand-new study just because the file doesn't exist on disk yet -- as long
        # as a path was actually configured for it.
        context = _context(self.root, enabled_layers=("climate_openmeteo",))
        context.study.raw["layer_inputs"] = {
            "climate_openmeteo": {"daily_csv": str(self.root / "not_fetched_yet.csv")}
        }
        plan = build_run_plan(context, catalog=self.catalog)[0]
        self.assertTrue(plan.preflight.runnable)
        self.assertNotIn("<missing:input_daily_csv>", plan.command)

    def test_self_fetch_study_input_still_blocks_when_unconfigured(self) -> None:
        context = _context(self.root, enabled_layers=("climate_openmeteo",))
        plan = build_run_plan(context, catalog=self.catalog)[0]
        self.assertFalse(plan.preflight.runnable)
        self.assertEqual(plan.preflight.status, PreflightStatus.MISSING_INPUT)


class OutputContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = load_layer_catalog()
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.context = _context(
            self.root,
            country="CL",
            enabled_layers=("pm25",),
            nominal_resolution_m=5000,
        )
        _write_polygons(self.context)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_boundary_cache_uses_study_id_and_legacy_name(self) -> None:
        path = prepare_boundary_cache(self.context, self.root / "layer-cache")
        self.assertEqual(path.name, "test_zipcodes_communes.geojson")
        cached = gpd.read_file(path)
        self.assertEqual(cached["name"].tolist(), ["Area Norte", "Área Sur"])
        self.assertEqual(cached["spatial_id"].tolist(), ["A-01", "A-02"])
        self.assertTrue((cached["area_km2"] > 0).all())

    def test_normalize_outputs_maps_names_one_to_one_and_adds_metadata(self) -> None:
        out_dir = self.context.paths.layer_processed("air_quality_pm25")
        out_dir.mkdir(parents=True)
        frame = pd.DataFrame(
            {
                "name": ["area norte", "Area Sur"],
                "pm25_mean": [12.0, 10.0],
                "pm25_pop_weighted": [13.0, 11.0],
                "pm25_who_ratio": [2.4, 2.0],
            }
        )
        frame.to_csv(out_dir / "pm25.csv", index=False)
        geo = gpd.GeoDataFrame(
            frame,
            geometry=[box(-58.50, -34.65, -58.49, -34.64), box(-58.48, -34.65, -58.47, -34.64)],
            crs="EPSG:4326",
        )
        geo.to_file(out_dir / "pm25.geojson", driver="GeoJSON")

        normalized = normalize_layer_outputs(
            self.context,
            self.catalog.get("pm25"),
            out_dir,
        )

        result = pd.read_csv(out_dir / "pm25.csv", dtype={"spatial_id": str})
        self.assertEqual(result.columns[:2].tolist(), ["spatial_id", "spatial_name"])
        self.assertEqual(result["spatial_id"].tolist(), ["A-01", "A-02"])
        self.assertEqual(result["spatial_name"].tolist(), ["Area Norte", "Área Sur"])
        metadata_path = out_dir / "air_quality_pm25_metadata.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["study"]["id"], "test_zipcodes")
        self.assertEqual(metadata["location"]["country_code"], "CL")
        self.assertIn(metadata_path, normalized)
        manifest_path = out_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["primary_table"], "pm25.csv")
        self.assertEqual(manifest["primary_geometry"], "pm25.geojson")
        self.assertTrue(all(asset["sha256"] for asset in manifest["assets"]))
        self.assertIn(manifest_path, normalized)

    def test_normalize_outputs_preserves_leading_zero_spatial_ids(self) -> None:
        """Regression test for Peru UBIGEO-style ids (Callao starts "07").

        `pd.read_csv` without `dtype={"spatial_id": str}` infers int64 for an
        all-digit id column and silently drops the leading zero, which then
        fails to match the string-typed boundary ids -- this broke
        lima_distritos mid-run on 2026-07-17.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = _context(
                root, country="PE", enabled_layers=("pm25",), nominal_resolution_m=5000
            )
            gpd.GeoDataFrame(
                {
                    "code": ["07", "15"],
                    "label": ["Callao", "Lima"],
                    "geometry": [
                        box(-77.20, -12.10, -77.00, -11.90),
                        box(-77.00, -12.10, -76.80, -11.90),
                    ],
                },
                crs="EPSG:4326",
            ).to_file(context.spatial_path, driver="GeoJSON")

            out_dir = context.paths.layer_processed("air_quality_pm25")
            out_dir.mkdir(parents=True)
            pd.DataFrame(
                {
                    "spatial_id": ["07", "15"],
                    "pm25_mean": [12.0, 10.0],
                    "pm25_pop_weighted": [13.0, 11.0],
                    "pm25_who_ratio": [2.4, 2.0],
                }
            ).to_csv(out_dir / "pm25.csv", index=False)

            normalize_layer_outputs(context, self.catalog.get("pm25"), out_dir)

            result = pd.read_csv(out_dir / "pm25.csv", dtype={"spatial_id": str})
            self.assertEqual(result["spatial_id"].tolist(), ["07", "15"])

    def test_normalize_outputs_keeps_provider_native_table_as_auxiliary(self) -> None:
        out_dir = self.context.paths.layer_processed("air_quality_pm25")
        out_dir.mkdir(parents=True)
        pd.DataFrame(
            {
                "name": ["Area Norte", "Área Sur"],
                "pm25_mean": [12.0, 10.0],
                "pm25_pop_weighted": [13.0, 11.0],
                "pm25_who_ratio": [2.4, 2.0],
            }
        ).to_csv(out_dir / "primary.csv", index=False)
        native = pd.DataFrame(
            {
                "pixel_id": ["p-1", "p-2"],
                "date": ["2024-01-01", "2024-01-01"],
                "value": [1.0, 2.0],
            }
        )
        native.to_csv(out_dir / "provider_native.csv", index=False)

        normalize_layer_outputs(self.context, self.catalog.get("pm25"), out_dir)

        self.assertEqual(
            pd.read_csv(out_dir / "provider_native.csv").columns.tolist(),
            native.columns.tolist(),
        )
        manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
        roles = {asset["path"]: asset["role"] for asset in manifest["assets"]}
        self.assertEqual(roles["primary.csv"], "primary_table")
        self.assertEqual(roles["provider_native.csv"], "auxiliary")

    def test_legacy_collector_ignores_diagnostic_subset_without_join_key(self) -> None:
        """A diagnostics/*_low_access.csv (an nsmallest() slice without
        spatial_id) satisfies master.required_columns and sorts ahead of the
        real output, but is not joinable. The legacy collector must not pick it
        as primary_table -- doing so demoted lima_distritos social_infrastructure's
        real table to auxiliary and blocked `exposome materialize` on 2026-07-22.
        """
        out_dir = self.context.paths.layer_processed("air_quality_pm25")
        (out_dir / "diagnostics").mkdir(parents=True)
        pd.DataFrame(
            {
                "spatial_name": ["Area Norte"],
                "pm25_mean": [12.0],
                "pm25_pop_weighted": [13.0],
                "pm25_who_ratio": [2.4],
            }
        ).to_csv(out_dir / "diagnostics" / "pm25_low_access.csv", index=False)
        pd.DataFrame(
            {
                "spatial_id": ["A-01", "A-02"],
                "spatial_name": ["Area Norte", "Área Sur"],
                "pm25_mean": [12.0, 10.0],
                "pm25_pop_weighted": [13.0, 11.0],
                "pm25_who_ratio": [2.4, 2.0],
            }
        ).to_csv(out_dir / "pm25.csv", index=False)

        result = collect_legacy_assets(out_dir, self.catalog.get("pm25"))
        roles = {asset.path.name: asset.role for asset in result.assets}
        self.assertEqual(roles["pm25.csv"], "primary_table")
        self.assertEqual(roles["pm25_low_access.csv"], "diagnostic")
        self.assertEqual(sum(a.role == "primary_table" for a in result.assets), 1)

    def test_master_manifest_refuses_unmanifested_layer_directories(self) -> None:
        with self.assertRaises((FileNotFoundError, ValueError)):
            build_master_manifest(
                self.context,
                catalog=self.catalog,
                layer_ids=("pm25", "greenspace_cv"),
            )

    def test_master_manifest_prefers_declared_primary_asset(self) -> None:
        out_dir = self.context.paths.layer_processed("air_quality_pm25")
        out_dir.mkdir(parents=True)
        pd.DataFrame(
            {
                "spatial_id": ["A-01", "A-02"],
                "pm25_mean": [1.0, 2.0],
                "pm25_pop_weighted": [1.0, 2.0],
                "pm25_who_ratio": [0.2, 0.4],
            }
        ).to_csv(out_dir / "primary.csv", index=False)
        normalize_layer_outputs(self.context, self.catalog.get("pm25"), out_dir)
        manifest = build_master_manifest(
            self.context, catalog=self.catalog, layer_ids=("pm25",)
        )
        self.assertEqual(
            Path(manifest["layers"][0]["path"]),
            (out_dir / "primary.csv").resolve(),
        )

    def test_execution_propagates_external_study_config(self) -> None:
        self.context.study.config_path.write_text("id: test_zipcodes\n", encoding="utf-8")
        plan = build_run_plan(self.context, catalog=self.catalog)[0]
        captured: dict[str, str] = {}

        def fake_runner(command, *, cwd, env, check):
            captured["study_config"] = env["EXPOSOME_STUDY_CONFIG"]
            pd.DataFrame(
                {
                    "name": ["Area Norte", "Área Sur"],
                    "pm25_mean": [10.0, 11.0],
                    "pm25_pop_weighted": [10.5, 11.5],
                    "pm25_who_ratio": [2.0, 2.2],
                }
            ).to_csv(plan.output_dir / "pm25.csv", index=False)

        result = execute_run_plan(self.context, (plan,), runner=fake_runner)
        self.assertEqual(
            captured["study_config"], str(self.context.study.config_path)
        )
        self.assertEqual(result[0].action, "executed")
        normalized = pd.read_csv(plan.output_dir / "pm25.csv")
        self.assertEqual(normalized["spatial_id"].tolist(), ["A-01", "A-02"])

    def test_execution_prefers_importable_portable_runner(self) -> None:
        plan = build_run_plan(self.context, catalog=self.catalog)[0]
        def direct(execution):
            pd.DataFrame(
                {
                    "name": ["Area Norte", "Área Sur"],
                    "pm25_mean": [10.0, 11.0],
                    "pm25_pop_weighted": [10.5, 11.5],
                    "pm25_who_ratio": [2.0, 2.2],
                }
            ).to_csv(execution.output_dir / "pm25.csv", index=False)
            return collect_legacy_assets(execution.output_dir, execution.spec)

        with patch("exposome.runners.get_layer_runner", return_value=direct):
            result = execute_run_plan(self.context, (plan,), runner=__import__("subprocess").run)

        self.assertEqual(result[0].action, "executed")

    def test_layer_failure_does_not_abort_remaining_layers(self) -> None:
        """One layer raising (e.g. an exhausted OSM/Overpass retry) must not
        stop sibling layers from running -- this previously stalled
        cdmx_native's `healthcare` layer behind an unrelated
        `food_environment` Overpass outage.
        """
        context = _context(
            self.root,
            country="CL",
            enabled_layers=("pm25", "alan"),
            nominal_resolution_m=5000,
        )
        _write_polygons(context)
        plans = build_run_plan(context, catalog=self.catalog)
        self.assertEqual({plan.layer.id for plan in plans}, {"air_quality_pm25", "alan"})

        def direct(execution):
            if execution.spec.id == "alan":
                raise RuntimeError("OSM/Overpass call failed after trying 2 endpoint(s)")
            pd.DataFrame(
                {
                    "name": ["Area Norte", "Área Sur"],
                    "pm25_mean": [10.0, 11.0],
                    "pm25_pop_weighted": [10.5, 11.5],
                    "pm25_who_ratio": [2.0, 2.2],
                }
            ).to_csv(execution.output_dir / "pm25.csv", index=False)
            return collect_legacy_assets(execution.output_dir, execution.spec)

        with patch("exposome.runners.get_layer_runner", return_value=direct):
            results = execute_run_plan(context, plans, runner=subprocess.run)

        by_id = {result.layer_id: result for result in results}
        self.assertEqual(by_id["air_quality_pm25"].action, "executed")
        self.assertEqual(by_id["alan"].action, "failed")
        self.assertIn("OSM/Overpass call failed", by_id["alan"].error)
        # The successful layer's output must exist despite its sibling's failure.
        self.assertTrue((context.paths.layer_processed("air_quality_pm25") / "pm25.csv").exists())


if __name__ == "__main__":
    unittest.main()

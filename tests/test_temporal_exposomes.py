from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import numpy as np
import rasterio
from rasterio.transform import from_origin

from exposome.studies import load_study
from exposome.temporal_exposomes import (
    AnnualBuildResult,
    AnnualRasterDetail,
    TemporalPaths,
    collect_missing,
    discover_temporal_specs,
    inventory,
    required_annual_products,
    validate_no_analysis_side_effects,
)


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestTemporalCatalog(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.context = load_study("santiago_communes", repo_root_path=REPO_ROOT)

    def test_all_declared_annual_products_are_discovered(self) -> None:
        specs = {spec.layer_id: spec for spec in discover_temporal_specs(self.context)}
        self.assertEqual(
            set(specs),
            {
                "air_quality_satellite",
                "alan",
                "climate_heat",
                "climate_openmeteo",
                "greenspace_coverage",
                "greenspace_multisource",
                "heavy_metals",
                "pm25",
                "precipitation",
                "wildfire",
                "wind",
            },
        )
        self.assertEqual(specs["pm25"].years(2015, 2024), tuple(range(2015, 2023)))
        self.assertEqual(specs["pm25"].indicators[0].detail_kind, "native_raster")
        self.assertEqual(specs["pm25"].indicators[0].detail_native_resolution_m, 1113)
        self.assertEqual(
            specs["air_quality_satellite"].years(2015, 2024),
            tuple(range(2019, 2025)),
        )
        self.assertEqual(
            specs["greenspace_multisource"].years(2015, 2024),
            tuple(range(2016, 2025)),
        )
        self.assertEqual(
            [item.exposome_id for item in specs["climate_heat"].indicators],
            ["heat_summer_tmax", "heat_hot_days", "heat_tropical_nights"],
        )
        self.assertEqual(
            [item.exposome_id for item in specs["greenspace_multisource"].indicators],
            ["green"],
        )

    def test_every_enabled_study_layer_is_classified(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = TemporalPaths(Path(tmp) / "out", Path(tmp) / "cache")
            table = inventory(self.context, paths=paths)
        self.assertEqual(set(table["layer_id"]), set(self.context.enabled_layers))
        static = table[table["layer_id"] == "noise"].iloc[0]
        self.assertEqual(static["classification"], "static_snapshot")
        outcomes = table[table["layer_id"] == "neuro_hospitalizations"].iloc[0]
        self.assertEqual(outcomes["classification"], "not_an_exposure")

    def test_status_inventory_does_not_create_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = TemporalPaths(Path(tmp) / "never-created", Path(tmp) / "cache")
            inventory(self.context, paths=paths, layers=["pm25"])
            self.assertFalse(paths.output_root.exists())
            self.assertFalse(paths.cache_root.exists())

    def test_static_layer_cannot_be_selected_for_download(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = TemporalPaths(Path(tmp) / "out", Path(tmp) / "cache")
            with self.assertRaisesRegex(ValueError, "non-temporal"):
                inventory(self.context, paths=paths, layers=["noise"])

    def test_forbidden_output_roots_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_no_analysis_side_effects(
                TemporalPaths(Path("webapp/public/data"), Path("cache/temporal"))
            )

    def test_documented_source_gap_is_visible_but_not_required(self) -> None:
        context = load_study("bogota_localidades", repo_root_path=REPO_ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            paths = TemporalPaths(Path(tmp) / "out", Path(tmp) / "cache")
            annual = inventory(
                context, paths=paths, layers=["greenspace_multisource"]
            )
        required = required_annual_products(annual, context)
        self.assertEqual(len(annual), 9)
        self.assertEqual(len(required), 8)
        self.assertNotIn(2019, required["year"].tolist())


class TestTemporalCollection(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.context = load_study("santiago_communes", repo_root_path=REPO_ROOT)
        cls.units = cls.context.load_spatial_units()

    def _synthetic_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "name": self.units["spatial_name"],
                "area_km2": self.units["area_km2"],
                "pm25_mean": range(1, len(self.units) + 1),
            }
        )

    def _synthetic_pm25_result(self, spec, year, *, context, paths, existing_frame=None):
        detail_dir = paths.year_dir(spec.layer_id, year) / "detail-source"
        detail_dir.mkdir(parents=True, exist_ok=True)
        raster = detail_dir / f"pm25_{year}_native.tif"
        with rasterio.open(
            raster,
            "w",
            driver="GTiff",
            width=2,
            height=2,
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(-71.0, -33.0, 0.01, 0.01),
        ) as dataset:
            dataset.write(np.full((2, 2), float(year), dtype="float32"), 1)
        from exposome.spatial_detail import raster_grid_signature

        grid = raster_grid_signature(raster)
        metadata = detail_dir / f"pm25_{year}_native.metadata.json"
        metadata.write_text(json.dumps({
            "source_native_resolution_m": 1113,
            "export_grid": grid,
            "temporal_support": {
                "kind": "year",
                "year": str(year),
                "source_label": "ACAG V6.GL.02",
            },
        }))
        return AnnualBuildResult(
            existing_frame if existing_frame is not None else self._synthetic_frame(),
            (AnnualRasterDetail("pm25", raster, metadata),),
        )

    def test_collection_is_checkpointed_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "exposome.temporal_exposomes._run_adapter",
                side_effect=self._synthetic_pm25_result,
            ) as run_adapter:
                first = collect_missing(
                    "santiago_communes",
                    layers=["pm25"],
                    output_root=root / "out",
                    cache_root=root / "cache",
                )
                self.assertEqual(run_adapter.call_count, 8)
                second = collect_missing(
                    "santiago_communes",
                    layers=["pm25"],
                    output_root=root / "out",
                    cache_root=root / "cache",
                )
                self.assertEqual(run_adapter.call_count, 8)

            annual = first[first["classification"] == "annual_downloadable"]
            self.assertTrue((annual["state"] == "complete").all())
            self.assertTrue(
                (second[second["classification"] == "annual_downloadable"]["state"] == "complete").all()
            )
            table = pd.read_csv(root / "out" / "pm25" / "2015" / "annual.csv")
            self.assertEqual(len(table), 52)
            self.assertEqual(table["spatial_id"].nunique(), 52)
            self.assertEqual(set(table["year"]), {2015})
            manifest = json.loads(
                (root / "out" / "pm25" / "2015" / "manifest.json").read_text()
            )
            self.assertEqual(manifest["study_id"], "santiago_communes")
            self.assertFalse(manifest["scope"]["master"])
            self.assertFalse(manifest["scope"]["webapp"])
            self.assertFalse(manifest["scope"]["health_analysis"])
            self.assertEqual(manifest["schema_version"], 2)
            self.assertIn("pm25", manifest["details"])

    def test_failure_is_recorded_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "exposome.temporal_exposomes._run_adapter",
                side_effect=RuntimeError("provider unavailable"),
            ):
                with self.assertRaises(RuntimeError):
                    collect_missing(
                        "santiago_communes",
                        layers=["air_quality_satellite"],
                        output_root=root / "out",
                        cache_root=root / "cache",
                    )
            failure = json.loads(
                (
                    root
                    / "out"
                    / "air_quality_satellite"
                    / "2019"
                    / "failure.json"
                ).read_text()
            )
            self.assertEqual(failure["error_type"], "RuntimeError")
            self.assertIn("--resume", failure["retry"])

    def test_collection_does_not_retry_documented_source_gap(self) -> None:
        """ADR 0008 gaps stay pending in inventory but never call the provider."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "exposome.temporal_exposomes._run_adapter",
                side_effect=RuntimeError("provider unavailable"),
            ) as run_adapter:
                with self.assertRaises(RuntimeError):
                    collect_missing(
                        "bogota_localidades",
                        layers=["greenspace_multisource"],
                        output_root=root / "out",
                        cache_root=root / "cache",
                    )
        # Dynamic World has 2016--2024 (nine) annual targets; 2019 is an
        # explicit source-gap exception, so only eight provider calls occur.
        self.assertEqual(run_adapter.call_count, 8)

    def test_non_santiago_inventory_never_uses_santiago_wildfire_cache(self) -> None:
        lima = load_study("lima_distritos", repo_root_path=REPO_ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = replace(
                lima.paths,
                processed=root / "processed",
                cache=root / "cache" / "pe" / "lima" / "lima_distritos",
            )
            context = replace(lima, paths=paths)

            table = inventory(
                context,
                paths=TemporalPaths(root / "annual", root / "annual-cache"),
                layers=["wildfire"],
            )

        self.assertTrue((table["state"] == "pending").all())

    def test_non_santiago_canonical_sources_are_detected_and_local_only_never_fetches(self) -> None:
        lima = load_study("lima_distritos", repo_root_path=REPO_ROOT)
        units = lima.load_spatial_units()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = replace(
                lima.paths,
                processed=root / "processed",
                cache=root / "cache" / "pe" / "lima" / "lima_distritos",
            )
            context = replace(lima, paths=paths)
            daily = (
                paths.processed
                / "precipitation"
                / "lima_distritos_precipitation_chirps_daily_2015_2024.csv"
            )
            daily.parent.mkdir(parents=True)
            pd.DataFrame(
                {
                    "name": units["spatial_name"],
                    "date": ["2015-01-01"] * len(units),
                    "precipitation_mm": [1.0] * len(units),
                }
            ).to_csv(daily, index=False)
            annual_paths = TemporalPaths(root / "annual", root / "annual-cache")

            first = inventory(context, paths=annual_paths, layers=["precipitation"])
            with patch("exposome.temporal_exposomes.load_study", return_value=context), patch(
                "exposome.temporal_exposomes._run_adapter"
            ) as remote:
                final = collect_missing(
                    "lima_distritos",
                    layers=["precipitation"],
                    output_root=annual_paths.output_root,
                    cache_root=annual_paths.cache_root,
                    local_only=True,
                )

            self.assertEqual(first.loc[first["year"] == 2015, "state"].item(), "source_cached")
            self.assertEqual(final.loc[final["year"] == 2015, "state"].item(), "source_cached")
            self.assertTrue((final.loc[final["year"] != 2015, "state"] == "pending").all())
            remote.assert_not_called()


if __name__ == "__main__":
    unittest.main()

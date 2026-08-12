"""Tests for the climate_heat exposome layer (cache-first, no network)."""
from __future__ import annotations

import json
import sys
from tempfile import TemporaryDirectory
import unittest
from artifact_test_case import MaterializedArtifactTestCase
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, box

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

DATA_DIR = REPO_ROOT / "data" / "processed"
CACHE_DIR = REPO_ROOT / "cache"
MASTER_CSV = DATA_DIR / "santiago_exposome_master.csv"


EXPECTED_COLUMNS = [
    "name",
    "area_km2",
    "tmean_annual_c",
    "tmax_mean_annual_c",
    "summer_tmax_mean_c",
    "tmax_p95_c",
    "tmax_abs_c",
    "apparent_tmax_mean_c",
    "hot_days_30c",
    "hot_days_35c",
    "apparent_hot_days_35c",
    "tropical_nights_20c",
    "precip_annual_mm",
    "heat_exposure_index",
    "urban_heat_anomaly_c",
    "n_area_grid_points",
    "nearest_climate_m",
    "used_nearest_fallback",
    "n_days",
]

EXPECTED_FALLBACK_COMMUNES = {
    "Cerro Navia",
    "Conchalí",
    "El Bosque",
    "Estación Central",
    "Huechuraba",
    "Independencia",
    "La Cisterna",
    "La Granja",
    "La Pintana",
    "La Reina",
    "Lo Espejo",
    "Lo Prado",
    "Padre Hurtado",
    "Pedro Aguirre Cerda",
    "Peñalolén",
    "Providencia",
    "Quilicura",
    "Quinta Normal",
    "Recoleta",
    "San Joaquín",
    "San Miguel",
    "San Ramón",
    "Santiago",
    "Ñuñoa",
}


class ClimateHeatLayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.csv_path = DATA_DIR / "climate_heat_exposome_rm_santiago.csv"
        cls.geojson_path = DATA_DIR / "climate_heat_exposome_rm_santiago.geojson"
        cls.metadata_path = DATA_DIR / "climate_heat_exposome_rm_santiago_metadata.json"
        cls.era5_path = DATA_DIR / "santiago_climate_heat_era5land_2024.csv"
        if not cls.csv_path.exists():
            raise unittest.SkipTest(
                f"Missing canonical CSV at {cls.csv_path}; run scripts/run_climate_heat.py first."
            )
        cls.df = pd.read_csv(cls.csv_path)
        if not cls.metadata_path.exists():
            # The metadata may lag by a few seconds in cloud-synced folders
            # (Dropbox); skip metadata checks if it is not yet visible.
            cls.metadata = None
        else:
            cls.metadata = json.loads(cls.metadata_path.read_text(encoding="utf-8"))

    def test_csv_has_52_communes(self) -> None:
        self.assertEqual(len(self.df), 52)
        self.assertEqual(self.df["name"].nunique(), 52)
        self.assertEqual(self.df["name"].isna().sum(), 0)

    def test_csv_columns_complete(self) -> None:
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, self.df.columns, f"missing column: {col}")
        # No NaN in any column (no per_ columns here, all should be populated).
        self.assertEqual(self.df.isna().sum().sum(), 0)

    def test_metadata_coherence(self) -> None:
        if self.metadata is None:
            self.skipTest("metadata file not yet visible (likely cloud-sync delay)")
        self.assertEqual(self.metadata["n_communes"], 52)
        self.assertEqual(self.metadata["year"], 2024)
        self.assertEqual(self.metadata["source"], "openmeteo")
        self.assertIn("thresholds_c", self.metadata)
        self.assertEqual(self.metadata["thresholds_c"]["hot_day"], 30.0)
        self.assertEqual(self.metadata["thresholds_c"]["tropical_night"], 20.0)
        self.assertGreater(self.metadata["n_daily_rows"], 0)
        self.assertGreaterEqual(self.metadata["n_fallback_communes"], 24)
        # grid + elev_band must be recorded
        self.assertEqual(self.metadata["grid_step_deg"], 0.1)
        self.assertEqual(self.metadata["elev_band_m"], 300.0)
        # columns list must be the canonical EXPORT_COLS order
        expected_cols = [
            "name", "area_km2",
            "tmean_annual_c", "tmax_mean_annual_c", "summer_tmax_mean_c",
            "tmax_p95_c", "tmax_abs_c", "apparent_tmax_mean_c",
            "hot_days_30c", "hot_days_35c", "apparent_hot_days_35c",
            "tropical_nights_20c", "precip_annual_mm",
            "heat_exposure_index", "urban_heat_anomaly_c",
            "n_area_grid_points", "nearest_climate_m",
            "used_nearest_fallback", "n_days",
        ]
        self.assertEqual(self.metadata["columns"], expected_cols)

    def test_heat_exposure_index_distribution(self) -> None:
        idx = self.df["heat_exposure_index"]
        self.assertEqual(idx.isna().sum(), 0)
        # Z-score composite: mean ≈ 0, std < 1.
        self.assertAlmostEqual(float(idx.mean()), 0.0, places=1)
        self.assertLess(float(idx.std()), 1.0)

    def test_urban_heat_anomaly_is_median_centered(self) -> None:
        anomaly = self.df["urban_heat_anomaly_c"]
        self.assertEqual(anomaly.isna().sum(), 0)
        # The anomaly is computed as summer_tmax - median(summer_tmax),
        # so the median of the anomaly should be ~0.
        self.assertAlmostEqual(float(anomaly.median()), 0.0, places=1)

    def test_fallback_communes_are_documented(self) -> None:
        """24 small urban communes with no grid point must use the fallback."""
        fallback = self.df.loc[
            self.df["used_nearest_fallback"].astype(bool), "name"
        ].tolist()
        self.assertGreaterEqual(len(fallback), 24)
        # All 24 historically expected communes must be present.
        for name in EXPECTED_FALLBACK_COMMUNES:
            self.assertIn(name, fallback, f"missing fallback commune: {name}")
        # All fallback communes must have n_area_grid_points=0.
        n_zero = self.df.loc[
            self.df["used_nearest_fallback"].astype(bool), "n_area_grid_points"
        ]
        self.assertTrue((n_zero == 0).all())

    def test_non_fallback_communes_have_grid_points(self) -> None:
        non_fallback = self.df.loc[
            ~self.df["used_nearest_fallback"].astype(bool), "name"
        ]
        n_pts = self.df.loc[
            ~self.df["used_nearest_fallback"].astype(bool), "n_area_grid_points"
        ]
        self.assertTrue((n_pts > 0).all(), "non-fallback communes must have at least 1 grid point")
        self.assertGreater(len(non_fallback), 0)

    def test_master_integration(self) -> None:
        if not MASTER_CSV.exists():
            self.skipTest("Master CSV missing; run scripts/build_master_exposome.py first.")
        master = pd.read_csv(MASTER_CSV, nrows=0)
        # 13 columns from climate_heat are merged without prefix
        unprefixed = [
            "tmean_annual_c",
            "tmax_mean_annual_c",
            "summer_tmax_mean_c",
            "tmax_p95_c",
            "tmax_abs_c",
            "apparent_tmax_mean_c",
            "hot_days_30c",
            "hot_days_35c",
            "apparent_hot_days_35c",
            "tropical_nights_20c",
            "precip_annual_mm",
            "heat_exposure_index",
            "urban_heat_anomaly_c",
        ]
        for col in unprefixed:
            self.assertIn(col, master.columns, f"master missing unprefixed: {col}")
        # 4 columns are renamed with the climate_ prefix
        prefixed = [
            "climate_n_area_grid_points",
            "climate_nearest_point_m",
            "climate_used_nearest_fallback",
            "climate_n_days",
        ]
        for col in prefixed:
            self.assertIn(col, master.columns, f"master missing prefixed: {col}")


class ClimateHeatEra5LayerTest(MaterializedArtifactTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = DATA_DIR / "santiago_climate_heat_era5land_2024.csv"
        if not cls.path.exists():
            return  # tests in this class skip themselves
        cls.df = pd.read_csv(cls.path)

    def test_era5_csv_present_and_well_formed(self) -> None:
        if not self.path.exists():
            self.skipTest("ERA5-Land CSV not built; run scripts/run_climate_heat.py --source era5land")
        self.assertEqual(len(self.df), 52)
        self.assertEqual(self.df["name"].nunique(), 52)
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, self.df.columns, f"ERA5 CSV missing column: {col}")
        # All ERA5 communes use the per-commune representative point,
        # so the fallback flag must be True for every row.
        self.assertTrue(self.df["used_nearest_fallback"].astype(bool).all())


class ClimateHeatBuildLayerTest(unittest.TestCase):
    """Smoke test the build_layer module from cache, no network."""

    def test_openmeteo_cache_is_rejected_as_a_noncanonical_spatial_product(self) -> None:
        """A node cache cannot re-enter the canonical heat publication path."""
        from exposome.climate.build_layer import build_climate_heat_layer
        with TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "requires source='era5land'"):
                build_climate_heat_layer(city="santiago", cache_dir=Path(tmp), out_dir=Path(tmp), source="openmeteo")

    def test_heat_indices_helpers(self) -> None:
        from exposome.climate.build_layer import (
            METRIC_COLS,
            EXPORT_COLS,
            SUMMER_MONTHS,
            add_heat_indices,
            zscore,
        )

        # z-score is mean-centered, std-normalised
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        z = zscore(s)
        self.assertAlmostEqual(float(z.mean()), 0.0, places=6)
        self.assertAlmostEqual(float(z.std(ddof=0)), 1.0, places=6)

        # add_heat_indices: anomaly = summer_tmax - median(summer_tmax)
        df = pd.DataFrame(
            {
                "summer_tmax_mean_c": [29.0, 30.0, 31.0],
                "tmax_p95_c": [30.0, 31.0, 32.0],
                "hot_days_30c": [10.0, 20.0, 30.0],
                "apparent_hot_days_35c": [0.0, 1.0, 2.0],
                "tropical_nights_20c": [0.0, 1.0, 2.0],
            }
        )
        out = add_heat_indices(df, ["summer_tmax_mean_c", "tmax_p95_c"])
        self.assertIn("heat_exposure_index", out.columns)
        self.assertIn("urban_heat_anomaly_c", out.columns)
        # anomaly at the median should be ~0
        med = float(df["summer_tmax_mean_c"].median())
        diffs = out["urban_heat_anomaly_c"] - (df["summer_tmax_mean_c"] - med)
        self.assertAlmostEqual(float(diffs.abs().max()), 0.0, places=6)

        # Sanity on the metric/export contract: all expected metrics are in METRIC_COLS
        self.assertIn("tmean_annual_c", METRIC_COLS)
        self.assertIn("hot_days_30c", METRIC_COLS)
        self.assertIn("precip_annual_mm", METRIC_COLS)
        for col in EXPECTED_COLUMNS:
            self.assertIn(col, EXPORT_COLS, f"EXPORT_COLS missing {col}")
        self.assertEqual(SUMMER_MONTHS, {12, 1, 2})

    def test_era5land_uses_nearest_observed_pixel_for_zero_intersection_unit(self) -> None:
        from exposome.climate.build_layer import METRIC_COLS, aggregate_to_communes

        metrics = {column: float(index + 1) for index, column in enumerate(METRIC_COLS)}
        point_metrics = pd.DataFrame(
            [{
                "pixel_id": "pixel-1",
                "x_m": 0.0,
                "y_m": 0.0,
                "source": "era5land_pixel",
                **metrics,
            }]
        )
        communes = gpd.GeoDataFrame(
            {"name": ["intersects", "coastal"], "area_km2": [4.0, 1.0]},
            geometry=[box(-1000, -1000, 1000, 1000), box(6000, -500, 7000, 500)],
            crs="EPSG:3857",
        )

        result, counts = aggregate_to_communes(
            points=gpd.GeoDataFrame(geometry=[], crs="EPSG:3857"),
            point_metrics=point_metrics,
            communes=communes,
            cfg={"crs": {"metric": "EPSG:3857"}},
            elev_band_m=300.0,
            fallback_to_representative_point=False,
        )

        coastal = result.set_index("name").loc["coastal"]
        intersects = result.set_index("name").loc["intersects"]
        self.assertEqual(counts["fallback_communes"], 1)
        self.assertTrue(bool(coastal["used_nearest_fallback"]))
        self.assertEqual(int(coastal["n_area_grid_points"]), 0)
        self.assertAlmostEqual(float(coastal["nearest_climate_m"]), 6000.0)
        self.assertEqual(float(coastal["tmean_annual_c"]), metrics["tmean_annual_c"])
        self.assertFalse(bool(intersects["used_nearest_fallback"]))
        self.assertEqual(int(intersects["n_area_grid_points"]), 1)
        self.assertEqual(float(intersects["nearest_climate_m"]), 0.0)

    def test_era5land_rejects_nearest_pixel_beyond_one_grid_spacing(self) -> None:
        from exposome.climate.build_layer import METRIC_COLS, aggregate_to_communes

        metrics = {column: float(index + 1) for index, column in enumerate(METRIC_COLS)}
        point_metrics = pd.DataFrame(
            [{
                "pixel_id": "pixel-1",
                "x_m": 0.0,
                "y_m": 0.0,
                "source": "era5land_pixel",
                **metrics,
            }]
        )
        communes = gpd.GeoDataFrame(
            {"name": ["intersects", "too-far"], "area_km2": [4.0, 1.0]},
            geometry=[box(-1000, -1000, 1000, 1000), box(20_000, -500, 21_000, 500)],
            crs="EPSG:3857",
        )

        with self.assertRaisesRegex(ValueError, "beyond one native grid spacing"):
            aggregate_to_communes(
                points=gpd.GeoDataFrame(geometry=[], crs="EPSG:3857"),
                point_metrics=point_metrics,
                communes=communes,
                cfg={"crs": {"metric": "EPSG:3857"}},
                elev_band_m=300.0,
                fallback_to_representative_point=False,
            )


class ClimateHeatAutoFetchTest(unittest.TestCase):
    """Regression test for the runners.py gating bug: the importable runner
    calls build_climate_heat_layer directly (not the scripts/run_climate_heat.py
    wrapper), so the grid must be auto-fetched here or a new city (no pre-existing
    cache, e.g. cdmx_alcaldias) would crash with FileNotFoundError."""

    class _StopAfterFetch(Exception):
        pass

    def _fixtures(self) -> tuple["gpd.GeoDataFrame", "gpd.GeoDataFrame"]:
        gdf_communes = gpd.GeoDataFrame(
            {"name": ["A"], "area_km2": [1.0]},
            geometry=[Point(-70.6, -33.5).buffer(0.01)],
            crs="EPSG:4326",
        )
        gdf_points = gpd.GeoDataFrame(
            {
                "location_id": [0],
                "source": ["grid"],
                "commune_name": [None],
                "lat": [-33.5],
                "lon": [-70.6],
            },
            geometry=[Point(-70.6, -33.5)],
            crs="EPSG:4326",
        )
        return gdf_communes, gdf_points

    def test_openmeteo_source_is_rejected_before_any_fetch(self) -> None:
        from exposome.climate import build_layer

        gdf_communes, gdf_points = self._fixtures()
        calls: list[dict] = []

        def fake_ensure_grid_daily(points, *, year, cache_dir, timezone):
            calls.append({"year": year, "cache_dir": Path(cache_dir), "timezone": timezone})
            self.assertNotIn("geometry", points.columns)

        def fake_load_daily(source, points, cache_dir, year, city="santiago"):
            raise self._StopAfterFetch()

        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with (
                patch.object(build_layer, "load_communes", return_value=gdf_communes),
                patch.object(build_layer, "build_climate_points", return_value=gdf_points),
                patch.object(build_layer, "load_daily", side_effect=fake_load_daily),
                patch(
                    "exposome.climate.fetch_grid_openmeteo.ensure_grid_daily",
                    side_effect=fake_ensure_grid_daily,
                ),
                patch(
                    "exposome.config.load_config",
                    return_value={"name": "testcity", "timezone": "America/Santiago"},
                ),
            ):
                with self.assertRaisesRegex(ValueError, "requires source='era5land'"):
                    build_layer.build_climate_heat_layer(
                        city="testcity",
                        cache_dir=cache_dir,
                        out_dir=cache_dir,
                        source="openmeteo",
                        year=2024,
                    )

        self.assertEqual(calls, [], "a rejected legacy source must not fetch")

    def test_era5land_source_does_not_touch_openmeteo_fetch(self) -> None:
        from exposome.climate import build_layer

        gdf_communes, gdf_points = self._fixtures()

        def fake_load_daily(source, points, cache_dir, year, city="santiago"):
            raise self._StopAfterFetch()

        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with (
                patch.object(build_layer, "load_communes", return_value=gdf_communes),
                patch.object(build_layer, "build_climate_points", return_value=gdf_points),
                patch.object(build_layer, "ensure_era5land_daily"),
                patch.object(build_layer, "load_daily", side_effect=fake_load_daily),
                patch(
                    "exposome.climate.fetch_grid_openmeteo.ensure_grid_daily",
                    side_effect=AssertionError("era5land must not call the Open-Meteo grid fetch"),
                ),
                patch(
                    "exposome.config.load_config",
                    return_value={"name": "testcity", "timezone": "America/Santiago"},
                ),
            ):
                with self.assertRaises(self._StopAfterFetch):
                    build_layer.build_climate_heat_layer(
                        city="testcity",
                        cache_dir=cache_dir,
                        out_dir=cache_dir,
                        source="era5land",
                        year=2024,
                    )

    def test_era5land_source_ensures_native_cache_before_loading(self) -> None:
        from exposome.climate import build_layer

        gdf_communes, gdf_points = self._fixtures()
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            with (
                patch.object(build_layer, "load_communes", return_value=gdf_communes),
                patch.object(build_layer, "ensure_era5land_daily") as ensure,
                patch.object(
                    build_layer,
                    "load_daily",
                    side_effect=self._StopAfterFetch(),
                ),
                patch(
                    "exposome.config.load_config",
                    return_value={"name": "testcity", "timezone": "America/Santiago", "crs": {"metric": "EPSG:32719"}},
                ),
            ):
                with self.assertRaises(self._StopAfterFetch):
                    build_layer.build_climate_heat_layer(
                        city="testcity",
                        cache_dir=cache_dir,
                        out_dir=cache_dir,
                        source="era5land",
                        year=2024,
                    )

        ensure.assert_called_once_with("testcity", year=2024, cache_dir=cache_dir)


class ClimateHeatMetadataTest(unittest.TestCase):
    def test_export_layer_does_not_require_legacy_region_query(self) -> None:
        from exposome.climate.build_layer import EXPORT_COLS, export_layer

        values = {column: [0.0] for column in EXPORT_COLS}
        values["name"] = ["A"]
        gdf = gpd.GeoDataFrame(values, geometry=[Point(-70.6, -33.5)], crs="EPSG:4326")
        with TemporaryDirectory() as tmp:
            _, _, metadata_path = export_layer(
                gdf,
                Path(tmp),
                "heat",
                "era5land",
                2024,
                {"name": "teststudy", "location_id": "test-location"},
                {},
            )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["region"], "test-location")


class LoadCommunesStudyScopedCacheTest(unittest.TestCase):
    """Regression guard for the lima_distritos climate_heat crash.

    ``prepare_boundary_cache`` seeds the canonical polygons under the study id
    (``<study_id>_communes.geojson``).  ``load_communes`` used to read the city
    name instead, missing that seed and falling through to the legacy OSM
    download, which built ``{cfg["region_query"], ...}`` and raised
    ``unhashable type: 'list'`` when ``region_query`` was a per-district list
    (Lima+Callao).  The fix reads the study-scoped seed; this test proves the
    OSM branch is never reached for a list ``region_query``.
    """

    def _seed_and_cfg(self, cache_dir: Path) -> dict:
        units = gpd.GeoDataFrame(
            {
                "name": ["Distrito A", "Distrito B"],
                "spatial_id": ["150101", "150102"],
                "spatial_name": ["Distrito A", "Distrito B"],
                "area_km2": [1.0, 2.0],
            },
            geometry=[
                Point(-77.0, -12.0).buffer(0.01),
                Point(-77.1, -12.1).buffer(0.01),
            ],
            crs="EPSG:4326",
        )
        # Seeded under the STUDY id, while cfg["name"] is the city -- only the
        # study-scoped lookup can find this file.
        (cache_dir / "lima_distritos_communes.geojson").write_bytes(
            units.to_json().encode("utf-8")
        )
        cfg = {
            "name": "lima",
            "study_id": "lima_distritos",
            "expected_units": 2,
            # A per-district Nominatim list, exactly what crashed the OSM path.
            "region_query": ["Lima, Peru", "Callao, Peru"],
            "crs": {"metric": "EPSG:32718"},
        }
        return cfg

    def test_study_scoped_seed_is_used_without_touching_osm(self) -> None:
        from exposome.climate import build_layer

        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            cfg = self._seed_and_cfg(cache_dir)
            with patch.object(
                build_layer.boundaries,
                "ox",
                create=True,
                geocode_to_gdf=lambda *a, **k: (_ for _ in ()).throw(
                    AssertionError("OSM download must not run when the seed exists")
                ),
            ):
                communes = build_layer.load_communes(cfg, cache_dir)
        self.assertEqual(len(communes), 2)
        self.assertIn("name", communes.columns)
        # Reprojected to the study metric CRS (not left in EPSG:4326).
        self.assertEqual(communes.crs.to_epsg(), 32718)


if __name__ == "__main__":
    unittest.main()

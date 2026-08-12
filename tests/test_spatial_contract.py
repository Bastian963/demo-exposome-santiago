from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import yaml
from shapely.geometry import Point, Polygon


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.spatial import (  # noqa: E402
    SpatialValidationError,
    load_spatial_units,
    normalize_spatial_units,
)
from exposome.studies import BoundingBox, load_study  # noqa: E402


class SpatialContractTest(unittest.TestCase):
    def _make_context(
        self,
        root: Path,
        spatial_path: Path,
        *,
        layer: str | None = None,
        expected_units: int | None = 2,
    ):
        location_dir = root / "config" / "locations" / "ar"
        study_dir = root / "config" / "studies"
        location_dir.mkdir(parents=True)
        study_dir.mkdir(parents=True)
        location = {
            "id": "buenos_aires",
            "name": "Buenos Aires",
            "country": "Argentina",
            "country_code": "AR",
            "country_code3": "ARG",
            "timezone": "America/Argentina/Buenos_Aires",
            "bbox": {"west": -58.55, "south": -34.72, "east": -58.32, "north": -34.50},
            "crs": {"geographic": "EPSG:4326", "metric": "auto"},
        }
        spatial = {
            "path": str(spatial_path),
            "id_column": "postal_code",
            "name_column": "label",
            "unit_type": "postal_code",
        }
        if layer is not None:
            spatial["layer"] = layer
        if expected_units is not None:
            spatial["expected_units"] = expected_units
        study = {
            "id": "ba_test",
            "location": "ar/buenos_aires",
            "spatial": spatial,
            "layers": ["pm25"],
        }
        (location_dir / "buenos_aires.yaml").write_text(
            yaml.safe_dump(location), encoding="utf-8"
        )
        (study_dir / "ba_test.yaml").write_text(yaml.safe_dump(study), encoding="utf-8")
        return load_study("ba_test", repo_root_path=root)

    @staticmethod
    def _postal_polygons() -> gpd.GeoDataFrame:
        polygons = [
            Polygon([(-58.45, -34.62), (-58.44, -34.62), (-58.44, -34.61), (-58.45, -34.61)]),
            Polygon([(-58.44, -34.62), (-58.43, -34.62), (-58.43, -34.61), (-58.44, -34.61)]),
        ]
        return gpd.GeoDataFrame(
            {
                "postal_code": ["C1001", "C1002"],
                "label": ["Postal 1", None],
                "source_value": [10, 20],
            },
            geometry=polygons,
            crs="EPSG:4326",
        )

    def test_loads_geojson_and_estimates_southern_utm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spatial_path = root / "inputs" / "postal.geojson"
            spatial_path.parent.mkdir()
            self._postal_polygons().to_file(spatial_path, driver="GeoJSON")
            context = self._make_context(root, spatial_path)

            result = load_spatial_units(context)

            resolved_config = context.resolved_config(spatial_units=result)

        self.assertEqual(
            result.columns[:4].tolist(),
            ["spatial_id", "spatial_name", "area_km2", "geometry"],
        )
        self.assertEqual(result["spatial_id"].tolist(), ["C1001", "C1002"])
        self.assertEqual(result["spatial_name"].tolist(), ["Postal 1", "C1002"])
        self.assertEqual(result.crs.to_epsg(), 4326)
        self.assertEqual(result.attrs["metric_crs"], "EPSG:32721")
        self.assertEqual(resolved_config["crs"]["metric"], "EPSG:32721")
        self.assertEqual(resolved_config["spatial_id_column"], "spatial_id")
        # Regression: the runner-injected resolved config must carry the
        # ``spatial_units`` metadata dict. Without it, layers that resolve
        # per-unit geometry from ``cfg["spatial_units"]`` (greenspace_access
        # bbox tiling, healthcare compact-AOI query) silently fall back to
        # un-tiled per-place-name Overpass queries and time out on large rural
        # units (Bogota's Sumapaz/Usme). See incidentes-multiciudad.md.
        spatial_units_cfg = resolved_config["spatial_units"]
        self.assertIsInstance(spatial_units_cfg, dict)
        self.assertEqual(Path(spatial_units_cfg["path"]).resolve(), spatial_path.resolve())
        self.assertEqual(spatial_units_cfg["id_column"], "postal_code")
        self.assertEqual(spatial_units_cfg["name_column"], "label")
        self.assertEqual(spatial_units_cfg["unit_type"], "postal_code")
        self.assertEqual(spatial_units_cfg["expected_units"], 2)
        self.assertTrue(result["area_km2"].gt(0).all())
        self.assertEqual(result["source_value"].tolist(), [10, 20])

    def test_loads_named_geopackage_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spatial_path = root / "inputs" / "postal.gpkg"
            spatial_path.parent.mkdir()
            self._postal_polygons().to_file(
                spatial_path, layer="postal_areas", driver="GPKG"
            )
            context = self._make_context(root, spatial_path, layer="postal_areas")

            result = load_spatial_units(context)

        self.assertEqual(len(result), 2)
        self.assertEqual(result.attrs["unit_count"], 2)

    def test_duplicate_ids_and_wrong_expected_count_are_rejected(self) -> None:
        duplicate = self._postal_polygons()
        duplicate["postal_code"] = ["same", "same"]

        with self.assertRaisesRegex(SpatialValidationError, "Duplicate spatial IDs"):
            normalize_spatial_units(duplicate, id_column="postal_code")
        with self.assertRaisesRegex(SpatialValidationError, "Expected 3 spatial units"):
            normalize_spatial_units(
                self._postal_polygons(), id_column="postal_code", expected_units=3
            )

    def test_missing_crs_and_non_polygon_geometry_are_rejected(self) -> None:
        no_crs = self._postal_polygons().set_crs(None, allow_override=True)
        points = gpd.GeoDataFrame(
            {"postal_code": ["one"]}, geometry=[Point(-58.4, -34.6)], crs=4326
        )

        with self.assertRaisesRegex(SpatialValidationError, "has no CRS"):
            normalize_spatial_units(no_crs, id_column="postal_code")
        with self.assertRaisesRegex(SpatialValidationError, "must be Polygon"):
            normalize_spatial_units(points, id_column="postal_code")

    def test_invalid_polygon_can_be_repaired_explicitly(self) -> None:
        bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
        invalid = gpd.GeoDataFrame(
            {"postal_code": ["one"]}, geometry=[bowtie], crs=4326
        )

        with self.assertRaisesRegex(SpatialValidationError, "Invalid geometries"):
            normalize_spatial_units(invalid, id_column="postal_code")
        repaired = normalize_spatial_units(
            invalid, id_column="postal_code", repair_invalid=True
        )

        self.assertTrue(repaired.geometry.is_valid.all())
        self.assertGreater(repaired.loc[0, "area_km2"], 0)

    def test_disjoint_location_bbox_is_rejected(self) -> None:
        with self.assertRaisesRegex(SpatialValidationError, "do not overlap"):
            normalize_spatial_units(
                self._postal_polygons(),
                id_column="postal_code",
                bbox=BoundingBox(west=-75, south=-40, east=-74, north=-39),
            )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from scripts.migrations.build_barcelona_districts_reference import build_reference
from exposome.raw_sources import load_source_manifest


class BarcelonaDistrictsReferenceTests(unittest.TestCase):
    def _source(self, root: Path, *, count: int = 10) -> Path:
        source = root / "districtes.geojson"
        gpd.GeoDataFrame(
            {
                "CODI_DISTRICTE": [f"{index:02d}" for index in range(1, count + 1)],
                "NOM_DISTRICTE": [f"District {index}" for index in range(1, count + 1)],
                "geometry": [box(index, 0, index + 1, 1) for index in range(count)],
            },
            crs="EPSG:4326",
        ).to_file(source, driver="GeoJSON")
        return source

    def test_builds_canonical_ten_district_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = build_reference(
                self._source(root),
                target_dir=root / "reference",
                source_url="https://example.test/districtes",
            )
            units = gpd.read_file(output)
            self.assertEqual(len(units), 10)
            self.assertEqual(units["unit_id"].tolist(), [f"{index:02d}" for index in range(1, 11)])
            self.assertEqual(set(units["unit_type"]), {"distrito"})
            metadata = json.loads((output.parent / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["unit_count"], 10)
            self.assertEqual(metadata["source_url"], "https://example.test/districtes")
            self.assertTrue((output.parent / "README.md").is_file())
            snapshot = load_source_manifest(root)
            self.assertEqual(snapshot.provider, "ajuntament-barcelona")
            self.assertEqual(snapshot.dataset, "districtes-municipals")
            self.assertEqual(len(snapshot.assets), 1)

    def test_rejects_non_district_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "Expected 10 Barcelona municipal districts, found 9"):
                build_reference(self._source(root, count=9), target_dir=root / "reference")

    def test_builds_reference_from_official_wkt_json_array(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "BarcelonaCiutat_Districtes.json"
            # The real Open Data BCN endpoint emits this shape, with WKT in
            # ETRS89 / UTM zone 31N, rather than a GeoJSON FeatureCollection.
            records = [
                {
                    "Codi_Districte": f"{index:02d}",
                    "nom_districte": f"District {index}",
                    "geometria_etrs89": box(
                        430000 + index * 1000, 4580000, 430900 + index * 1000, 4580900
                    ).wkt,
                }
                for index in range(1, 11)
            ]
            source.write_text(json.dumps(records), encoding="utf-8")
            output = build_reference(source, target_dir=root / "reference")
            units = gpd.read_file(output)
            self.assertEqual(len(units), 10)
            self.assertEqual(units["unit_id"].tolist(), [f"{index:02d}" for index in range(1, 11)])
            metadata = json.loads((output.parent / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["spatial_id"], "unit_id (Codi_Districte)")

    def test_allows_explicit_source_field_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "custom.geojson"
            gpd.GeoDataFrame(
                {
                    "official_code": [str(index) for index in range(1, 11)],
                    "official_label": [f"District {index}" for index in range(1, 11)],
                    "geometry": [box(index, 0, index + 1, 1) for index in range(10)],
                },
                crs="EPSG:4326",
            ).to_file(source, driver="GeoJSON")
            output = build_reference(
                source,
                target_dir=root / "reference",
                id_column="official_code",
                name_column="official_label",
            )
            self.assertTrue(output.is_file())

    def test_rejects_overlapping_district_polygons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root)
            raw = gpd.read_file(source)
            raw.loc[1, "geometry"] = box(1.5, 0, 2.5, 1)
            raw.to_file(source, driver="GeoJSON")
            with self.assertRaisesRegex(ValueError, "geometries overlap"):
                build_reference(source, target_dir=root / "reference")


if __name__ == "__main__":
    unittest.main()

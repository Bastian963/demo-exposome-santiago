from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exposome.noise_spain import (  # noqa: E402
    LDEN_LAYER,
    _resolve_overlaps,
    build_noise_spain_layer,
)
from exposome.raw_sources import (  # noqa: E402
    RawSnapshotStore,
    build_raw_source_asset,
    load_source_manifest,
    write_source_manifest,
)
from scripts.migrations import ingest_spain_noise_snapshot as ingest  # noqa: E402


class NoiseSpainLayerTests(unittest.TestCase):
    def _snapshot(self, root: Path) -> Path:
        source_gpkg = root / "contours.gpkg"
        contours = gpd.GeoDataFrame(
            {
                "category": ["Lden5559", "Lden6569"],
                "geometry": [box(0, 0, 50, 100), box(50, 0, 100, 100)],
            },
            crs="EPSG:3035",
        )
        contours.to_file(source_gpkg, layer=LDEN_LAYER, driver="GPKG")
        snapshot = root / "raw"
        zip_path = snapshot / "cataluna" / "fixture.zip"
        zip_path.parent.mkdir(parents=True)
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(source_gpkg, "fixture.gpkg")
            archive.writestr("fixture.xml", "<metadata/>")
        asset = build_raw_source_asset(snapshot, zip_path, url="https://example.test/sica")
        write_source_manifest(
            snapshot,
            provider="miteco",
            dataset="sica-mer-agglomerations",
            version="4f-2022",
            license_name="test",
            assets=[asset],
        )
        return snapshot

    def _study(self) -> SimpleNamespace:
        units = gpd.GeoDataFrame(
            {
                "spatial_id": ["a", "b"],
                "spatial_name": ["Área A", "Área B"],
                "area_km2": [0.01, 0.01],
                "geometry": [box(0, 0, 100, 100), box(100, 0, 200, 100)],
            },
            crs="EPSG:3035",
        )
        return SimpleNamespace(
            location=SimpleNamespace(id="cataluna"),
            study=SimpleNamespace(id="cataluna_comarques"),
            spatial_units=units,
        )

    def _pilot_study(self) -> SimpleNamespace:
        pilot = self._study()
        return SimpleNamespace(
            location=SimpleNamespace(id="barcelones"),
            study=SimpleNamespace(
                id="barcelones_noise_pilot",
                raw={"noise_spain": {"source_region": "cataluna", "coverage": "partial"}},
            ),
            spatial_units=pilot.spatial_units.iloc[:1].copy(),
        )

    def test_area_weighted_bands_and_no_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch("exposome.noise_spain.EXPECTED_ARCHIVES", {"cataluna": 1}):
                outputs = build_noise_spain_layer(
                    study=self._study(),
                    raw_dir=self._snapshot(root),
                    cache_dir=root / "cache",
                    out_dir=root / "out",
                )
            table = pd.read_csv(outputs.table).set_index("spatial_id")
            self.assertAlmostEqual(table.loc["a", "noise_lden_band_mean_dba"], 62.0)
            self.assertAlmostEqual(table.loc["a", "noise_lden_ge55_area_pct"], 100.0)
            self.assertAlmostEqual(table.loc["a", "noise_lden_ge65_area_pct"], 50.0)
            self.assertEqual(table.loc["a", "noise_has_modelled_ge55"], 1)
            self.assertTrue(pd.isna(table.loc["b", "noise_lden_band_mean_dba"]))
            self.assertEqual(table.loc["b", "noise_has_modelled_ge55"], 0)
            self.assertEqual(table.loc["b", "noise_agglomeration_count"], 0)
            self.assertTrue(outputs.geometry.is_file())
            self.assertTrue(outputs.metadata.is_file())

    def test_partial_pilot_accepts_a_selected_subset_and_marks_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = self._snapshot(root)
            outputs = build_noise_spain_layer(
                study=self._pilot_study(),
                raw_snapshot=RawSnapshotStore(snapshot, snapshot),
                cache_dir=root / "cache",
                out_dir=root / "out",
            )
            metadata = outputs.metadata.read_text(encoding="utf-8")
            self.assertIn('"coverage":"partial"', metadata)

    def test_cross_agglomeration_overlap_is_resolved_not_rejected(self) -> None:
        contours = gpd.GeoDataFrame(
            {
                "source_id": ["north", "north", "south"],
                "band_midpoint": [62.0, 67.0, 67.0],
                "geometry": [box(0, 0, 10, 10), box(5, 0, 15, 10), box(10, 0, 20, 10)],
            },
            crs="EPSG:3035",
        )
        bands, cross_overlap, within = _resolve_overlaps(contours)
        self.assertAlmostEqual(cross_overlap, 0.2)
        self.assertAlmostEqual(within["north"], 0.25)
        self.assertEqual(within["south"], 0.0)
        self.assertAlmostEqual(float(bands.geometry.area.sum()), 200.0)


class SpainNoiseSnapshotTests(unittest.TestCase):
    def _write_archive(self, directory: Path, *, valid: bool = True) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        archive_path = directory / "MER fixture.zip"
        if not valid:
            archive_path.write_bytes(b"not a ZIP")
            return archive_path
        gpkg_path = directory / "fixture.gpkg"
        gpd.GeoDataFrame(
            {"category": ["Lden5559"], "geometry": [box(0, 0, 1, 1)]},
            crs="EPSG:3035",
        ).to_file(gpkg_path, layer=LDEN_LAYER, driver="GPKG")
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(gpkg_path, "fixture.gpkg")
            archive.writestr("fixture.xml", "<metadata/>")
        return archive_path

    def test_freeze_creates_a_verified_immutable_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._write_archive(source / "Cataluña")
            self._write_archive(source / "Pais Vasco")
            destination = root / "raw"
            with patch.object(ingest, "EXPECTED_COUNTS", {"cataluna": 1, "pais_vasco": 1}):
                copied = ingest.freeze_snapshot(source, destination=destination)
            self.assertEqual(len(copied), 2)
            manifest = destination / "source_manifest.json"
            self.assertTrue(manifest.is_file())
            snapshot = load_source_manifest(destination)
            self.assertEqual(snapshot.provider, "miteco")
            self.assertEqual(len(snapshot.assets), 2)
            self.assertTrue((destination / "cataluna" / "mer_fixture.zip").is_file())
            with patch.object(ingest, "EXPECTED_COUNTS", {"cataluna": 1, "pais_vasco": 1}):
                self.assertEqual(
                    ingest.freeze_snapshot(source, destination=destination),
                    copied,
                )

    def test_freeze_rejects_corrupt_zip_without_creating_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._write_archive(source / "Cataluña")
            self._write_archive(source / "Pais Vasco", valid=False)
            with patch.object(ingest, "EXPECTED_COUNTS", {"cataluna": 1, "pais_vasco": 1}):
                with self.assertRaisesRegex(ValueError, "Invalid ZIP"):
                    ingest.freeze_snapshot(source, destination=root / "raw")
            self.assertFalse((root / "raw" / "source_manifest.json").exists())

    def test_barcelones_pilot_selects_valid_intersection_on_external_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            self._write_archive(source / "Cataluña")
            self._write_archive(source / "Pais Vasco")
            units_path = root / "barcelones.geojson"
            gpd.GeoDataFrame(
                {"unit_id": ["cat_13"], "geometry": [box(0, 0, 2, 2)]},
                crs="EPSG:3035",
            ).to_file(units_path, driver="GeoJSON")
            manifest_root = root / "repo" / "raw" / "pilot"
            payload_root = root / "external" / "miteco" / "pilot"
            with patch.object(ingest, "EXPECTED_COUNTS", {"cataluna": 1, "pais_vasco": 1}):
                copied = ingest.freeze_barcelones_pilot_snapshot(
                    source,
                    spatial_units=units_path,
                    spatial_id="cat_13",
                    destination=manifest_root,
                    payload_root=payload_root,
                )
            self.assertEqual(len(copied), 1)
            snapshot = load_source_manifest(manifest_root, payload_root=payload_root)
            self.assertEqual(snapshot.version, "4f-2022-barcelones-pilot")
            self.assertEqual(len(snapshot.assets), 1)
            self.assertTrue(snapshot.asset_path(snapshot.assets[0]).is_file())


if __name__ == "__main__":
    unittest.main()

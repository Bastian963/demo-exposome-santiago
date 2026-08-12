"""Offline tests for the greenspace showcase renderer."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import numpy as np
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.greenspace_showcase import _build_refined_cv_masks, build_showcase_pdf, render_location_page  # noqa: E402


def _synthetic_scene() -> np.ndarray:
    img = np.full((768, 768, 3), 140, dtype=np.uint8)
    img[140:620, 180:600] = [35, 180, 40]
    img[250:520, 300:700] = [45, 170, 50]
    return img


class TestGreenspaceShowcase(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = {
            "region_query": "Santiago, Chile",
            "greenspace": {
                "cv": {
                    "zoom": 17,
                    "url": "https://example.com/{z}/{x}/{y}.jpg",
                    "exg_min_threshold": 0.05,
                    "min_blob_px": 10,
                },
                "access": {
                    "osm_tags": {"leisure": ["park"]},
                },
            },
            "outputs": {
                "figures_dir": "figures",
                "base_dir": "data/processed",
            },
        }
        self.loc = {
            "name": "Lugar de prueba",
            "comuna": "Santiago",
            "lat": -33.44,
            "lon": -70.64,
            "zoom": 17,
            "n_tiles": 3,
            "category": "OSM submapea",
            "blurb": "Escena sintetica",
        }
        self.green_areas = gpd.GeoDataFrame({"geometry": [box(-70.66, -33.45, -70.64, -33.43)]}, crs="EPSG:4326")

    @patch("exposome.greenspace_showcase.fetch_scene")
    @patch("exposome.greenspace_showcase._rasterize_osm_green")
    def test_render_location_page_returns_stats_in_range(self, mock_rasterize, mock_fetch) -> None:
        mock_fetch.return_value = (_synthetic_scene(), 0, 0)
        osm_mask = np.zeros((768, 768), dtype=bool)
        osm_mask[180:500, 220:520] = True
        mock_rasterize.return_value = osm_mask

        fig, stats = render_location_page(self.loc, self.green_areas, self.cfg, Path("cache"))
        try:
            for key in (
                "osm_pct",
                "cv_strict_pct",
                "cv_refined_pct",
                "cv_unmapped_pct",
                "hybrid_pct",
                "unmapped_share_of_refined_cv",
                "cv_pct",
                "new_pct",
                "outside_pct",
            ):
                self.assertGreaterEqual(stats[key], 0.0)
                self.assertLessEqual(stats[key], 100.0)
            self.assertEqual(stats["name"], self.loc["name"])
            self.assertEqual(len(fig.axes), 4)
        finally:
            fig.clf()

    @patch("exposome.greenspace_showcase.detect_vegetation_exg")
    def test_refined_mask_can_recover_weak_patch_missed_by_strict(self, mock_detect) -> None:
        img = np.full((128, 128, 3), 128, dtype=np.uint8)
        img[40:96, 52:108] = [122, 150, 120]
        mock_detect.return_value = (np.zeros((128, 128), dtype=bool), 0.18)

        masks = _build_refined_cv_masks(img, self.cfg["greenspace"]["cv"])

        self.assertEqual(masks["strict_mask"].sum(), 0)
        self.assertGreater(masks["refined_mask"][50:90, 60:100].mean(), 0.5)
        self.assertGreater(masks["relaxed_mask"][50:90, 60:100].mean(), 0.5)

    @patch("exposome.greenspace_showcase.fetch_scene")
    @patch("exposome.greenspace_showcase._rasterize_osm_green")
    def test_hybrid_metric_preserves_osm_green_when_cv_is_empty(self, mock_rasterize, mock_fetch) -> None:
        mock_fetch.return_value = (np.full((768, 768, 3), 128, dtype=np.uint8), 0, 0)
        osm_mask = np.zeros((768, 768), dtype=bool)
        osm_mask[180:500, 220:520] = True
        mock_rasterize.return_value = osm_mask

        fig, stats = render_location_page(self.loc, self.green_areas, self.cfg, Path("cache"))
        try:
            self.assertAlmostEqual(stats["hybrid_pct"], stats["osm_pct"], places=4)
            self.assertAlmostEqual(stats["cv_unmapped_pct"], 0.0, places=4)
        finally:
            fig.clf()

    @patch("exposome.greenspace_showcase._load_osm_green_areas")
    @patch("exposome.greenspace_showcase.render_location_page")
    @patch("exposome.greenspace_showcase.config.load_config")
    def test_build_showcase_pdf_writes_outputs(self, mock_cfg, mock_render, mock_loader) -> None:
        mock_cfg.return_value = self.cfg
        mock_loader.return_value = self.green_areas

        def fake_render(loc, green_areas, cfg, cache_dir):
            import matplotlib.pyplot as plt

            fig, ax = plt.subplots(figsize=(4, 4))
            ax.imshow(np.zeros((32, 32, 3), dtype=np.uint8))
            ax.axis("off")
            return fig, {
                "name": loc["name"],
                "comuna": loc["comuna"],
                "category": loc["category"],
                "lat": loc["lat"],
                "lon": loc["lon"],
                "zoom": loc["zoom"],
                "n_tiles": loc["n_tiles"],
                "threshold_exg": 0.1,
                "threshold_relaxed_exg": 0.12,
                "osm_pct": 10.0,
                "cv_strict_pct": 20.0,
                "cv_refined_pct": 25.0,
                "cv_unmapped_pct": 15.0,
                "hybrid_pct": 25.0,
                "unmapped_share_of_refined_cv": 60.0,
                "cv_pct": 25.0,
                "new_pct": 15.0,
                "outside_pct": 60.0,
                "osm_pixels": 10,
                "cv_strict_pixels": 20,
                "cv_refined_pixels": 25,
                "cv_unmapped_pixels": 15,
                "hybrid_pixels": 25,
                "cv_pixels": 25,
                "new_pixels": 15,
            }

        mock_render.side_effect = fake_render

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            pdf_path = tmp / "showcase.pdf"
            csv_path = tmp / "showcase.csv"
            png_dir = tmp / "pages"
            df = build_showcase_pdf(
                city="santiago",
                out_pdf=pdf_path,
                out_csv=csv_path,
                figures_subdir=png_dir,
                cache_dir=tmp / "cache",
                locations=[self.loc],
            )

            self.assertTrue(pdf_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue((png_dir / "lugar_de_prueba.png").exists())
            self.assertEqual(len(df), 1)
            cols = [
                "osm_pct",
                "cv_strict_pct",
                "cv_refined_pct",
                "cv_unmapped_pct",
                "hybrid_pct",
                "unmapped_share_of_refined_cv",
                "cv_pct",
                "new_pct",
                "outside_pct",
            ]
            self.assertTrue(((df[cols] >= 0).all().all()))
            self.assertTrue(((df[cols] <= 100).all().all()))


if __name__ == "__main__":
    unittest.main()

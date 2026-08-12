"""Offline tests for the greenspace validation workflow."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome.greenspace_validation import (  # noqa: E402
    build_annotation_batch_manifest,
    build_annotation_queue,
    _confusion_metrics,
    _label_progress,
    evaluate_validation_results,
    _labelme_shapes_to_mask,
    _sites_paths,
    prepare_validation_package,
    run_validation,
    select_validation_sites,
)


def _write_sample_outputs(base: Path) -> None:
    processed = base / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    rows = []
    geoms = []
    for comuna in ("A", "B"):
        values = [
            (0, 10.0, 5.0, 60.0),
            (1, 30.0, 10.0, 20.0),
            (2, 1.0, 0.0, 95.0),
            (3, 5.0, 1.0, 80.0),
            (4, 12.0, 6.0, 40.0),
        ]
        for sample_id, cv_green, osm_green, outside in values:
            rows.append(
                {
                    "name": comuna,
                    "sample_id": sample_id,
                    "cv_green_pct": cv_green,
                    "osm_green_pct": osm_green,
                    "cv_inside_osm_pct": max(0.0, 100.0 - outside),
                    "cv_outside_osm_pct": outside,
                    "method": "exg",
                    "zoom": 17,
                    "exg_threshold": 0.2,
                }
            )
            minx = -70.0 + sample_id * 0.01
            miny = -33.0 - sample_id * 0.01
            geoms.append(
                {
                    "name": comuna,
                    "sample_id": sample_id,
                    "geometry": box(minx, miny, minx + 0.008, miny + 0.008),
                }
            )
    pd.DataFrame(rows).to_csv(processed / "santiago_greenspace_cv_sample.csv", index=False)
    gpd.GeoDataFrame(geoms, crs="EPSG:4326").to_file(processed / "santiago_greenspace_cv_sample.geojson", driver="GeoJSON")


class TestGreenspaceValidation(unittest.TestCase):
    def test_select_validation_sites_picks_three_distinct_samples_per_commune(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_sample_outputs(tmp)
            sites = select_validation_sites(processed_dir=tmp / "data" / "processed", include_showcase=False)
            counts = sites.groupby("name")["site_id"].count().to_dict()
            self.assertEqual(counts, {"A": 3, "B": 3})
            self.assertEqual(sites["site_id"].nunique(), 6)
            self.assertEqual(set(sites["stratum"]), {"osm_green_high", "cv_outside_high", "low_combined_green"})

    def test_labelme_shapes_to_mask_rasterizes_polygon(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            label = Path(tmpdir) / "sample.json"
            payload = {
                "imageWidth": 16,
                "imageHeight": 16,
                "shapes": [
                    {
                        "label": "vegetation",
                        "points": [[2, 2], [12, 2], [12, 12], [2, 12]],
                    }
                ],
            }
            label.write_text(json.dumps(payload), encoding="utf-8")
            mask = _labelme_shapes_to_mask(label)
            self.assertEqual(mask.shape, (16, 16))
            self.assertTrue(mask[5, 5])
            self.assertFalse(mask[0, 0])

    def test_confusion_metrics_basic_values(self) -> None:
        truth = np.zeros((4, 4), dtype=bool)
        pred = np.zeros((4, 4), dtype=bool)
        truth[:2, :2] = True
        pred[:2, 1:3] = True
        metrics = _confusion_metrics(pred, truth)
        self.assertAlmostEqual(metrics["precision"], 0.5)
        self.assertAlmostEqual(metrics["recall"], 0.5)
        self.assertAlmostEqual(metrics["green_pct_pred"], metrics["green_pct_truth"])
        self.assertLess(metrics["iou"], 1.0)

    def test_evaluate_validation_results_pending_when_coverage_is_low(self) -> None:
        metrics = pd.DataFrame(
            [
                {"site_id": "a", "comuna": "A", "source_kind": "sample", "method": "cv_strict", "stratum": "cv_outside_high", "precision": 0.7, "recall": 0.4, "mae_pct": 10.0},
                {"site_id": "a", "comuna": "A", "source_kind": "sample", "method": "cv_refined", "stratum": "cv_outside_high", "precision": 0.65, "recall": 0.6, "mae_pct": 8.0},
                {"site_id": "a", "comuna": "A", "source_kind": "sample", "method": "osm", "stratum": "cv_outside_high", "precision": 0.9, "recall": 0.3, "mae_pct": 12.0},
                {"site_id": "a", "comuna": "A", "source_kind": "sample", "method": "hybrid", "stratum": "cv_outside_high", "precision": 0.75, "recall": 0.55, "mae_pct": 7.0},
            ]
        )
        decision = evaluate_validation_results(metrics, pd.DataFrame())
        self.assertEqual(decision["decision"], "pending_more_labels")

    def test_evaluate_validation_results_excludes_showcase_from_commune_gate(self) -> None:
        rows = []
        for idx in range(99):
            site_id = f"sample_{idx:03d}"
            for method in ("osm", "cv_strict", "cv_refined", "hybrid"):
                rows.append(
                    {
                        "site_id": site_id,
                        "comuna": "A",
                        "source_kind": "sample",
                        "method": method,
                        "stratum": "cv_outside_high",
                        "precision": 0.8,
                        "recall": 0.8,
                        "mae_pct": 5.0,
                    }
                )
        for idx in range(51):
            site_id = f"showcase_{idx:03d}"
            for method in ("osm", "cv_strict", "cv_refined", "hybrid"):
                rows.append(
                    {
                        "site_id": site_id,
                        "comuna": f"Showcase {idx:02d}",
                        "source_kind": "showcase",
                        "method": method,
                        "stratum": "showcase",
                        "precision": 0.8,
                        "recall": 0.8,
                        "mae_pct": 5.0,
                    }
                )
        agreement = pd.DataFrame([{"site_id": "sample_000", "iou": 0.9}])
        decision = evaluate_validation_results(pd.DataFrame(rows), agreement)
        label_coverage = next(c for c in decision["criteria"] if c["name"] == "label_coverage")
        self.assertFalse(label_coverage["passed"])
        self.assertEqual(decision["n_labeled_sites"], 150)
        self.assertEqual(decision["n_communes"], 1)
        self.assertEqual(decision["n_showcase_sites_labeled"], 51)
        self.assertEqual(decision["decision"], "pending_more_labels")

    @patch("exposome.greenspace_validation.fetch_scene")
    def test_prepare_validation_package_writes_sites_images_and_templates(self, mock_fetch) -> None:
        mock_fetch.return_value = (np.full((32, 32, 3), 180, dtype=np.uint8), 0, 0)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            _write_sample_outputs(tmp)
            paths = prepare_validation_package(
                cache_dir=tmp / "cache",
                processed_dir=tmp / "data" / "processed",
                validation_dir=tmp / "data" / "validation",
                include_showcase=False,
            )
            sites = pd.read_csv(paths.sites_csv)
            second_pass = pd.read_csv(paths.second_pass_csv)
            batches = pd.read_csv(paths.batches_csv)
            self.assertEqual(len(sites), 6)
            self.assertEqual(len(second_pass), 6)
            self.assertTrue(sites["second_pass_required"].all())
            self.assertEqual(len(batches), 6)
            self.assertIn("batch_id", sites.columns)
            self.assertTrue((paths.images_dir / f"{sites.iloc[0]['site_id']}.png").exists())
            self.assertTrue((paths.labels_dir / f"{sites.iloc[0]['site_id']}.json").exists())
            self.assertTrue((paths.second_pass_dir / f"{sites.iloc[0]['site_id']}.json").exists())
            self.assertTrue(paths.contact_sheet_pdf.exists())
            progress = _label_progress(sites, paths.labels_dir, paths.second_pass_dir)
            self.assertEqual(progress["official_communes_covered"], 0)
            self.assertEqual(progress["showcase_sites_labeled"], 0)
            self.assertTrue(progress["by_batch"])
            self.assertEqual(progress["by_batch"][0]["batch_id"], "batch_01")
            queue = build_annotation_queue(sites, paths.labels_dir, paths.second_pass_dir)
            self.assertFalse(queue.empty)
            self.assertEqual(queue.iloc[0]["task_type"], "primary")

    @patch("exposome.greenspace_validation._load_osm_green_areas")
    @patch("exposome.greenspace_validation._scene_masks")
    def test_run_validation_writes_metrics_and_summary(self, mock_scene_masks, mock_loader) -> None:
        mock_loader.return_value = gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")

        def fake_masks(city, site, cache_dir, green_areas):
            scene = np.full((16, 16, 3), 150, dtype=np.uint8)
            truth_like = np.zeros((16, 16), dtype=bool)
            truth_like[2:10, 2:10] = True
            return scene, {
                "osm": truth_like.copy(),
                "cv_strict": truth_like.copy(),
                "cv_refined": truth_like.copy(),
                "hybrid": truth_like.copy(),
            }, {
                "threshold_exg": 0.2,
                "threshold_relaxed_exg": 0.12,
            }

        mock_scene_masks.side_effect = fake_masks

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paths = _sites_paths(tmp / "data" / "validation")
            paths.sites_csv.parent.mkdir(parents=True, exist_ok=True)
            paths.labels_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    {
                        "site_id": "site_a",
                        "name": "A",
                        "comuna": "A",
                        "lat": -33.0,
                        "lon": -70.0,
                        "zoom": 17,
                        "n_tiles": 3,
                        "stratum": "showcase",
                        "selection_source": "test",
                        "source_kind": "showcase",
                        "second_pass_required": True,
                        "batch_id": "batch_01",
                    }
                ]
            ).to_csv(paths.sites_csv, index=False)
            pd.DataFrame(
                [
                    {
                        "site_id": "site_a",
                        "name": "A",
                        "comuna": "A",
                        "stratum": "showcase",
                        "source_kind": "showcase",
                        "second_pass_required": True,
                        "batch_id": "batch_01",
                    }
                ]
            ).to_csv(paths.second_pass_csv, index=False)
            label_payload = {
                "imageWidth": 16,
                "imageHeight": 16,
                "shapes": [
                    {"label": "vegetation", "points": [[2, 2], [9, 2], [9, 9], [2, 9]]}
                ],
            }
            (paths.labels_dir / "site_a.json").write_text(json.dumps(label_payload), encoding="utf-8")
            paths.second_pass_dir.mkdir(parents=True, exist_ok=True)
            (paths.second_pass_dir / "site_a.json").write_text(json.dumps(label_payload), encoding="utf-8")
            metrics_path, summary_path = run_validation(
                cache_dir=tmp / "cache",
                validation_dir=tmp / "data" / "validation",
                out_dir=tmp / "data" / "processed",
                include_examples=False,
            )
            metrics = pd.read_csv(metrics_path)
            summary = pd.read_csv(summary_path)
            commune_summary = pd.read_csv(tmp / "data" / "processed" / "santiago_greenspace_cv_validation_summary_by_commune.csv")
            comparison_summary = pd.read_csv(tmp / "data" / "processed" / "santiago_greenspace_cv_validation_comparison_summary.csv")
            method_ranking = pd.read_csv(tmp / "data" / "processed" / "santiago_greenspace_cv_validation_method_ranking.csv")
            agreement = pd.read_csv(tmp / "data" / "processed" / "santiago_greenspace_cv_validation_annotator_agreement.csv")
            metadata = json.loads((tmp / "data" / "processed" / "santiago_greenspace_cv_validation_metadata.json").read_text(encoding="utf-8"))
            decision = json.loads((tmp / "data" / "processed" / "santiago_greenspace_cv_validation_decision.json").read_text(encoding="utf-8"))
            audit_text = (tmp / "data" / "processed" / "santiago_greenspace_cv_validation_audit.md").read_text(encoding="utf-8")
            self.assertEqual(set(metrics["method"]), {"osm", "cv_strict", "cv_refined", "hybrid"})
            self.assertTrue((summary["f1_mean"] == 1.0).all())
            self.assertEqual(set(commune_summary["method"]), {"osm", "cv_strict", "cv_refined", "hybrid"})
            self.assertIn("hybrid_mae_reduction_vs_osm", comparison_summary.columns)
            self.assertIn("best_iou_method", method_ranking.columns)
            self.assertEqual(len(agreement), 1)
            self.assertEqual(float(agreement.iloc[0]["iou"]), 1.0)
            self.assertEqual(metadata["label_progress"]["n_primary_labeled"], 1)
            self.assertEqual(metadata["label_progress"]["n_second_pass_labeled"], 1)
            self.assertEqual(metadata["official_communes_covered"], 0)
            self.assertEqual(metadata["showcase_sites_labeled"], 1)
            self.assertEqual(metadata["label_progress"]["showcase_sites_labeled"], 1)
            self.assertTrue(metadata["label_progress"]["by_batch"])
            self.assertIn("scientific_use_recommendation", metadata)
            self.assertIn("scientific_use_recommendation", decision)
            self.assertIn("## Key Deltas By Stratum", audit_text)
            self.assertEqual(decision["decision"], "pending_more_labels")
            queue = build_annotation_queue(pd.read_csv(paths.sites_csv), paths.labels_dir, paths.second_pass_dir)
            self.assertTrue(queue.empty)

    def test_run_validation_without_labels_writes_pending_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paths = _sites_paths(tmp / "data" / "validation")
            paths.sites_csv.parent.mkdir(parents=True, exist_ok=True)
            paths.labels_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    {
                        "site_id": "site_a",
                        "name": "A",
                        "comuna": "A",
                        "lat": -33.0,
                        "lon": -70.0,
                        "zoom": 17,
                        "n_tiles": 3,
                        "stratum": "showcase",
                        "selection_source": "test",
                        "source_kind": "showcase",
                        "second_pass_required": False,
                        "batch_id": "batch_01",
                    }
                ]
            ).to_csv(paths.sites_csv, index=False)
            pd.DataFrame(columns=["site_id"]).to_csv(paths.second_pass_csv, index=False)
            metrics_path, summary_path = run_validation(
                cache_dir=tmp / "cache",
                validation_dir=tmp / "data" / "validation",
                out_dir=tmp / "data" / "processed",
                include_examples=False,
            )
            metrics = pd.read_csv(metrics_path)
            summary = pd.read_csv(summary_path)
            commune_summary = pd.read_csv(tmp / "data" / "processed" / "santiago_greenspace_cv_validation_summary_by_commune.csv")
            comparison_summary = pd.read_csv(tmp / "data" / "processed" / "santiago_greenspace_cv_validation_comparison_summary.csv")
            method_ranking = pd.read_csv(tmp / "data" / "processed" / "santiago_greenspace_cv_validation_method_ranking.csv")
            metadata = json.loads((tmp / "data" / "processed" / "santiago_greenspace_cv_validation_metadata.json").read_text(encoding="utf-8"))
            decision = json.loads((tmp / "data" / "processed" / "santiago_greenspace_cv_validation_decision.json").read_text(encoding="utf-8"))
            audit_text = (tmp / "data" / "processed" / "santiago_greenspace_cv_validation_audit.md").read_text(encoding="utf-8")
            self.assertTrue(metrics.empty)
            self.assertTrue(summary.empty)
            self.assertTrue(commune_summary.empty)
            self.assertTrue(comparison_summary.empty)
            self.assertTrue(method_ranking.empty)
            self.assertEqual(metadata["label_progress"]["n_primary_labeled"], 0)
            self.assertIn("manual labels are still missing", decision["scientific_use_recommendation"])
            self.assertIn("No comparison summary available yet.", audit_text)
            self.assertEqual(decision["decision"], "pending_no_labels")

    def test_build_annotation_queue_empty_when_everything_is_labeled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            label_dir = tmp / "labels"
            second_pass_dir = tmp / "labels_second_pass"
            label_dir.mkdir()
            second_pass_dir.mkdir()
            sites = pd.DataFrame(
                [
                    {
                        "site_id": "site_a",
                        "comuna": "A",
                        "stratum": "cv_outside_high",
                        "source_kind": "sample",
                        "batch_id": "batch_01",
                        "batch_position": 1,
                        "annotation_order": 1,
                        "second_pass_required": True,
                        "image_path": "image.png",
                        "label_path": "primary.json",
                    }
                ]
            )
            payload = {
                "imageWidth": 16,
                "imageHeight": 16,
                "shapes": [
                    {"label": "vegetation", "points": [[2, 2], [9, 2], [9, 9], [2, 9]]}
                ],
            }
            (label_dir / "site_a.json").write_text(json.dumps(payload), encoding="utf-8")
            (second_pass_dir / "site_a.json").write_text(json.dumps(payload), encoding="utf-8")
            queue = build_annotation_queue(sites, label_dir, second_pass_dir)
            self.assertTrue(queue.empty)

    def test_build_annotation_queue_prioritizes_second_pass_after_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            label_dir = tmp / "labels"
            second_pass_dir = tmp / "labels_second_pass"
            label_dir.mkdir()
            second_pass_dir.mkdir()
            sites = pd.DataFrame(
                [
                    {
                        "site_id": "site_a",
                        "comuna": "A",
                        "stratum": "cv_outside_high",
                        "source_kind": "sample",
                        "batch_id": "batch_01",
                        "batch_position": 1,
                        "annotation_order": 1,
                        "second_pass_required": True,
                        "image_path": "image_a.png",
                        "label_path": "primary_a.json",
                    },
                    {
                        "site_id": "site_b",
                        "comuna": "B",
                        "stratum": "osm_green_high",
                        "source_kind": "sample",
                        "batch_id": "batch_01",
                        "batch_position": 2,
                        "annotation_order": 2,
                        "second_pass_required": True,
                        "image_path": "image_b.png",
                        "label_path": "primary_b.json",
                    },
                ]
            )
            payload = {
                "imageWidth": 16,
                "imageHeight": 16,
                "shapes": [
                    {"label": "vegetation", "points": [[2, 2], [9, 2], [9, 9], [2, 9]]}
                ],
            }
            (label_dir / "site_a.json").write_text(json.dumps(payload), encoding="utf-8")
            queue = build_annotation_queue(sites, label_dir, second_pass_dir)
            self.assertEqual(queue.iloc[0]["site_id"], "site_b")
            self.assertEqual(queue.iloc[0]["task_type"], "primary")
            self.assertEqual(queue.iloc[1]["site_id"], "site_a")
            self.assertEqual(queue.iloc[1]["task_type"], "second_pass")
            batch_manifest, summary = build_annotation_batch_manifest(queue)
            self.assertEqual(summary["batch_id"], "batch_01")
            self.assertEqual(summary["n_pending_tasks"], 3)
            self.assertEqual(batch_manifest.iloc[0]["site_id"], "site_b")

    def test_build_annotation_batch_manifest_honors_explicit_batch(self) -> None:
        queue = pd.DataFrame(
            [
                {
                    "site_id": "site_a",
                    "comuna": "A",
                    "stratum": "showcase",
                    "source_kind": "showcase",
                    "batch_id": "batch_01",
                    "batch_position": 1,
                    "annotation_order": 1,
                    "task_type": "primary",
                    "task_status": "empty_template",
                    "image_path": "a.png",
                    "label_path": "a.json",
                },
                {
                    "site_id": "site_b",
                    "comuna": "B",
                    "stratum": "cv_outside_high",
                    "source_kind": "sample",
                    "batch_id": "batch_02",
                    "batch_position": 1,
                    "annotation_order": 21,
                    "task_type": "primary",
                    "task_status": "empty_template",
                    "image_path": "b.png",
                    "label_path": "b.json",
                },
            ]
        )
        batch_manifest, summary = build_annotation_batch_manifest(queue, batch_id="batch_02")
        self.assertEqual(summary["batch_id"], "batch_02")
        self.assertEqual(summary["n_pending_tasks"], 1)
        self.assertEqual(batch_manifest.iloc[0]["site_id"], "site_b")


if __name__ == "__main__":
    unittest.main()

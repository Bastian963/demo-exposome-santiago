"""Validation workflow for CV and hybrid greenspace methods."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from PIL import Image, ImageDraw

from . import config
from .greenspace_cv import (
    _load_osm_green_areas,
    _rasterize_osm_green,
    _tile2deg,
    detect_vegetation_exg,
    fetch_scene,
)
from .greenspace_showcase import LOCATIONS, _build_refined_cv_masks


@dataclass(frozen=True)
class ValidationPaths:
    """Output locations for greenspace validation artifacts."""

    sites_csv: Path
    images_dir: Path
    labels_dir: Path
    second_pass_dir: Path
    second_pass_csv: Path
    manifest_json: Path
    batches_csv: Path
    contact_sheet_pdf: Path


@dataclass(frozen=True)
class AnnotationQueuePaths:
    """Output locations for annotation queue helpers."""

    queue_csv: Path
    summary_json: Path


@dataclass(frozen=True)
class AnnotationBatchPaths:
    """Output locations for batch-specific annotation helpers."""

    batch_dir: Path
    manifest_csv: Path
    readme_md: Path


LABELING_INSTRUCTIONS = (
    "Annotate polygons labeled 'vegetation' only. Include visible tree canopy, shrubs, grass, "
    "private gardens and planted medians. Exclude shadows, bare soil, water, artificial turf and "
    "uncertain green-painted surfaces."
)


def _slugify(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in text).strip("_")


def _sites_paths(base_dir: Path) -> ValidationPaths:
    root = Path(base_dir) / "greenspace_cv"
    return ValidationPaths(
        sites_csv=root / "greenspace_cv_sites.csv",
        images_dir=root / "images",
        labels_dir=root / "labels",
        second_pass_dir=root / "labels_second_pass",
        second_pass_csv=root / "greenspace_cv_second_pass_sites.csv",
        manifest_json=root / "manifest.json",
        batches_csv=root / "greenspace_cv_annotation_batches.csv",
        contact_sheet_pdf=root / "greenspace_cv_annotation_contact_sheet.pdf",
    )


def _queue_paths(base_dir: Path) -> AnnotationQueuePaths:
    root = Path(base_dir) / "greenspace_cv"
    return AnnotationQueuePaths(
        queue_csv=root / "greenspace_cv_annotation_queue.csv",
        summary_json=root / "greenspace_cv_annotation_queue_summary.json",
    )


def _batch_paths(base_dir: Path, batch_id: str) -> AnnotationBatchPaths:
    batch_dir = Path(base_dir) / "greenspace_cv" / "batches" / batch_id
    return AnnotationBatchPaths(
        batch_dir=batch_dir,
        manifest_csv=batch_dir / f"{batch_id}_annotation_manifest.csv",
        readme_md=batch_dir / "README.md",
    )


def _load_sample_sources(processed_dir: Path) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    csv_path = Path(processed_dir) / "santiago_greenspace_cv_sample.csv"
    geojson_path = Path(processed_dir) / "santiago_greenspace_cv_sample.geojson"
    samples = pd.read_csv(csv_path)
    boxes = gpd.read_file(geojson_path)[["name", "sample_id", "geometry"]]
    merged = samples.merge(boxes, on=["name", "sample_id"], how="left", validate="one_to_one")
    sample_gdf = gpd.GeoDataFrame(merged, geometry="geometry", crs=boxes.crs)
    return samples, sample_gdf


def _pick_distinct_rows(group: pd.DataFrame) -> list[pd.Series]:
    candidates = [
        group.sort_values("osm_green_pct", ascending=False),
        group.sort_values("cv_outside_osm_pct", ascending=False),
        group.assign(_combined=group["osm_green_pct"] + group["cv_green_pct"]).sort_values("_combined", ascending=True),
    ]
    picks: list[pd.Series] = []
    chosen_ids: set[int] = set()
    for ranked in candidates:
        picked = None
        for _, row in ranked.iterrows():
            sid = int(row["sample_id"])
            if sid not in chosen_ids:
                picked = row
                chosen_ids.add(sid)
                break
        if picked is not None:
            picks.append(picked)
    return picks


def select_validation_sites(
    city: str = "santiago",
    processed_dir: Path = Path("data/processed"),
    include_showcase: bool = True,
) -> pd.DataFrame:
    """Build a fixed validation sample from CV outputs plus showcase sites."""
    samples, sample_gdf = _load_sample_sources(processed_dir)
    rows: list[dict[str, Any]] = []
    for comuna, group in sample_gdf.groupby("name", sort=True):
        picks = _pick_distinct_rows(group.reset_index(drop=True))
        labels = [
            ("osm_green_high", "highest_osm_green_pct"),
            ("cv_outside_high", "highest_cv_outside_osm_pct"),
            ("low_combined_green", "lowest_osm_plus_cv_green_pct"),
        ]
        for (stratum, source), row in zip(labels, picks, strict=False):
            minx, miny, maxx, maxy = row.geometry.bounds
            rows.append(
                {
                    "site_id": f"{_slugify(comuna)}_sample_{int(row['sample_id'])}",
                    "name": comuna,
                    "comuna": comuna,
                    "lat": float((miny + maxy) / 2.0),
                    "lon": float((minx + maxx) / 2.0),
                    "zoom": int(row["zoom"]),
                    "n_tiles": 3,
                    "stratum": stratum,
                    "selection_source": source,
                    "source_kind": "sample",
                    "sample_id": int(row["sample_id"]),
                    "cv_green_pct": float(row["cv_green_pct"]),
                    "osm_green_pct": float(row["osm_green_pct"]),
                    "cv_outside_osm_pct": float(row["cv_outside_osm_pct"]),
                    "notes": "",
                }
            )

    if include_showcase:
        for loc in LOCATIONS:
            rows.append(
                {
                    "site_id": f"showcase_{_slugify(loc['name'])}",
                    "name": loc["name"],
                    "comuna": loc["comuna"],
                    "lat": float(loc["lat"]),
                    "lon": float(loc["lon"]),
                    "zoom": int(loc["zoom"]),
                    "n_tiles": int(loc["n_tiles"]),
                    "stratum": "showcase",
                    "selection_source": "showcase_location",
                    "source_kind": "showcase",
                    "sample_id": None,
                    "cv_green_pct": np.nan,
                    "osm_green_pct": np.nan,
                    "cv_outside_osm_pct": np.nan,
                    "notes": loc["category"],
                }
            )

    sites = pd.DataFrame(rows).sort_values(["source_kind", "name", "stratum", "site_id"]).reset_index(drop=True)
    return sites


def _ensure_label_template(
    label_path: Path,
    image_path: Path,
    site: dict[str, Any],
    width: int,
    height: int,
) -> None:
    if label_path.exists():
        return
    payload = {
        "version": "5.0.0",
        "flags": {},
        "shapes": [],
        "imagePath": image_path.name,
        "imageData": None,
        "imageHeight": height,
        "imageWidth": width,
        "metadata": {
            "site_id": site["site_id"],
            "comuna": site["comuna"],
            "stratum": site["stratum"],
            "selection_source": site["selection_source"],
            "instructions": LABELING_INSTRUCTIONS,
        },
    }
    label_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _select_second_pass_sites(sites: pd.DataFrame, n_sites: int = 20) -> pd.DataFrame:
    """Pick a reproducible subset for duplicate annotation."""
    ranked = sites.copy()
    ranked["priority"] = ranked["stratum"].map(
        {
            "showcase": 0,
            "cv_outside_high": 1,
            "osm_green_high": 2,
            "low_combined_green": 3,
        }
    ).fillna(9)
    second_pass = (
        ranked.sort_values(["priority", "source_kind", "name", "site_id"])
        .head(n_sites)
        .drop(columns="priority")
        .copy()
    )
    second_pass["second_pass_required"] = True
    return second_pass


def _assign_annotation_batches(sites: pd.DataFrame, batch_size: int = 20) -> pd.DataFrame:
    batched = sites.copy()
    batched["batch_priority"] = batched["stratum"].map(
        {
            "showcase": 0,
            "cv_outside_high": 1,
            "osm_green_high": 2,
            "low_combined_green": 3,
        }
    ).fillna(9)
    batched = batched.sort_values(["batch_priority", "source_kind", "name", "site_id"]).reset_index(drop=True)
    batched["annotation_order"] = np.arange(1, len(batched) + 1)
    batched["batch_id"] = ((batched["annotation_order"] - 1) // batch_size + 1).map(lambda n: f"batch_{int(n):02d}")
    batched["batch_position"] = ((batched["annotation_order"] - 1) % batch_size) + 1
    return batched.drop(columns="batch_priority")


def _write_contact_sheet(sites: pd.DataFrame, images_dir: Path, pdf_path: Path, per_page: int = 9) -> None:
    if sites.empty:
        return
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    ncols = 3
    nrows = 3
    with PdfPages(pdf_path) as pdf:
        for start in range(0, len(sites), per_page):
            chunk = sites.iloc[start : start + per_page]
            fig, axes = plt.subplots(nrows, ncols, figsize=(11, 11), dpi=180)
            axes = np.asarray(axes).reshape(-1)
            for ax in axes:
                ax.axis("off")
            for ax, (_, row) in zip(axes, chunk.iterrows(), strict=False):
                image_path = images_dir / f"{row['site_id']}.png"
                if image_path.exists():
                    ax.imshow(np.asarray(Image.open(image_path)))
                title = (
                    f"{row['site_id']}\n"
                    f"{row['comuna']} · {row['stratum']}\n"
                    f"{row['batch_id']} #{int(row['batch_position'])}"
                )
                ax.set_title(title, fontsize=8)
                ax.axis("off")
            fig.suptitle(
                f"Greenspace validation annotation contact sheet · scenes {start + 1}-{start + len(chunk)}",
                fontsize=12,
            )
            fig.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)


def prepare_validation_package(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    processed_dir: Path = Path("data/processed"),
    validation_dir: Path = Path("data/validation"),
    include_showcase: bool = True,
) -> ValidationPaths:
    """Export candidate scenes and empty label templates for manual annotation."""
    cfg = config.load_config(city)
    paths = _sites_paths(validation_dir)
    paths.images_dir.mkdir(parents=True, exist_ok=True)
    paths.labels_dir.mkdir(parents=True, exist_ok=True)
    paths.second_pass_dir.mkdir(parents=True, exist_ok=True)
    sites = select_validation_sites(city=city, processed_dir=processed_dir, include_showcase=include_showcase)

    cv_cfg = cfg["greenspace"]["cv"]
    tile_cache = Path(cache_dir) / "cv_tiles"
    manifest_rows: list[dict[str, Any]] = []
    for site in sites.to_dict(orient="records"):
        scene, _, _ = fetch_scene(
            lat=float(site["lat"]),
            lon=float(site["lon"]),
            z=int(site["zoom"]),
            n=int(site["n_tiles"]),
            url_template=cv_cfg["url"],
            cache_dir=tile_cache,
        )
        image_path = paths.images_dir / f"{site['site_id']}.png"
        Image.fromarray(scene).save(image_path)
        label_path = paths.labels_dir / f"{site['site_id']}.json"
        _ensure_label_template(label_path, image_path, site, scene.shape[1], scene.shape[0])
        manifest_rows.append(
            {
                **site,
                "image_path": image_path.as_posix(),
                "label_path": label_path.as_posix(),
                "label_status": "empty_template" if json.loads(label_path.read_text(encoding="utf-8"))["shapes"] == [] else "labeled",
            }
        )

    sites_out = pd.DataFrame(manifest_rows)
    second_pass = _select_second_pass_sites(sites_out)
    second_pass_ids = set(second_pass["site_id"])
    sites_out["second_pass_required"] = sites_out["site_id"].isin(second_pass_ids)
    sites_out = _assign_annotation_batches(sites_out)
    second_pass = second_pass.merge(
        sites_out[["site_id", "batch_id", "annotation_order", "batch_position"]],
        on="site_id",
        how="left",
        validate="one_to_one",
    )
    for site in second_pass.to_dict(orient="records"):
        label_path = paths.second_pass_dir / f"{site['site_id']}.json"
        image_path = paths.images_dir / f"{site['site_id']}.png"
        _ensure_label_template(label_path, image_path, site, int(json.loads((paths.labels_dir / f"{site['site_id']}.json").read_text(encoding="utf-8"))["imageWidth"]), int(json.loads((paths.labels_dir / f"{site['site_id']}.json").read_text(encoding="utf-8"))["imageHeight"]))
    paths.sites_csv.parent.mkdir(parents=True, exist_ok=True)
    sites_out.to_csv(paths.sites_csv, index=False)
    second_pass.to_csv(paths.second_pass_csv, index=False)
    (
        sites_out[
            [
                "site_id",
                "comuna",
                "stratum",
                "batch_id",
                "batch_position",
                "annotation_order",
                "second_pass_required",
            ]
        ]
        .sort_values(["batch_id", "batch_position"])
        .to_csv(paths.batches_csv, index=False)
    )
    _write_contact_sheet(
        sites_out.sort_values(["annotation_order", "site_id"]).reset_index(drop=True),
        paths.images_dir,
        paths.contact_sheet_pdf,
    )
    paths.manifest_json.write_text(
        json.dumps(
            {
                "city": city,
                "n_sites": int(len(sites_out)),
                "n_second_pass_sites": int(len(second_pass)),
                "n_showcase_sites": int((sites_out["source_kind"] == "showcase").sum()),
                "n_sample_sites": int((sites_out["source_kind"] == "sample").sum()),
                "sites_csv": paths.sites_csv.as_posix(),
                "second_pass_csv": paths.second_pass_csv.as_posix(),
                "batches_csv": paths.batches_csv.as_posix(),
                "images_dir": paths.images_dir.as_posix(),
                "labels_dir": paths.labels_dir.as_posix(),
                "second_pass_dir": paths.second_pass_dir.as_posix(),
                "contact_sheet_pdf": paths.contact_sheet_pdf.as_posix(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return paths


def _labelme_shapes_to_mask(label_path: Path) -> np.ndarray:
    payload = json.loads(label_path.read_text(encoding="utf-8"))
    width = int(payload["imageWidth"])
    height = int(payload["imageHeight"])
    mask_img = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask_img)
    for shape in payload.get("shapes", []):
        if shape.get("label") != "vegetation":
            continue
        points = [tuple(point) for point in shape.get("points", [])]
        if len(points) >= 3:
            draw.polygon(points, fill=1)
    return np.asarray(mask_img).astype(bool)


def _label_status(label_path: Path) -> str:
    if not label_path.exists():
        return "missing"
    payload = json.loads(label_path.read_text(encoding="utf-8"))
    return "labeled" if payload.get("shapes") else "empty_template"


def _label_progress(sites: pd.DataFrame, labels_dir: Path, second_pass_dir: Path) -> dict[str, Any]:
    progress_columns = ["site_id", "comuna", "stratum", "second_pass_required"]
    if "source_kind" in sites.columns:
        progress_columns.append("source_kind")
    if "batch_id" in sites.columns:
        progress_columns.append("batch_id")
    progress = sites[progress_columns].copy()
    progress["primary_status"] = progress["site_id"].map(
        lambda site_id: _label_status(labels_dir / f"{site_id}.json")
    )
    progress["second_pass_status"] = progress["site_id"].map(
        lambda site_id: _label_status(second_pass_dir / f"{site_id}.json")
        if bool(progress.loc[progress["site_id"] == site_id, "second_pass_required"].iloc[0])
        else "not_required"
    )
    by_stratum = (
        progress.groupby("stratum", dropna=False)
        .agg(
            n_sites=("site_id", "count"),
            primary_labeled=("primary_status", lambda s: int((s == "labeled").sum())),
            second_pass_required=("second_pass_required", lambda s: int(s.astype(bool).sum())),
            second_pass_labeled=("second_pass_status", lambda s: int((s == "labeled").sum())),
        )
        .reset_index()
    )
    by_stratum["primary_completion_pct"] = 100.0 * by_stratum["primary_labeled"] / by_stratum["n_sites"].clip(lower=1)
    by_stratum["second_pass_completion_pct"] = 100.0 * by_stratum["second_pass_labeled"] / by_stratum["second_pass_required"].clip(lower=1)
    by_batch: list[dict[str, Any]] = []
    if "batch_id" in progress.columns:
        by_batch_df = (
            progress.groupby("batch_id", dropna=False)
            .agg(
                n_sites=("site_id", "count"),
                primary_labeled=("primary_status", lambda s: int((s == "labeled").sum())),
                second_pass_required=("second_pass_required", lambda s: int(s.astype(bool).sum())),
                second_pass_labeled=("second_pass_status", lambda s: int((s == "labeled").sum())),
            )
            .reset_index()
            .sort_values("batch_id")
        )
        by_batch_df["primary_completion_pct"] = 100.0 * by_batch_df["primary_labeled"] / by_batch_df["n_sites"].clip(lower=1)
        by_batch_df["second_pass_completion_pct"] = 100.0 * by_batch_df["second_pass_labeled"] / by_batch_df["second_pass_required"].clip(lower=1)
        by_batch = by_batch_df.to_dict(orient="records")
    official_communes_covered = 0
    if "source_kind" in progress.columns:
        official_labeled = progress[
            (progress["source_kind"] == "sample") & (progress["primary_status"] == "labeled")
        ]
        official_communes_covered = int(official_labeled["comuna"].nunique())
    showcase_sites_labeled = 0
    if "source_kind" in progress.columns:
        showcase_sites_labeled = int(
            progress[
                (progress["source_kind"] == "showcase") & (progress["primary_status"] == "labeled")
            ]["site_id"].nunique()
        )
    return {
        "n_sites": int(len(progress)),
        "n_primary_labeled": int((progress["primary_status"] == "labeled").sum()),
        "n_second_pass_required": int(progress["second_pass_required"].astype(bool).sum()),
        "n_second_pass_labeled": int((progress["second_pass_status"] == "labeled").sum()),
        "official_communes_covered": official_communes_covered,
        "showcase_sites_labeled": showcase_sites_labeled,
        "by_stratum": by_stratum.to_dict(orient="records"),
        "by_batch": by_batch,
    }


def build_annotation_queue(
    sites: pd.DataFrame,
    labels_dir: Path,
    second_pass_dir: Path,
) -> pd.DataFrame:
    """Return pending annotation tasks ordered by batch and priority."""
    queue_rows: list[dict[str, Any]] = []
    for site in sites.to_dict(orient="records"):
        primary_status = _label_status(labels_dir / f"{site['site_id']}.json")
        if primary_status != "labeled":
            queue_rows.append(
                {
                    "site_id": site["site_id"],
                    "comuna": site["comuna"],
                    "stratum": site["stratum"],
                    "source_kind": site.get("source_kind", "sample"),
                    "batch_id": site.get("batch_id", ""),
                    "batch_position": int(site.get("batch_position", 0) or 0),
                    "annotation_order": int(site.get("annotation_order", 0) or 0),
                    "task_type": "primary",
                    "task_status": primary_status,
                    "image_path": site.get("image_path", ""),
                    "label_path": site.get("label_path", ""),
                }
            )
        if bool(site.get("second_pass_required", False)):
            second_pass_path = second_pass_dir / f"{site['site_id']}.json"
            second_pass_status = _label_status(second_pass_path)
            if second_pass_status != "labeled":
                queue_rows.append(
                    {
                        "site_id": site["site_id"],
                        "comuna": site["comuna"],
                        "stratum": site["stratum"],
                        "source_kind": site.get("source_kind", "sample"),
                        "batch_id": site.get("batch_id", ""),
                        "batch_position": int(site.get("batch_position", 0) or 0),
                        "annotation_order": int(site.get("annotation_order", 0) or 0),
                        "task_type": "second_pass",
                        "task_status": second_pass_status,
                        "image_path": site.get("image_path", ""),
                        "label_path": second_pass_path.as_posix(),
                    }
                )
    if not queue_rows:
        return pd.DataFrame(
            columns=[
                "site_id",
                "comuna",
                "stratum",
                "source_kind",
                "batch_id",
                "batch_position",
                "annotation_order",
                "task_type",
                "task_status",
                "image_path",
                "label_path",
            ]
        )
    queue = pd.DataFrame(queue_rows)
    task_priority = {"primary": 0, "second_pass": 1}
    queue["task_priority"] = queue["task_type"].map(task_priority).fillna(9)
    queue = queue.sort_values(
        ["task_priority", "annotation_order", "batch_id", "batch_position", "task_type", "site_id"]
    ).reset_index(drop=True)
    return queue.drop(columns="task_priority")


def build_annotation_batch_manifest(queue: pd.DataFrame, batch_id: str | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return a single-batch manifest and compact summary."""
    if queue.empty:
        empty = pd.DataFrame(columns=queue.columns)
        return empty, {
            "batch_id": "",
            "n_pending_tasks": 0,
            "n_primary_pending": 0,
            "n_second_pass_pending": 0,
            "n_unique_sites": 0,
            "next_site_id": "",
        }
    chosen_batch = batch_id or str(queue.iloc[0]["batch_id"])
    batch_queue = queue[queue["batch_id"] == chosen_batch].copy()
    task_priority = {"primary": 0, "second_pass": 1}
    batch_queue["task_priority"] = batch_queue["task_type"].map(task_priority).fillna(9)
    batch_queue = batch_queue.sort_values(
        ["task_priority", "annotation_order", "batch_position", "site_id"]
    ).reset_index(drop=True)
    summary = {
        "batch_id": chosen_batch,
        "n_pending_tasks": int(len(batch_queue)),
        "n_primary_pending": int((batch_queue["task_type"] == "primary").sum()),
        "n_second_pass_pending": int((batch_queue["task_type"] == "second_pass").sum()),
        "n_unique_sites": int(batch_queue["site_id"].nunique()),
        "next_site_id": str(batch_queue.iloc[0]["site_id"]) if not batch_queue.empty else "",
    }
    return batch_queue.drop(columns="task_priority"), summary


def _confusion_metrics(pred: np.ndarray, truth: np.ndarray) -> dict[str, float]:
    pred = pred.astype(bool)
    truth = truth.astype(bool)
    tp = int((pred & truth).sum())
    fp = int((pred & ~truth).sum())
    fn = int((~pred & truth).sum())
    total = int(pred.size)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    iou = tp / max(tp + fp + fn, 1)
    green_pred = 100.0 * float(pred.mean())
    green_truth = 100.0 * float(truth.mean())
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "iou": iou,
        "green_pct_pred": green_pred,
        "green_pct_truth": green_truth,
        "mae_pct": abs(green_pred - green_truth),
        "false_positive_pct": 100.0 * fp / total,
        "false_negative_pct": 100.0 * fn / total,
    }


def _annotator_agreement(primary: np.ndarray, secondary: np.ndarray) -> dict[str, float]:
    """Agreement between two manual masks."""
    return _confusion_metrics(primary, secondary)


def _mean_for(metrics_df: pd.DataFrame, method: str, metric: str, stratum: str | None = None) -> float | None:
    subset = metrics_df[metrics_df["method"] == method]
    if stratum is not None:
        subset = subset[subset["stratum"] == stratum]
    if subset.empty:
        return None
    return float(subset[metric].mean())


def _official_commune_coverage(metrics_df: pd.DataFrame) -> int:
    if metrics_df.empty:
        return 0
    if "source_kind" not in metrics_df.columns:
        return int(metrics_df["comuna"].nunique())
    sample_metrics = metrics_df[metrics_df["source_kind"] == "sample"]
    return int(sample_metrics["comuna"].nunique()) if not sample_metrics.empty else 0


def _comparison_summary(summary_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for stratum, group in summary_df.groupby("stratum", dropna=False):
        by_method = group.set_index("method").to_dict(orient="index")
        osm = by_method.get("osm", {})
        strict = by_method.get("cv_strict", {})
        refined = by_method.get("cv_refined", {})
        hybrid = by_method.get("hybrid", {})
        rows.append(
            {
                "stratum": stratum,
                "n_sites": int(group["n_sites"].max()) if not group.empty else 0,
                "cv_refined_recall_gain_vs_strict": refined.get("recall_mean", np.nan) - strict.get("recall_mean", np.nan),
                "cv_refined_precision_drop_vs_strict": strict.get("precision_mean", np.nan) - refined.get("precision_mean", np.nan),
                "hybrid_f1_gain_vs_osm": hybrid.get("f1_mean", np.nan) - osm.get("f1_mean", np.nan),
                "hybrid_iou_gain_vs_osm": hybrid.get("iou_mean", np.nan) - osm.get("iou_mean", np.nan),
                "hybrid_mae_reduction_vs_osm": osm.get("mae_pct_mean", np.nan) - hybrid.get("mae_pct_mean", np.nan),
                "hybrid_false_negative_reduction_vs_osm": osm.get("false_negative_pct_mean", np.nan) - hybrid.get("false_negative_pct_mean", np.nan),
                "hybrid_false_positive_increase_vs_osm": hybrid.get("false_positive_pct_mean", np.nan) - osm.get("false_positive_pct_mean", np.nan),
            }
        )
    return pd.DataFrame(rows).sort_values("stratum").reset_index(drop=True)


def _method_ranking_summary(summary_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for stratum, group in summary_df.groupby("stratum", dropna=False):
        if group.empty:
            continue
        best_iou = group.sort_values(["iou_mean", "f1_mean"], ascending=False).iloc[0]
        best_mae = group.sort_values(["mae_pct_mean", "iou_mean"], ascending=[True, False]).iloc[0]
        rows.append(
            {
                "stratum": stratum,
                "n_sites": int(group["n_sites"].max()),
                "best_iou_method": best_iou["method"],
                "best_iou_value": float(best_iou["iou_mean"]),
                "best_f1_method": group.sort_values(["f1_mean", "iou_mean"], ascending=False).iloc[0]["method"],
                "best_f1_value": float(group.sort_values(["f1_mean", "iou_mean"], ascending=False).iloc[0]["f1_mean"]),
                "lowest_mae_method": best_mae["method"],
                "lowest_mae_value": float(best_mae["mae_pct_mean"]),
            }
        )
    return pd.DataFrame(rows).sort_values("stratum").reset_index(drop=True)


def evaluate_validation_results(
    metrics_df: pd.DataFrame,
    agreement_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Apply approval criteria to validation outputs."""
    agreement_df = agreement_df if agreement_df is not None else pd.DataFrame()
    n_sites = int(metrics_df["site_id"].nunique()) if not metrics_df.empty else 0
    n_communes = _official_commune_coverage(metrics_df)
    n_showcase_sites = (
        int(metrics_df.loc[metrics_df["source_kind"] == "showcase", "site_id"].nunique())
        if not metrics_df.empty and "source_kind" in metrics_df.columns
        else 0
    )
    strict_recall = _mean_for(metrics_df, "cv_strict", "recall")
    refined_recall = _mean_for(metrics_df, "cv_refined", "recall")
    strict_precision = _mean_for(metrics_df, "cv_strict", "precision")
    refined_precision = _mean_for(metrics_df, "cv_refined", "precision")
    osm_mae_submap = _mean_for(metrics_df, "osm", "mae_pct", "cv_outside_high")
    hybrid_mae_submap = _mean_for(metrics_df, "hybrid", "mae_pct", "cv_outside_high")
    osm_mae_park = _mean_for(metrics_df, "osm", "mae_pct", "osm_green_high")
    hybrid_mae_park = _mean_for(metrics_df, "hybrid", "mae_pct", "osm_green_high")
    osm_mae_low = _mean_for(metrics_df, "osm", "mae_pct", "low_combined_green")
    hybrid_mae_low = _mean_for(metrics_df, "hybrid", "mae_pct", "low_combined_green")
    agreement_iou_median = float(agreement_df["iou"].median()) if not agreement_df.empty else None

    criteria = [
        {
            "name": "label_coverage",
            "passed": n_sites >= 150 and n_communes >= 52,
            "detail": (
                f"{n_sites} labeled sites with {n_communes} official sample communes covered "
                f"(target: >=150 and 52); showcase scenes labeled: {n_showcase_sites}."
            ),
        },
        {
            "name": "annotator_agreement",
            "passed": agreement_iou_median is not None and agreement_iou_median >= 0.75,
            "detail": (
                f"Median IoU between annotators: {agreement_iou_median:.3f} (target: >=0.75)."
                if agreement_iou_median is not None
                else "No second-pass agreement available yet."
            ),
        },
        {
            "name": "cv_refined_recall_gain",
            "passed": (
                strict_recall is not None
                and refined_recall is not None
                and refined_recall - strict_recall >= 0.15
            ),
            "detail": f"Recall gain cv_refined - cv_strict = {((refined_recall or 0.0) - (strict_recall or 0.0)):.3f} (target: >=0.15).",
        },
        {
            "name": "cv_refined_precision_floor",
            "passed": (
                strict_precision is not None
                and refined_precision is not None
                and refined_precision >= 0.60
                and strict_precision - refined_precision <= 0.10
            ),
            "detail": (
                f"cv_refined precision = {(refined_precision or 0.0):.3f}; "
                f"precision drop vs strict = {((strict_precision or 0.0) - (refined_precision or 0.0)):.3f}."
            ),
        },
        {
            "name": "hybrid_submapping_gain",
            "passed": (
                osm_mae_submap is not None
                and hybrid_mae_submap is not None
                and osm_mae_submap > 0
                and (osm_mae_submap - hybrid_mae_submap) / osm_mae_submap >= 0.20
            ),
            "detail": (
                f"MAE reduction in cv_outside_high = "
                f"{(((osm_mae_submap or 0.0) - (hybrid_mae_submap or 0.0)) / max(osm_mae_submap or 1.0, 1e-9)):.3f}."
            ),
        },
        {
            "name": "hybrid_does_not_break_parks",
            "passed": (
                osm_mae_park is not None
                and hybrid_mae_park is not None
                and hybrid_mae_park - osm_mae_park <= 5.0
            ),
            "detail": f"Hybrid - OSM MAE in osm_green_high = {((hybrid_mae_park or 0.0) - (osm_mae_park or 0.0)):.3f} pp.",
        },
        {
            "name": "hybrid_does_not_break_low_green",
            "passed": (
                osm_mae_low is not None
                and hybrid_mae_low is not None
                and hybrid_mae_low - osm_mae_low <= 5.0
            ),
            "detail": f"Hybrid - OSM MAE in low_combined_green = {((hybrid_mae_low or 0.0) - (osm_mae_low or 0.0)):.3f} pp.",
        },
    ]

    if n_sites == 0:
        decision = "pending_no_labels"
    elif any(c["name"] in {"label_coverage", "annotator_agreement"} and not c["passed"] for c in criteria):
        decision = "pending_more_labels"
    elif all(c["passed"] for c in criteria):
        decision = "approved_as_hybrid_layer"
    elif any(c["name"] == "hybrid_submapping_gain" and c["passed"] for c in criteria):
        decision = "approved_as_validation_only"
    else:
        decision = "not_approved"

    recommendation_map = {
        "pending_no_labels": "No scientific recommendation yet; manual labels are still missing.",
        "pending_more_labels": "Do not approve yet; collect more labels and second-pass agreement before deciding.",
        "approved_as_hybrid_layer": "Use the hybrid mask as the scientific greenspace metric for this validation scope.",
        "approved_as_validation_only": "Keep CV/hybrid as a validation or narrative layer, not as the final master metric.",
        "not_approved": "Do not use CV or hybrid as a final scientific layer in the current form.",
    }

    return {
        "decision": decision,
        "scientific_use_recommendation": recommendation_map[decision],
        "criteria": criteria,
        "n_labeled_sites": n_sites,
        "n_communes": n_communes,
        "n_showcase_sites_labeled": n_showcase_sites,
        "annotator_agreement_iou_median": agreement_iou_median,
    }


def _write_decision_report(report_path: Path, evaluation: dict[str, Any]) -> None:
    showcase_sites_labeled = evaluation.get("n_showcase_sites_labeled", 0)
    lines = [
        "# Greenspace Validation Decision Report",
        "",
        f"- decision: `{evaluation['decision']}`",
        f"- recommendation: {evaluation['scientific_use_recommendation']}",
        f"- labeled_sites: `{evaluation['n_labeled_sites']}`",
        f"- official_communes_covered: `{evaluation['n_communes']}`",
        f"- showcase_sites_labeled: `{showcase_sites_labeled}`",
        f"- annotator_iou_median: `{evaluation['annotator_agreement_iou_median']}`",
        "",
        "## Criteria",
        "",
    ]
    for criterion in evaluation["criteria"]:
        status = "PASS" if criterion["passed"] else "FAIL"
        lines.append(f"- `{criterion['name']}`: **{status}**. {criterion['detail']}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _format_optional(value: Any, decimals: int = 3) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "NA"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.{decimals}f}"
    return str(value)


def _write_audit_report(
    report_path: Path,
    evaluation: dict[str, Any],
    metadata: dict[str, Any],
    comparison_summary_df: pd.DataFrame,
    method_ranking_df: pd.DataFrame,
    agreement_df: pd.DataFrame,
) -> None:
    progress = metadata.get("label_progress", {})
    showcase_sites_labeled = evaluation.get("n_showcase_sites_labeled", 0)
    lines = [
        "# Greenspace CV Validation Audit",
        "",
        "## Decision",
        "",
        f"- decision: `{evaluation['decision']}`",
        f"- recommendation: {evaluation['scientific_use_recommendation']}",
        f"- labeled_sites: `{evaluation['n_labeled_sites']}`",
        f"- official_communes_covered: `{evaluation['n_communes']}`",
        f"- showcase_sites_labeled: `{showcase_sites_labeled}`",
        f"- annotator_iou_median: `{_format_optional(evaluation['annotator_agreement_iou_median'])}`",
        "",
        "## Labeling Progress",
        "",
        f"- primary labels: `{progress.get('n_primary_labeled', 0)} / {progress.get('n_sites', 0)}`",
        f"- second pass labels: `{progress.get('n_second_pass_labeled', 0)} / {progress.get('n_second_pass_required', 0)}`",
        "",
        "## Criteria",
        "",
    ]
    for criterion in evaluation["criteria"]:
        status = "PASS" if criterion["passed"] else "FAIL"
        lines.append(f"- `{criterion['name']}`: **{status}**. {criterion['detail']}")

    lines.extend(["", "## Key Deltas By Stratum", ""])
    if comparison_summary_df.empty:
        lines.append("No comparison summary available yet.")
    else:
        lines.extend(
            [
                "| stratum | n_sites | cv_refined_recall_gain_vs_strict | cv_refined_precision_drop_vs_strict | hybrid_iou_gain_vs_osm | hybrid_mae_reduction_vs_osm |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for _, row in comparison_summary_df.iterrows():
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row["stratum"]),
                        _format_optional(row["n_sites"], 0),
                        _format_optional(row["cv_refined_recall_gain_vs_strict"]),
                        _format_optional(row["cv_refined_precision_drop_vs_strict"]),
                        _format_optional(row["hybrid_iou_gain_vs_osm"]),
                        _format_optional(row["hybrid_mae_reduction_vs_osm"]),
                    ]
                )
                + " |"
            )

    lines.extend(["", "## Best Method By Stratum", ""])
    if method_ranking_df.empty:
        lines.append("No method ranking available yet.")
    else:
        lines.extend(
            [
                "| stratum | n_sites | best_iou_method | best_iou_value | best_f1_method | best_f1_value | lowest_mae_method | lowest_mae_value |",
                "| --- | ---: | --- | ---: | --- | ---: | --- | ---: |",
            ]
        )
        for _, row in method_ranking_df.iterrows():
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(row["stratum"]),
                        _format_optional(row["n_sites"], 0),
                        _format_optional(row["best_iou_method"], 0),
                        _format_optional(row["best_iou_value"]),
                        _format_optional(row["best_f1_method"], 0),
                        _format_optional(row["best_f1_value"]),
                        _format_optional(row["lowest_mae_method"], 0),
                        _format_optional(row["lowest_mae_value"]),
                    ]
                )
                + " |"
            )

    lines.extend(["", "## Annotator Agreement", ""])
    if agreement_df.empty:
        lines.append("No second-pass agreement rows available yet.")
    else:
        lines.append(
            f"Median IoU across second-pass scenes: `{_format_optional(float(agreement_df['iou'].median()))}`."
        )

    lines.extend(
        [
            "",
            "## Interpretation Guardrails",
            "",
            "- Do not approve the hybrid layer while coverage or agreement gates are failing.",
            "- Favor the hybrid layer only if it improves sub-mapped scenes without materially breaking park scenes.",
            "- If gains are narrow, unstable, or driven by false positives, keep CV/hybrid as validation only.",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _empty_validation_evaluation() -> dict[str, Any]:
    return {
        "decision": "pending_no_labels",
        "scientific_use_recommendation": "No scientific recommendation yet; manual labels are still missing.",
        "criteria": [
            {
                "name": "label_coverage",
                "passed": False,
                "detail": "No labeled scenes available yet.",
            },
            {
                "name": "annotator_agreement",
                "passed": False,
                "detail": "No second-pass agreement available yet.",
            },
        ],
        "n_labeled_sites": 0,
        "n_communes": 0,
        "n_showcase_sites_labeled": 0,
        "annotator_agreement_iou_median": None,
    }


def _scene_masks(
    city: str,
    site: dict[str, Any],
    cache_dir: Path,
    green_areas: gpd.GeoDataFrame,
) -> tuple[np.ndarray, dict[str, np.ndarray], dict[str, float]]:
    cfg = config.load_config(city)
    cv_cfg = cfg["greenspace"]["cv"]
    scene, x0, y0 = fetch_scene(
        lat=float(site["lat"]),
        lon=float(site["lon"]),
        z=int(site["zoom"]),
        n=int(site["n_tiles"]),
        url_template=cv_cfg["url"],
        cache_dir=Path(cache_dir) / "cv_tiles",
    )
    cv_masks = _build_refined_cv_masks(scene, cv_cfg)
    north, west = _tile2deg(x0, y0, int(site["zoom"]))
    south, east = _tile2deg(x0 + int(site["n_tiles"]), y0 + int(site["n_tiles"]), int(site["zoom"]))
    osm_mask = _rasterize_osm_green(
        north,
        west,
        south,
        east,
        x0,
        y0,
        int(site["zoom"]),
        int(site["n_tiles"]),
        green_areas,
    )
    methods = {
        "osm": osm_mask,
        "cv_strict": cv_masks["strict_mask"],
        "cv_refined": cv_masks["refined_mask"],
        "hybrid": osm_mask | cv_masks["refined_mask"],
    }
    thresholds = {
        "threshold_exg": cv_masks["strict_thr"],
        "threshold_relaxed_exg": cv_masks["relaxed_thr"],
    }
    return scene, methods, thresholds


def run_validation(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    validation_dir: Path = Path("data/validation"),
    out_dir: Path = Path("data/processed"),
    include_examples: bool = True,
) -> tuple[Path, Path]:
    """Compare OSM, strict CV, refined CV and hybrid masks against manual labels."""
    cfg = config.load_config(city)
    paths = _sites_paths(validation_dir)
    sites = pd.read_csv(paths.sites_csv)
    green_areas = _load_osm_green_areas(
        cfg["region_query"],
        cfg["greenspace"]["access"]["osm_tags"],
        Path(cache_dir) / f"{city}_greenspace_osm.geojson",
    )

    metrics_rows: list[dict[str, Any]] = []
    agreement_rows: list[dict[str, Any]] = []
    missing_labels: list[str] = []
    missing_second_pass_labels: list[str] = []
    example_dir = Path("figures") / "greenspace_cv_validation_examples"
    if include_examples:
        example_dir.mkdir(parents=True, exist_ok=True)

    for site in sites.to_dict(orient="records"):
        label_path = paths.labels_dir / f"{site['site_id']}.json"
        if not label_path.exists():
            missing_labels.append(site["site_id"])
            continue
        truth_mask = _labelme_shapes_to_mask(label_path)
        if truth_mask.sum() == 0:
            missing_labels.append(site["site_id"])
            continue
        second_pass_path = paths.second_pass_dir / f"{site['site_id']}.json"
        if second_pass_path.exists():
            second_truth = _labelme_shapes_to_mask(second_pass_path)
            if second_truth.sum() > 0:
                agreement_rows.append(
                    {
                        "site_id": site["site_id"],
                        "name": site["name"],
                        "comuna": site["comuna"],
                        "stratum": site["stratum"],
                        **_annotator_agreement(truth_mask, second_truth),
                    }
                )
            else:
                missing_second_pass_labels.append(site["site_id"])
        elif bool(site.get("second_pass_required", False)):
            missing_second_pass_labels.append(site["site_id"])
        scene, methods, thresholds = _scene_masks(city, site, cache_dir, green_areas)
        for method_name, mask in methods.items():
            row = {
                "site_id": site["site_id"],
                "name": site["name"],
                "comuna": site["comuna"],
                "stratum": site["stratum"],
                "selection_source": site["selection_source"],
                "source_kind": site.get("source_kind", "sample"),
                "method": method_name,
                **thresholds,
                **_confusion_metrics(mask, truth_mask),
            }
            metrics_rows.append(row)

        if include_examples:
            fig, axes = plt.subplots(1, 5, figsize=(15, 3.6), dpi=180)
            panel_defs = [
                ("Image", scene),
                ("Truth", np.dstack([truth_mask * 180, truth_mask * 255, truth_mask * 120]).astype(np.uint8)),
                ("OSM", np.dstack([methods["osm"] * 0, methods["osm"] * 210, methods["osm"] * 255]).astype(np.uint8)),
                ("CV refined", np.dstack([methods["cv_refined"] * 170, methods["cv_refined"] * 255, methods["cv_refined"] * 0]).astype(np.uint8)),
                ("Hybrid", np.dstack([(methods["hybrid"] & ~methods["osm"]) * 170, methods["hybrid"] * 255, methods["osm"] * 255]).astype(np.uint8)),
            ]
            for ax, (title, panel) in zip(axes, panel_defs, strict=True):
                ax.imshow(panel)
                ax.set_title(title, fontsize=9)
                ax.axis("off")
            fig.suptitle(site["site_id"], fontsize=10)
            fig.tight_layout()
            fig.savefig(example_dir / f"{site['site_id']}.png", bbox_inches="tight")
            plt.close(fig)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / f"{city}_greenspace_cv_validation_metrics.csv"
    summary_path = out_dir / f"{city}_greenspace_cv_validation_summary.csv"
    commune_summary_path = out_dir / f"{city}_greenspace_cv_validation_summary_by_commune.csv"
    comparison_summary_path = out_dir / f"{city}_greenspace_cv_validation_comparison_summary.csv"
    method_ranking_path = out_dir / f"{city}_greenspace_cv_validation_method_ranking.csv"
    agreement_path = out_dir / f"{city}_greenspace_cv_validation_annotator_agreement.csv"
    metadata_path = out_dir / f"{city}_greenspace_cv_validation_metadata.json"
    decision_json_path = out_dir / f"{city}_greenspace_cv_validation_decision.json"
    decision_md_path = out_dir / f"{city}_greenspace_cv_validation_decision.md"
    audit_md_path = out_dir / f"{city}_greenspace_cv_validation_audit.md"
    figure_path = Path("figures") / "greenspace_cv_validation_summary.png"
    agreement_df = pd.DataFrame(agreement_rows)

    if metrics_rows:
        metrics_df = pd.DataFrame(metrics_rows)
        summary_df = (
            metrics_df.groupby(["method", "stratum"], dropna=False)
            .agg(
                n_sites=("site_id", "nunique"),
                precision_mean=("precision", "mean"),
                recall_mean=("recall", "mean"),
                f1_mean=("f1", "mean"),
                iou_mean=("iou", "mean"),
                mae_pct_mean=("mae_pct", "mean"),
                false_positive_pct_mean=("false_positive_pct", "mean"),
                false_negative_pct_mean=("false_negative_pct", "mean"),
            )
            .reset_index()
        )
        commune_summary_df = (
            metrics_df.groupby(["method", "comuna"], dropna=False)
            .agg(
                n_sites=("site_id", "nunique"),
                precision_mean=("precision", "mean"),
                recall_mean=("recall", "mean"),
                f1_mean=("f1", "mean"),
                iou_mean=("iou", "mean"),
                mae_pct_mean=("mae_pct", "mean"),
                green_pct_pred_mean=("green_pct_pred", "mean"),
                green_pct_truth_mean=("green_pct_truth", "mean"),
            )
            .reset_index()
        )
        comparison_summary_df = _comparison_summary(summary_df)
        method_ranking_df = _method_ranking_summary(summary_df)
        metrics_df.to_csv(metrics_path, index=False)
        summary_df.to_csv(summary_path, index=False)
        commune_summary_df.to_csv(commune_summary_path, index=False)
        comparison_summary_df.to_csv(comparison_summary_path, index=False)
        method_ranking_df.to_csv(method_ranking_path, index=False)
        if not agreement_df.empty:
            agreement_df.to_csv(agreement_path, index=False)
        evaluation = evaluate_validation_results(metrics_df, agreement_df)
        figure_path.parent.mkdir(parents=True, exist_ok=True)
        plot_df = summary_df.sort_values(["stratum", "method"]).copy()
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), dpi=180)
        x = np.arange(len(plot_df))
        axes[0].bar(x, plot_df["f1_mean"], color="#2e7d32")
        axes[0].set_title("F1 mean")
        axes[0].set_ylim(0, 1)
        axes[0].set_xticks(x, [f"{m}\n{s}" for m, s in zip(plot_df["method"], plot_df["stratum"], strict=True)], rotation=45, ha="right")
        axes[1].bar(x, plot_df["mae_pct_mean"], color="#00838f")
        axes[1].set_title("MAE of green cover (%)")
        axes[1].set_xticks(x, [f"{m}\n{s}" for m, s in zip(plot_df["method"], plot_df["stratum"], strict=True)], rotation=45, ha="right")
        for ax in axes:
            ax.grid(axis="y", alpha=0.25)
            ax.tick_params(axis="x", labelsize=8)
        fig.tight_layout()
        fig.savefig(figure_path, bbox_inches="tight")
        plt.close(fig)
    else:
        metrics_df = pd.DataFrame(
            columns=[
                "site_id",
                "name",
                "comuna",
                "stratum",
                "selection_source",
                "source_kind",
                "method",
                "threshold_exg",
                "threshold_relaxed_exg",
                "precision",
                "recall",
                "f1",
                "iou",
                "green_pct_pred",
                "green_pct_truth",
                "mae_pct",
                "false_positive_pct",
                "false_negative_pct",
            ]
        )
        summary_df = pd.DataFrame(
            columns=[
                "method",
                "stratum",
                "n_sites",
                "precision_mean",
                "recall_mean",
                "f1_mean",
                "iou_mean",
                "mae_pct_mean",
                "false_positive_pct_mean",
                "false_negative_pct_mean",
            ]
        )
        commune_summary_df = pd.DataFrame(
            columns=[
                "method",
                "comuna",
                "n_sites",
                "precision_mean",
                "recall_mean",
                "f1_mean",
                "iou_mean",
                "mae_pct_mean",
                "green_pct_pred_mean",
                "green_pct_truth_mean",
            ]
        )
        comparison_summary_df = pd.DataFrame(
            columns=[
                "stratum",
                "n_sites",
                "cv_refined_recall_gain_vs_strict",
                "cv_refined_precision_drop_vs_strict",
                "hybrid_f1_gain_vs_osm",
                "hybrid_iou_gain_vs_osm",
                "hybrid_mae_reduction_vs_osm",
                "hybrid_false_negative_reduction_vs_osm",
                "hybrid_false_positive_increase_vs_osm",
            ]
        )
        method_ranking_df = pd.DataFrame(
            columns=[
                "stratum",
                "n_sites",
                "best_iou_method",
                "best_iou_value",
                "best_f1_method",
                "best_f1_value",
                "lowest_mae_method",
                "lowest_mae_value",
            ]
        )
        metrics_df.to_csv(metrics_path, index=False)
        summary_df.to_csv(summary_path, index=False)
        commune_summary_df.to_csv(commune_summary_path, index=False)
        comparison_summary_df.to_csv(comparison_summary_path, index=False)
        method_ranking_df.to_csv(method_ranking_path, index=False)
        evaluation = _empty_validation_evaluation()

    label_progress = _label_progress(sites, paths.labels_dir, paths.second_pass_dir)
    audit_metadata = {
        "city": city,
        "label_progress": label_progress,
        "summary_figure": figure_path.as_posix(),
    }
    decision_json_path.write_text(json.dumps(evaluation, indent=2), encoding="utf-8")
    _write_decision_report(decision_md_path, evaluation)
    _write_audit_report(
        audit_md_path,
        evaluation,
        audit_metadata,
        comparison_summary_df,
        method_ranking_df,
        agreement_df,
    )
    metadata_path.write_text(
        json.dumps(
            {
                "city": city,
                "n_labeled_sites": int(metrics_df["site_id"].nunique()),
                "methods": sorted(metrics_df["method"].unique().tolist()),
                "missing_or_empty_labels": missing_labels,
                "missing_second_pass_labels": missing_second_pass_labels,
                "annotator_agreement_csv": agreement_path.as_posix() if not agreement_df.empty else "",
                "annotator_agreement_n_sites": int(agreement_df["site_id"].nunique()) if not agreement_df.empty else 0,
                "annotator_agreement_iou_median": float(agreement_df["iou"].median()) if not agreement_df.empty else None,
                "decision_json": decision_json_path.as_posix(),
                "decision_md": decision_md_path.as_posix(),
                "audit_md": audit_md_path.as_posix(),
                "decision": evaluation["decision"],
                "scientific_use_recommendation": evaluation["scientific_use_recommendation"],
                "official_communes_covered": evaluation["n_communes"],
                "showcase_sites_labeled": evaluation["n_showcase_sites_labeled"],
                "commune_summary_csv": commune_summary_path.as_posix(),
                "comparison_summary_csv": comparison_summary_path.as_posix(),
                "method_ranking_csv": method_ranking_path.as_posix(),
                "sites_csv": paths.sites_csv.as_posix(),
                "second_pass_csv": paths.second_pass_csv.as_posix(),
                "batches_csv": paths.batches_csv.as_posix(),
                "labels_dir": paths.labels_dir.as_posix(),
                "second_pass_dir": paths.second_pass_dir.as_posix(),
                "summary_figure": figure_path.as_posix(),
                "contact_sheet_pdf": paths.contact_sheet_pdf.as_posix(),
                "label_progress": label_progress,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return metrics_path, summary_path

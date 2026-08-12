"""Export the REAL sub-commune green grid for the webapp.

Replaces the synthetic ``subcomuna/ndvi.geojson`` placeholder (commune mean +
Gaussian noise) with a genuine 1 km grid whose value is the Dynamic World
green-cover fraction computed per cell via Google Earth Engine.

Output is study-local ``data/processed/.../subcomuna/green.geojson``.  The
publisher attaches it only to the matching study bundle.  Commune boundaries
never define the grid origin or its values; they only delimit the visible AOI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import ee
import geopandas as gpd
from shapely import make_valid, union_all
from shapely.geometry import MultiPolygon, Polygon, mapping
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome import gee  # noqa: E402
from exposome.greenspace_multisource import build_dynamic_world_masks  # noqa: E402
from exposome.spatial_detail import build_aligned_metric_grid  # noqa: E402
from exposome.studies import load_study  # noqa: E402

# Each batch's cell polygons are embedded directly in the reduceRegions
# request (client-side geometries, not a server-side asset reference), so the
# request itself -- not just the response -- counts against Earth Engine's
# 10 MiB payload limit. 1500 (and even 435, Medellin's whole grid in one
# batch) overflowed it for cities with more irregular/mountainous comuna
# boundaries and thus higher-vertex-count cells. Smaller batches, more
# round-trips, but safely under the limit regardless of geometry complexity.
BATCH_SIZE = 200


def _valid_polygonal(geometry):
    """Return a valid polygonal geometry after the CRS transformation.

    Reprojecting a clipped grid can create tiny self-intersections where an
    administrative boundary meets a cell edge. Earth Engine encodes those as
    NaN in the request, so only valid polygonal pieces may be sampled.
    """
    fixed = geometry if geometry.is_valid else make_valid(geometry)
    parts = []

    def collect(value):
        if isinstance(value, (Polygon, MultiPolygon)):
            parts.append(value)
        elif hasattr(value, "geoms"):
            for child in value.geoms:
                collect(child)

    collect(fixed)
    if not parts:
        return None
    merged = union_all(parts)
    return merged if merged.is_valid else make_valid(merged)


def _build_cells(aoi: gpd.GeoDataFrame, *, metric_crs: str) -> list[dict]:
    """One stable 1-km grid over the dissolved study AOI."""
    grid = build_aligned_metric_grid(aoi, spacing_m=1000, metric_crs=metric_crs)
    grid = grid.to_crs("EPSG:4326")
    cells = []
    for row in grid.itertuples():
        geometry = _valid_polygonal(row.geometry)
        if geometry is not None and not geometry.is_empty and geometry.is_valid:
            cells.append({"cell_id": row.cell_id, "geometry": geometry})
    return cells


def _load_checkpoint(path: Path) -> dict[str, float | None]:
    """Load completed cell values from an interrupt-safe local checkpoint."""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("values")
    if not isinstance(values, dict):
        raise RuntimeError(f"Invalid green-detail checkpoint: {path}")
    return {
        str(cell_id): None if value is None else float(value)
        for cell_id, value in values.items()
    }


def _write_checkpoint(path: Path, values: dict[str, float | None]) -> None:
    """Atomically persist every completed batch so an overnight run resumes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"version": 1, "values": values}, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(path)


def _green_fraction_per_cell(
    green_band: ee.Image,
    cells: list[dict],
    scale: int,
    *,
    checkpoint_path: Path,
) -> list[float | None]:
    """Zonal mean of the DW green mask, checkpointing after every GEE batch."""
    values_by_cell = _load_checkpoint(checkpoint_path)
    batches = range(0, len(cells), BATCH_SIZE)
    for start in tqdm(batches, desc="Dynamic World detail batches", unit="batch"):
        batch = cells[start : start + BATCH_SIZE]
        if all(cell["cell_id"] in values_by_cell for cell in batch):
            continue
        features = [
            ee.Feature(ee.Geometry(mapping(cell["geometry"])), {"idx": start + i})
            for i, cell in enumerate(batch)
        ]
        fc = ee.FeatureCollection(features)
        reduced = green_band.reduceRegions(
            collection=fc, reducer=ee.Reducer.mean(), scale=scale, crs="EPSG:4326", tileScale=8
        )
        # Only idx/green|mean are read below; drop the echoed input geometry
        # before fetching so the response doesn't add to the payload too.
        reduced = reduced.map(lambda feature: ee.Feature(None, feature.toDictionary()))
        rows = gee.fc_to_dicts(reduced)
        # reduceRegions names the single-band mean property "mean" (not "green").
        by_idx = {
            int(r["idx"]): (r["green"] if "green" in r else r.get("mean"))
            for r in rows
            if "idx" in r
        }
        for i, cell in enumerate(batch):
            frac = by_idx.get(start + i)
            values_by_cell[cell["cell_id"]] = (
                None if frac is None else round(float(frac) * 100, 2)
            )
        _write_checkpoint(checkpoint_path, values_by_cell)
    return [values_by_cell.get(cell["cell_id"]) for cell in cells]


def main(study: str = "santiago_communes") -> None:
    context = load_study(study)
    if context.is_native:
        raise ValueError("Green detail must be built for the visible aggregate study")
    communes = context.load_spatial_units()
    cfg = context.resolved_config(spatial_units=communes)
    gee.init_gee()

    dw_cfg = cfg["greenspace"]["dynamic_world"]
    # The AOI is geometry only. Administrative attributes from the combined
    # AMBA file contain legitimate missing values, which must not become JSON
    # NaN literals in the Earth Engine graph.
    roi = gee.gdf_to_feature_collection(communes[["geometry"]]).geometry()
    green_band = build_dynamic_world_masks(
        roi=roi,
        years=dw_cfg["years"],
        season_months=dw_cfg["season_months"],
        green_classes=dw_cfg["green_classes"],
    ).select("green")

    print("Building one AOI-wide 1 km grid (communes are mask only)...")
    cells = _build_cells(communes, metric_crs=cfg["crs"]["metric"])
    scale = int(dw_cfg.get("fine_scale_meters", dw_cfg["native_scale_meters"]))
    print(f"  {len(cells)} cells; computing real Dynamic World green fraction at {scale} m...")
    checkpoint = context.paths.layer_cache("greenspace_multisource") / "green_detail_1km.json"
    values = _green_fraction_per_cell(
        green_band, cells, scale, checkpoint_path=checkpoint
    )

    features = []
    for cell, value in zip(cells, values, strict=True):
        if value is None:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "value": value,
                    "pixel_id": cell["cell_id"],
                },
                "geometry": mapping(cell["geometry"]),
            }
        )

    payload = {
        "type": "FeatureCollection",
        "exposome": "green",
        "column": "green_total_pct",
        "source": "GOOGLE/DYNAMICWORLD/V1 (argmax green cover, Oct-Mar)",
        "analysis_resolution_m": 1000,
        "source_resolution_m": 10,
        "sample_scale_m": scale,
        "grid_alignment": "study_aoi_metric_grid",
        "is_synthetic": False,
        "n_features": len(features),
        "features": features,
    }
    out_path = context.paths.processed / "subcomuna" / "green.geojson"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"Wrote {out_path.relative_to(REPO_ROOT)} ({len(features)} cells, {size_kb:.1f} KB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", default="santiago_communes")
    args = parser.parse_args()
    main(study=args.study)

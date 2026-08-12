"""Compatibility entrypoint for AOI-wide native ALAN COG publication.

Legacy helpers are retained for offline geometry tests only.  The entrypoint
uses the native study raster, avoiding Chile-specific CRS and commune tiles.
"""
from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

import ee
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, box, shape

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome import boundaries, config, gee  # noqa: E402
from exposome.alan import _annual_radiance_image  # noqa: E402
from exposome.spatial_detail import build_study_detail  # noqa: E402

OUT_PATH = REPO_ROOT / "webapp" / "public" / "data" / "subcomuna" / "alan.geojson"


def slugify(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().replace(" ", "_").replace("-", "_")
    return "".join(c for c in s if c.isalnum() or c == "_").strip("_") or "unknown"


def round_floats(obj, decimals: int = 5):
    if isinstance(obj, float):
        if obj != obj:
            return None
        return round(obj, decimals)
    if isinstance(obj, dict):
        return {k: round_floats(v, decimals) for k, v in obj.items()}
    if isinstance(obj, list):
        return [round_floats(v, decimals) for v in obj]
    return obj


def _iter_tiles(communes: gpd.GeoDataFrame, tile_size_m: int) -> gpd.GeoDataFrame:
    metric = communes.to_crs("EPSG:32719")
    rows: list[dict] = []
    for row in metric.itertuples():
        minx, miny, maxx, maxy = row.geometry.bounds
        xs = np.arange(minx, maxx + tile_size_m, tile_size_m)
        ys = np.arange(miny, maxy + tile_size_m, tile_size_m)
        for x0 in xs[:-1]:
            for y0 in ys[:-1]:
                tile = box(x0, y0, x0 + tile_size_m, y0 + tile_size_m)
                clipped = row.geometry.intersection(tile)
                if clipped.is_empty:
                    continue
                rows.append(
                    {
                        "commune_name": row.name,
                        "commune_slug": slugify(row.name),
                        "geometry": clipped,
                    }
                )
    return gpd.GeoDataFrame(rows, crs="EPSG:32719").to_crs("EPSG:4326")


def _sample_pixels(
    image: ee.Image,
    band: str,
    scale_m: int,
    tiles: gpd.GeoDataFrame,
) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    for tile in tiles.itertuples():
        sampled = image.select(band).sample(
            region=ee.Geometry(tile.geometry.__geo_interface__),
            scale=scale_m,
            geometries=True,
            tileScale=4,
        )
        rows = gee.fc_to_dicts(sampled)
        if not rows:
            continue
        df = pd.DataFrame(rows)
        if band not in df.columns:
            continue
        df = df.rename(columns={band: "value"})
        df["name"] = tile.commune_name
        df["commune_slug"] = tile.commune_slug
        chunks.append(df[["name", "commune_slug", "value", "geometry"]])
    if not chunks:
        raise RuntimeError("ALAN tile sampling returned no pixel rows")
    df = pd.concat(chunks, ignore_index=True)
    df = df[df["value"].notna()].copy()
    return df


def _pixels_from_existing_geojson(path: Path) -> pd.DataFrame:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict] = []
    for feature in data.get("features", []):
        geom = shape(feature["geometry"])
        props = feature.get("properties", {})
        rows.append(
            {
                "name": props.get("commune_name") or props.get("commune_slug") or "unknown",
                "value": props.get("value"),
                "geometry": geom.centroid.__geo_interface__,
            }
        )
    if not rows:
        raise RuntimeError(f"No features found in offline ALAN source: {path}")
    return pd.DataFrame(rows)


def _infer_axis_step(
    primary: pd.Series,
    secondary: pd.Series,
    *,
    group_rounding: int = 4,
    coord_rounding: int = 6,
) -> float:
    diffs: list[float] = []
    frame = pd.DataFrame({"primary": primary, "secondary": secondary})
    for _, group in frame.groupby(frame["secondary"].round(group_rounding)):
        coords = np.array(sorted({round(float(v), coord_rounding) for v in group["primary"]}))
        group_diffs = np.diff(coords)
        group_diffs = group_diffs[group_diffs > 1e-6]
        diffs.extend(group_diffs.tolist())
    if not diffs:
        coords = np.array(sorted({round(float(v), coord_rounding) for v in primary}))
        global_diffs = np.diff(coords)
        diffs = global_diffs[global_diffs > 1e-6].tolist()
    if len(diffs) == 0:
        raise RuntimeError("Unable to infer ALAN native grid spacing from sampled points")
    return float(np.median(diffs))


def _pixel_id(lon: float, lat: float) -> str:
    return f"{lon:.6f}_{lat:.6f}"


def _points_to_native_rectangles(
    pixels: pd.DataFrame,
    cfg: dict,
) -> tuple[gpd.GeoDataFrame, dict[str, float]]:
    gdf = gpd.GeoDataFrame(
        pixels[["name", "value"]].copy(),
        geometry=pixels["geometry"].map(shape),
        crs=cfg["crs"]["geographic"],
    )
    if not gdf.geometry.map(lambda geom: isinstance(geom, Point)).all():
        raise RuntimeError("ALAN sampling must return point geometries at pixel centers")
    gdf["center_lon"] = gdf.geometry.x
    gdf["center_lat"] = gdf.geometry.y
    step_lon = _infer_axis_step(gdf["center_lon"], gdf["center_lat"])
    step_lat = _infer_axis_step(gdf["center_lat"], gdf["center_lon"])
    half_lon = step_lon / 2.0
    half_lat = step_lat / 2.0
    gdf["commune_name"] = gdf["name"]
    gdf["commune_slug"] = gdf["name"].map(slugify)
    gdf["pixel_id"] = [
        _pixel_id(lon, lat)
        for lon, lat in zip(gdf["center_lon"], gdf["center_lat"], strict=False)
    ]
    gdf = gdf.drop(columns=["name"])
    gdf["value"] = gdf["value"].astype(float).round(4)
    gdf["geometry"] = [
        box(lon - half_lon, lat - half_lat, lon + half_lon, lat + half_lat)
        for lon, lat in zip(gdf["center_lon"], gdf["center_lat"], strict=False)
    ]
    gdf = gdf.drop(columns=["center_lon", "center_lat"])
    grid_meta = {
        "pixel_width_deg": round(step_lon, 6),
        "pixel_height_deg": round(step_lat, 6),
    }
    return gdf, grid_meta


def main(study: str = "santiago_communes") -> None:
    """Materialize the existing native ALAN raster locally; no GEE request."""
    results = build_study_detail(study, indicators=["alan"], resume=True)
    print(results[0].message)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", default="santiago_communes")
    args = parser.parse_args()
    main(study=args.study)

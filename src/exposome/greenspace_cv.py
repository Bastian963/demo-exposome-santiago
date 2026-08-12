"""High-resolution greenspace detection via computer vision.

Provides two methods:
- ``exg``: fast CPU-based vegetation detection with Excess Green + Otsu.
- ``sam``: GPU-based segmentation refinement with Segment Anything (optional,
  slow, intended for overnight runs).

The layer is designed as a validation/sampled complement to the OSM and
satellite coverage layers, not as a full regional replacement.
"""
from __future__ import annotations

import io
import json
import math
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
import requests
from PIL import Image, ImageDraw
from scipy import ndimage
from tqdm import tqdm

from . import boundaries, config

warnings.filterwarnings("ignore", category=UserWarning)


def _deg2tile(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def _tile2deg(x: float, y: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


def _fetch_tile(z: int, x: int, y: int, url_template: str, cache_dir: Path) -> tuple[int, int, np.ndarray]:
    """Fetch a single Esri World Imagery tile with local caching.

    Returns (tile_x, tile_y, rgb_array).
    """
    fp = cache_dir / f"{z}_{x}_{y}.jpg"
    if fp.exists():
        return x, y, np.asarray(Image.open(fp).convert("RGB"))
    r = requests.get(
        url_template.format(z=z, x=x, y=y),
        timeout=60,
        headers={"User-Agent": "exposome-cv"},
    )
    r.raise_for_status()
    fp.write_bytes(r.content)
    return x, y, np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"))


def fetch_scene(
    lat: float,
    lon: float,
    z: int,
    n: int,
    url_template: str,
    cache_dir: Path,
    max_workers: int = 9,
) -> tuple[np.ndarray, int, int]:
    """Build an NxN tile mosaic centered on (lat, lon).

    Returns (rgb_array, x0, y0) where x0/y0 are the tile coordinates of the
    top-left corner. Tiles are downloaded in parallel.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    xf, yf = _deg2tile(lat, lon, z)
    x0, y0 = int(xf) - n // 2, int(yf) - n // 2

    coords = [(x0 + i, y0 + j) for j in range(n) for i in range(n)]
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_fetch_tile, z, x, y, url_template, cache_dir)
            for x, y in coords
        ]
        tiles = { (x, y): arr for x, y, arr in [f.result() for f in futures] }

    rows = [np.hstack([tiles[(x0 + i, y0 + j)] for i in range(n)]) for j in range(n)]
    img = np.vstack(rows)
    return img, x0, y0


def _otsu_threshold(x: np.ndarray) -> float:
    """Otsu threshold for a 1-D array of values."""
    x = x[np.isfinite(x)]
    hist, edges = np.histogram(x, bins=256)
    centers = (edges[:-1] + edges[1:]) / 2
    w = hist.astype(float)
    total = w.sum()
    if total == 0:
        return 0.0
    wB = np.cumsum(w)
    wF = total - wB
    sum_b = np.cumsum(w * centers)
    sum_total = (w * centers).sum()
    mB = np.divide(sum_b, wB, out=np.zeros_like(sum_b), where=wB > 0)
    mF = np.divide(sum_total - sum_b, wF, out=np.zeros_like(sum_b), where=wF > 0)
    var_between = wB * wF * (mB - mF) ** 2
    return centers[int(np.argmax(var_between))]


def detect_vegetation_exg(
    rgb: np.ndarray,
    min_threshold: float = 0.05,
    min_blob_px: int = 10,
) -> tuple[np.ndarray, float]:
    """Detect vegetation using Excess Green + Otsu + green-dominance filter."""
    a = rgb.astype(float)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    s = R + G + B + 1e-6
    exg = 2 * (G / s) - (R / s) - (B / s)
    thr = max(_otsu_threshold(exg), min_threshold)
    veg = (exg > thr) & (G >= R) & (G >= B)
    veg = ndimage.binary_opening(veg, structure=np.ones((3, 3)))
    labeled, k = ndimage.label(veg)
    if k:
        sizes = ndimage.sum(np.ones_like(labeled), labeled, range(1, k + 1))
        veg = np.isin(labeled, np.where(sizes >= min_blob_px)[0] + 1)
    return veg, thr


def _rasterize_osm_green(
    north: float,
    west: float,
    south: float,
    east: float,
    x0: int,
    y0: int,
    z: int,
    n: int,
    green_areas: gpd.GeoDataFrame,
) -> np.ndarray:
    """Rasterize cached OSM green-area polygons to the tile pixel grid."""
    from shapely.geometry import box
    W = H = n * 256
    tile_bbox = box(west, south, east, north)
    candidates = green_areas[green_areas.geometry.intersects(tile_bbox)]
    if candidates.empty:
        return np.zeros((H, W), dtype=bool)

    mask_img = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(mask_img)
    for geom in candidates.geometry:
        polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for poly in polys:
            pts = []
            for lon_, lat_ in poly.exterior.coords:
                xt, yt = _deg2tile(lat_, lon_, z)
                pts.append(((xt - x0) * 256, (yt - y0) * 256))
            if len(pts) >= 3:
                draw.polygon(pts, fill=1)
    return np.asarray(mask_img).astype(bool)


def _load_osm_green_areas(
    region_query: str,
    green_tags: dict[str, list[str]],
    cache_path: Path,
) -> gpd.GeoDataFrame:
    """Load OSM green areas from cache or download them once."""
    cache_path = Path(cache_path)
    if cache_path.exists():
        return gpd.read_file(cache_path)

    ox.settings.requests_timeout = 300
    gdf = ox.features_from_place(region_query, tags=green_tags)
    gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].copy().reset_index(drop=True)
    gdf["geometry"] = gdf.geometry.buffer(0)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    keep_cols = ["geometry", "name", "leisure", "landuse"]
    available = [c for c in keep_cols if c in gdf.columns]
    gdf = gdf[available].copy()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(cache_path, driver="GeoJSON")
    return gdf


def _sample_points(
    communes: gpd.GeoDataFrame,
    samples_per_commune: int,
    rng: np.random.Generator,
) -> gpd.GeoDataFrame:
    """Generate random sample points inside each commune."""
    samples = []
    for _, row in communes.iterrows():
        geom = row.geometry
        minx, miny, maxx, maxy = geom.bounds
        pts = []
        attempts = 0
        while len(pts) < samples_per_commune and attempts < samples_per_commune * 50:
            x = rng.uniform(minx, maxx)
            y = rng.uniform(miny, maxy)
            p = gpd.points_from_xy([x], [y], crs=communes.crs)[0]
            if geom.contains(p):
                pts.append(p)
            attempts += 1
        for p in pts:
            samples.append({"name": row["name"], "geometry": p})
    return gpd.GeoDataFrame(samples, crs=communes.crs)


def build_greenspace_cv_layer(
    city: str = "santiago",
    method: str = "exg",
    samples_per_commune: int = 5,
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    seed: int = 42,
) -> tuple[Path, Path]:
    """Build the high-resolution CV greenspace validation layer."""
    cfg = config.load_config(city)
    if method not in ("exg", "sam"):
        raise ValueError(f"Unknown CV method: {method}. Use 'exg' or 'sam'.")

    cache_dir = Path(cache_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    cv_cfg = cfg["greenspace"]["cv"]
    z = cv_cfg["zoom"]
    n = 3  # 3x3 tile mosaic -> ~768x768 px
    url_template = cv_cfg["url"]
    green_tags = cfg["greenspace"]["access"]["osm_tags"]

    print(f"Building greenspace CV layer for {city} (method={method})")

    # Load communes, OSM green areas and sample points
    cache_path = cache_dir / f"{city}_communes.geojson"
    communes = boundaries.get_communes(cfg, cache_path=cache_path)
    metric_crs = cfg["crs"]["metric"]
    communes_metric = communes.to_crs(metric_crs)

    green_cache = cache_dir / f"{city}_greenspace_osm.geojson"
    print("Loading OSM green areas...")
    green_areas = _load_osm_green_areas(cfg["region_query"], green_tags, green_cache)
    print(f"  {len(green_areas)} green-area polygons cached")

    rng = np.random.default_rng(seed)
    samples = _sample_points(communes_metric, samples_per_commune, rng)
    samples_wgs = samples.to_crs(cfg["crs"]["geographic"])

    tile_cache = cache_dir / "cv_tiles"

    rows = []
    for idx, row in tqdm(
        list(samples_wgs.iterrows()), desc=f"greenspace_cv [{city}]", unit="scene"
    ):
        lat, lon = row.geometry.y, row.geometry.x
        scene, x0, y0 = fetch_scene(lat, lon, z, n, url_template, tile_cache)

        if method == "exg":
            veg_mask, thr = detect_vegetation_exg(
                scene,
                min_threshold=cv_cfg["exg_min_threshold"],
                min_blob_px=cv_cfg["min_blob_px"],
            )
        else:
            raise NotImplementedError(
                "SAM method is not implemented yet. Run with --method exg."
            )

        north, west = _tile2deg(x0, y0, z)
        south, east = _tile2deg(x0 + n, y0 + n, z)
        osm_mask = _rasterize_osm_green(north, west, south, east, x0, y0, z, n, green_areas)

        veg_total = veg_mask.sum()
        inside = (veg_mask & osm_mask).sum()
        outside = veg_total - inside
        cv_green_pct = 100 * veg_mask.mean()
        osm_green_pct = 100 * osm_mask.mean()
        inside_pct = 100 * inside / max(veg_total, 1)
        outside_pct = 100 * outside / max(veg_total, 1)

        # Build bounding box geometry in WGS84
        from shapely.geometry import box
        bbox = box(west, south, east, north)

        rows.append({
            "name": row["name"],
            "sample_id": idx,
            "cv_green_pct": round(cv_green_pct, 2),
            "osm_green_pct": round(osm_green_pct, 2),
            "cv_inside_osm_pct": round(inside_pct, 2),
            "cv_outside_osm_pct": round(outside_pct, 2),
            "method": method,
            "zoom": z,
            "exg_threshold": round(thr, 3) if method == "exg" else None,
            "geometry": bbox,
        })

    result = gpd.GeoDataFrame(rows, crs=cfg["crs"]["geographic"])

    # Aggregate per commune for easier comparison
    agg = result.groupby("name").agg(
        cv_green_pct_mean=("cv_green_pct", "mean"),
        cv_green_pct_std=("cv_green_pct", "std"),
        osm_green_pct_mean=("osm_green_pct", "mean"),
        cv_outside_osm_pct_mean=("cv_outside_osm_pct", "mean"),
        n_samples=("sample_id", "count"),
    ).reset_index()
    agg["cv_green_pct_mean"] = agg["cv_green_pct_mean"].round(2)
    agg["cv_green_pct_std"] = agg["cv_green_pct_std"].round(2).fillna(0)
    agg["osm_green_pct_mean"] = agg["osm_green_pct_mean"].round(2)
    agg["cv_outside_osm_pct_mean"] = agg["cv_outside_osm_pct_mean"].round(2)
    agg["n_samples"] = agg["n_samples"].astype(int)

    base_name = f"{city}_greenspace_cv_sample"
    csv_path = out_dir / f"{base_name}.csv"
    geojson_path = out_dir / f"{base_name}.geojson"
    agg_csv_path = out_dir / f"{city}_greenspace_cv_commune.csv"

    # CSV without geometry for sample detail, plus aggregate
    result.drop(columns="geometry").to_csv(csv_path, index=False)
    agg.to_csv(agg_csv_path, index=False)
    result.to_file(geojson_path, driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "method": method,
        "samples_per_commune": samples_per_commune,
        "actual_samples": int(len(result)),
        "zoom": z,
        "tile_mosaic": f"{n}x{n}",
        "source": cv_cfg["source"],
        "outputs": [csv_path.name, geojson_path.name, agg_csv_path.name],
    }
    (out_dir / f"{base_name}_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )

    print(f"Wrote {csv_path.name}: {len(result)} samples")
    print(f"Wrote {agg_csv_path.name}: {len(agg)} communes")
    print(f"Wrote {geojson_path.name}")

    return csv_path, geojson_path

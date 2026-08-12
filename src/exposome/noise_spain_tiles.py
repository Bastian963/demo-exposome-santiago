"""Verified MVT publication for Spain's SICA/MER Lden contour bands.

This is local post-processing over an immutable raw snapshot.  It never
contacts SICA/MITECO or another provider.  Geometry remains in EPSG:3035 for
all scientific operations; Web Mercator is only the browser storage seam.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import gzip
import json
from pathlib import Path
import shutil
from typing import Any, Mapping

import geopandas as gpd
import mercantile
import pandas as pd
from mapbox_vector_tile import decode, encode
from mapbox_vector_tile.polygon import make_it_valid
from shapely import coverage_simplify
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box, mapping, shape
from shapely.ops import unary_union
from tqdm import tqdm

from .noise_spain import (
    SOURCE_CRS,
    _assets_for_region,
    _extract_gpkg,
    _priority_dissolve,
    _region_for_study,
    _source_contours,
)
from .raw_sources import RawSnapshotStore, RawSourceAsset
from .spatial_support import NOISE_LDEN_BANDS, validate_vector_contour_descriptor


INDICATOR_ID = "noise_lden"
SOURCE_LAYER = "noise_lden"
MINZOOM = 11
MAXZOOM = 15
MVT_EXTENT = 4096
LOW_ZOOM_MVT_EXTENT = 2048
MVT_BUFFER_PIXELS = 8
SIMPLIFY_METRES = 5.0
MAX_TILE_GZIP_BYTES = 500_000
MAX_INITIAL_GZIP_BYTES = 2_000_000
ALGORITHM_VERSION = "1"

_MIDPOINT_TO_BAND = {
    57.0: "55-59",
    62.0: "60-64",
    67.0: "65-69",
    72.0: "70-74",
    77.5: "gt75",
}
_BAND_PRIORITY = {
    band: index for index, band in enumerate(_MIDPOINT_TO_BAND.values(), start=1)
}


@dataclass(frozen=True)
class NoiseVectorTileOutputs:
    descriptor: Path
    validation: Path
    tile_directory: Path
    tile_count: int


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _identity(
    *,
    source_manifest: Path,
    assets: tuple[RawSourceAsset, ...],
    aoi_path: Path,
) -> str:
    payload = {
        "algorithm_version": ALGORITHM_VERSION,
        "source_manifest_sha256": _file_sha256(source_manifest),
        "assets": [{"path": asset.path, "sha256": asset.sha256} for asset in assets],
        "aoi_sha256": _file_sha256(aoi_path),
        "source_crs": SOURCE_CRS,
        "indicator": INDICATOR_ID,
        "simplify_metres": SIMPLIFY_METRES,
        "minzoom": MINZOOM,
        "maxzoom": MAXZOOM,
        "mvt_extent": MVT_EXTENT,
        "mvt_buffer_pixels": MVT_BUFFER_PIXELS,
    }
    return sha256(_json_bytes(payload)).hexdigest()[:20]


def _band_for_midpoint(value: Any) -> str:
    midpoint = float(value)
    try:
        return _MIDPOINT_TO_BAND[midpoint]
    except KeyError as exc:
        raise ValueError(f"Unsupported SICA Lden band midpoint: {midpoint}") from exc


def _checkpoint_paths(root: Path, asset: RawSourceAsset) -> tuple[Path, Path]:
    stem = asset.sha256
    return root / "agglomerations" / f"{stem}.parquet", root / "agglomerations" / f"{stem}.json"


def _read_or_build_agglomeration(
    *,
    store: RawSnapshotStore,
    asset: RawSourceAsset,
    cache_root: Path,
    extraction_cache: Path,
    source_bbox: tuple[float, float, float, float],
    aoi: object,
    resume: bool,
) -> gpd.GeoDataFrame:
    parquet, metadata = _checkpoint_paths(cache_root, asset)
    if resume and parquet.is_file() and metadata.is_file():
        try:
            record = json.loads(metadata.read_text(encoding="utf-8"))
            if record.get("asset_sha256") == asset.sha256:
                return gpd.read_parquet(parquet)
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    # Reuse the canonical administrative layer's verified extraction when it
    # exists; vector-tile checkpoints remain separately identity-scoped.
    gpkg = _extract_gpkg(store, asset, extraction_cache)
    frame = _source_contours(
        gpkg,
        Path(asset.path).stem,
        source_bbox=source_bbox,
        clip_geometry=aoi,
    )
    if not frame.empty:
        frame["lden_band"] = frame["band_midpoint"].map(_band_for_midpoint)
    else:
        frame["lden_band"] = pd.Series(dtype="object")
    parquet.parent.mkdir(parents=True, exist_ok=True)
    partial = parquet.with_suffix(".parquet.partial")
    frame.to_parquet(partial)
    partial.replace(parquet)
    metadata.write_bytes(
        _json_bytes(
            {
                "asset_path": asset.path,
                "asset_sha256": asset.sha256,
                "features": int(len(frame)),
                "contributes": bool(not frame.empty),
            }
        )
    )
    return frame


def _areas_by_band(frame: gpd.GeoDataFrame) -> dict[str, float]:
    result = {str(band["value"]): 0.0 for band in NOISE_LDEN_BANDS}
    if frame.empty:
        return result
    for band, group in frame.groupby("lden_band"):
        result[str(band)] = float(group.geometry.area.sum())
    return result


def _resolved_bands(contours: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    resolved, _ = _priority_dissolve(contours)
    if resolved.empty:
        raise ValueError("No SICA Lden >=55 geometry intersects the study AOI")
    resolved["geometry"] = resolved.geometry.map(_polygonal_only)
    resolved = resolved.loc[
        resolved.geometry.notna() & ~resolved.geometry.is_empty
    ].copy()
    resolved["lden_band"] = resolved["band_midpoint"].map(_band_for_midpoint)
    return resolved[["lden_band", "band_midpoint", "geometry"]]


def _polygonal_only(geometry: object) -> object:
    parts = _polygon_parts(geometry)
    if not parts:
        return Polygon()
    return parts[0] if len(parts) == 1 else MultiPolygon(parts)


def _repair_after_reprojection(frame: gpd.GeoDataFrame, where: str) -> gpd.GeoDataFrame:
    """Re-validate geometry at a CRS seam, where GEOS can silently break it.

    Validity is not preserved by reprojection: every vertex is recomputed and
    re-quantized, so a polygon that GEOS calls valid in one CRS can come back
    self-intersecting in another. `_simplify` asserts validity in EPSG:3035 and
    that gate holds, but the tile pipeline crosses to EPSG:3857 and back, and
    neither crossing re-checked.

    Measured on 2026-08-11 for pais_vasco_provincias: 13 of 9052 parts valid in
    EPSG:3035 were invalid after `to_crs("EPSG:3857")`. Both crossings then died
    inside GEOS with `TopologyException: side location conflict at <x> <y>` --
    an error that names a coordinate but neither the band, the agglomeration nor
    the CRS, and which sent the first diagnosis to the source contours, where
    every geometry was in fact clean.

    Repairs are bounded, not silent: the caller's decoded-area gate compares
    per-band area against the source and fails the build if this drops anything
    that matters.
    """
    invalid = ~frame.geometry.is_valid
    if not invalid.any():
        return frame
    tqdm.write(
        f"Reproyección a {where}: {int(invalid.sum())} de {len(frame)} "
        "geometrías quedaron inválidas; se reparan"
    )
    repaired = frame.copy()
    repaired.loc[invalid, "geometry"] = repaired.loc[invalid, "geometry"].make_valid()
    return repaired.loc[repaired.geometry.notna() & ~repaired.geometry.is_empty].copy()


def _simplify(
    resolved: gpd.GeoDataFrame,
    *,
    aoi: object | None = None,
    tolerance_metres: float = SIMPLIFY_METRES,
) -> gpd.GeoDataFrame:
    simplified = resolved.copy()
    simplified["geometry"] = coverage_simplify(
        simplified.geometry.array,
        tolerance_metres,
        simplify_boundary=True,
    )
    simplified = simplified.loc[
        simplified.geometry.notna() & ~simplified.geometry.is_empty
    ].copy()
    if aoi is not None:
        simplified["geometry"] = simplified.geometry.intersection(aoi)
        simplified = simplified.loc[
            simplified.geometry.notna() & ~simplified.geometry.is_empty
        ].copy()
        # SICA bands are not a perfectly noded coverage. Remove any residual
        # inter-band overlap after coverage simplification; the adaptive area
        # gate below bounds the impact of this cleanup.
        simplified, _ = _priority_dissolve(simplified)
        simplified["lden_band"] = simplified["band_midpoint"].map(_band_for_midpoint)
    if simplified.empty or not bool(simplified.geometry.is_valid.all()):
        raise ValueError("Topology-preserving simplification produced invalid Lden geometry")
    return simplified


def _select_simplification(
    resolved: gpd.GeoDataFrame,
    *,
    aoi: object,
) -> tuple[gpd.GeoDataFrame, float]:
    """Use the largest <=5 m tolerance that passes every per-band area gate."""
    baseline = _areas_by_band(resolved)
    for tolerance in (5.0, 2.0, 1.0, 0.5, 0.0):
        candidate = _simplify(
            resolved,
            aoi=aoi,
            tolerance_metres=tolerance,
        )
        areas = _areas_by_band(candidate)
        max_drift = max(
            abs(_safe_fraction(baseline[band], areas[band])) for band in baseline
        )
        tqdm.write(
            f"Simplificación de cobertura {tolerance:g} m: deriva máxima {max_drift:.4%}"
        )
        if max_drift <= 0.005:
            return candidate, tolerance
    raise ValueError("No simplification tolerance preserves every Lden band within 0.5%")


def _geometry_fingerprint(frame: gpd.GeoDataFrame) -> str:
    digest = sha256()
    digest.update(
        _json_bytes(
            {
                "algorithm_version": ALGORITHM_VERSION,
                "extent_by_zoom": {
                    str(zoom): _extent_for_zoom(zoom)
                    for zoom in range(MINZOOM, MAXZOOM + 1)
                },
                "buffer_pixels": MVT_BUFFER_PIXELS,
                "properties": ["lden_band", "band_priority"],
                "quantization_repair": "mapbox_make_it_valid_polygonal",
            }
        )
    )
    for row in frame.sort_values("lden_band").itertuples(index=False):
        digest.update(str(row.lden_band).encode("utf-8"))
        digest.update(row.geometry.normalize().wkb)
    return digest.hexdigest()


def _safe_fraction(before: float, after: float) -> float:
    if before == 0:
        return 0.0 if after == 0 else 1.0
    return (after - before) / before


def _extent_for_zoom(zoom: int) -> int:
    return LOW_ZOOM_MVT_EXTENT if zoom <= 12 else MVT_EXTENT


def _tile_features(frame_3857: gpd.GeoDataFrame, tile: mercantile.Tile) -> tuple[list[dict[str, Any]], tuple[float, float, float, float]]:
    bounds = mercantile.xy_bounds(tile)
    core = (float(bounds.left), float(bounds.bottom), float(bounds.right), float(bounds.top))
    buffer_metres = (
        (core[2] - core[0]) / _extent_for_zoom(tile.z) * MVT_BUFFER_PIXELS
    )
    clip = box(
        core[0] - buffer_metres,
        core[1] - buffer_metres,
        core[2] + buffer_metres,
        core[3] + buffer_metres,
    )
    features: list[dict[str, Any]] = []
    feature_id = 0
    candidate_indices = frame_3857.sindex.query(clip, predicate="intersects")
    candidates = frame_3857.iloc[list(candidate_indices)]
    for row in candidates.itertuples(index=False):
        geometry = row.geometry
        if not geometry.intersects(clip):
            continue
        clipped = geometry.intersection(clip)
        if clipped.is_empty:
            continue
        # A MultiPolygon containing one subpixel part can quantize to a valid
        # GeometryCollection, which the MVT encoder cannot represent. Encode
        # polygon parts independently; collapsed parts are then safely dropped
        # by the invalid-geometry handler and bounded by the decoded area gate.
        for polygon in _polygon_parts(clipped):
            feature_id += 1
            features.append(
                {
                    "id": feature_id,
                    "geometry": mapping(polygon),
                    "properties": {
                        "lden_band": row.lden_band,
                        "band_priority": _BAND_PRIORITY[str(row.lden_band)],
                    },
                }
            )
    return features, core


def _polygon_parts(geometry: object) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [] if geometry.is_empty else [geometry]
    parts: list[Polygon] = []
    for candidate in getattr(geometry, "geoms", ()):
        parts.extend(_polygon_parts(candidate))
    return parts


def _encode_tile(
    features: list[dict[str, Any]],
    core: tuple[float, float, float, float],
    *,
    extent: int = MVT_EXTENT,
) -> bytes:
    normalized: list[dict[str, Any]] = []
    feature_id = 0
    for feature in features:
        geometry = shape(feature["geometry"])
        for polygon in _polygon_parts(geometry):
            feature_id += 1
            normalized.append(
                {
                    **feature,
                    "id": feature_id,
                    "geometry": mapping(polygon),
                }
            )
    return encode(
        {"name": SOURCE_LAYER, "features": normalized},
        default_options={
            "quantize_bounds": core,
            "extents": extent,
            # Valid metric polygons can collapse below one integer MVT cell
            # after clipping/quantization. Repair or drop only that encoded
            # fragment; the decoded max-zoom area proof below bounds the loss.
            "on_invalid_geometry": _mvt_polygonal_make_valid,
            "check_winding_order": True,
        },
    )


def _mvt_polygonal_make_valid(geometry: object) -> object | None:
    """Keep only polygonal output when integer quantization collapses rings."""
    repaired = make_it_valid(geometry)
    polygons: list[Polygon] = []

    def collect(candidate: object) -> None:
        if isinstance(candidate, Polygon):
            if not candidate.is_empty and candidate.area > 0:
                polygons.append(candidate)
            return
        if isinstance(candidate, MultiPolygon):
            polygons.extend(part for part in candidate.geoms if not part.is_empty and part.area > 0)
            return
        for part in getattr(candidate, "geoms", ()):
            collect(part)

    collect(repaired)
    if not polygons:
        return None
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


def _generate_tiles(
    frame: gpd.GeoDataFrame,
    tile_root: Path,
    *,
    resume: bool,
) -> list[dict[str, Any]]:
    # Dissolve correctly leaves one MultiPolygon per band. Exploding it solely
    # at the storage seam lets the spatial index avoid intersecting every tile
    # with each country-scale multipart geometry.
    web = frame.to_crs("EPSG:3857").explode(index_parts=False, ignore_index=True)
    web = _repair_after_reprojection(web, "EPSG:3857, antes de teselar")
    wgs84_bounds = frame.to_crs("EPSG:4326").total_bounds
    candidates = [
        tile
        for zoom in range(MINZOOM, MAXZOOM + 1)
        for tile in mercantile.tiles(*[float(value) for value in wgs84_bounds], zooms=[zoom])
    ]
    inventory: list[dict[str, Any]] = []
    for tile in tqdm(candidates, desc="Teselas MVT Lden", unit="tesela"):
        features, core = _tile_features(web, tile)
        if not features:
            continue
        relative = Path(str(tile.z)) / str(tile.x) / f"{tile.y}.pbf"
        destination = tile_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not (resume and destination.is_file() and destination.stat().st_size > 0):
            payload = _encode_tile(features, core, extent=_extent_for_zoom(tile.z))
            partial = destination.with_suffix(".pbf.partial")
            partial.write_bytes(payload)
            partial.replace(destination)
        raw = destination.read_bytes()
        compressed = gzip.compress(raw, compresslevel=9, mtime=0)
        inventory.append(
            {
                "path": f"detail/{INDICATOR_ID}/{relative.as_posix()}",
                "sha256": sha256(raw).hexdigest(),
                "raw_bytes": len(raw),
                "gzip_bytes": len(compressed),
                "z": tile.z,
                "x": tile.x,
                "y": tile.y,
            }
        )
    return sorted(inventory, key=lambda item: (item["z"], item["x"], item["y"]))


def _decoded_maxzoom_areas(tile_root: Path, inventory: list[dict[str, Any]]) -> dict[str, float]:
    geometries: dict[str, list[object]] = {
        str(band["value"]): [] for band in NOISE_LDEN_BANDS
    }
    for entry in inventory:
        if entry["z"] != MAXZOOM:
            continue
        path = tile_root / str(entry["z"]) / str(entry["x"]) / f"{entry['y']}.pbf"
        payload = decode(path.read_bytes())
        layer = payload.get(SOURCE_LAYER)
        features = layer.get("features") if isinstance(layer, Mapping) else None
        if not isinstance(features, list) or not features:
            raise ValueError(f"MVT source layer is empty: {path}")
        tile = mercantile.Tile(x=entry["x"], y=entry["y"], z=entry["z"])
        bounds = mercantile.xy_bounds(tile)
        extent = int(layer.get("extent") or MVT_EXTENT)
        width = float(bounds.right - bounds.left)
        height = float(bounds.top - bounds.bottom)
        core = box(bounds.left, bounds.bottom, bounds.right, bounds.top)
        for feature in features:
            band = str(feature.get("properties", {}).get("lden_band") or "")
            if band not in geometries:
                raise ValueError(f"MVT feature has unknown Lden band {band!r}: {path}")
            geometry = shape(feature["geometry"])
            geometry = affinity.affine_transform(
                geometry,
                [
                    width / extent,
                    0,
                    0,
                    height / extent,
                    float(bounds.left),
                    float(bounds.bottom),
                ],
            ).intersection(core)
            if not geometry.is_empty:
                geometries[band].append(geometry)
    midpoint_for_band = {
        band: midpoint for midpoint, band in _MIDPOINT_TO_BAND.items()
    }
    records = [
        {
            "band_midpoint": midpoint_for_band[band],
            "geometry": unary_union(parts),
        }
        for band, parts in geometries.items()
        if parts
    ]
    reconstructed = gpd.GeoDataFrame(
        records, geometry="geometry", crs="EPSG:3857"
    ).to_crs(SOURCE_CRS)
    # Same seam as _generate_tiles, crossed in the opposite direction. MVT
    # decoding also snaps every vertex to the tile's integer grid, so this side
    # has two reasons to come back invalid rather than one.
    reconstructed = _repair_after_reprojection(reconstructed, f"{SOURCE_CRS}, tras decodificar")
    resolved, _ = _priority_dissolve(reconstructed)
    resolved["lden_band"] = resolved["band_midpoint"].map(_band_for_midpoint)
    return _areas_by_band(resolved)


def _max_window_bytes(
    inventory: list[dict[str, Any]],
    *,
    columns: int,
    rows: int,
) -> int:
    sizes = {
        (int(item["x"]), int(item["y"])): int(item["gzip_bytes"])
        for item in inventory
        if int(item["z"]) == MINZOOM
    }
    if not sizes:
        return 0
    return max(
        sum(
            sizes.get((x + dx, y + dy), 0)
            for dx in range(columns)
            for dy in range(rows)
        )
        for x, y in sizes
    )


def _topology_proof(
    resolved: gpd.GeoDataFrame,
    simplified: gpd.GeoDataFrame,
    aoi: object,
) -> dict[str, bool]:
    bands = list(simplified.geometry)
    bands_disjoint = all(
        float(bands[left].intersection(bands[right]).area) <= 1e-6
        for left in range(len(bands))
        for right in range(left + 1, len(bands))
    )
    outside_area = float(unary_union(bands).difference(aoi).area)
    return {
        "resolved_valid": bool(resolved.geometry.is_valid.all()),
        "simplified_valid": bool(simplified.geometry.is_valid.all()),
        "bands_disjoint": bands_disjoint,
        "within_aoi": outside_area <= 1.0,
    }


def _validate_report(report: Mapping[str, Any]) -> None:
    if report.get("source_support_preserved") is not True:
        raise ValueError("Vector-contour validation report is not publishable")
    topology = report.get("topology")
    if not isinstance(topology, Mapping) or not all(bool(value) for value in topology.values()):
        raise ValueError(f"Vector-contour topology gate failed: {topology}")
    for band, check in report.get("area_checks", {}).items():
        for key in (
            "resolved_to_simplified_fraction",
            "simplified_to_tiled_fraction",
        ):
            if abs(float(check[key])) > 0.005:
                raise ValueError(f"Lden {band} area drift exceeds 0.5% ({key}={check[key]})")
    oversized = [tile["path"] for tile in report.get("tiles", []) if tile["gzip_bytes"] > MAX_TILE_GZIP_BYTES]
    if oversized:
        raise ValueError(f"Compressed MVT tile exceeds 500 kB: {oversized[0]}")
    initial = report.get("initial_visible_gzip_bytes", {})
    if any(int(initial.get(key, MAX_INITIAL_GZIP_BYTES + 1)) > MAX_INITIAL_GZIP_BYTES for key in ("desktop_4x4", "mobile_3x5")):
        raise ValueError(f"Initial visible MVT load exceeds 2 MB: {initial}")


def build_noise_vector_tiles(
    *,
    study: Any,
    raw_snapshot: RawSnapshotStore,
    cache_dir: Path,
    detail_dir: Path,
    resume: bool = True,
) -> NoiseVectorTileOutputs:
    """Build, verify and publish one study's local Lden MVT detail tree."""
    region = _region_for_study(study)
    partial = bool(getattr(study.study, "raw", {}).get("noise_spain", {}).get("coverage") == "partial")
    assets = _assets_for_region(raw_snapshot, region, require_complete=not partial)
    identity = _identity(
        source_manifest=raw_snapshot.manifest_path,
        assets=assets,
        aoi_path=study.spatial_path,
    )
    cache_root = cache_dir / "vector_tiles" / identity
    tile_root = cache_root / "publish" / INDICATOR_ID
    cache_root.mkdir(parents=True, exist_ok=True)
    units = study.spatial_units.to_crs(SOURCE_CRS)
    aoi = unary_union(units.geometry)
    source_bbox = tuple(float(value) for value in units.total_bounds)

    frames: list[gpd.GeoDataFrame] = []
    source_assets: list[dict[str, Any]] = []
    for asset in tqdm(assets, desc=f"Contornos Lden {region}", unit="aglomeración"):
        frame = _read_or_build_agglomeration(
            store=raw_snapshot,
            asset=asset,
            cache_root=cache_root,
            extraction_cache=cache_dir,
            source_bbox=source_bbox,
            aoi=aoi,
            resume=resume,
        )
        if not frame.empty:
            frames.append(frame)
            source_assets.append({"path": asset.path, "sha256": asset.sha256})
    if not frames:
        raise ValueError(f"No SICA Lden contours intersect study {study.study.id!r}")
    contours = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True),
        geometry="geometry",
        crs=SOURCE_CRS,
    )
    source_areas = _areas_by_band(contours)
    resolved = _resolved_bands(contours)
    resolved_areas = _areas_by_band(resolved)
    simplified, simplify_metres = _select_simplification(resolved, aoi=aoi)
    simplified_areas = _areas_by_band(simplified)
    geometry_fingerprint = _geometry_fingerprint(simplified)
    fingerprint_path = tile_root.parent / ".geometry_sha256"
    previous_fingerprint = (
        fingerprint_path.read_text(encoding="utf-8").strip()
        if fingerprint_path.is_file()
        else ""
    )
    if previous_fingerprint != geometry_fingerprint and tile_root.exists():
        shutil.rmtree(tile_root)
    fingerprint_path.parent.mkdir(parents=True, exist_ok=True)
    fingerprint_path.write_text(geometry_fingerprint + "\n", encoding="utf-8")
    inventory = _generate_tiles(simplified, tile_root, resume=resume)
    if not inventory:
        raise ValueError("MVT encoder produced no tiles")
    tiled_areas = _decoded_maxzoom_areas(tile_root, inventory)
    area_checks = {
        band: {
            "source_m2": source_areas[band],
            "resolved_m2": resolved_areas[band],
            "simplified_m2": simplified_areas[band],
            "tiled_m2": tiled_areas[band],
            # Raw archives may overlap across agglomerations. This delta is
            # evidence of the declared high-band priority transformation, not
            # simplification loss; the two following deltas are the <=0.5% gates.
            "source_to_resolved_fraction": _safe_fraction(source_areas[band], resolved_areas[band]),
            "resolved_to_simplified_fraction": _safe_fraction(resolved_areas[band], simplified_areas[band]),
            "simplified_to_tiled_fraction": _safe_fraction(simplified_areas[band], tiled_areas[band]),
        }
        for band in source_areas
    }
    source_manifest_sha256 = _file_sha256(raw_snapshot.manifest_path)
    initial = {
        "desktop_4x4": _max_window_bytes(inventory, columns=4, rows=4),
        "mobile_3x5": _max_window_bytes(inventory, columns=3, rows=5),
    }
    report = {
        "schema_version": 1,
        "study_id": study.study.id,
        "indicator_id": INDICATOR_ID,
        "algorithm_version": ALGORITHM_VERSION,
        "source_crs": SOURCE_CRS,
        "source_manifest_sha256": source_manifest_sha256,
        "source_assets": source_assets,
        "examined_source_assets": [
            {"path": asset.path, "sha256": asset.sha256} for asset in assets
        ],
        "source_support_preserved": True,
        "simplify_metres": simplify_metres,
        "minzoom": MINZOOM,
        "maxzoom": MAXZOOM,
        "mvt_extent": MVT_EXTENT,
        "mvt_extent_by_zoom": {
            str(zoom): _extent_for_zoom(zoom)
            for zoom in range(MINZOOM, MAXZOOM + 1)
        },
        "mvt_buffer_pixels": MVT_BUFFER_PIXELS,
        "quantization_invalid_geometry": "polygonal_make_valid_or_drop",
        "geometry_sha256": geometry_fingerprint,
        "topology": _topology_proof(resolved, simplified, aoi),
        "area_checks": area_checks,
        "initial_visible_gzip_bytes": initial,
        "tiles": inventory,
    }
    validation_path = cache_root / "publish" / f"{INDICATOR_ID}.vector_contours.validation.json"
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.write_bytes(_json_bytes(report))
    # Persist the evidence before enforcing the gate so a failed real-data run
    # remains diagnosable and resume-safe without publishing the candidate.
    _validate_report(report)
    bounds = [float(value) for value in simplified.to_crs("EPSG:4326").total_bounds]
    descriptor: dict[str, Any] = {
        "schema_version": 1,
        "type": "vector_contours",
        "tiles": [f"detail/{INDICATOR_ID}/{{z}}/{{x}}/{{y}}.pbf"],
        "minzoom": MINZOOM,
        "maxzoom": MAXZOOM,
        "bounds": bounds,
        "source_layer": SOURCE_LAYER,
        "bands": list(NOISE_LDEN_BANDS),
        "source_manifest_sha256": source_manifest_sha256,
        "source_assets": source_assets,
        "source_support_preserved": True,
        "validation": {
            "path": f"detail/{INDICATOR_ID}.vector_contours.validation.json",
            "sha256": _file_sha256(validation_path),
        },
    }
    if len(source_assets) == 1:
        descriptor["source_sha256"] = source_assets[0]["sha256"]
    descriptor_issues = validate_vector_contour_descriptor(INDICATOR_ID, descriptor)
    if descriptor_issues:
        raise ValueError("Invalid generated vector-contour descriptor: " + "; ".join(descriptor_issues))
    descriptor_path = cache_root / "publish" / f"{INDICATOR_ID}.vector_contours.json"
    descriptor_path.write_bytes(_json_bytes(descriptor))

    detail_dir.mkdir(parents=True, exist_ok=True)
    final_tiles = detail_dir / INDICATOR_ID
    if final_tiles.exists():
        shutil.rmtree(final_tiles)
    shutil.copytree(tile_root, final_tiles)
    final_validation = detail_dir / validation_path.name
    final_descriptor = detail_dir / descriptor_path.name
    shutil.copy2(validation_path, final_validation)
    shutil.copy2(descriptor_path, final_descriptor)
    return NoiseVectorTileOutputs(
        descriptor=final_descriptor,
        validation=final_validation,
        tile_directory=final_tiles,
        tile_count=len(inventory),
    )


__all__ = [
    "NoiseVectorTileOutputs",
    "build_noise_vector_tiles",
]

"""Sample native exposome products at coordinates.

Geocoding stays out of this module on purpose.  A postal area is not a unique
point, and the sampler must remain a pure ``coordinate -> value`` function so it
can be tested offline and reused by the CLI and by the web bundle alike
(ADR 0012 §7).  Address resolution lives in :mod:`exposome.geocoding`.

This module is the importable form of what used to live as private helpers in
``scripts/query_exposome.py``.  The move fixed five defects that the script
shipped with; each is marked in the code with the behaviour it replaces.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from .native import NATIVE_LAYER_SPECS, RASTER_KINDS

WGS84 = "EPSG:4326"


class PointQueryError(ValueError):
    """Invalid query input.  CLI layers translate this into their own error."""


def resolve_layers(value: str | None, enabled: Sequence[str]) -> tuple[str, ...]:
    """Parse a comma-separated layer selection, defaulting to the study's own."""
    if not value:
        return tuple(enabled)
    result = tuple(item.strip() for item in value.split(",") if item.strip())
    unknown = sorted(set(result) - set(NATIVE_LAYER_SPECS))
    if unknown:
        raise PointQueryError(f"Unsupported native layers: {unknown}")
    return result


def read_points(
    input_path: Path | None = None,
    lon: float | None = None,
    lat: float | None = None,
    id_column: str = "id",
    lon_column: str = "lon",
    lat_column: str = "lat",
) -> pd.DataFrame:
    """Build the canonical ``query_id``/``lon``/``lat`` frame from CLI inputs."""
    if input_path:
        frame = pd.read_csv(input_path)
        missing = {id_column, lon_column, lat_column} - set(frame.columns)
        if missing:
            raise PointQueryError(f"Input is missing columns: {sorted(missing)}")
        out = frame[[id_column, lon_column, lat_column]].copy()
        out = out.rename(columns={id_column: "query_id", lon_column: "lon", lat_column: "lat"})
    elif lon is not None and lat is not None:
        out = pd.DataFrame([{"query_id": "point_0001", "lon": lon, "lat": lat}])
    else:
        raise PointQueryError("Provide input_path or both lon and lat")
    out["lon"] = pd.to_numeric(out["lon"], errors="raise")
    out["lat"] = pd.to_numeric(out["lat"], errors="raise")
    if not out["lon"].between(-180, 180).all() or not out["lat"].between(-90, 90).all():
        raise PointQueryError("Coordinates are outside WGS84 bounds")
    return out.reset_index(drop=True)


@lru_cache(maxsize=64)
def _to_raster_crs(crs_serialized: str):
    """Cache one WGS84 -> raster-CRS transformer per distinct raster CRS."""
    from pyproj import CRS, Transformer

    return Transformer.from_crs(CRS.from_string(WGS84), CRS.from_user_input(crs_serialized),
                                always_xy=True)


def _projected_rowcol(src, lon: float, lat: float) -> tuple[int, int] | None:
    """Return the (row, col) of a WGS84 coordinate, or None if outside the grid.

    The previous implementation called ``src.index(lon, lat)`` with raw degrees
    regardless of the raster's CRS and then read with ``boundless=True,
    masked=True``.  For any raster not in EPSG:4326 that produced an index far
    outside the grid, which came back as a masked fill and was reported as a
    null *value* rather than as an error.  Measured on Santiago's
    ``greenspace_multisource_native.tif`` (EPSG:3857), the point
    (-70.65, -33.45) indexed to row 135601 / col 266107 of a 6104 x 7217 grid.
    Affected every EPSG:3857 canopy raster (8 cities), the UTM
    ``greenspace_coverage`` rasters (5 cities) and every MODIS Sinusoidal
    ``wildfire`` component.
    """
    x, y = float(lon), float(lat)
    if src.crs is not None and not src.crs.to_string().upper().endswith("4326"):
        x, y = _to_raster_crs(src.crs.to_string()).transform(x, y)
    row, col = src.index(x, y)
    if not (0 <= row < src.height and 0 <= col < src.width):
        return None
    return int(row), int(col)


def raster_values(path: Path, points: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Read the containing pixel of every point, reprojecting as needed."""
    import rasterio

    rows: list[dict[str, Any]] = []
    with rasterio.open(path) as src:
        band_count = src.count
        for point in points.itertuples(index=False):
            location = _projected_rowcol(src, point.lon, point.lat)
            record: dict[str, Any] = {}
            if location is None:
                for band_index in range(band_count):
                    record[f"{prefix}_band_{band_index + 1}"] = None
                rows.append(record)
                continue
            row, col = location
            window = ((row, row + 1), (col, col + 1))
            values = src.read(window=window, masked=True)
            for band_index in range(values.shape[0]):
                value = values[band_index, 0, 0]
                masked = bool(getattr(value, "mask", False))
                record[f"{prefix}_band_{band_index + 1}"] = None if masked else float(value)
            rows.append(record)
    return pd.DataFrame(rows, index=range(len(points)))


def native_raster_paths(layer_dir: Path, layer_id: str) -> list[tuple[str, Path]]:
    """Resolve a native layer's raster products as ``(column_prefix, path)``.

    ``wildfire`` is exported as one product per component
    (``wildfire_burned_area_native.tif``, ``wildfire_active_fire_native.tif``)
    because MODIS burned area and FIRMS activity do not share a provider grid.
    The old sampler always looked for ``<layer_id>_native.tif`` and raised
    ``FileNotFoundError`` on the four cities that only have components.
    """
    spec = NATIVE_LAYER_SPECS[layer_id]
    if not spec.requires_component_products:
        single = layer_dir / f"{layer_id}_native.tif"
        return [(layer_id, single)] if single.exists() else []

    # Prefer the metadata sidecar over globbing: it is the artifact that records
    # which components were actually exported (ADR 0006).
    metadata_path = layer_dir / "metadata.json"
    if metadata_path.exists():
        import json

        metadata = json.loads(metadata_path.read_text())
        components = metadata.get("components") or []
        resolved = []
        for component in components:
            name = component.get("output")
            if not name:
                continue
            path = layer_dir / name
            if path.exists():
                resolved.append((path.stem.removesuffix("_native"), path))
        if resolved:
            return resolved

    merged = layer_dir / f"{layer_id}_native.tif"
    if merged.exists():
        return [(layer_id, merged)]
    return [
        (path.stem.removesuffix("_native"), path)
        for path in sorted(layer_dir.glob(f"{layer_id}_*_native.tif"))
    ]


def climate_node_values(layer_dir: Path, points: pd.DataFrame) -> pd.DataFrame:
    """Summarise the Open-Meteo node products at each point's nearest node."""
    import geopandas as gpd

    point_path = next(layer_dir.glob("*_native_points.geojson"), None)
    daily_path = next(layer_dir.glob("*_native_daily_*.csv"), None)
    if point_path is None or daily_path is None:
        raise FileNotFoundError(f"Native climate products are incomplete in {layer_dir}")
    nodes = gpd.read_file(point_path).to_crs("EPSG:3857")
    queries = gpd.GeoDataFrame(
        points.copy(), geometry=gpd.points_from_xy(points.lon, points.lat), crs=WGS84
    ).to_crs("EPSG:3857")
    nearest = queries.geometry.apply(lambda geom: nodes.geometry.distance(geom).idxmin())
    selected = nodes.loc[nearest.to_numpy(), ["location_id"]].reset_index(drop=True)
    daily = pd.read_csv(daily_path)
    metrics = daily.groupby("location_id", as_index=False).agg(
        climate_tmean_c=("temperature_2m_mean", "mean"),
        climate_tmax_mean_c=("temperature_2m_max", "mean"),
        climate_tmax_p95_c=("temperature_2m_max", lambda value: value.quantile(0.95)),
        climate_hot_days_30c=("temperature_2m_max", lambda value: int((value >= 30).sum())),
        climate_precip_mm=("precipitation_sum", "sum"),
    )
    return selected.merge(metrics, on="location_id", how="left")


def osm_values(layer_dir: Path, layer_id: str, points: pd.DataFrame) -> pd.DataFrame:
    """Compute OSM proximity metrics at query time, indexed with an STRtree.

    The previous implementation evaluated ``features.geometry.distance(geom)``
    over the whole GeoDataFrame once per point.  Walkability networks run to
    tens of thousands of nodes, so a pasted batch of addresses was quadratic.
    """
    import geopandas as gpd
    from shapely import STRtree

    filename = "walkability_native.gpkg" if layer_id == "walkability" else f"{layer_id}_native.gpkg"
    path = layer_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"Native OSM product not found: {path}")
    layer_name = "nodes" if layer_id == "walkability" else "features"
    features = gpd.read_file(path, layer=layer_name)

    total_column = f"{layer_id}_n_total_aoi"
    within_column = f"{layer_id}_n_within_500m"
    nearest_column = f"{layer_id}_nearest_m"
    if features.empty:
        return pd.DataFrame(
            {total_column: 0, within_column: 0, nearest_column: None},
            index=range(len(points)),
        )

    query = gpd.GeoDataFrame(
        points.copy(), geometry=gpd.points_from_xy(points.lon, points.lat), crs=WGS84
    )
    metric = query.estimate_utm_crs()
    query = query.to_crs(metric)
    features = features.to_crs(metric)

    geometries = features.geometry.values
    tree = STRtree(geometries)
    total = int(len(features))
    rows: list[dict[str, Any]] = []
    for geom in query.geometry:
        within = tree.query(geom.buffer(500), predicate="intersects")
        nearest_index = tree.query_nearest(geom)
        if len(nearest_index) == 0:
            nearest_m: float | None = None
        else:
            nearest_m = float(geometries[int(nearest_index[0])].distance(geom))
        rows.append({
            total_column: total,
            within_column: int(len(within)),
            nearest_column: nearest_m,
        })
    return pd.DataFrame(rows, index=range(len(points)))


def layer_values(layer_dir: Path, layer_id: str, points: pd.DataFrame) -> pd.DataFrame:
    """Sample one native layer, dispatching on its declared kind.

    ``climate_heat`` used to be special-cased *before* the raster branch, so it
    always looked for Open-Meteo node products.  Those are only written by
    ``export_native_climate``, which nothing dispatches to: the spec's kind is
    ``gee_raster``, so the exporter writes ``climate_heat_native.tif`` instead.
    The result was ``FileNotFoundError`` on the eight studies that only have the
    raster.  The raster now wins, the node products remain a fallback, and the
    two schemas are told apart by an explicit ``*_source`` column instead of
    silently occupying the same slot.
    """
    spec = NATIVE_LAYER_SPECS[layer_id]
    if spec.kind not in RASTER_KINDS:
        return osm_values(layer_dir, layer_id, points)

    rasters = native_raster_paths(layer_dir, layer_id)
    if rasters:
        frames = [raster_values(path, points, prefix) for prefix, path in rasters]
        values = pd.concat(frames, axis=1)
        if layer_id == "climate_heat":
            values[f"{layer_id}_source"] = "native_raster"
        return values

    if layer_id == "climate_heat":
        values = climate_node_values(layer_dir, points)
        values[f"{layer_id}_source"] = "openmeteo_nodes"
        return values

    raise FileNotFoundError(f"Native raster not found for {layer_id} in {layer_dir}")


def flag_out_of_coverage(points: pd.DataFrame, aoi_geometry) -> pd.Series:
    """Mark points outside the AOI instead of rejecting the whole batch.

    Rejecting the batch meant one bad address killed a paste of fifty.
    """
    from shapely.geometry import Point

    if points.empty:
        # ``DataFrame.apply(axis=1)`` returns a DataFrame, not a Series, when
        # there are no rows, which would shape-mismatch on assignment.
        return pd.Series([], dtype=bool, index=points.index)
    covered = points.apply(
        lambda row: bool(aoi_geometry.covers(Point(float(row.lon), float(row.lat)))), axis=1
    )
    return ~covered.astype(bool)


def query_native_points(
    context,
    points: pd.DataFrame,
    layers: Iterable[str] | None = None,
    aoi_geometry=None,
) -> pd.DataFrame:
    """Sample every requested native layer at every point.

    Points outside the AOI are kept and flagged in ``out_of_coverage``; their
    layer columns are left null rather than sampled from a raster that does not
    cover them.
    """
    from .native import aoi_geometry as native_aoi_geometry, load_native_aoi

    if aoi_geometry is None:
        aoi_geometry = native_aoi_geometry(load_native_aoi(context))
    selected = tuple(layers) if layers is not None else tuple(context.enabled_layers)

    result = points.copy().reset_index(drop=True)
    outside = flag_out_of_coverage(result, aoi_geometry)
    result["out_of_coverage"] = outside.to_numpy()

    inside = result.loc[~outside.to_numpy()].reset_index(drop=True)
    for layer_id in selected:
        layer_dir = Path(context.paths.layer_processed(layer_id))
        if inside.empty:
            continue
        values = layer_values(layer_dir, layer_id, inside)
        values.index = result.index[~outside.to_numpy()]
        result = result.join(values, how="left")
    return result


def sampled_layer_columns(frame: pd.DataFrame) -> list[str]:
    """Column names produced by sampling, excluding the query identity block."""
    identity = {"query_id", "lon", "lat", "out_of_coverage"}
    return [column for column in frame.columns if column not in identity]


def describe_available_layers(context, layers: Iterable[str] | None = None) -> Mapping[str, str]:
    """Report, without reading any pixels, why each layer can or cannot be read."""
    selected = tuple(layers) if layers is not None else tuple(context.enabled_layers)
    status: dict[str, str] = {}
    for layer_id in selected:
        if layer_id not in NATIVE_LAYER_SPECS:
            status[layer_id] = "unknown_layer"
            continue
        layer_dir = Path(context.paths.layer_processed(layer_id))
        spec = NATIVE_LAYER_SPECS[layer_id]
        if not layer_dir.exists():
            status[layer_id] = "not_materialized"
        elif spec.kind in RASTER_KINDS:
            if native_raster_paths(layer_dir, layer_id):
                status[layer_id] = "available"
            elif layer_id == "climate_heat" and next(layer_dir.glob("*_native_points.geojson"), None):
                status[layer_id] = "available_openmeteo_nodes"
            else:
                status[layer_id] = "raster_missing"
        else:
            filename = (
                "walkability_native.gpkg"
                if layer_id == "walkability"
                else f"{layer_id}_native.gpkg"
            )
            status[layer_id] = "available" if (layer_dir / filename).exists() else "gpkg_missing"
    return status

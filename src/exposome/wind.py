"""Wind exposure layer via ERA5-Land 10-m wind components (GEE).

Computes commune-level annual and seasonal mean wind speed,
prevailing direction, and the fraction of "calm" days
(wind speed < threshold) from the ERA5-Land hourly reanalysis.
Wind is not a pollutant in itself but **modulates the effective
exposure** to PM2.5, NO2 and O3: communes with low wind + high
emissions have higher residence time and higher local dose, an
effect known as ventilation/dispersion capacity.

Indicators
----------
- ``wind_speed_mean``   : annual mean 10-m wind speed [m/s]
- ``wind_speed_max_p99``: 99th percentile wind speed [m/s]
- ``wind_calm_pct``     : fraction of hours with wind speed < 2 m/s
                          (low-dispersion episodes)
- ``wind_u_mean``, ``wind_v_mean`` : annual mean U/V components [m/s]
- ``wind_dir_prevailing`` : prevailing direction [degrees from North]

Seasonal indicators (winter = Jun-Aug, summer = Dec-Feb,
southern hemisphere meteorological seasons):
- ``wind_speed_<season>_mean`` : mean 10-m wind speed per season [m/s]
- ``wind_speed_<season>_max_p99`` : 99th percentile per season [m/s]
- ``wind_calm_pct_<season>`` : calm fraction per season
- ``wind_dir_<season>_mean`` : prevailing direction per season

The collection is configurable via ``wind.id`` in the city config
(default ``ECMWF/ERA5_LAND/HOURLY``; ~11.1 km native). The legacy
``ECMWF/ERA5/HOURLY`` (~30 km) is **not** recommended: at commune
level, 17/52 communes share a single ERA5 pixel; at zip-code level
this would jump to ~95% pixel sharing. ERA5-Land reduces this to
~3-5/52 communes and ~30-50% for zip codes.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box
from tqdm import tqdm

from . import boundaries, config, gee
from .cache import CacheIdentity, CacheRecord, CacheStore, spatial_fingerprint


def _native_pixel_samples(
    image: ee.Image,
    regions_fc: ee.FeatureCollection,
    *,
    scale: float,
    value_columns: list[str],
) -> pd.DataFrame:
    """Read native grid cells that can intersect the requested AOI.

    Earth Engine only returns pixels whose centres are inside ``region``.  A
    coastal or very small administrative unit can intersect a valid ERA5-Land
    cell while containing none of its centres.  Querying one native cell beyond
    the AOI bounds supplies the edge ring; aggregation below still uses only
    the true polygon intersection and never invents a finer grid.
    """
    samples = image.select(value_columns).sample(
        region=regions_fc.geometry().bounds().buffer(scale),
        scale=scale,
        projection=image.projection(),
        geometries=True,
        tileScale=4,
    )
    rows: list[dict[str, Any]] = []
    for feature in samples.getInfo().get("features", []):
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if len(coordinates) < 2:
            continue
        props = feature.get("properties", {})
        row = {"lon": float(coordinates[0]), "lat": float(coordinates[1])}
        row.update({column: props.get(column) for column in value_columns})
        rows.append(row)
    frame = pd.DataFrame(rows)
    if frame.empty or frame[value_columns].isna().any().any():
        raise ValueError("ERA5-Land returned no complete native wind pixels")
    return frame


def _aggregate_native_pixels(
    samples: pd.DataFrame,
    units: gpd.GeoDataFrame,
    cfg: dict[str, Any],
    *,
    value_columns: list[str],
) -> pd.DataFrame:
    """Area-weight native ERA5-Land pixel values to study units.

    A nearest observed pixel may be used only for a unit with no intersecting
    land pixel and only within one native cell.  This is the same bounded
    coastal fallback used by the ERA5-Land heat pipeline.
    """
    metric_crs = cfg["crs"]["metric"]
    scale = float(cfg["wind"]["scale_meters"])
    points = gpd.GeoDataFrame(
        samples.copy(), geometry=gpd.points_from_xy(samples["lon"], samples["lat"]), crs="EPSG:4326"
    ).to_crs(metric_crs)
    points["pixel_id"] = points.geometry.map(lambda point: f"{point.x:.3f}:{point.y:.3f}")
    half = scale / 2.0
    pixels = gpd.GeoDataFrame(
        points[["pixel_id", *value_columns]].copy(),
        geometry=[box(point.x - half, point.y - half, point.x + half, point.y + half) for point in points.geometry],
        crs=metric_crs,
    )
    unit_columns = [column for column in ("name", "area_km2") if column in units.columns]
    if "name" not in unit_columns:
        raise ValueError("Wind aggregation requires a name column on spatial units")
    unit_metric = units[unit_columns + ["geometry"]].to_crs(metric_crs).copy()
    intersections = gpd.overlay(
        pixels[["pixel_id", *value_columns, "geometry"]],
        unit_metric[["name", "geometry"]],
        how="intersection",
        keep_geom_type=True,
    )
    rows: list[dict[str, Any]] = []
    # GeoPandas may return a column-less GeoDataFrame for a completely empty
    # overlay.  That is expected for small coastal units with no sampled pixel
    # footprint: preserve the unit rows so the bounded nearest-pixel fallback
    # below can make the explicit, auditable decision.
    if not intersections.empty and "name" in intersections.columns:
        for name, group in intersections.groupby("name", dropna=False):
            weights = group.geometry.area
            rows.append({
                "name": name,
                **{column: float(np.average(group[column], weights=weights)) for column in value_columns},
                "n_native_wind_pixels": int(group["pixel_id"].nunique()),
                "used_nearest_wind_fallback": False,
                "nearest_wind_m": 0.0,
            })
    aggregate_columns = [
        "name", *value_columns, "n_native_wind_pixels",
        "used_nearest_wind_fallback", "nearest_wind_m",
    ]
    aggregates = pd.DataFrame(rows, columns=aggregate_columns)
    result = unit_metric[["name", "geometry"]].merge(aggregates, on="name", how="left")
    missing = result[value_columns].isna().any(axis=1)
    for index in result.index[missing]:
        distances = points.geometry.distance(result.at[index, "geometry"])
        nearest_index = distances.idxmin()
        nearest_distance = float(distances.loc[nearest_index])
        if nearest_distance > scale:
            raise ValueError(
                f"Nearest ERA5-Land wind pixel for {result.at[index, 'name']} is "
                f"{nearest_distance:.0f} m away, beyond one native grid spacing ({scale:.0f} m)"
            )
        for column in value_columns:
            result.at[index, column] = points.at[nearest_index, column]
        result.at[index, "n_native_wind_pixels"] = 0
        result.at[index, "used_nearest_wind_fallback"] = True
        result.at[index, "nearest_wind_m"] = nearest_distance
    return result.drop(columns="geometry")


def wind_cache_namespace(collection_id: str) -> str:
    """Return a stable cache namespace tied to the configured collection."""
    token = re.sub(r"[^a-z0-9]+", "_", collection_id.lower()).strip("_")
    if not token:
        raise ValueError("wind collection id cannot be empty")
    return token


def fetch_wind_speed(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    units: gpd.GeoDataFrame | None = None,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Fetch annual mean 10-m wind speed (m/s) and components (u, v) from ERA5."""
    wind_cfg = cfg["wind"]
    start = start or wind_cfg["start_date"]
    end = end or wind_cfg["end_date"]
    scale = wind_cfg["scale_meters"]

    col = (
        ee.ImageCollection(wind_cfg["id"])
        .filterDate(start, end)
        .select(["u_component_of_wind_10m", "v_component_of_wind_10m"])
    )
    mean_img = col.mean()

    if units is not None:
        samples = _native_pixel_samples(
            mean_img, regions_fc, scale=scale,
            value_columns=["u_component_of_wind_10m", "v_component_of_wind_10m"],
        ).rename(columns={
            "u_component_of_wind_10m": "wind_u_mean",
            "v_component_of_wind_10m": "wind_v_mean",
        })
        aggregated = _aggregate_native_pixels(
            samples, units, cfg, value_columns=["wind_u_mean", "wind_v_mean"],
        )
        return aggregated[["name", "wind_u_mean", "wind_v_mean"]]

    u_stats = gee.image_to_stats(
        mean_img.select("u_component_of_wind_10m"),
        regions_fc, band="u_component_of_wind_10m", scale=scale, reducer="mean",
    )
    v_stats = gee.image_to_stats(
        mean_img.select("v_component_of_wind_10m"),
        regions_fc, band="v_component_of_wind_10m", scale=scale, reducer="mean",
    )

    df_u = pd.DataFrame(gee.fc_to_dicts(u_stats))
    df_v = pd.DataFrame(gee.fc_to_dicts(v_stats))
    df_u = df_u.rename(columns={"mean": "wind_u_mean"})
    df_v = df_v.rename(columns={"mean": "wind_v_mean"})
    for df_ in (df_u, df_v):
        for c in ("geometry", "area_km2", "spatial_id", "spatial_name"):
            if c in df_.columns:
                df_.drop(columns=c, inplace=True)
    return df_u.merge(df_v, on="name", how="outer")


def fetch_wind_calm_pct(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    units: gpd.GeoDataFrame | None = None,
    start: str | None = None,
    end: str | None = None,
    threshold_m_s: float = 2.0,
) -> pd.DataFrame:
    """Fetch fraction of hours with wind speed < threshold (calm, low dispersion).

    Implementation: hourly wind speed is computed as sqrt(u^2 + v^2) per
    hour over the full year (~8760 hours), then reduced per commune as
    a mean over time. The calm fraction is the share of hours with
    speed < threshold (default 2 m/s). Native 0.25 deg, downscaled to
    30 km for zonal stats.
    """
    wind_cfg = cfg["wind"]
    start = start or wind_cfg["start_date"]
    end = end or wind_cfg["end_date"]
    scale = wind_cfg["scale_meters"]

    col = (
        ee.ImageCollection(wind_cfg["id"])
        .filterDate(start, end)
        .select(["u_component_of_wind_10m", "v_component_of_wind_10m"])
    )

    def add_speed(img: ee.Image) -> ee.Image:
        u = img.select("u_component_of_wind_10m")
        v = img.select("v_component_of_wind_10m")
        speed = u.pow(2).add(v.pow(2)).sqrt().rename("wind_speed")
        return img.addBands(speed)

    col = col.map(add_speed)

    # Count hours where speed < threshold.
    def add_calm(img: ee.Image) -> ee.Image:
        speed = img.select("wind_speed")
        calm = speed.lt(threshold_m_s).rename("calm")
        return img.addBands(calm)

    col = col.map(add_calm)

    # Mean over time per pixel = fraction of calm hours.
    calm_mean = col.select("calm").mean()
    speed_max = col.select("wind_speed").reduce(ee.Reducer.percentile([99]))

    speed_mean = col.select("wind_speed").mean()
    if units is not None:
        combined = calm_mean.rename("wind_calm_pct").addBands(
            speed_max.rename("wind_speed_max_p99")
        ).addBands(speed_mean.rename("wind_speed_mean"))
        samples = _native_pixel_samples(
            combined, regions_fc, scale=scale,
            value_columns=["wind_calm_pct", "wind_speed_max_p99", "wind_speed_mean"],
        )
        aggregated = _aggregate_native_pixels(
            samples, units, cfg,
            value_columns=["wind_speed_mean", "wind_speed_max_p99", "wind_calm_pct"],
        )
        return aggregated[["name", "wind_speed_mean", "wind_speed_max_p99", "wind_calm_pct"]]

    calm_stats = gee.image_to_stats(
        calm_mean, regions_fc, band="calm", scale=scale, reducer="mean",
    )
    speed_p99_stats = gee.image_to_stats(
        speed_max, regions_fc, band="wind_speed_p99", scale=scale, reducer="mean",
    )
    speed_mean_stats = gee.image_to_stats(
        speed_mean,
        regions_fc, band="wind_speed", scale=scale, reducer="mean",
    )

    df_calm = pd.DataFrame(gee.fc_to_dicts(calm_stats))
    df_p99 = pd.DataFrame(gee.fc_to_dicts(speed_p99_stats))
    df_mean = pd.DataFrame(gee.fc_to_dicts(speed_mean_stats))
    df_calm = df_calm.rename(columns={"mean": "wind_calm_pct"})
    df_p99 = df_p99.rename(columns={"mean": "wind_speed_max_p99"})
    df_mean = df_mean.rename(columns={"mean": "wind_speed_mean"})
    for df_ in (df_calm, df_p99, df_mean):
        for c in ("geometry", "area_km2", "spatial_id", "spatial_name"):
            if c in df_.columns:
                df_.drop(columns=c, inplace=True)
    return df_mean.merge(df_p99, on="name", how="outer").merge(
        df_calm, on="name", how="outer"
    )


def _add_prevailing_direction(df: pd.DataFrame) -> pd.DataFrame:
    """Compute prevailing wind direction from U, V components [degrees from N]."""
    u = df["wind_u_mean"].astype(float)
    v = df["wind_v_mean"].astype(float)
    # Meteorological convention: direction FROM which wind blows.
    # atan2(-u, -v) gives the direction the wind is coming from, in
    # degrees clockwise from North.
    deg = (np.degrees(np.arctan2(-u, -v)) + 360.0) % 360.0
    df["wind_dir_prevailing"] = deg.round(1)
    return df


def _season_date_range(
    year: int, season: str,
) -> tuple[str, str]:
    """Return (start_date, end_date) ISO strings for a southern-hemisphere season.

    Winter:  Jun-Aug  of `year` (single calendar year).
    Summer:  Dec of `year` + Jan-Feb of `year+1` (crosses calendar year).
    """
    if season == "winter":
        return f"{year}-06-01", f"{year}-09-01"
    if season == "summer":
        return f"{year}-12-01", f"{year + 1}-03-01"
    raise ValueError(f"Unknown season: {season!r}; expected 'winter' or 'summer'")


def fetch_wind_seasonal(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    season: str,
    units: gpd.GeoDataFrame | None = None,
    start: str | None = None,
    end: str | None = None,
    threshold_m_s: float = 2.0,
) -> pd.DataFrame:
    """Fetch seasonal wind components + speed + calm fraction from ERA5.

    Returns a DataFrame with columns:
        name, wind_u_mean_<season>, wind_v_mean_<season>,
        wind_speed_mean_<season>, wind_speed_max_p99_<season>,
        wind_calm_pct_<season>

    Implementation: filters ERA5 hourly to the season's date range,
    then applies the same u/v + speed + calm pipeline as the annual
    version (see fetch_wind_speed, fetch_wind_calm_pct).
    """
    if season not in ("winter", "summer"):
        raise ValueError(f"season must be 'winter' or 'summer', got {season!r}")
    wind_cfg = cfg["wind"]
    year = wind_cfg["year"]
    if start is None or end is None:
        start, end = _season_date_range(year, season)
    scale = wind_cfg["scale_meters"]

    col = (
        ee.ImageCollection(wind_cfg["id"])
        .filterDate(start, end)
        .select(["u_component_of_wind_10m", "v_component_of_wind_10m"])
    )

    def add_speed(img: ee.Image) -> ee.Image:
        u = img.select("u_component_of_wind_10m")
        v = img.select("v_component_of_wind_10m")
        speed = u.pow(2).add(v.pow(2)).sqrt().rename("wind_speed")
        return img.addBands(speed)

    def add_calm(img: ee.Image) -> ee.Image:
        speed = img.select("wind_speed")
        calm = speed.lt(threshold_m_s).rename("calm")
        return img.addBands(calm)

    col = col.map(add_speed).map(add_calm)

    mean_u = col.select("u_component_of_wind_10m").mean()
    mean_v = col.select("v_component_of_wind_10m").mean()
    speed_mean = col.select("wind_speed").mean()
    speed_p99 = col.select("wind_speed").reduce(ee.Reducer.percentile([99]))
    calm_mean = col.select("calm").mean()
    if units is not None:
        columns = [
            f"wind_u_mean_{season}", f"wind_v_mean_{season}",
            f"wind_speed_mean_{season}", f"wind_speed_max_p99_{season}",
            f"wind_calm_pct_{season}",
        ]
        combined = mean_u.rename(columns[0]).addBands(mean_v.rename(columns[1])).addBands(
            speed_mean.rename(columns[2])
        ).addBands(speed_p99.rename(columns[3])).addBands(calm_mean.rename(columns[4]))
        samples = _native_pixel_samples(combined, regions_fc, scale=scale, value_columns=columns)
        aggregated = _aggregate_native_pixels(samples, units, cfg, value_columns=columns)
        return aggregated[["name", *columns]]

    u_stats = gee.image_to_stats(
        mean_u,
        regions_fc, band="u_component_of_wind_10m", scale=scale, reducer="mean",
    )
    v_stats = gee.image_to_stats(
        mean_v,
        regions_fc, band="v_component_of_wind_10m", scale=scale, reducer="mean",
    )
    speed_mean_stats = gee.image_to_stats(
        speed_mean,
        regions_fc, band="wind_speed", scale=scale, reducer="mean",
    )
    speed_p99_stats = gee.image_to_stats(
        speed_p99,
        regions_fc, band="wind_speed_p99", scale=scale, reducer="mean",
    )
    calm_stats = gee.image_to_stats(
        calm_mean,
        regions_fc, band="calm", scale=scale, reducer="mean",
    )

    def _to_df(stats: Any, name: str) -> pd.DataFrame:
        d = pd.DataFrame(gee.fc_to_dicts(stats))
        if "mean" in d.columns:
            d = d.rename(columns={"mean": name})
        for c in ("geometry", "area_km2", "spatial_id", "spatial_name"):
            if c in d.columns:
                d.drop(columns=c, inplace=True)
        return d

    df_u = _to_df(u_stats, f"wind_u_mean_{season}")
    df_v = _to_df(v_stats, f"wind_v_mean_{season}")
    df_smean = _to_df(speed_mean_stats, f"wind_speed_mean_{season}")
    df_sp99 = _to_df(speed_p99_stats, f"wind_speed_max_p99_{season}")
    df_calm = _to_df(calm_stats, f"wind_calm_pct_{season}")

    out = df_u
    for other in (df_v, df_smean, df_sp99, df_calm):
        out = out.merge(other, on="name", how="outer")
    return out


def _add_seasonal_direction(df: pd.DataFrame, season: str) -> pd.DataFrame:
    """Compute seasonal prevailing direction from seasonal U, V [degrees from N]."""
    u = df[f"wind_u_mean_{season}"].astype(float)
    v = df[f"wind_v_mean_{season}"].astype(float)
    deg = (np.degrees(np.arctan2(-u, -v)) + 360.0) % 360.0
    df[f"wind_dir_{season}_mean"] = deg.round(1)
    return df


def build_wind_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    year: int | None = None,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Run the wind exposure pipeline and write CSV/GeoJSON/metadata.

    Produces annual + seasonal (winter, summer) wind indicators.
    Seasonal definitions (southern hemisphere meteorological seasons)
    can be overridden via ``wind.winter_months`` and
    ``wind.summer_months`` in the city config.
    """
    cfg = config.load_config(city)

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    year = int(year if year is not None else cfg["wind"]["year"])
    cfg["wind"]["year"] = year
    cfg["wind"]["start_date"] = f"{year}-01-01"
    cfg["wind"]["end_date"] = f"{year + 1}-01-01"
    threshold = float(cfg["wind"].get("threshold_calm_m_s", 2.0))
    cache_namespace = wind_cache_namespace(str(cfg["wind"]["id"]))

    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)
    spatial_key = spatial_fingerprint(
        gdf_comm,
        id_column="spatial_id" if "spatial_id" in gdf_comm.columns else "name",
    )
    wind_cfg = cfg["wind"]
    common = {
        "collection": wind_cfg["id"],
        "bands": ["u_component_of_wind_10m", "v_component_of_wind_10m"],
        "scale_meters": wind_cfg["scale_meters"],
        "reducer": "native_pixel_intersection_area_weighted",
        "query_buffer_native_cells": 1,
    }
    identities = {
        "uv": CacheIdentity(
            "wind",
            "annual_uv",
            {**common, "start": wind_cfg["start_date"], "end_exclusive": wind_cfg["end_date"]},
            spatial_key,
            "3",
        ),
        "speed": CacheIdentity(
            "wind",
            "annual_speed",
            {
                **common,
                "start": wind_cfg["start_date"],
                "end_exclusive": wind_cfg["end_date"],
                "speed": "sqrt(u^2 + v^2)",
                "percentile": 99,
                "threshold_calm_m_s": threshold,
            },
            spatial_key,
            "3",
        ),
    }
    for season in ("winter", "summer"):
        season_start, season_end = _season_date_range(year, season)
        identities[season] = CacheIdentity(
            "wind",
            season,
            {
                **common,
                "start": season_start,
                "end_exclusive": season_end,
                "configured_months": wind_cfg.get(f"{season}_months"),
                "speed": "sqrt(u^2 + v^2)",
                "percentile": 99,
                "threshold_calm_m_s": threshold,
            },
            spatial_key,
            "3",
        )
    stores = {name: CacheStore(cache_dir, identity) for name, identity in identities.items()}
    records: dict[str, CacheRecord] = {
        "uv": stores["uv"].load_csv(
            str(year), required_columns=["name", "wind_u_mean", "wind_v_mean"]
        ),
        "speed": stores["speed"].load_csv(
            str(year),
            required_columns=[
                "name",
                "wind_speed_mean",
                "wind_speed_max_p99",
                "wind_calm_pct",
            ],
        ),
    }
    for season in ("winter", "summer"):
        records[season] = stores[season].load_csv(
            str(year),
            required_columns=[
                "name",
                f"wind_u_mean_{season}",
                f"wind_v_mean_{season}",
                f"wind_speed_mean_{season}",
                f"wind_speed_max_p99_{season}",
                f"wind_calm_pct_{season}",
            ],
        )
    regions_fc: ee.FeatureCollection | None = None
    if not all(record.hit for record in records.values()):
        gee.init_gee()
        regions_fc = gee.gdf_to_feature_collection(gdf_comm)

    progress = tqdm(total=4, desc=f"wind [{city}]", unit="step")

    # 1. U, V components (annual mean)
    if records["uv"].hit:
        tqdm.write(f"  [wind_uv] {records['uv'].reason} …")
        assert records["uv"].frame is not None
        df_uv = records["uv"].frame
    else:
        tqdm.write(f"  [wind_uv] cache miss ({records['uv'].reason}); fetching from GEE …")
        assert regions_fc is not None
        df_uv = fetch_wind_speed(cfg, regions_fc, units=gdf_comm)
        records["uv"] = stores["uv"].write_csv_atomic(str(year), df_uv)
    progress.update(1)

    # 2. Wind speed stats + calm fraction
    if records["speed"].hit:
        tqdm.write(f"  [wind_speed] {records['speed'].reason} …")
        assert records["speed"].frame is not None
        df_speed = records["speed"].frame
    else:
        tqdm.write(
            f"  [wind_speed] cache miss ({records['speed'].reason}); fetching from GEE …"
        )
        assert regions_fc is not None
        df_speed = fetch_wind_calm_pct(cfg, regions_fc, units=gdf_comm, threshold_m_s=threshold)
        records["speed"] = stores["speed"].write_csv_atomic(str(year), df_speed)
    progress.update(1)

    # 3. Seasonal stats (winter + summer) — one cache per season.
    seasonal_dfs: dict[str, pd.DataFrame] = {}
    for season in ("winter", "summer"):
        if records[season].hit:
            tqdm.write(f"  [wind_{season}] {records[season].reason} …")
            assert records[season].frame is not None
            seasonal_dfs[season] = records[season].frame
        else:
            tqdm.write(
                f"  [wind_{season}] cache miss ({records[season].reason}); "
                "fetching from GEE …"
            )
            assert regions_fc is not None
            seasonal_dfs[season] = fetch_wind_seasonal(
                cfg, regions_fc, season=season, units=gdf_comm, threshold_m_s=threshold,
            )
            records[season] = stores[season].write_csv_atomic(
                str(year), seasonal_dfs[season]
            )
        progress.update(1)
    progress.close()

    # 4. Merge all pieces
    df = gdf_comm[["name", "area_km2"]].copy()
    df = df.merge(df_uv, on="name", how="left")
    df = df.merge(df_speed, on="name", how="left")
    for season, sdf in seasonal_dfs.items():
        df = df.merge(sdf, on="name", how="left")

    # 5. Validate native-pixel coverage.  A regional mean is not a valid
    # substitute for an unobserved coastal/isolated unit; the only permitted
    # fallback occurred above and is bounded to one native cell.
    annual_cols = (
        "wind_u_mean", "wind_v_mean", "wind_speed_mean",
        "wind_speed_max_p99", "wind_calm_pct",
    )
    seasonal_cols = [
        c for c in df.columns
        if c.endswith(("_winter", "_summer"))
        and any(c.startswith(p) for p in (
            "wind_u_mean_", "wind_v_mean_", "wind_speed_mean_",
            "wind_speed_max_p99_", "wind_calm_pct_",
        ))
    ]
    missing_values = [
        column for column in annual_cols + tuple(seasonal_cols)
        if column not in df.columns or df[column].isna().any()
    ]
    if missing_values:
        raise ValueError("ERA5-Land wind coverage missing required values: " + ", ".join(missing_values))

    # 6. Prevailing directions (annual + seasonal).
    df = _add_prevailing_direction(df)
    for season in ("winter", "summer"):
        df = _add_seasonal_direction(df, season)

    # 7. Formatting
    for col in annual_cols + tuple(seasonal_cols):
        if col in df.columns:
            df[col] = df[col].round(3)

    # 8. Validate
    n_expected = cfg["expected_communes"]
    if len(df) != n_expected:
        raise ValueError(f"Expected {n_expected} rows, got {len(df)}")
    if df["name"].duplicated().any():
        raise ValueError("Duplicate commune names")
    if df.isna().any().any():
        missing = df.columns[df.isna().any()].tolist()
        raise ValueError(f"Missing values in: {missing}")

    # 9. Geo version
    gdf = gdf_comm[["name", "geometry"]].merge(df, on="name", how="right")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    # 10. Write outputs
    base_name = f"{city}_wind"
    df.to_csv(out_dir / f"{base_name}.csv", index=False)
    gdf.to_file(out_dir / f"{base_name}.geojson", driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "year": year,
        "method": "ERA5-Land hourly 10-m wind (u, v) → speed, calm pct, prevailing dir (annual + winter + summer)",
        "source": f"{cfg['wind']['id']} via GEE",
        "collection_id": cfg["wind"]["id"],
        "cache_namespace": cache_namespace,
        "cache_fingerprints": {
            name: identity.digest for name, identity in identities.items()
        },
        "resolution_m": cfg["wind"]["scale_meters"],
        "scale_meters": cfg["wind"]["scale_meters"],
        "aggregation_support": "native ERA5-Land pixels intersected with study units; bounded nearest-pixel fallback only",
        "threshold_calm_m_s": threshold,
        "season_definitions": {
            "winter": "Jun-Aug (southern hemisphere)",
            "summer": "Dec-Feb (southern hemisphere)",
        },
        "interpretation": (
            "Wind is not a pollutant. Low wind_calm_pct + high NO2/PM2.5 "
            "implies poor ventilation and higher effective dose. Wind "
            "modulates all other air-quality exposures; it is a "
            "modifier-of-effect rather than a direct exposure. "
            "Seasonal columns use the configured Jun-Aug and Dec-Feb windows; "
            "their interpretation depends on the study location."
        ),
        "limitations": [
            f"ERA5-Land native ~{cfg['wind']['scale_meters'] / 1000:.1f} km; administrative-unit interpretation is limited.",
            "Local topography and urban roughness are not fully resolved.",
            "Prevailing direction is vector mean; daily reversals are smoothed.",
            "Single year (2024); multi-year climatology would be more robust.",
        ],
        "columns": df.columns.tolist(),
        "n_rows": len(df),
    }
    meta_path = out_dir / f"{base_name}_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(f"Wrote {base_name}.csv / .geojson ({len(df)} rows x {df.shape[1]} cols)")
    return df, gdf


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    build_wind_layer()

"""Build the climate_heat exposome layer from cached daily climate data.

The canonical source is ERA5-Land.  Daily values are sampled from its native
pixels over the dissolved study AOI, metrics are calculated per pixel, and
administrative summaries are produced only afterwards by area intersection.
Units without an intersecting observed land pixel use the nearest observed
ERA5-Land pixel centre only when it lies within one native grid spacing.  The
fallback is explicit in the output; representative-commune points are never
fabricated.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from shapely.geometry import Point, box

from .. import boundaries
from .. import config as _config  # used inside build_climate_heat_layer
from .fetch_era5land import ensure_era5land_daily


# ---------------------------------------------------------------------------
# Commune loading
# ---------------------------------------------------------------------------


def load_communes(cfg: dict[str, Any], cache_dir: Path) -> gpd.GeoDataFrame:
    """Return configured spatial units, reusing the boundary cache.

    The Study runner seeds the canonical polygons at
    ``cache_dir/<study_id>_communes.geojson`` via
    :func:`exposome.layers.prepare_boundary_cache`.  Read that study-scoped
    seed rather than the legacy ``<city>_communes.geojson`` name: multi-city
    studies key their cache by study id (``buenos_aires_amba`` and
    ``buenos_aires_comunas`` share a city but not polygons), and studies whose
    ``region_query`` is a per-unit list (e.g. ``lima_distritos``: Lima+Callao)
    cannot fall through to :func:`boundaries.get_communes`' legacy OSM download,
    which builds ``{cfg["region_query"], ...}`` and raises ``unhashable type:
    'list'``.  ``cfg["study_id"]`` is always present for Study-driven runs; a
    direct legacy-city caller keeps the old ``cfg["name"]`` filename.
    """
    study_key = cfg.get("study_id", cfg["name"])
    cache_path = cache_dir / f"{study_key}_communes.geojson"
    gdf = boundaries.get_communes(cfg, cache_path=cache_path)
    return gdf.to_crs(cfg["crs"]["metric"]).copy()


# ---------------------------------------------------------------------------
# Climate point grid + representative commune points
# ---------------------------------------------------------------------------


def build_climate_points(
    communes: gpd.GeoDataFrame,
    grid_step_deg: float,
) -> gpd.GeoDataFrame:
    """Build the set of climate sampling points.

    Two kinds of points, all in WGS84:

    - ``grid``: regular lat/lon grid (~grid_step_deg) clipped to the
      union of all commune polygons.
    - ``commune_point``: a representative point guaranteed to fall inside
      each commune polygon (used as a fallback when the regular grid
      does not intersect a small/urban commune).

    Returns a GeoDataFrame with columns
    ``location_id, source, commune_name, lat, lon, geometry``.
    """
    communes_wgs = communes.to_crs("EPSG:4326")
    region_union = communes_wgs.geometry.union_all().buffer(0)
    minx, miny, maxx, maxy = communes_wgs.total_bounds

    lons = np.arange(
        np.floor(minx / grid_step_deg) * grid_step_deg,
        maxx + grid_step_deg,
        grid_step_deg,
    )
    lats = np.arange(
        np.floor(miny / grid_step_deg) * grid_step_deg,
        maxy + grid_step_deg,
        grid_step_deg,
    )

    regular: list[dict[str, Any]] = []
    for lat in lats:
        for lon in lons:
            pt = Point(float(lon), float(lat))
            if pt.within(region_union):
                regular.append(
                    {
                        "source": "grid",
                        "commune_name": None,
                        "lat": round(float(lat), 4),
                        "lon": round(float(lon), 4),
                        "geometry": pt,
                    }
                )

    cent = communes_wgs.copy()
    cent["geometry"] = cent.geometry.representative_point()
    centroids = [
        {
            "source": "commune_point",
            "commune_name": row["name"],
            "lat": round(row.geometry.y, 4),
            "lon": round(row.geometry.x, 4),
            "geometry": row.geometry,
        }
        for _, row in cent.iterrows()
    ]

    pts = gpd.GeoDataFrame(regular + centroids, crs="EPSG:4326")
    pts = pts.drop_duplicates(subset=["source", "commune_name", "lat", "lon"]).reset_index(drop=True)
    pts["location_id"] = np.arange(len(pts), dtype=int)
    return pts[["location_id", "source", "commune_name", "lat", "lon", "geometry"]]


# ---------------------------------------------------------------------------
# Daily value loaders (cache-first, no network)
# ---------------------------------------------------------------------------


def _load_openmeteo_daily(
    points: gpd.GeoDataFrame,
    cache_path: Path,
) -> pd.DataFrame:
    """Load Open-Meteo daily data from the chunked cache file."""
    if not cache_path.exists():
        raise FileNotFoundError(
            f"Open-Meteo cache not found at {cache_path}. "
            "Run scripts/run_climate_openmeteo.py to populate it first."
        )
    df = pd.read_csv(cache_path)
    df["date"] = pd.to_datetime(df["date"])
    needed = {"location_id", "lat", "lon", "date"}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"Open-Meteo cache is missing required columns: {missing}")
    return df


def _load_era5land_daily(cache_path: Path) -> pd.DataFrame:
    """Load native ERA5-Land pixel-day values; never expand commune values.

    The cache is created by :mod:`fetch_era5land` and has one value per
    ``pixel_id`` and date.  The old ``name,date`` cache is intentionally
    rejected because it was already reduced by commune and cannot recover the
    underlying spatial support.
    """
    if not cache_path.exists():
        raise FileNotFoundError(
            f"ERA5-Land cache not found at {cache_path}. "
            "Run scripts/run_climate_fetch.py to populate it first."
        )
    df = pd.read_csv(cache_path)
    required_location = {"pixel_id", "lon", "lat", "date"}
    missing_location = required_location - set(df.columns)
    if missing_location:
        raise ValueError(
            "ERA5 cache must contain native pixel_id/lon/lat/date values; "
            "commune-reduced caches are not valid for climate_heat (missing "
            + ", ".join(sorted(missing_location)) + ")"
        )
    rename = {
        "temperature_2m_max": "temperature_2m_max",
        "temperature_2m_min": "temperature_2m_min",
        "temperature_2m_mean": "temperature_2m_mean",
        "dewpoint_temperature_2m": "dewpoint_temperature_2m",
        "total_precipitation_sum": "precipitation_sum",
    }
    df = df.rename(columns=rename)
    if "dewpoint_temperature_2m" not in df.columns:
        raise ValueError(
            "ERA5 cache must contain 'dewpoint_temperature_2m' to derive apparent temperature."
        )
    df["date"] = pd.to_datetime(df["date"])
    df["apparent_temperature_max"] = _steadman_apparent_max(
        df["temperature_2m_max"].to_numpy(),
        df["dewpoint_temperature_2m"].to_numpy(),
    )
    keep = [
        "pixel_id",
        "lon",
        "lat",
        "date",
        "temperature_2m_mean",
        "temperature_2m_max",
        "temperature_2m_min",
        "apparent_temperature_max",
        "precipitation_sum",
    ]
    df = df[keep].copy()
    df["source"] = "era5land_pixel"
    return df


def _steadman_apparent_max(tmax_c: np.ndarray, dewpoint_c: np.ndarray) -> np.ndarray:
    """Steadman (1984) apparent temperature (warm-weather approximation).

    AT = t + 0.33 * e - 0.70 * ws - 4.00   (Steadman)
    with vapour pressure ``e`` (hPa) from dewpoint and wind speed = 1 m/s
    (a constant residential-wind assumption, identical for every pixel).
    """
    e = 6.105 * np.exp((17.27 * dewpoint_c) / (237.7 + dewpoint_c))
    ws = 1.0  # m/s
    return tmax_c + 0.33 * e - 0.70 * ws - 4.00


def load_daily(
    source: str,
    points: gpd.GeoDataFrame,
    cache_dir: Path,
    year: int,
    city: str = "santiago",
) -> tuple[pd.DataFrame, str]:
    """Dispatch to the requested source's cache loader.

    Returns ``(df, location_id_strategy)`` where ``location_id_strategy``
    is either ``"point"`` (openmeteo, one location_id per point) or
    ``"commune"`` (era5land, replicated onto commune_point rows).
    """
    if source == "openmeteo":
        cache = cache_dir / f"climate_heat_grid_daily_{year}.csv"
        return _load_openmeteo_daily(points, cache), "point"
    if source == "era5land":
        cache = cache_dir / f"{city}_era5land_grid_{year}.csv"
        return _load_era5land_daily(cache), "pixel"
    raise ValueError(f"Unknown climate source: {source!r} (expected 'era5land')")


# ---------------------------------------------------------------------------
# Daily -> per-location summary
# ---------------------------------------------------------------------------


SUMMER_MONTHS = {1, 2, 12}


def summarize_location(
    group: pd.DataFrame,
    summer_months: set[int] | None = None,
) -> pd.Series:
    """Compute the 12 climate metrics for one location/year."""
    summer = group[group["month"].isin(summer_months or SUMMER_MONTHS)]
    return pd.Series(
        {
            "tmean_annual_c": group["temperature_2m_mean"].mean(),
            "tmax_mean_annual_c": group["temperature_2m_max"].mean(),
            "summer_tmax_mean_c": summer["temperature_2m_max"].mean()
            if len(summer) > 0
            else np.nan,
            "tmax_p95_c": group["temperature_2m_max"].quantile(0.95),
            "tmax_abs_c": group["temperature_2m_max"].max(),
            "apparent_tmax_mean_c": group["apparent_temperature_max"].mean(),
            "hot_days_30c": (group["temperature_2m_max"] >= 30.0).sum(),
            "hot_days_35c": (group["temperature_2m_max"] >= 35.0).sum(),
            "apparent_hot_days_35c": (group["apparent_temperature_max"] >= 35.0).sum(),
            "tropical_nights_20c": (group["temperature_2m_min"] >= 20.0).sum(),
            "precip_annual_mm": group["precipitation_sum"].sum(min_count=1),
            "n_days": group["date"].nunique(),
        }
    )


METRIC_COLS = [
    "tmean_annual_c",
    "tmax_mean_annual_c",
    "summer_tmax_mean_c",
    "tmax_p95_c",
    "tmax_abs_c",
    "apparent_tmax_mean_c",
    "hot_days_30c",
    "hot_days_35c",
    "apparent_hot_days_35c",
    "tropical_nights_20c",
    "precip_annual_mm",
    "n_days",
]

ERA5LAND_PIXEL_SIZE_M = 11_132


# ---------------------------------------------------------------------------
# Elevation (Open-Meteo elevation API, cached)
# ---------------------------------------------------------------------------


def fetch_elevations(
    latlon: pd.DataFrame,
    cache_path: Path,
    batch_size: int = 100,
    sleep_s: float = 1.0,
) -> pd.DataFrame:
    """Fetch elevations in (lat, lon) chunks via the Open-Meteo elevation API.

    Cached locally so the same network call is never repeated.
    """
    uniq = latlon.drop_duplicates(["lat", "lon"]).reset_index(drop=True)
    if cache_path.exists():
        cached = pd.read_csv(cache_path)
        have = set(zip(cached["lat"].round(4), cached["lon"].round(4)))
        need = set(zip(uniq["lat"].round(4), uniq["lon"].round(4)))
        if need.issubset(have):
            return cached

    rows: list[pd.DataFrame] = []
    for start in range(0, len(uniq), batch_size):
        ch = uniq.iloc[start : start + batch_size]
        r = requests.get(
            "https://api.open-meteo.com/v1/elevation",
            params={
                "latitude": ",".join(ch["lat"].astype(str)),
                "longitude": ",".join(ch["lon"].astype(str)),
            },
            timeout=60,
        )
        r.raise_for_status()
        rows.append(
            pd.DataFrame(
                {
                    "lat": ch["lat"].values,
                    "lon": ch["lon"].values,
                    "elevation_m": r.json()["elevation"],
                }
            )
        )
        time.sleep(sleep_s)

    out = pd.concat(rows, ignore_index=True)
    out.to_csv(cache_path, index=False)
    return out


# ---------------------------------------------------------------------------
# Aggregation: per-point metrics -> per-commune metrics (with valley + fallback)
# ---------------------------------------------------------------------------


def aggregate_to_communes(
    points: gpd.GeoDataFrame,
    point_metrics: pd.DataFrame,
    communes: gpd.GeoDataFrame,
    cfg: dict[str, Any],
    elev_band_m: float,
    fallback_to_representative_point: bool,
    elevation_cache: Path | None = None,
) -> tuple[gpd.GeoDataFrame, dict[str, int]]:
    """Aggregate per-location daily summaries to one row per commune.

    Two operating modes:

    - ``grid`` mode (Open-Meteo): per-point metrics exist for both grid
      cells and commune points. Grid points are spatial-joined to their
      commune, then filtered to a valley band (≤ ``elev_band_m`` above
      each commune's minimum elevation). Communes with no grid point
      inside their polygon use the per-commune representative point as
      a fallback (recorded via ``used_nearest_fallback=True``).
    - ``era5land`` mode: metrics are calculated per native pixel. Pixel
      footprints are intersected with the administrative polygons and
      averaged with intersection area as weight. A unit with no intersecting
      observed land pixel may use the nearest observed pixel centre, capped at
      one native grid spacing and recorded as a fallback. Representative
      commune points are never used.
    """
    gdf_comm = communes[["name", "area_km2", "geometry"]].copy()
    sources = set(point_metrics.get("source", []).tolist())

    if "era5land_pixel" in sources:
        # ERA5-Land is a raster product.  Build cells around the native pixel
        # centres and use the actual polygon intersection as a fractional
        # weight.  This preserves a stable grid when communes are split or
        # dissolved and gives a tiny unit its intersecting cells rather than a
        # fabricated representative point.
        half = ERA5LAND_PIXEL_SIZE_M / 2
        pixel = gpd.GeoDataFrame(
            point_metrics.copy(),
            geometry=[box(x - half, y - half, x + half, y + half)
                      for x, y in zip(point_metrics["x_m"], point_metrics["y_m"])],
            crs=cfg["crs"]["metric"],
        )
        units = gdf_comm.reset_index(names="_unit_index")
        intersections = gpd.overlay(
            pixel[["pixel_id", *METRIC_COLS, "geometry"]],
            units[["_unit_index", "name", "area_km2", "geometry"]],
            how="intersection",
            keep_geom_type=True,
        )
        intersections["intersection_area_m2"] = intersections.geometry.area
        weighted_rows: list[dict[str, Any]] = []
        for name, group in intersections.groupby("name", dropna=False):
            weights = group["intersection_area_m2"]
            weighted_rows.append({
                "name": name,
                **{column: float(np.average(group[column], weights=weights)) for column in METRIC_COLS},
                "n_area_grid_points": int(group["pixel_id"].nunique()),
            })
        values = pd.DataFrame(
            weighted_rows,
            columns=["name", *METRIC_COLS, "n_area_grid_points"],
        )
        gdf_result = gdf_comm.merge(values, on="name", how="left")
        gdf_result["n_area_grid_points"] = (
            gdf_result["n_area_grid_points"].fillna(0).astype(int)
        )
        gdf_result["used_nearest_fallback"] = False
        gdf_result["nearest_climate_m"] = 0.0
        missing_primary = gdf_result["tmean_annual_c"].isna()
        if missing_primary.any():
            pixel_centres = gpd.GeoDataFrame(
                point_metrics.reset_index(drop=True).copy(),
                geometry=gpd.points_from_xy(
                    point_metrics["x_m"], point_metrics["y_m"]
                ),
                crs=cfg["crs"]["metric"],
            ).sort_values("pixel_id", kind="stable")
            if pixel_centres.empty:
                raise ValueError("No observed ERA5-Land pixels are available")
            for index in gdf_result.index[missing_primary]:
                distances = pixel_centres.geometry.distance(
                    gdf_result.at[index, "geometry"]
                )
                nearest_index = distances.idxmin()
                nearest_distance = float(distances.loc[nearest_index])
                if nearest_distance > ERA5LAND_PIXEL_SIZE_M:
                    name = str(gdf_result.at[index, "name"])
                    raise ValueError(
                        f"Nearest ERA5-Land pixel for {name} is "
                        f"{nearest_distance:.0f} m away, beyond one native "
                        f"grid spacing ({ERA5LAND_PIXEL_SIZE_M} m)"
                    )
                for column in METRIC_COLS:
                    gdf_result.at[index, column] = pixel_centres.at[
                        nearest_index, column
                    ]
                gdf_result.at[index, "used_nearest_fallback"] = True
                gdf_result.at[index, "nearest_climate_m"] = nearest_distance

        if gdf_result[METRIC_COLS].isna().any().any():
            missing = gdf_result.loc[
                gdf_result["tmean_annual_c"].isna(), "name"
            ].tolist()
            raise ValueError("ERA5-Land coverage missing for: " + ", ".join(missing))
        return gdf_result, {"fallback_communes": int(missing_primary.sum())}

    if "grid" in sources:
        gdf_point_metrics = point_metrics.copy()
        if "geometry" not in gdf_point_metrics.columns:
            gdf_point_metrics = gpd.GeoDataFrame(
                gdf_point_metrics,
                geometry=gpd.points_from_xy(gdf_point_metrics["lon"], gdf_point_metrics["lat"]),
                crs="EPSG:4326",
            ).to_crs(cfg["crs"]["metric"])
        else:
            gdf_point_metrics = gdf_point_metrics.to_crs(cfg["crs"]["metric"])

        gdf_grid_metrics = gdf_point_metrics[
            gdf_point_metrics["source"].eq("grid")
        ].copy()

        grid_for_elev = pd.DataFrame(
            {
                "lat": gdf_grid_metrics["lat"].astype(float).to_numpy(),
                "lon": gdf_grid_metrics["lon"].astype(float).to_numpy(),
            }
        )
        if elevation_cache is not None and len(grid_for_elev) > 0:
            elev_df = fetch_elevations(grid_for_elev, elevation_cache)
            gdf_grid_metrics = gdf_grid_metrics.merge(
                elev_df, on=["lat", "lon"], how="left"
            )
        else:
            gdf_grid_metrics["elevation_m"] = 0.0

        joined_grid = gpd.sjoin(
            gdf_grid_metrics,
            gdf_comm[["name", "geometry"]],
            how="inner",
            predicate="within",
        )
        area_counts = (
            joined_grid.groupby("name")
            .size()
            .rename("n_area_grid_points")
            .reset_index()
        )

        joined_grid["min_elev"] = joined_grid.groupby("name")[
            "elevation_m"
        ].transform("min")
        valley = joined_grid[
            joined_grid["elevation_m"] <= joined_grid["min_elev"] + elev_band_m
        ]
        rep_grid = valley.groupby("name")[METRIC_COLS].mean().reset_index()

        gdf_result = gdf_comm.merge(rep_grid, on="name", how="left")
        gdf_result = gdf_result.merge(area_counts, on="name", how="left")
        gdf_result["n_area_grid_points"] = gdf_result["n_area_grid_points"].fillna(0).astype(int)

        missing_primary = gdf_result["tmean_annual_c"].isna()
        fallback_used: dict[str, int] = {
            "fallback_communes": int(missing_primary.sum())
        }

        if missing_primary.any() and fallback_to_representative_point:
            rep_pt = (
                gdf_point_metrics[gdf_point_metrics["source"].eq("commune_point")]
                .drop(columns="geometry")
                .rename(columns={"commune_name": "name"})
                .dropna(subset=["name"])
                .drop_duplicates("name")
                .set_index("name")
            )
            for col in METRIC_COLS:
                gdf_result.loc[missing_primary, col] = (
                    gdf_result.loc[missing_primary, "name"].map(rep_pt[col]).to_numpy()
                )

        gdf_result["used_nearest_fallback"] = missing_primary.to_numpy()
    else:
        raise ValueError("Climate metrics must be based on spatial pixel observations")

    gdf_result["nearest_climate_m"] = 0.0
    return gdf_result, fallback_used


# ---------------------------------------------------------------------------
# Heat indices: z-score composite + urban anomaly
# ---------------------------------------------------------------------------


def zscore(s: pd.Series) -> pd.Series:
    """Population z-score (ddof=0); returns zeros when std is zero or NaN."""
    std = s.std(ddof=0)
    if std == 0 or pd.isna(std):
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / std


def add_heat_indices(
    gdf_result: gpd.GeoDataFrame,
    heat_components: list[str],
) -> gpd.GeoDataFrame:
    """Add the relative heat-exposure index and the urban-anomaly metric.

    - ``heat_exposure_index``: average of z-scores of the configured heat
      components. Mean = 0, SD ~ 0.5 by construction. Higher = worse
      relative exposure within the RM.
    - ``urban_heat_anomaly_c``: deviation of the commune's
      ``summer_tmax_mean_c`` from the **median** commune. This is a
      *relative* anomaly, not a satellite-derived Urban Heat Island.
    """
    for col in heat_components:
        gdf_result[col + "_z"] = zscore(gdf_result[col])
    gdf_result["heat_exposure_index"] = gdf_result[
        [c + "_z" for c in heat_components]
    ].mean(axis=1)
    gdf_result["urban_heat_anomaly_c"] = (
        gdf_result["summer_tmax_mean_c"]
        - gdf_result["summer_tmax_mean_c"].median()
    )
    return gdf_result


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


EXPORT_COLS = [
    "name",
    "area_km2",
    "tmean_annual_c",
    "tmax_mean_annual_c",
    "summer_tmax_mean_c",
    "tmax_p95_c",
    "tmax_abs_c",
    "apparent_tmax_mean_c",
    "hot_days_30c",
    "hot_days_35c",
    "apparent_hot_days_35c",
    "tropical_nights_20c",
    "precip_annual_mm",
    "heat_exposure_index",
    "urban_heat_anomaly_c",
    "n_area_grid_points",
    "nearest_climate_m",
    "used_nearest_fallback",
    "n_days",
]


def export_layer(
    gdf_result: gpd.GeoDataFrame,
    out_dir: Path,
    base_name: str,
    source: str,
    year: int,
    cfg: dict[str, Any],
    extra_metadata: dict[str, Any],
) -> tuple[Path, Path, Path]:
    """Write the canonical CSV/GeoJSON/metadata trio and return their paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / f"{base_name}.csv"
    geojson_path = out_dir / f"{base_name}.geojson"
    metadata_path = out_dir / f"{base_name}_metadata.json"

    df_export = pd.DataFrame(gdf_result.drop(columns="geometry"))[EXPORT_COLS].copy()
    df_export.to_csv(csv_path, index=False)

    gdf_wgs = gdf_result.to_crs("EPSG:4326").copy()
    gdf_wgs[EXPORT_COLS + ["geometry"]].to_file(geojson_path, driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        # New Study settings are injected directly by the runner and do not
        # need the legacy OSM query.  It is descriptive metadata only, so use
        # the resolved location/study identity when that compatibility key is
        # absent.
        "region": cfg.get("region_query", cfg.get("location_id", cfg["name"])),
        "year": year,
        "source": source,
        "columns": EXPORT_COLS,
        **extra_metadata,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    return csv_path, geojson_path, metadata_path


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


def build_climate_heat_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
    *,
    source: str = "era5land",
    year: int = 2024,
    grid_step_deg: float = 0.10,
    elev_band_m: float = 300.0,
    heat_components: list[str] | None = None,
    fallback_to_representative_point: bool = False,
    base_name: str | None = None,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame, dict[str, Any]]:
    """Run the full climate_heat pipeline (cache-first, no network).

    Returns ``(df, gdf, metadata)`` where ``gdf`` carries the commune
    geometry in metric CRS and ``metadata`` is the dict that was written
    to disk.
    """
    cfg = _config.load_config(city)

    if source != "era5land":
        raise ValueError(
            "climate_heat requires source='era5land': Open-Meteo node and "
            "commune-point fallbacks are no longer a valid spatial product"
        )

    if heat_components is None:
        heat_components = [
            "summer_tmax_mean_c",
            "tmax_p95_c",
            "hot_days_30c",
            "apparent_hot_days_35c",
            "tropical_nights_20c",
        ]

    cfg = _config.load_config(city)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if base_name is None:
        base_name = f"{city}_climate_heat_{source}_{year}"

    gdf_communes = load_communes(cfg, cache_dir)
    # This is retained only as an empty compatibility object for callers that
    # inspect the return diagnostics.  ERA5 pixels come from the cache, not a
    # commune-dependent candidate-point grid.
    gdf_points = gpd.GeoDataFrame(columns=["location_id", "geometry"], geometry="geometry", crs="EPSG:4326")
    # The Study runner calls this importable builder directly.  Ensure the
    # provider cache at this seam so a first run is as resumable as the
    # standalone fetch command; complete caches are read without refetching.
    ensure_era5land_daily(city, year=year, cache_dir=cache_dir)
    daily, location_strategy = load_daily(
        source, gdf_points, cache_dir, year, city=city
    )
    summer_months = set(
        cfg.get("climate", {}).get("seasons", {}).get("summer", SUMMER_MONTHS)
    )

    # Summarise per location_id (openmeteo) or per name+date (era5land).
    daily = daily.copy()
    daily["month"] = pd.to_datetime(daily["date"]).dt.month
    if location_strategy == "point":
        df_point_metrics = (
            daily.groupby(["location_id"], dropna=False)
            .apply(lambda g: summarize_location(g, summer_months))
            .reset_index()
            .merge(
                gdf_points[["location_id", "source", "commune_name", "lat", "lon"]],
                on="location_id",
                how="left",
            )
        )
    else:
        # Per-pixel annual metrics.  Project centres once; aggregation below
        # intersects pixel footprints with the administrative polygons.
        df_point_metrics = (
            daily.groupby("pixel_id", dropna=False)
            .apply(lambda g: summarize_location(g, summer_months))
            .reset_index()
            .merge(
                daily[["pixel_id", "lon", "lat"]].drop_duplicates("pixel_id"),
                on="pixel_id",
                how="left",
            )
        )
        centres = gpd.GeoDataFrame(
            df_point_metrics, geometry=gpd.points_from_xy(df_point_metrics["lon"], df_point_metrics["lat"]), crs="EPSG:4326"
        ).to_crs(cfg["crs"]["metric"])
        df_point_metrics["x_m"] = centres.geometry.x.to_numpy()
        df_point_metrics["y_m"] = centres.geometry.y.to_numpy()
        df_point_metrics["source"] = "era5land_pixel"

    gdf_result, fallback_counts = aggregate_to_communes(
        points=gdf_points,
        point_metrics=df_point_metrics,
        communes=gdf_communes,
        cfg=cfg,
        elev_band_m=elev_band_m,
        fallback_to_representative_point=fallback_to_representative_point,
        elevation_cache=None,
    )

    gdf_result = add_heat_indices(gdf_result, heat_components)

    # Round to two decimals for the canonical numeric columns.
    round_cols = [c for c in METRIC_COLS if c != "n_days"] + [
        "nearest_climate_m",
        "heat_exposure_index",
        "urban_heat_anomaly_c",
    ]
    for col in round_cols:
        if col in gdf_result.columns:
            gdf_result[col] = gdf_result[col].round(2)
    gdf_result["area_km2"] = gdf_result["area_km2"].round(2)

    if gdf_result["heat_exposure_index"].isna().any():
        bad = gdf_result.loc[gdf_result["heat_exposure_index"].isna(), "name"].tolist()
        raise ValueError(f"heat_exposure_index NaN for: {bad}")

    extra_metadata = {
        "n_communes": int(len(gdf_result)),
        "n_spatial_units": int(len(gdf_result)),
        "summer_months": sorted(summer_months),
        "n_climate_points": int(df_point_metrics["pixel_id"].nunique()),
        "n_daily_rows": int(len(daily)),
        "thresholds_c": {
            "hot_day": 30.0,
            "very_hot_day": 35.0,
            "apparent_hot_day": 35.0,
            "tropical_night": 20.0,
        },
        "era5land_pixel_size_m": ERA5LAND_PIXEL_SIZE_M,
        "heat_exposure_components": heat_components,
        "aggregation_method": (
            "native_era5land_pixel_metrics; "
            "polygon_intersection_area_weighted; "
            "nearest_observed_pixel_within_one_grid_spacing_for_zero_intersection_units"
        ),
        "n_fallback_communes": fallback_counts.get("fallback_communes", 0),
        "fallback_method": "nearest observed ERA5-Land pixel centre within 11132 m",
        "fallback_spatial_units": gdf_result.loc[
            gdf_result["used_nearest_fallback"].astype(bool), "name"
        ].astype(str).tolist(),
        "max_fallback_distance_m": float(
            gdf_result.loc[
                gdf_result["used_nearest_fallback"].astype(bool),
                "nearest_climate_m",
            ].max()
        )
        if fallback_counts.get("fallback_communes", 0)
        else 0.0,
    }
    csv_path, geojson_path, metadata_path = export_layer(
        gdf_result,
        out_dir=out_dir,
        base_name=base_name,
        source=source,
        year=year,
        cfg=cfg,
        extra_metadata=extra_metadata,
    )
    print(
        f"Wrote {csv_path.name} ({len(gdf_result)} rows x {len(EXPORT_COLS)} cols, "
        f"source={source}, year={year})"
    )
    print(f"  GeoJSON: {geojson_path.name}")
    print(f"  Metadata: {metadata_path.name}")
    print(
        f"  Fallback communes: {fallback_counts.get('fallback_communes', 0)}"
    )

    df_out = pd.DataFrame(gdf_result.drop(columns="geometry"))[EXPORT_COLS].copy()
    return df_out, gdf_result, extra_metadata

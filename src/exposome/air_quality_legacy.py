"""Legacy CAMS/Open-Meteo air-quality layer for Santiago.

This module preserves the coarse 2024 commune-level air-quality layer that was
originally built in the notebook workflow. The layer remains useful as a
historical/comparative reference and as the source of the legacy NO2 columns
integrated in the master exposome table.
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

from . import boundaries, config


GRID_STEP_DEGREES = 0.1
OPEN_METEO_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
OPEN_METEO_VARS = {
    "pm25": "pm2_5",
    "no2": "nitrogen_dioxide",
}


def _mean_clean(values: list[float | None]) -> float:
    valid = [value for value in values if value is not None]
    return float(np.mean(valid)) if valid else float("nan")


def _fetch_chunk(
    chunk: list[tuple[float, float]],
    start_date: str,
    end_date: str,
    timezone_name: str = "America/Santiago",
    retries: int = 6,
) -> list[dict[str, Any]]:
    params = {
        "latitude": ",".join(str(lat) for lat, _ in chunk),
        "longitude": ",".join(str(lon) for _, lon in chunk),
        "hourly": ",".join(OPEN_METEO_VARS.values()),
        "start_date": start_date,
        "end_date": end_date,
        "timezone": timezone_name,
    }
    for attempt in range(retries):
        response = requests.get(OPEN_METEO_URL, params=params, timeout=120)
        if response.status_code == 429:
            wait_seconds = int(response.headers.get("Retry-After", "0") or 0) or min(70, 8 * 2**attempt)
            print(f"Open-Meteo rate limit (429). Waiting {wait_seconds}s before retry {attempt + 1}/{retries}.")
            time.sleep(wait_seconds)
            continue
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else [payload]
    raise RuntimeError("Open-Meteo rate limit persisted after all retries.")


def _grid_points(cfg: dict[str, Any]) -> list[tuple[float, float]]:
    bbox = cfg["bbox"]
    lats = np.arange(bbox["lat_min"], bbox["lat_max"] + 1e-9, GRID_STEP_DEGREES)
    lons = np.arange(bbox["lon_min"], bbox["lon_max"] + 1e-9, GRID_STEP_DEGREES)
    return [(round(lat, 3), round(lon, 3)) for lat in lats for lon in lons]


def fetch_openmeteo_grid(
    cfg: dict[str, Any],
    cache_path: Path,
    start_date: str,
    end_date: str,
    chunk_size: int = 40,
) -> pd.DataFrame:
    """Fetch the coarse CAMS/Open-Meteo grid and cache it locally."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = cache_path.with_suffix(cache_path.suffix + ".partial")
    points = _grid_points(cfg)

    rows: list[dict[str, float]] = []
    done: set[tuple[float, float]] = set()
    if partial_path.exists():
        previous = pd.read_csv(partial_path)
        rows = previous.to_dict("records")
        done = {(round(row["lat"], 3), round(row["lon"], 3)) for row in rows}
        print(f"Resuming Open-Meteo grid from partial cache with {len(done)} points.")

    todo = [point for point in points if point not in done]
    print(f"Sampling {len(todo)}/{len(points)} CAMS grid points from Open-Meteo.")
    for index in range(0, len(todo), chunk_size):
        chunk = todo[index:index + chunk_size]
        payload = _fetch_chunk(chunk, start_date=start_date, end_date=end_date)
        for (lat, lon), location in zip(chunk, payload):
            hourly = location["hourly"]
            rows.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "pm25": _mean_clean(hourly[OPEN_METEO_VARS["pm25"]]),
                    "no2": _mean_clean(hourly[OPEN_METEO_VARS["no2"]]),
                }
            )
        pd.DataFrame(rows).to_csv(partial_path, index=False)
        print(f"  cached {len(rows)}/{len(points)} points")
        time.sleep(8)

    df_grid = pd.DataFrame(rows)
    df_grid.to_csv(cache_path, index=False)
    if partial_path.exists():
        partial_path.unlink()
    return df_grid


def load_or_fetch_grid(
    cfg: dict[str, Any],
    cache_dir: Path,
    start_date: str,
    end_date: str,
) -> tuple[pd.DataFrame, Path]:
    year = cfg["air_quality"]["year"]
    cache_path = cache_dir / f"air_quality_grid_{year}.csv"
    if cache_path.exists():
        return pd.read_csv(cache_path), cache_path
    return fetch_openmeteo_grid(cfg, cache_path, start_date=start_date, end_date=end_date), cache_path


def _legacy_base_name(city: str, year: int) -> str:
    if city == "santiago":
        return "air_quality_exposome_rm_santiago"
    return f"{city}_air_quality_legacy_{year}"


def build_air_quality_legacy_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Build the legacy CAMS/Open-Meteo commune layer."""
    cfg = config.load_config(city)
    cache_dir = Path(cache_dir)
    out_dir = Path(out_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    start_date = cfg["air_quality"]["start_date"]
    end_date = cfg["air_quality"]["end_date"]
    year = cfg["air_quality"]["year"]
    who_pm25 = cfg["air_quality"]["who_guidelines"]["pm25"]
    who_no2 = cfg["air_quality"]["who_guidelines"]["no2"]

    df_grid, cache_path = load_or_fetch_grid(cfg, cache_dir=cache_dir, start_date=start_date, end_date=end_date)
    gdf_grid = gpd.GeoDataFrame(
        df_grid,
        geometry=gpd.points_from_xy(df_grid["lon"], df_grid["lat"]),
        crs=cfg["crs"]["geographic"],
    )
    gdf_grid_metric = gdf_grid.to_crs(cfg["crs"]["metric"])

    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_communes = boundaries.get_communes(cfg, cache_path=boundaries_cache)[["name", "geometry", "area_km2"]].copy()
    gdf_communes_metric = gdf_communes.to_crs(cfg["crs"]["metric"])

    joined = gpd.sjoin(gdf_grid_metric, gdf_communes_metric, how="inner", predicate="within")
    interior = (
        joined.groupby("name")
        .agg(
            pm25_mean=("pm25", "mean"),
            no2_mean=("no2", "mean"),
            n_grid=("pm25", "size"),
        )
        .reset_index()
    )

    centroids = gdf_communes_metric.copy()
    centroids["geometry"] = centroids.geometry.centroid
    nearest = (
        gpd.sjoin_nearest(
            centroids,
            gdf_grid_metric[["pm25", "no2", "geometry"]],
            how="left",
        )
        .groupby("name")
        .first()
        .reset_index()
        [["name", "pm25", "no2"]]
        .rename(columns={"pm25": "pm25_mean", "no2": "no2_mean"})
    )

    gdf_result = gdf_communes_metric.merge(nearest, on="name", how="left")
    gdf_result = gdf_result.merge(interior, on="name", how="left", suffixes=("", "_interior"))
    for column in ["pm25_mean", "no2_mean"]:
        gdf_result[column] = gdf_result[f"{column}_interior"].fillna(gdf_result[column])
    gdf_result = gdf_result.drop(columns=[f"{column}_interior" for column in ["pm25_mean", "no2_mean"]])
    gdf_result["n_grid"] = gdf_result["n_grid"].fillna(0).astype(int)
    gdf_result["pm25_who_ratio"] = (gdf_result["pm25_mean"] / who_pm25).round(2)
    gdf_result["no2_who_ratio"] = (gdf_result["no2_mean"] / who_no2).round(2)

    df_export = gdf_result.drop(columns="geometry").copy()
    df_export["area_km2"] = df_export["area_km2"].round(2)
    for column in ["pm25_mean", "no2_mean"]:
        df_export[column] = df_export[column].round(2)
    df_export = df_export[
        ["name", "area_km2", "pm25_mean", "no2_mean", "n_grid", "pm25_who_ratio", "no2_who_ratio"]
    ].sort_values("name").reset_index(drop=True)

    if len(df_export) != cfg["expected_communes"]:
        raise ValueError(f"Expected {cfg['expected_communes']} communes, got {len(df_export)}")
    if df_export["name"].duplicated().any():
        raise ValueError("Duplicate commune names in legacy air-quality layer.")
    if df_export.isna().any().any():
        missing = df_export.columns[df_export.isna().any()].tolist()
        raise ValueError(f"Missing values in legacy air-quality layer: {missing}")

    gdf_wgs = (
        gdf_result[["name", "geometry"]]
        .merge(df_export, on="name", how="right", validate="one_to_one")
        .to_crs(cfg["crs"]["geographic"])
        .sort_values("name")
        .reset_index(drop=True)
    )

    base_name = _legacy_base_name(city, year)
    csv_path = out_dir / f"{base_name}.csv"
    geojson_path = out_dir / f"{base_name}.geojson"
    metadata_path = out_dir / f"{base_name}_metadata.json"
    df_export.to_csv(csv_path, index=False)
    gdf_wgs.to_file(geojson_path, driver="GeoJSON")

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "year": year,
        "role": "Historical/comparative CAMS/Open-Meteo layer; master consumes only no2_mean, n_grid, no2_who_ratio.",
        "method": "Legacy commune aggregation from CAMS reanalysis served by Open-Meteo.",
        "source": {
            "provider": "Open-Meteo Air Quality API",
            "dataset": "CAMS reanalysis",
            "url": OPEN_METEO_URL,
            "variables": OPEN_METEO_VARS,
        },
        "grid": {
            "bbox": cfg["bbox"],
            "step_degrees": GRID_STEP_DEGREES,
            "points": int(len(df_grid)),
            "cache_csv": cache_path.as_posix(),
            "fallback": "Nearest grid point to commune centroid when a commune has no interior grid points.",
            "n_communes_with_zero_interior_points": int((df_export["n_grid"] == 0).sum()),
        },
        "period": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "who_guidelines_ug_m3": {
            "pm25": who_pm25,
            "no2": who_no2,
        },
        "columns": {
            "pm25_mean": "Legacy CAMS annual mean PM2.5 [ug/m3]; retained only for comparison, not merged into master.",
            "no2_mean": "Legacy CAMS annual mean NO2 [ug/m3]; merged into master.",
            "n_grid": "Number of coarse CAMS grid points fully inside the commune polygon before centroid fallback.",
            "pm25_who_ratio": "pm25_mean / WHO 2021 PM2.5 guideline (5 ug/m3); comparison only.",
            "no2_who_ratio": "no2_mean / WHO 2021 NO2 guideline (10 ug/m3); merged into master.",
        },
        "outputs": {
            "csv": csv_path.name,
            "geojson": geojson_path.name,
        },
        "n_rows": int(len(df_export)),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Wrote {csv_path.name}, {geojson_path.name}, and {metadata_path.name}")
    return df_export, gdf_wgs

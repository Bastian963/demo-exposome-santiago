"""Portable annual climate-metric layer derived from a declared daily input."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import boundaries, config
from .climate.metrics import calculate_climate_metrics


def build_climate_metrics_layer(
    city: str,
    daily_csv: Path,
    out_dir: Path,
    cache_dir: Path | None = None,
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Aggregate a daily climate artifact into one aggregate-study layer."""
    cfg = config.load_config(city)
    daily_csv = Path(daily_csv)
    if not daily_csv.is_file():
        raise FileNotFoundError(f"Configured daily climate input not found: {daily_csv}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    daily = pd.read_csv(daily_csv)
    thresholds = cfg.get("climate", {}).get("thresholds", {})
    metrics = calculate_climate_metrics(
        daily,
        date_col="date",
        tmax_col="temperature_2m_max",
        tmin_col="temperature_2m_min",
        tmean_col="temperature_2m_mean",
        group_col="name",
        thresholds=thresholds,
    )
    if metrics["name"].duplicated().any() or metrics.isna().any().any():
        raise ValueError("Daily climate input produced duplicate or missing aggregate metrics")

    cache_path = None
    if cache_dir is not None:
        cache_path = Path(cache_dir) / f"{city}_communes.geojson"
    units = boundaries.get_communes(cfg, cache_path=cache_path)
    geometry = units[["name", "geometry"]].merge(
        metrics, on="name", how="right", validate="one_to_one"
    )
    geometry = gpd.GeoDataFrame(geometry, geometry="geometry", crs=cfg["crs"]["geographic"])
    base = f"{city}_climate_metrics_annual"
    csv_path = out_dir / f"{base}.csv"
    geojson_path = out_dir / f"{base}.geojson"
    metadata_path = out_dir / f"{base}_metadata.json"
    metrics.to_csv(csv_path, index=False)
    geometry.to_file(geojson_path, driver="GeoJSON")
    dates = pd.to_datetime(daily["date"])
    metadata_path.write_text(
        json.dumps(
            {
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "city": city,
                "n_rows": len(metrics),
                "daily_input": str(daily_csv),
                "years": sorted(dates.dt.year.unique().tolist()),
                "source": "Declared daily climate input",
                "thresholds": thresholds,
                "columns": metrics.columns.tolist(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return metrics, geometry

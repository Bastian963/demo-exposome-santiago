"""Resumable Open-Meteo grid fetch used by the portable heat layer."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from tqdm import tqdm


ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARIABLES = (
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "precipitation_sum",
)


def ensure_grid_daily(
    points: pd.DataFrame,
    *,
    year: int,
    cache_dir: Path,
    timezone: str = "auto",
    chunk_size: int = 35,
    request_sleep_s: float = 10.0,
    retries: int = 10,
) -> Path:
    """Return the complete daily cache, fetching only missing point IDs."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"climate_heat_grid_daily_{year}.csv"
    partial = cache_dir / f"climate_heat_grid_daily_{year}.partial.csv"
    if cache.exists():
        return cache

    required = {"location_id", "source", "lat", "lon"}
    missing = required - set(points.columns)
    if missing:
        raise ValueError(f"Climate point table is missing columns: {sorted(missing)}")

    rows: list[dict[str, Any]] = []
    done_ids: set[int] = set()
    if partial.exists():
        previous = pd.read_csv(partial)
        rows = previous.to_dict("records")
        done_ids = set(previous["location_id"].dropna().astype(int).unique())

    todo = points[~points["location_id"].isin(done_ids)].copy()
    chunk_starts = list(range(0, len(todo), chunk_size))
    for start in tqdm(chunk_starts, desc="climate_heat grid (Open-Meteo)", unit="chunk"):
        chunk = todo.iloc[start : start + chunk_size]
        payload = _fetch_chunk(
            chunk,
            year=year,
            timezone=timezone,
            retries=retries,
        )
        rows.extend(_payload_to_rows(chunk, payload))
        pd.DataFrame(rows).to_csv(partial, index=False)
        if start + chunk_size < len(todo):
            time.sleep(request_sleep_s)

    result = pd.DataFrame(rows)
    expected_ids = set(points["location_id"].astype(int))
    actual_ids = set(result["location_id"].dropna().astype(int))
    if actual_ids != expected_ids:
        raise RuntimeError(
            "Open-Meteo grid cache is incomplete: "
            f"missing point IDs={sorted(expected_ids - actual_ids)}"
        )
    result.to_csv(cache, index=False)
    partial.unlink(missing_ok=True)
    return cache


def _fetch_chunk(
    chunk: pd.DataFrame,
    *,
    year: int,
    timezone: str,
    retries: int,
) -> list[dict[str, Any]]:
    params = {
        "latitude": ",".join(chunk["lat"].astype(str)),
        "longitude": ",".join(chunk["lon"].astype(str)),
        "daily": ",".join(DAILY_VARIABLES),
        "start_date": f"{year}-01-01",
        "end_date": f"{year}-12-31",
        "timezone": timezone,
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
        "cell_selection": "land",
    }
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(ARCHIVE_URL, params=params, timeout=180)
            if response.status_code == 429 or response.status_code >= 500:
                wait = int(response.headers.get("Retry-After", 0)) or min(
                    300, 5 * (2**attempt)
                )
                time.sleep(wait)
                continue
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, list) else [payload]
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(min(90, 5 * (2**attempt)))
    raise RuntimeError(f"Open-Meteo grid request failed after {retries} attempts") from last_error


def _payload_to_rows(
    chunk: pd.DataFrame,
    payload: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(payload) != len(chunk):
        raise RuntimeError(
            f"Open-Meteo returned {len(payload)} locations for {len(chunk)} requested"
        )
    rows: list[dict[str, Any]] = []
    for (_, requested), location in zip(chunk.iterrows(), payload):
        daily = location.get("daily", {})
        dates = daily.get("time", [])
        if not dates:
            raise RuntimeError(
                f"Open-Meteo returned no daily data for location_id={requested.location_id}"
            )
        for index, date in enumerate(dates):
            row: dict[str, Any] = {
                "location_id": int(requested.location_id),
                "source": requested.source,
                "lat": float(requested.lat),
                "lon": float(requested.lon),
                "date": date,
            }
            for variable in DAILY_VARIABLES:
                values = daily.get(variable, [])
                row[variable] = (
                    np.nan
                    if index >= len(values) or values[index] is None
                    else values[index]
                )
            rows.append(row)
    return rows

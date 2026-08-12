"""Build the per-year climate heat series consumed by the webapp year slider.

Runs the *same canonical pipeline* as ``scripts/run_climate_heat.py``
(Open-Meteo grid + elevation downscaling, ``build_climate_heat_layer``)
once per year, so the 2015-2023 values are method-consistent with the
canonical 2024 layer (``santiago_climate_heat_exposome_rm_santiago.csv``).
Commune-level Open-Meteo/ERA5 shortcuts were rejected: they correlate
poorly with the canonical valley-band aggregation (r=0.23-0.75 in 2024).

Grid daily inputs are cached at ``cache/climate_heat_grid_daily_<YEAR>.csv``
(the same file the canonical run reads). Missing years are fetched from the
Open-Meteo archive API in coordinate batches with resume support — the same
strategy as the former Santiago climate notebook.

Output (wide, 52 communes):

- ``data/processed/santiago_climate_heat_by_year.csv`` with columns
  ``summer_tmax_mean_c_<Y>``, ``hot_days_30c_<Y>``, ``tropical_nights_20c_<Y>``
  for 2015-2023. 2024 is *not* duplicated: the canonical layer already
  carries those columns un-suffixed.
- ``..._by_year_metadata.json``

Run from the repo root:

    .venv/bin/python scripts/run_climate_heat_annual.py --years 2015-2023
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import requests  # noqa: E402
import typer  # noqa: E402

from exposome import config as _config  # noqa: E402
from exposome.climate.build_layer import (  # noqa: E402
    build_climate_heat_layer,
    build_climate_points,
    load_communes,
)

app = typer.Typer(help="Per-year canonical climate heat series (2015-2023).")

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARS = [
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "precipitation_sum",
]
CHUNK_SIZE = 35
# The archive API weights multi-location calls by location count, so a full
# year (6 chunks x 35 points) burns minute-level quota fast — long pauses and
# patient 429 backoff are cheaper than failing and restarting.
REQUEST_SLEEP_S = 10.0

# Webapp sub-layer columns (see webapp/public/palette.json heat children).
SERIES_COLS = ["summer_tmax_mean_c", "hot_days_30c", "tropical_nights_20c"]


def _fetch_chunk(chunk: pd.DataFrame, start: str, end: str, retries: int = 10) -> list[dict]:
    """One batched Open-Meteo archive call with 429/5xx backoff."""
    params = {
        "latitude": ",".join(chunk["lat"].astype(str)),
        "longitude": ",".join(chunk["lon"].astype(str)),
        "daily": ",".join(DAILY_VARS),
        "start_date": start,
        "end_date": end,
        "timezone": "America/Santiago",
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
        "cell_selection": "land",
    }
    for attempt in range(retries):
        try:
            r = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=180)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 0)) or min(300, 15 * 2**attempt)
                print(f"    rate-limit 429 → waiting {wait}s ({attempt + 1}/{retries})", flush=True)
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                wait = min(90, 5 * 2**attempt)
                print(f"    server {r.status_code} → waiting {wait}s ({attempt + 1}/{retries})", flush=True)
                time.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else [data]
        except requests.RequestException as exc:
            wait = min(90, 5 * 2**attempt)
            print(f"    network error: {exc}; waiting {wait}s ({attempt + 1}/{retries})", flush=True)
            time.sleep(wait)
    raise RuntimeError("Open-Meteo: batch failed after retries")


def _payload_to_rows(chunk: pd.DataFrame, payload: list[dict]) -> list[dict]:
    if len(payload) != len(chunk):
        raise RuntimeError(f"Got {len(payload)} locations for {len(chunk)} requested")
    rows = []
    for (_, req), loc in zip(chunk.iterrows(), payload):
        daily = loc.get("daily", {})
        dates = daily.get("time", [])
        if not dates:
            raise RuntimeError(f"Empty daily payload for location_id={req.location_id}")
        for i, date in enumerate(dates):
            row = {
                "location_id": int(req.location_id),
                "source": req.source,
                "lat": float(req.lat),
                "lon": float(req.lon),
                "date": date,
            }
            for var in DAILY_VARS:
                values = daily.get(var, [])
                row[var] = np.nan if i >= len(values) or values[i] is None else values[i]
            rows.append(row)
    return rows


def _ensure_grid_daily(points: pd.DataFrame, year: int, cache_dir: Path) -> Path:
    """Fetch ``climate_heat_grid_daily_<year>.csv`` if missing (resumable)."""
    cache = cache_dir / f"climate_heat_grid_daily_{year}.csv"
    partial = cache_dir / f"climate_heat_grid_daily_{year}.partial.csv"
    if cache.exists():
        return cache

    rows: list[dict] = []
    done_ids: set[int] = set()
    if partial.exists():
        prev = pd.read_csv(partial)
        rows = prev.to_dict("records")
        done_ids = set(prev["location_id"].dropna().astype(int).unique())
        print(f"  {year}: resuming, {len(done_ids)} points already fetched", flush=True)

    todo = points[~points["location_id"].isin(done_ids)].copy()
    print(f"  {year}: fetching {len(todo)}/{len(points)} grid points…", flush=True)
    for start_idx in range(0, len(todo), CHUNK_SIZE):
        chunk = todo.iloc[start_idx : start_idx + CHUNK_SIZE]
        payload = _fetch_chunk(chunk, f"{year}-01-01", f"{year}-12-31")
        rows.extend(_payload_to_rows(chunk, payload))
        pd.DataFrame(rows).to_csv(partial, index=False)
        time.sleep(REQUEST_SLEEP_S)

    df = pd.DataFrame(rows)
    df.to_csv(cache, index=False)
    partial.unlink(missing_ok=True)
    print(f"  {year}: cached {len(df):,} daily rows → {cache.name}", flush=True)
    return cache


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name"),
    years: str = typer.Option("2015-2023", help="Year range 'START-END' (inclusive)"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
    check_2024: bool = typer.Option(
        True,
        help="Rebuild 2024 from cache and assert it matches the canonical layer.",
    ),
) -> None:
    """Fetch missing grid dailies and build the per-year heat series."""
    y0, y1 = (int(p) for p in years.split("-"))
    year_list = list(range(y0, y1 + 1))
    cache_dir = Path(cache_dir)
    out_dir = Path(out_dir)
    tmp_dir = cache_dir / "climate_heat_annual_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    cfg = _config.load_config(city)
    communes = load_communes(cfg, cache_dir)
    points = pd.DataFrame(
        build_climate_points(communes, grid_step_deg=0.10).drop(columns="geometry")
    )

    # Sanity: our point numbering must match the canonical 2024 cache,
    # otherwise the per-year series would not be comparable.
    canon_cache = cache_dir / "climate_heat_grid_daily_2024.csv"
    if canon_cache.exists():
        canon = pd.read_csv(canon_cache)[["location_id", "lat", "lon"]].drop_duplicates()
        merged = points.merge(canon, on="location_id", suffixes=("", "_canon"))
        if not np.allclose(merged["lat"], merged["lat_canon"], atol=1e-4) or not np.allclose(
            merged["lon"], merged["lon_canon"], atol=1e-4
        ):
            raise RuntimeError("Grid point numbering diverges from the canonical 2024 cache")

    # 1) Ensure grid dailies exist for every year.
    for year in year_list:
        _ensure_grid_daily(points, year, cache_dir)

    # 2) Canonical build per year (outputs to a temp dir; canonical files untouched).
    per_year: dict[int, pd.DataFrame] = {}
    for year in year_list:
        print(f"\nBuilding canonical heat layer for {year}…", flush=True)
        df_out, _, _ = build_climate_heat_layer(
            city=city,
            cache_dir=cache_dir,
            out_dir=tmp_dir,
            source="openmeteo",
            year=year,
            base_name=f"{city}_climate_heat_annual_{year}",
        )
        per_year[year] = df_out[["name", *SERIES_COLS]].copy()

    # 3) Optional consistency check against the canonical 2024 layer.
    if check_2024:
        canonical = pd.read_csv(out_dir / "climate_heat_exposome_rm_santiago.csv")
        df24, _, _ = build_climate_heat_layer(
            city=city,
            cache_dir=cache_dir,
            out_dir=tmp_dir,
            source="openmeteo",
            year=2024,
            base_name=f"{city}_climate_heat_annual_2024_check",
        )
        chk = canonical[["name", *SERIES_COLS]].merge(
            df24[["name", *SERIES_COLS]], on="name", suffixes=("_canon", "_rebuilt")
        )
        for col in SERIES_COLS:
            diff = (chk[f"{col}_canon"] - chk[f"{col}_rebuilt"]).abs().max()
            print(f"  2024 check {col}: max |diff| = {diff:.3f}")
            if diff > 0.51:  # canonical values are rounded to 2 decimals
                raise RuntimeError(f"2024 rebuild diverges from canonical layer on {col}")

    # 4) Assemble the wide series.
    wide = None
    for year, df in per_year.items():
        renamed = df.rename(columns={c: f"{c}_{year}" for c in SERIES_COLS})
        wide = renamed if wide is None else wide.merge(renamed, on="name", how="outer")
    wide = wide.sort_values("name").reset_index(drop=True)

    expected = cfg.get("expected_communes", 52)
    if len(wide) != expected:
        raise ValueError(f"Expected {expected} communes, got {len(wide)}")
    value_cols = [c for c in wide.columns if c != "name"]
    if wide[value_cols].isna().any().any():
        bad = wide.columns[wide.isna().any()].tolist()
        raise ValueError(f"NaN values in per-year heat series: {bad}")

    csv_path = out_dir / f"{city}_climate_heat_by_year.csv"
    wide.to_csv(csv_path, index=False)

    meta = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "layer": "climate_heat_by_year",
        "years": year_list,
        "columns_per_year": SERIES_COLS,
        "n_rows": int(len(wide)),
        "n_cols": int(len(wide.columns)),
        "source": "Open-Meteo archive API (ERA5-based best_match), 0.10° grid",
        "method": (
            "Same canonical pipeline as run_climate_heat.py per year: "
            "grid dailies → per-point metrics → valley-band elevation "
            "aggregation with representative-point fallback. Summer metrics "
            "use calendar months {1, 2, 12} of the same year. 2024 is not "
            "duplicated here: the canonical layer carries it un-suffixed."
        ),
        "consumers": [
            "scripts/build_master_exposome.py",
            "webapp year slider (palette.json year_columns)",
        ],
    }
    meta_path = out_dir / f"{city}_climate_heat_by_year_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    print(f"\nWrote {csv_path.name} ({len(wide)} rows x {len(wide.columns)} cols)")
    print(f"  Metadata: {meta_path.name}")


if __name__ == "__main__":
    app()

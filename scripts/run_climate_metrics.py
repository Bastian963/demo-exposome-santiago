"""CLI entrypoint for the climate_openmeteo exposome layer.

Aggregates daily Open-Meteo observations into the canonical annual /
seasonal metrics consumed by ``scripts/build_master_exposome.py``
(LAYER_SPECS["climate_openmeteo"], 24 columns renamed with the
``om_`` prefix).

Canonical input
---------------
``data/processed/santiago_climate_openmeteo_daily_2024_2024.csv`` —
the 2024-only daily archive (19,032 rows = 52 communes x 366 days),
matching the temporal scope of the legacy ``climate_heat`` layer.
A wider 2015-2024 archive is also present in ``data/processed/`` but
is not used by the canonical climate_openmeteo layer.

Outputs
-------
- ``data/processed/<city>_climate_metrics_annual.csv`` (52 x 30)
- ``data/processed/<city>_climate_metrics_annual.geojson``
- ``data/processed/<city>_climate_metrics_annual_metadata.json``
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer

from exposome.climate.fetch_openmeteo import fetch_openmeteo_years
from exposome.climate.metrics import calculate_climate_metrics
from exposome import config
import geopandas as gpd
import pandas as pd

app = typer.Typer(help="Calculate climate exposure metrics.")

_YEAR_RANGE_RE = re.compile(r"_(\d{4})_(\d{4})\.csv$")


def _ensure_daily_csv(daily_csv: Path, city: str, cache_dir: Path) -> None:
    """Auto-fetch the Open-Meteo daily archive if it isn't cached yet.

    The year range is read from the expected filename (e.g.
    ``..._2024_2024.csv``) so this works for any study without a
    per-city hardcoded range; falls back to the city config's
    ``climate.years`` if the filename doesn't encode a range.
    """
    if daily_csv.exists():
        return
    match = _YEAR_RANGE_RE.search(daily_csv.name)
    if match:
        start, end = int(match.group(1)), int(match.group(2))
        years = list(range(start, end + 1))
    else:
        cfg = config.load_config(city)
        years = cfg.get("climate", {}).get("years", list(range(2015, 2025)))
    print(f"  {daily_csv.name} not found — fetching from Open-Meteo ({years[0]}-{years[-1]})...")
    df = fetch_openmeteo_years(city=city, years=years, cache_dir=cache_dir, out_dir=daily_csv.parent)
    daily_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(daily_csv, index=False)


def _metadata_block(
    df_daily: pd.DataFrame,
    df_metrics: pd.DataFrame,
    city: str,
    daily_csv: Path,
    thresholds: dict,
) -> dict:
    """Build the metadata dict for the climate_metrics_annual outputs."""
    n_daily = int(len(df_daily))
    n_communes = int(df_metrics.shape[0])
    n_cols = int(df_metrics.shape[1])
    df_daily = df_daily.copy()
    df_daily["date"] = pd.to_datetime(df_daily["date"])
    years = sorted(df_daily["date"].dt.year.unique().tolist())
    return {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "n_rows": n_communes,
        "n_cols": n_cols,
        "n_daily_rows": n_daily,
        "daily_csv": daily_csv.name,
        "years": years,
        "source": "Open-Meteo Historical Weather API (archive-api.open-meteo.com)",
        "thresholds": thresholds,
        "columns": df_metrics.columns.tolist(),
        "outputs": [
            f"{city}_climate_metrics_annual.csv",
            f"{city}_climate_metrics_annual.geojson",
        ],
        "limitations": (
            "Canonical layer is computed from a 2024-only daily archive "
            "(19,032 rows, 52 communes x 366 days), matching the temporal "
            "scope of the legacy climate_heat layer. A wider 2015-2024 "
            "daily archive is present in data/processed/ but is not used "
            "by this layer; the master builder and downstream analyses "
            "consume the 2024-only values for consistency with climate_heat."
        ),
    }


@app.command()
def metrics(
    city: str = typer.Option("santiago", help="City config name"),
    daily_csv: Path = typer.Option(
        Path("data/processed/santiago_climate_openmeteo_daily_2024_2024.csv"),
        help="Daily climate CSV (must have name, date, temperature_2m_max/min/mean, precipitation_sum)",
    ),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
    cache_dir: Path = typer.Option(
        Path("cache"), help="Cache directory (used to auto-fetch daily_csv if it's missing)"
    ),
) -> None:
    """Compute derived climate metrics from daily time series."""
    cfg = config.load_config(city)
    _ensure_daily_csv(daily_csv, city, cache_dir)
    df_daily = pd.read_csv(daily_csv)

    thresholds = cfg.get("climate", {}).get("thresholds", {})
    df_metrics = calculate_climate_metrics(
        df_daily,
        date_col="date",
        tmax_col="temperature_2m_max",
        tmin_col="temperature_2m_min",
        tmean_col="temperature_2m_mean",
        group_col="name",
        thresholds=thresholds,
    )

    if df_metrics["name"].duplicated().any():
        dupes = df_metrics.loc[df_metrics["name"].duplicated(), "name"].tolist()
        raise ValueError(f"Duplicate commune names in output: {dupes}")
    if df_metrics.isna().any().any():
        bad = df_metrics.columns[df_metrics.isna().any()].tolist()
        raise ValueError(f"NaN in output columns: {bad}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"{city}_climate_metrics_annual"
    csv_path = out_dir / f"{base}.csv"
    geojson_path = out_dir / f"{base}.geojson"
    meta_path = out_dir / f"{base}_metadata.json"

    df_metrics.to_csv(csv_path, index=False)

    boundaries_cache = REPO_ROOT / "cache" / f"{city}_communes.geojson"
    if boundaries_cache.exists():
        gdf = gpd.read_file(boundaries_cache)[["name", "geometry"]]
        gdf = gdf.merge(df_metrics, on="name", how="right", validate="one_to_one")
        gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])
        gdf.to_file(geojson_path, driver="GeoJSON")
    else:
        geojson_path = None  # type: ignore[assignment]

    metadata = _metadata_block(df_daily, df_metrics, city, daily_csv, thresholds)
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(
        f"Saved {csv_path.name} ({len(df_metrics)} rows x {df_metrics.shape[1]} cols)"
    )
    if geojson_path is not None:
        print(f"Saved {geojson_path.name}")
    print(f"Saved {meta_path.name}")


if __name__ == "__main__":
    app()

"""Wildfire (forest-fire) exposome layer — the "climate disasters" factor.

Commune-level wildfire exposure for the 52 communes of the Santiago
Metropolitan Region, 2015-2024. This is the *discrete-hazard* complement to the
project's continuous climate layers (heat waves, drought/SPI, extreme
precipitation): forest fires are the dominant climate disaster in the RM, with
catastrophic seasons in 2017, 2023 and 2024.

Two satellite sources are combined (both via Google Earth Engine, no extra API
key beyond the GEE project):

- **MODIS Burned Area** (``MODIS/061/MCD64A1``, 500 m, monthly): area actually
  burned per commune and year — the spatial *extent* of fire.
- **FIRMS active fire** (``FIRMS``, ~1 km, daily): count of fire detections per
  commune — captures interface / peri-urban fire *activity* that the 500 m
  burned-area product misses in densely built communes.

An optional **official enrichment** (CONAF / itrend forest-fire statistics by
commune) is merged when a local CSV is dropped in ``data/raw/`` (see the
``wildfire.official`` block in the city config); the layer is fully reproducible
from satellite alone if it is absent.

Brain-health rationale
----------------------
- **Wildfire smoke** → acute PM2.5/PM10 spikes → neuroinflammation, oxidative
  stress, accelerated cognitive decline; complements the air-quality layer.
- **Recurrent fire exposure** → chronic stress, evacuation/displacement,
  damage to green space and the wildland-urban interface.

This module mirrors :mod:`exposome.alan` (GEE zonal statistics + strict
validation + CSV/GeoJSON/metadata outputs) and :mod:`exposome.precipitation_spi`
(derived index + rich metadata), so the output plugs straight into
``build_master_exposome``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import ee
import geopandas as gpd
import numpy as np
import pandas as pd

from . import boundaries, config, demography, gee

# Burned area below this (km^2 ≈ 1 ha) in a year is treated as noise / no fire
# when counting "years with fire" for the recurrence metric.
_BURN_YEAR_MIN_KM2 = 0.01


# --------------------------------------------------------------------------- #
# Per-year satellite fetchers
# --------------------------------------------------------------------------- #
def _burned_area_km2(
    cfg: dict[str, Any], regions_fc: ee.FeatureCollection, year: int
) -> pd.DataFrame:
    """Burned area (km^2) per commune for a single year (MODIS MCD64A1)."""
    ba = cfg["wildfire"]["collections"]["burned_area"]
    coll = (
        ee.ImageCollection(ba["id"])
        .filterDate(f"{year}-01-01", f"{year}-12-31")
        .select(ba["band"])
    )
    # BurnDate > 0 marks a burned pixel; reduce to a binary mask for the year.
    burned_m2 = coll.max().gt(0).unmask(0).multiply(ee.Image.pixelArea()).rename("burned_m2")
    stats = gee.image_to_stats(
        burned_m2, regions_fc, band="burned_m2", scale=ba["scale_meters"], reducer="sum"
    )
    df = pd.DataFrame(gee.fc_to_dicts(stats)).rename(columns={"sum": "burned_m2"})
    df["burned_km2"] = (df["burned_m2"] / 1e6).round(4)
    return df[["name", "burned_km2"]]


def _firms_activity(
    cfg: dict[str, Any], regions_fc: ee.FeatureCollection, year: int
) -> pd.DataFrame:
    """FIRMS detection count and max brightness per commune for a single year."""
    af = cfg["wildfire"]["collections"]["active_fire"]
    band = af["band"]
    scale = af["scale_meters"]
    coll = ee.ImageCollection(af["id"]).filterDate(f"{year}-01-01", f"{year}-12-31").select(band)

    # Detection count: per-pixel number of days with a fire detection.
    det_img = coll.map(lambda im: im.gt(0).unmask(0)).sum().rename("det")
    det = pd.DataFrame(
        gee.fc_to_dicts(gee.image_to_stats(det_img, regions_fc, band="det", scale=scale, reducer="sum"))
    ).rename(columns={"sum": "detections"})[["name", "detections"]]

    # Intensity proxy: max brightness temperature (K) over the year.
    bright_img = coll.max().rename(band)
    bright = pd.DataFrame(
        gee.fc_to_dicts(gee.image_to_stats(bright_img, regions_fc, band=band, scale=scale, reducer="max"))
    ).rename(columns={"max": "brightness_max_k"})
    bright = bright[["name", "brightness_max_k"]] if "brightness_max_k" in bright.columns else bright[["name"]]

    df = det.merge(bright, on="name", how="outer")
    df["detections"] = df["detections"].fillna(0.0).round(1)
    if "brightness_max_k" in df.columns:
        df["brightness_max_k"] = df["brightness_max_k"].round(1)
    else:
        df["brightness_max_k"] = np.nan
    return df


def fetch_annual_metrics(
    cfg: dict[str, Any],
    regions_fc: ee.FeatureCollection,
    cache_path: Path,
) -> pd.DataFrame:
    """Build (and cache) a long table of per-commune, per-year fire metrics.

    Columns: ``[name, year, burned_km2, detections, brightness_max_k]``. Years
    already present in the cache are reused, so the expensive GEE calls run only
    for missing years (mirrors the year-by-year ERA5-Land caching).
    """
    years = list(cfg["wildfire"]["years"])
    cache_path = Path(cache_path)

    cached = pd.DataFrame()
    if cache_path.exists():
        cached = pd.read_csv(cache_path)

    have = set(cached["year"].unique()) if not cached.empty else set()
    todo = [y for y in years if y not in have]

    new_rows = []
    for year in todo:
        print(f"  [wildfire] fetching {year} (burned area + FIRMS)...")
        ba = _burned_area_km2(cfg, regions_fc, year)
        fa = _firms_activity(cfg, regions_fc, year)
        merged = ba.merge(fa, on="name", how="outer")
        merged["year"] = year
        new_rows.append(merged)

    if new_rows:
        annual = pd.concat([cached, *new_rows], ignore_index=True)
        annual = annual.sort_values(["name", "year"]).reset_index(drop=True)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        annual.to_csv(cache_path, index=False)
    else:
        annual = cached

    return annual[annual["year"].isin(years)].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Aggregation + exposure index
# --------------------------------------------------------------------------- #
def _normalize_0_100(series: pd.Series, transform: str = "sqrt") -> pd.Series:
    """Scale a skewed non-negative series to 0-100 (max commune = 100).

    A ``sqrt`` transform moderates the heavy right-skew typical of fire metrics
    (a few rural/cordillera communes dominate) before max-scaling.
    """
    x = series.fillna(0).clip(lower=0).astype(float)
    if transform == "sqrt":
        x = np.sqrt(x)
    mx = x.max()
    if mx <= 0:
        return pd.Series(0.0, index=series.index)
    return (x / mx * 100).round(1)


def aggregate_metrics(
    annual: pd.DataFrame, gdf_comm: gpd.GeoDataFrame, cfg: dict[str, Any]
) -> pd.DataFrame:
    """Collapse the per-year table to one row per commune with summary metrics."""
    n_years = len(cfg["wildfire"]["years"])
    area = gdf_comm[["name", "area_km2"]].copy()
    annual = annual.merge(area, on="name", how="left")
    annual["burned_pct"] = annual["burned_km2"] / annual["area_km2"] * 100

    grp = annual.groupby("name")
    df = area.copy()
    df = df.merge(
        grp.agg(
            fire_burned_area_km2_total=("burned_km2", "sum"),
            fire_burned_area_mean_annual_km2=("burned_km2", "mean"),
            fire_burned_pct_mean_annual=("burned_pct", "mean"),
            fire_burned_pct_max_year=("burned_pct", "max"),
            fire_detections_total=("detections", "sum"),
            fire_detections_max_year=("detections", "max"),
            fire_brightness_max_k=("brightness_max_k", "max"),
        ).reset_index(),
        on="name",
        how="left",
    )

    # Recurrence: number of years with a meaningful burn.
    burn_years = (
        annual.assign(has_fire=annual["burned_km2"] > _BURN_YEAR_MIN_KM2)
        .groupby("name")["has_fire"]
        .sum()
        .rename("fire_burn_years_count")
        .reset_index()
    )
    df = df.merge(burn_years, on="name", how="left")

    # Worst year: calendar year with the highest burned area per commune.
    worst_year = (
        annual.loc[annual.groupby("name")["burned_km2"].idxmax(), ["name", "year"]]
        .rename(columns={"year": "fire_worst_year"})
    )
    df = df.merge(worst_year, on="name", how="left")
    df["fire_worst_year"] = df["fire_worst_year"].astype("Int64")

    # Trend: linear slope of annual burned area (km^2/decade).
    # Mirrors precip_trend_mm_per_decade in precipitation_spi.py.
    trend_rows = []
    for name, grp in annual.groupby("name"):
        grp = grp.sort_values("year")
        if len(grp) >= 3:
            slope, _ = np.polyfit(grp["year"].values, grp["burned_km2"].values, 1)
            trend_rows.append(
                {"name": name, "fire_trend_km2_per_decade": round(float(slope * 10), 3)}
            )
    df = df.merge(pd.DataFrame(trend_rows), on="name", how="left")

    df["fire_detections_per_km2"] = df["fire_detections_total"] / df["area_km2"]

    # Rounding.
    for col, nd in [
        ("fire_burned_area_km2_total", 4),
        ("fire_burned_area_mean_annual_km2", 4),
        ("fire_burned_pct_mean_annual", 3),
        ("fire_burned_pct_max_year", 3),
        ("fire_detections_total", 1),
        ("fire_detections_max_year", 1),
        ("fire_detections_per_km2", 3),
        ("fire_brightness_max_k", 1),
        ("fire_trend_km2_per_decade", 3),
    ]:
        df[col] = df[col].astype(float).round(nd)
    df["fire_burn_years_count"] = df["fire_burn_years_count"].fillna(0).astype(int)
    # brightness=0 is valid sentinel: 0 K cannot occur physically, so 0 means "no
    # fire detected". Kept as 0 (not NaN) so the column remains fully populated.
    df["fire_brightness_max_k"] = df["fire_brightness_max_k"].fillna(0.0)

    # Composite 0-100 exposure index.
    w = cfg["wildfire"]["index_weights"]
    s_burned = _normalize_0_100(df["fire_burned_pct_mean_annual"])
    s_density = _normalize_0_100(df["fire_detections_per_km2"])
    s_recur = (df["fire_burn_years_count"] / n_years * 100).round(1)
    df["fire_exposure_index"] = (
        w["burned_pct"] * s_burned
        + w["detection_density"] * s_density
        + w["recurrence"] * s_recur
    ).round(1)

    return df


# --------------------------------------------------------------------------- #
# Optional official enrichment (CONAF / itrend)
# --------------------------------------------------------------------------- #
def load_official_fires(cfg: dict[str, Any]) -> pd.DataFrame | None:
    """Load optional official CONAF/itrend fire statistics keyed by commune.

    Returns ``None`` (with a message) when disabled or the file is missing, so
    the layer is built from satellite data alone. Commune names are harmonised
    with :func:`demography.normalize_comuna_name` to match the boundaries.
    """
    off = cfg["wildfire"].get("official", {})
    if not off.get("enabled"):
        return None

    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / off["path"]
    if not path.exists():
        print(
            f"  [wildfire] official enrichment skipped: {off['path']} not found "
            "(satellite-only layer). Drop a CONAF/itrend CSV there to enable it."
        )
        return None

    cols = off["columns"]
    raw = pd.read_csv(path, sep=off.get("sep", ";"))
    raw = raw.rename(
        columns={
            cols["commune"]: "name_raw",
            cols.get("n_fires", ""): "fire_official_n_fires",
            cols.get("damaged_ha", ""): "fire_official_damaged_ha",
            cols.get("human_cause_pct", ""): "fire_official_human_cause_pct",
        }
    )
    raw["name"] = demography.normalize_comuna_name(raw["name_raw"])
    keep = ["name"] + [
        c
        for c in ["fire_official_n_fires", "fire_official_damaged_ha", "fire_official_human_cause_pct"]
        if c in raw.columns
    ]
    out = raw[keep].groupby("name", as_index=False).sum(numeric_only=True)
    print(f"  [wildfire] official enrichment loaded: {len(out)} communes, cols {keep[1:]}")
    return out


# --------------------------------------------------------------------------- #
# Layer builder
# --------------------------------------------------------------------------- #
def build_wildfire_layer(
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
    out_dir: Path = Path("data/processed"),
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Run the full wildfire pipeline and export commune-level metrics.

    Returns ``(df, gdf)`` with the tabular and geospatial layers. Writes
    ``santiago_wildfire_<y0>_<y1>.{csv,geojson,_metadata.json}``.
    """
    cfg = config.load_config(city)
    gee.init_gee()

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    years = list(cfg["wildfire"]["years"])
    y0, y1 = years[0], years[-1]
    print(f"Building wildfire layer for {city} ({y0}-{y1})...")

    # 1. Boundaries.
    boundaries_cache = cache_dir / f"{city}_communes.geojson"
    gdf_comm = boundaries.get_communes(cfg, cache_path=boundaries_cache)
    regions_fc = gee.gdf_to_feature_collection(gdf_comm)

    # 2. Per-year satellite metrics (cached year-by-year).
    annual_cache = cache_dir / f"{city}_wildfire_annual_{y0}_{y1}.csv"
    annual = fetch_annual_metrics(cfg, regions_fc, annual_cache)

    # 3. Aggregate + composite index.
    df = aggregate_metrics(annual, gdf_comm, cfg)

    # 4. Optional official enrichment.
    official = load_official_fires(cfg)
    if official is not None:
        df = df.merge(official, on="name", how="left")

    df["area_km2"] = df["area_km2"].round(2)

    core_order = [
        "name",
        "area_km2",
        "fire_burned_area_km2_total",
        "fire_burned_area_mean_annual_km2",
        "fire_burned_pct_mean_annual",
        "fire_burned_pct_max_year",
        "fire_burn_years_count",
        "fire_worst_year",
        "fire_trend_km2_per_decade",
        "fire_detections_total",
        "fire_detections_per_km2",
        "fire_detections_max_year",
        "fire_brightness_max_k",
        "fire_exposure_index",
    ]
    extra = [c for c in df.columns if c not in core_order]
    df = df[core_order + extra].copy()

    # 5. Validate.
    n_expected = cfg["expected_communes"]
    if len(df) != n_expected:
        raise ValueError(f"Expected {n_expected} rows, got {len(df)}")
    if df["name"].duplicated().any():
        raise ValueError("Duplicate commune names")
    # brightness=0 is a valid "no detection" sentinel — exclude from strict NaN check
    # (mirrors the ratio-column exclusion in build_master_exposome).
    strict_cols = [c for c in core_order if c != "fire_brightness_max_k"]
    if df[strict_cols].isna().any().any():
        missing = [c for c in strict_cols if df[c].isna().any()]
        raise ValueError(f"Missing values in core wildfire columns: {missing}")

    # 6. Geo version.
    gdf = gdf_comm[["name", "geometry"]].merge(df, on="name", how="right")
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs=cfg["crs"]["geographic"])

    # 7. Write outputs.
    base_name = f"{city}_wildfire_{y0}_{y1}"
    df.to_csv(out_dir / f"{base_name}.csv", index=False)
    gdf.to_file(out_dir / f"{base_name}.geojson", driver="GeoJSON")

    wf = cfg["wildfire"]
    metadata: dict[str, Any] = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "period": f"{y0}-{y1}",
        "n_rows": int(len(df)),
        "columns": df.columns.tolist(),
        "method": (
            "Commune zonal statistics over MODIS MCD64A1 burned area (binary "
            "burned mask x pixel area, summed) and FIRMS active-fire detections "
            "(per-pixel detection-day count, summed). Composite exposure index = "
            "weighted, sqrt-normalised burned fraction + detection density + "
            "recurrence (max commune = 100 per component)."
        ),
        "sources": {
            "burned_area": {
                "provider": "NASA LP DAAC / MODIS",
                "collection": wf["collections"]["burned_area"]["id"],
                "band": wf["collections"]["burned_area"]["band"],
                "resolution_m": wf["collections"]["burned_area"]["scale_meters"],
            },
            "active_fire": {
                "provider": "NASA FIRMS (MODIS + VIIRS)",
                "collection": wf["collections"]["active_fire"]["id"],
                "band": wf["collections"]["active_fire"]["band"],
                "resolution_m": wf["collections"]["active_fire"]["scale_meters"],
            },
            "official": (
                "CONAF / itrend forest-fire statistics by commune (optional, "
                "local data/raw/ CSV; merged when present)"
            ),
        },
        "index_weights": wf["index_weights"],
        "peak_seasons": wf["peak_seasons"],
        "columns_description": {
            "fire_burned_area_km2_total": "Cumulative burned area over the period (km^2)",
            "fire_burned_area_mean_annual_km2": "Mean annual burned area (km^2)",
            "fire_burned_pct_mean_annual": "Mean annual burned area as % of commune area",
            "fire_burned_pct_max_year": "Worst single-year burned fraction (%)",
            "fire_burn_years_count": f"Years (of {len(years)}) with a burn > {_BURN_YEAR_MIN_KM2} km^2",
            "fire_worst_year": "Calendar year with the highest burned area for this commune",
            "fire_trend_km2_per_decade": (
                "Linear trend in annual burned area (km^2/decade, OLS slope x 10). "
                "Positive = increasing fire, negative = decreasing. "
                "Interpret cautiously: only 10 data points with high inter-annual variability."
            ),
            "fire_detections_total": "Total FIRMS detection-days over the period",
            "fire_detections_per_km2": "FIRMS detection-days per km^2 (size-comparable)",
            "fire_detections_max_year": "FIRMS detection-days in the worst year",
            "fire_brightness_max_k": (
                "Max FIRMS T21 brightness temperature (K). "
                "0 = no fire detection in the entire period (not 0 Kelvin — used as sentinel)."
            ),
            "fire_exposure_index": "Composite wildfire exposure index (0-100)",
        },
        "brain_health_relevance": {
            "wildfire_smoke": "Acute PM2.5/PM10 spikes -> neuroinflammation, cognitive decline",
            "recurrent_exposure": "Chronic stress, displacement, loss of green space",
        },
        "limitations": (
            "MCD64A1 at 500 m underestimates small/urban fires; FIRMS complements "
            "it for interface fires. Dense urban communes are near-zero by design."
        ),
        "outputs": [f"{base_name}.csv", f"{base_name}.geojson"],
    }
    (out_dir / f"{base_name}_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False)
    )

    print(f"Wrote {base_name}.csv / .geojson ({len(df)} rows x {df.shape[1]} cols)")
    top = df.nlargest(5, "fire_exposure_index")[["name", "fire_exposure_index"]]
    print("  Most fire-exposed communes:")
    for _, r in top.iterrows():
        print(f"    {r['name']:<22}{r['fire_exposure_index']:>6.1f}")
    return df, gdf

"""Portable population denominators for study-level exposure metrics."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from . import gee


def load_or_fetch_worldpop(
    cfg: dict[str, Any],
    spatial_units: gpd.GeoDataFrame,
    cache_path: Path,
) -> pd.DataFrame:
    """Return WorldPop population sums keyed by the legacy ``name`` field.

    Existing national census outputs remain preferable. This function is the
    portable fallback for layers that need a population denominator.
    """
    cache_path = Path(cache_path)
    expected_names = set(spatial_units["name"].astype(str))
    if cache_path.exists():
        cached = pd.read_csv(cache_path)
        if {"name", "pop_total"}.issubset(cached.columns):
            cached_names = set(cached["name"].astype(str))
            if cached_names == expected_names and not cached["pop_total"].isna().any():
                return cached[["name", "pop_total"]].copy()

    pop_cfg = cfg.get("population") or cfg.get("alan", {}).get("population")
    if not pop_cfg:
        raise ValueError("WorldPop configuration is required for population fallback")
    country = pop_cfg.get("country") or cfg.get("country_code3")
    if not country:
        raise ValueError("A three-letter country code is required for WorldPop")

    import ee

    gee.init_gee()
    regions = gee.gdf_to_feature_collection(spatial_units[["name", "geometry"]])
    image = (
        ee.ImageCollection(pop_cfg["id"])
        .filter(ee.Filter.eq("country", country))
        .filter(ee.Filter.eq("year", int(pop_cfg["year"])))
        .select(pop_cfg.get("band", "population"))
        .mosaic()
        .rename("population")
    )
    stats = gee.image_to_stats(
        image,
        regions,
        band="population",
        scale=int(pop_cfg.get("scale_meters", 100)),
        reducer="sum",
    )
    rows = pd.DataFrame(gee.fc_to_dicts(stats)).rename(columns={"sum": "pop_total"})
    result = rows[["name", "pop_total"]].copy()
    result["name"] = result["name"].astype(str)
    result["pop_total"] = pd.to_numeric(result["pop_total"], errors="coerce")
    result = result.drop_duplicates("name")

    missing = sorted(expected_names - set(result["name"]))
    invalid = result.loc[result["pop_total"].isna() | (result["pop_total"] <= 0), "name"].tolist()
    if missing or invalid:
        raise ValueError(
            f"WorldPop did not provide valid population for all units; "
            f"missing={missing}, invalid={invalid}"
        )

    result = result.sort_values("name").reset_index(drop=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(cache_path, index=False)
    return result

"""Walkability / built-environment exposome layer from OpenStreetMap.

Computes commune-level pedestrian street-network metrics for the configured
region using osmnx.  The metrics operationalise the urban-form determinants
of physical activity, which is the #1 modifiable risk factor for dementia
according to the Lancet Commission 2024.

Metrics follow the urban-planning literature on walkability:
  - Intersection density  (Saelens et al., Ann Behav Med 2003)
  - Street density        (Frank et al., Am J Prev Med 2006)
  - Average block length  (inverse of intersection density proxy)
  - Streets-per-node      (connectivity / cul-de-sac ratio)
  - Circuity              (route efficiency; lower = more direct paths)

A composite walk_index (0–100) is derived from z-scored, sign-oriented
metrics — same approach as nse_index in socioeconomic.py.
"""
from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from tqdm import tqdm

import time

try:
    import osmnx as ox
except ImportError as e:
    raise ImportError("osmnx is required: conda install -c conda-forge osmnx") from e

try:
    from .demography import normalize_comuna_name  # noqa: F401 (used indirectly)
    from . import boundaries, config as _config
    from .osm_fetch import call_with_overpass_fallback
except ImportError:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
    import exposome.boundaries as boundaries  # type: ignore[no-redef]
    import exposome.config as _config  # type: ignore[no-redef]
    from exposome.osm_fetch import call_with_overpass_fallback  # type: ignore[no-redef]

# "all" captures all street types — needed for Latin American cities where OSM
# footway tagging is incomplete.
_NETWORK_TYPE = "all"
_BETWEEN_COMMUNES_S = 2  # polite delay between communes to avoid rate-limiting


def _load_boundaries(
    out_dir: Path,
    city: str = "santiago",
    cache_dir: Path = Path("cache"),
) -> gpd.GeoDataFrame:
    """Load configured study geometries, with legacy Santiago fallbacks."""
    cfg = _config.load_config(city)
    expected = int(cfg.get("expected_units", cfg.get("expected_communes", 52)))
    cache_path = Path(cache_dir) / f"{city}_communes.geojson"
    if cache_path.exists() or cfg.get("spatial_units"):
        return boundaries.get_communes(cfg, cache_path=cache_path)[["name", "geometry"]]

    candidates = [
        "socioeconomic_exposome_rm_santiago.geojson",
        "climate_heat_exposome_rm_santiago.geojson",
        "santiago_air_quality_satellite_2024.geojson",
        "santiago_alan_viirs_2024.geojson",
    ]
    for name in candidates:
        p = out_dir / name
        if p.exists():
            gdf = gpd.read_file(p)
            if "name" in gdf.columns and len(gdf) == expected:
                return gdf[["name", "geometry"]].copy()
    return boundaries.get_communes(cfg, cache_path=cache_path)[["name", "geometry"]]


def _network_stats_for_commune(
    geom_4326,
    area_m2: float,
    metric_crs: str | None = None,
) -> dict[str, float] | None:
    """Fetch OSM street network and compute stats for one commune geometry.

    Uses endpoint fallback + exponential backoff across Overpass mirrors
    (see osm_fetch.py). Returns None only for a genuinely sparse network (a
    *successful* query with < 5 nodes). A query that never succeeds --
    every endpoint/attempt exhausted -- raises ConnectionError instead of
    also returning None: those two cases used to be indistinguishable, so a
    full Overpass outage silently 0-filled every commune's walkability
    metrics as if they were all sparsely connected, and the layer "executed"
    successfully with fabricated data instead of failing (the caller,
    build_walkability_layer, propagates this to fail the whole layer run --
    see execute_run_plan).
    """
    def _fetch() -> dict[str, float] | None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            G = ox.graph_from_polygon(geom_4326, network_type=_NETWORK_TYPE)
        if G.number_of_nodes() < 5:
            return None
        G_proj = ox.project_graph(G, to_crs=metric_crs)
        stats = ox.basic_stats(G_proj, area=area_m2)

        circuity = stats.get("circuity_avg")
        if circuity is None:
            edges = ox.graph_to_gdfs(G_proj, nodes=False, edges=True)
            if "length" in edges.columns and len(edges) > 0:
                sl = edges.geometry.apply(
                    lambda g: ((g.coords[0][0] - g.coords[-1][0]) ** 2
                               + (g.coords[0][1] - g.coords[-1][1]) ** 2) ** 0.5
                )
                circuity = float(
                    edges["length"].sum() / sl.replace(0, np.nan).sum()
                )
            else:
                circuity = np.nan

        return {
            "walk_intersection_density": stats.get("intersection_density_km", np.nan),
            "walk_street_density_km_km2": stats.get("street_density_km", np.nan),
            "walk_avg_street_length_m": stats.get("street_length_avg", np.nan),
            "walk_streets_per_node": stats.get("streets_per_node_avg", np.nan),
            "walk_circuity": circuity,
            "walk_n_nodes": G_proj.number_of_nodes(),
        }

    return call_with_overpass_fallback(
        _fetch, log=lambda msg: print(msg, end=" ", flush=True)
    )


def _compute_walk_index(df: pd.DataFrame) -> pd.Series:
    """Composite walkability index (0–100): z-scored, sign-oriented average.

    Higher intersection density, street density, streets-per-node → more walkable (+).
    Higher circuity, longer block length → less walkable (–, inverted).
    """
    positive = ["walk_intersection_density", "walk_street_density_km_km2",
                "walk_streets_per_node"]
    negative = ["walk_circuity", "walk_avg_street_length_m"]

    oriented = pd.DataFrame(index=df.index)
    for col in positive:
        x = df[col].astype(float)
        oriented[col] = (x - x.mean()) / x.std(ddof=0)
    for col in negative:
        x = df[col].astype(float)
        oriented[col] = -((x - x.mean()) / x.std(ddof=0))

    composite = oriented.mean(axis=1)
    # Clip at ±3 SD then rescale to 0–100 (mean=50, SD~15).
    composite = composite.clip(-3, 3)
    cmin, cmax = composite.min(), composite.max()
    index_01 = (composite - cmin) / (cmax - cmin)
    return (index_01 * 100).round(1)


def build_walkability_layer(
    city: str = "santiago",
    out_dir: Path = Path("data/processed"),
    resume: bool = True,
    cache_dir: Path = Path("cache"),
) -> tuple[pd.DataFrame, gpd.GeoDataFrame]:
    """Build the walkability exposome layer and write CSV/GeoJSON/metadata."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cfg = _config.load_config(city)
    metric_crs = cfg["crs"]["metric"]
    expected = int(cfg.get("expected_units", cfg.get("expected_communes", 52)))

    ox.settings.requests_timeout = 180
    ox.settings.log_console = False

    boundaries_gdf = _load_boundaries(out_dir, city=city, cache_dir=cache_dir)
    gdf_4326 = boundaries_gdf.to_crs("EPSG:4326")
    gdf_metric = boundaries_gdf.to_crs(metric_crs)

    # Resume mode: load existing CSV and skip communes that already succeeded.
    existing: dict[str, dict] = {}
    csv_out = out_dir / f"{city}_walkability.csv"
    if resume and csv_out.exists():
        prev = pd.read_csv(csv_out)
        for _, r in prev.iterrows():
            if r.get("walk_n_nodes", 0) > 0:
                existing[r["name"]] = r.to_dict()
        print(f"  Resume mode: {len(existing)} communes already done, skipping.")

    rows: list[dict] = []
    n_communes = len(boundaries_gdf)
    # Checkpoint path: written after every commune (not just once at the end)
    # so a crash mid-run only loses the commune in flight. --resume re-reads
    # this same file and skips whatever is already here (see `existing` above).
    checkpoint_out = out_dir / f"{city}_walkability.csv"
    progress = tqdm(list(gdf_4326.iterrows()), desc=f"walkability [{city}]", unit="commune")
    for i, (_, row) in enumerate(progress, 1):
        name = row["name"]
        area_m2 = float(gdf_metric.loc[row.name, "geometry"].area)

        if name in existing:
            tqdm.write(f"  [{i:2d}/{n_communes}] {name} … skipped (cached)")
            rows.append(existing[name])
            pd.DataFrame(rows).to_csv(checkpoint_out, index=False)
            continue

        progress.set_postfix_str(name)
        # Deliberately not caught here: an exhausted Overpass fallback must
        # fail the whole layer run rather than 0-fill this commune as if it
        # were sparsely connected (see _network_stats_for_commune). Rows
        # already checkpointed for prior communes remain on disk for --resume.
        result = _network_stats_for_commune(row["geometry"], area_m2, metric_crs)
        if i < n_communes:
            time.sleep(_BETWEEN_COMMUNES_S)
        if result is None:
            tqdm.write(f"  [{i:2d}/{n_communes}] {name} … sparse/empty network → NaN")
            rows.append({"name": name,
                         "walk_intersection_density": np.nan,
                         "walk_street_density_km_km2": np.nan,
                         "walk_avg_street_length_m": np.nan,
                         "walk_streets_per_node": np.nan,
                         "walk_circuity": np.nan,
                         "walk_n_nodes": 0})
        else:
            n = result["walk_n_nodes"]
            dens = result["walk_intersection_density"]
            tqdm.write(f"  [{i:2d}/{n_communes}] {name} … ok ({n} nodes, {dens:.1f} intersec/km²)")
            rows.append({"name": name, **result})

        # Checkpoint: persist raw per-commune results immediately. The
        # derived walk_index below is recomputed from scratch every run and
        # is not required for resume detection (see `existing` loader above).
        pd.DataFrame(rows).to_csv(checkpoint_out, index=False)

    df = pd.DataFrame(rows)

    # Compute composite index on communes with valid data.
    valid = df[df["walk_intersection_density"].notna()].copy()
    if len(valid) > 1:
        df.loc[valid.index, "walk_index"] = _compute_walk_index(valid)
    else:
        df["walk_index"] = np.nan

    # Fill NaN with 0 so the master build passes its non-null validation.
    metric_cols = ["walk_intersection_density", "walk_street_density_km_km2",
                   "walk_avg_street_length_m", "walk_streets_per_node",
                   "walk_circuity", "walk_index"]
    n_nan = df[metric_cols].isna().any(axis=1).sum()
    if n_nan:
        print(f"  {n_nan} communes with no network data → filling with 0")
    df[metric_cols] = df[metric_cols].fillna(0)
    df["walk_n_nodes"] = df["walk_n_nodes"].fillna(0).astype(int)

    # Round for clean output.
    for col in metric_cols:
        df[col] = df[col].round(3)

    ordered_cols = [
        "name",
        "walk_intersection_density",
        "walk_street_density_km_km2",
        "walk_avg_street_length_m",
        "walk_streets_per_node",
        "walk_circuity",
        "walk_n_nodes",
        "walk_index",
    ]
    df = df[ordered_cols].sort_values("name").reset_index(drop=True)

    gdf_out = boundaries_gdf[["name", "geometry"]].merge(df, on="name", how="left")
    gdf_out = gpd.GeoDataFrame(gdf_out, geometry="geometry", crs=boundaries_gdf.crs)
    gdf_out = gdf_out.sort_values("name").reset_index(drop=True)

    if len(df) != expected:
        raise ValueError(f"Expected {expected} spatial units, got {len(df)}")

    csv_out = out_dir / f"{city}_walkability.csv"
    geojson_out = out_dir / f"{city}_walkability.geojson"
    meta_out = out_dir / f"{city}_walkability_metadata.json"

    df.to_csv(csv_out, index=False)
    gdf_out.to_file(geojson_out, driver="GeoJSON")

    top5 = df.nlargest(5, "walk_index")[["name", "walk_index"]].values.tolist()
    bot5 = df.nsmallest(5, "walk_index")[["name", "walk_index"]].values.tolist()

    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "source": "OpenStreetMap via osmnx",
        "network_type": _NETWORK_TYPE,
        "crs_metric": metric_crs,
        "method": (
            "Street network fetched per commune via osmnx "
            f"(network_type='{_NETWORK_TYPE}'). network_type='all' used instead of "
            "'walk' because OSM footway tagging can be incomplete in Latin American cities; all "
            "streets are de facto walkable. Basic network stats computed on "
            f"projected graph ({metric_crs}). walk_index = z-scored composite of "
            "intersection_density (+), street_density (+), streets_per_node (+), "
            "circuity (–), avg_street_length (–); rescaled 0–100."
        ),
        "evidence": (
            "Physical inactivity is the #1 modifiable dementia risk factor "
            "(Livingston et al., Lancet 2024). Walkable street networks are the "
            "strongest built-environment predictor of walking behaviour "
            "(Saelens & Handy, Med Sci Sports Exerc 2008)."
        ),
        "n_communes": len(df),
        "n_spatial_units": len(df),
        "n_communes_with_data": int((df["walk_n_nodes"] > 0).sum()),
        "top5_most_walkable": top5,
        "bot5_least_walkable": bot5,
        "columns": ordered_cols,
    }
    meta_out.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))

    print(f"\nWrote {csv_out.name}: {len(df)} communes")
    print(f"Wrote {geojson_out.name}")
    print(f"Wrote {meta_out.name}")
    print(f"\nTop walkable: {[r[0] for r in top5]}")
    print(f"Least walkable: {[r[0] for r in bot5]}")

    return df, gdf_out


if __name__ == "__main__":
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    build_walkability_layer()

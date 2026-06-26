"""Compare DEIS official registry and OpenStreetMap healthcare coverage.

Produces two CSV reports:
- ``healthcare_source_comparison_by_commune.csv`` : counts per source and
  differences by commune.
- ``healthcare_unmatched_facilities.csv`` : individual DEIS/OSM facilities
  that have no counterpart within the configured buffer distance.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import numpy as np
import pandas as pd
import typer  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

from exposome import boundaries, config  # noqa: E402
from exposome.healthcare import classify_facilities, fetch_healthcare_osm  # noqa: E402
from exposome.healthcare_official import prepare_official_facilities  # noqa: E402

app = typer.Typer(help="Compare DEIS and OSM healthcare sources.")


def _count_by_commune(
    gdf_facilities,
    gdf_communes,
    metric_crs: str,
    prefix: str,
) -> pd.DataFrame:
    """Spatially join facilities to communes and count total + categories."""
    communes_metric = gdf_communes.to_crs(metric_crs)[["name", "geometry"]].rename(
        columns={"name": "commune_name"}
    )
    pts_metric = gdf_facilities.to_crs(metric_crs)
    joined = pts_metric.sjoin(communes_metric, how="inner", predicate="within")

    cats = [c for c in gdf_facilities.columns if c.startswith("is_")]
    agg: dict[str, tuple[str, str]] = {f"{prefix}_n_total": ("geometry", "size")}
    for cat in cats:
        agg[f"{prefix}_{cat}"] = (cat, "sum")

    counts = joined.groupby("commune_name").agg(**agg).reset_index()
    counts = counts.rename(columns={"commune_name": "name"})
    int_cols = [c for c in counts.columns if c != "name"]
    counts[int_cols] = counts[int_cols].fillna(0).astype(int)
    return counts


def _find_unmatched(
    gdf_a,
    gdf_b,
    buffer_m: float,
    metric_crs: str,
    source_label: str,
    missing_label: str,
    gdf_communes=None,
) -> pd.DataFrame:
    """Return rows from ``gdf_a`` with no counterpart in ``gdf_b`` within buffer."""
    if gdf_a.empty:
        return pd.DataFrame()

    a_metric = gdf_a.to_crs(metric_crs)

    if gdf_b.empty:
        unmatched = gdf_a.copy()
    else:
        b_metric = gdf_b.to_crs(metric_crs)
        b_coords = np.vstack([b_metric.geometry.x, b_metric.geometry.y]).T
        tree = cKDTree(b_coords)
        a_coords = np.vstack([a_metric.geometry.x, a_metric.geometry.y]).T
        dists, _ = tree.query(a_coords, k=1)
        unmatched = gdf_a[dists > buffer_m].copy()

    if unmatched.empty:
        return pd.DataFrame()

    unmatched["source"] = source_label
    unmatched["matched_in"] = missing_label
    unmatched["lon"] = unmatched.geometry.x
    unmatched["lat"] = unmatched.geometry.y

    cols = ["source", "matched_in", "name", "official_type", "commune", "lon", "lat"]
    for c in cols:
        if c not in unmatched.columns:
            unmatched[c] = ""

    # Add commune name via spatial join if boundaries are provided.
    if gdf_communes is not None and not unmatched.empty:
        communes_metric = gdf_communes.to_crs(metric_crs)[["name", "geometry"]].rename(
            columns={"name": "commune_matched"}
        )
        unmatched_metric = unmatched.to_crs(metric_crs)
        unmatched_metric = unmatched_metric.drop(
            columns=[c for c in unmatched_metric.columns if c == "commune"], errors="ignore"
        )
        unmatched_with_commune = unmatched_metric.sjoin(
            communes_metric, how="left", predicate="within"
        )
        unmatched["commune"] = unmatched_with_commune["commune_matched"].values

    return unmatched[cols].copy()


@app.command()
def run(
    city: str = typer.Option("santiago", help="City config name"),
    cache_dir: Path = typer.Option(Path("cache"), help="Cache directory"),
    out_dir: Path = typer.Option(Path("data/processed"), help="Output directory"),
    buffer_m: float = typer.Option(150.0, help="Conflation buffer in metres"),
) -> None:
    """Generate DEIS vs OSM comparison tables."""
    cfg = config.load_config(city)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metric_crs = cfg["crs"]["metric"]
    geo_crs = cfg["crs"]["geographic"]

    # Load commune boundaries.
    communes_cache = cache_dir / f"{city}_communes.geojson"
    gdf_communes = boundaries.get_communes(cfg, cache_path=communes_cache)

    # Load both sources independently (no conflation).
    print("Loading official DEIS facilities...")
    gdf_official = prepare_official_facilities(cfg, cache_dir)
    print(f"  Official: {len(gdf_official)} facilities")

    print("Loading OSM facilities...")
    osm_cache = cache_dir / f"{city}_healthcare_osm.geojson"
    gdf_osm = classify_facilities(fetch_healthcare_osm(cfg, cache_path=osm_cache), cfg)
    print(f"  OSM: {len(gdf_osm)} facilities")

    # Counts by commune.
    official_counts = _count_by_commune(gdf_official, gdf_communes, metric_crs, "deis")
    osm_counts = _count_by_commune(gdf_osm, gdf_communes, metric_crs, "osm")

    comparison = gdf_communes[["name"]].merge(
        official_counts, on="name", how="left"
    ).merge(
        osm_counts, on="name", how="left", suffixes=("", "_osm")
    )

    numeric_cols = [c for c in comparison.columns if c != "name"]
    comparison[numeric_cols] = comparison[numeric_cols].fillna(0).astype(int)

    # Difference columns.
    if "deis_n_total" in comparison.columns and "osm_n_total" in comparison.columns:
        comparison["diff_n_total"] = (
            comparison["deis_n_total"] - comparison["osm_n_total"]
        )

    # Unmatched facilities.
    unmatched_deis = _find_unmatched(
        gdf_official, gdf_osm, buffer_m, metric_crs, "deis", "osm", gdf_communes
    )
    unmatched_osm = _find_unmatched(
        gdf_osm, gdf_official, buffer_m, metric_crs, "osm", "deis", gdf_communes
    )
    unmatched = pd.concat([unmatched_deis, unmatched_osm], ignore_index=True)

    # Write outputs.
    comparison_path = out_dir / "healthcare_source_comparison_by_commune.csv"
    unmatched_path = out_dir / "healthcare_unmatched_facilities.csv"

    comparison.to_csv(comparison_path, index=False)
    unmatched.to_csv(unmatched_path, index=False)

    print(f"\nWrote {comparison_path.name} ({len(comparison)} communes)")
    print(f"Wrote {unmatched_path.name} ({len(unmatched)} unmatched facilities)")
    print(
        f"  DEIS without OSM match: {len(unmatched_deis)} | "
        f"OSM without DEIS match: {len(unmatched_osm)}"
    )


if __name__ == "__main__":
    app()

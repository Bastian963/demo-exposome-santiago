"""Commune clustering with K-means over canonical exposome features.

Reads `data/processed/santiago_exposome_master.csv` and applies
K-means to standardise a curated set of 6 features (one per pillar)
to produce 4-5 **discrete typologies** of communes:

Outputs
-------
1. `data/processed/commune_clusters.csv`
   Columns: name, cluster_id, cluster_label, cluster_size, silhouette.
2. `figures/commune_clusters_map.png`
   Choropleth of cluster assignments + side table with top-3 communes
   per cluster (sorted by EBI score).
3. Update `data/processed/cross_layer_summary.json` with
   `cluster_assignments` block (re-run analyze_cross_layer.py to
   propagate the cluster table into the summary).

The number of clusters is selected automatically by maximising the
silhouette score over k ∈ [3, 6]. If the maximum silhouette is
below 0.20, we fall back to k=4 (more stable, fewer singletons).

Features
--------
The 6 features span the main exposome pillars:
- pm25_mean           (air)
- nse_index           (socioeconomic; sign-flipped to "deprivation")
- green_cover_pct_ndvi (greenspace; sign-flipped to "low green")
- walk_index          (walkability)
- urban_heat_anomaly_c (heat)
- health_n_primary_care (healthcare density; sign-flipped)

Each feature is standardised (zero mean, unit variance) before
clustering so that no single pillar dominates the distance metric.

Usage
-----
    python scripts/cluster_communes.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "processed"
FIGURES_DIR = REPO_ROOT / "figures"

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "font.family": "STIXGeneral",
        "mathtext.fontset": "stix",
        "axes.titlesize": 10.5,
        "axes.labelsize": 9.5,
    }
)

# (column, sign): +1 = higher value = higher burden, -1 = flip sign
# so that high values always = high burden before scaling.
CLUSTER_FEATURES: list[tuple[str, int]] = [
    ("pm25_mean", +1),
    ("nse_index", -1),
    ("green_cover_pct_ndvi", -1),
    ("walk_index", +1),
    ("urban_heat_anomaly_c", +1),
    ("health_n_primary_care", -1),
]

K_MIN = 3
K_MAX = 5
SILHOUETTE_FLOOR = 0.20
FALLBACK_K = 4
RANDOM_STATE = 42

CLUSTER_PALETTE = ["#d7191c", "#fdae61", "#abd9e9", "#2c7bb6", "#1a9641"]


def _load_master() -> pd.DataFrame:
    csv = DATA_DIR / "santiago_exposome_master.csv"
    if not csv.exists():
        raise FileNotFoundError(
            f"Master CSV not found: {csv}. "
            "Run scripts/build_master_exposome.py first."
        )
    return pd.read_csv(csv)


def _select_k(features: np.ndarray) -> tuple[int, dict[int, float]]:
    """Return best k (max silhouette) and dict of {k: silhouette}."""
    scores: dict[int, float] = {}
    for k in range(K_MIN, K_MAX + 1):
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10)
        labels = km.fit_predict(features)
        scores[k] = float(silhouette_score(features, labels))
    best_k = max(scores, key=scores.get)
    return best_k, scores


def _label_clusters(
    df: pd.DataFrame, cluster_col: str = "cluster_id",
) -> dict[int, str]:
    """Assign a semantic label to each cluster based on centroids.

    Uses a **rank-based** rule system (rank of each cluster's mean
    on each feature, 1=lowest, k=highest) so that the labels are
    robust to outliers and to the absolute scale of the features.
    """
    means = df.groupby(cluster_col).agg({
        "nse_index": "mean",
        "pm25_mean": "mean",
        "green_cover_pct_ndvi": "mean",
        "walk_index": "mean",
        "urban_heat_anomaly_c": "mean",
        "health_n_primary_care": "mean",
    })
    n_clusters = len(means)
    # Higher rank = higher mean.
    ranks = means.rank(method="min").astype(int)
    labels: dict[int, str] = {}
    used_labels: set[str] = set()
    # Process clusters from most distinctive (extreme ranks) to least.
    cluster_order = sorted(
        ranks.index,
        key=lambda c: sum(
            abs(ranks.loc[c, col] - (n_clusters + 1) / 2)
            for col in ranks.columns
        ),
        reverse=True,
    )
    for cid in cluster_order:
        r = ranks.loc[cid]
        # Top-2 features per cluster (highest rank = most extreme).
        high_cols = r.nlargest(2).index.tolist()
        low_cols = r.nsmallest(2).index.tolist()
        # Build candidate label from extremes.
        if "pm25_mean" in high_cols and "nse_index" in low_cols:
            candidate = "industrial-periferia"
        elif "pm25_mean" in high_cols and "walk_index" in high_cols:
            candidate = "central-urbana-densa"
        elif "green_cover_pct_ndvi" in high_cols and "nse_index" in high_cols \
                and "pm25_mean" in low_cols:
            candidate = "residencial-Andes"
        elif "urban_heat_anomaly_c" in high_cols and "pm25_mean" in high_cols:
            candidate = "periurbana-calida"
        elif "green_cover_pct_ndvi" in high_cols and "pm25_mean" in low_cols:
            candidate = "rural-verde"
        elif "walk_index" in high_cols:
            candidate = "central-urbana"
        else:
            candidate = "periurbana-mixta"
        # Disambiguate duplicates.
        if candidate in used_labels:
            n_dup = sum(1 for l in used_labels if l.startswith(candidate))
            candidate = f"{candidate}-{n_dup + 1}"
        labels[int(cid)] = candidate
        used_labels.add(candidate)
    return labels


def _plot_clusters(
    gdf: gpd.GeoDataFrame, df: pd.DataFrame, cluster_labels: dict[int, str],
    ebi: pd.DataFrame, out: Path,
) -> None:
    gdf_plot = gdf.merge(df[["name", "cluster_id", "cluster_label"]],
                         on="name", how="left")
    fig, axes = plt.subplots(1, 2, figsize=(15, 9),
                             gridspec_kw={"width_ratios": [2.2, 1]})
    fig.suptitle(
        "Tipologias comunales via K-means — exposome Region Metropolitana de Santiago\n"
        "6 features estandarizadas (PM2.5, NSE, green, walk, heat, health)",
        fontsize=11,
    )

    ax_map = axes[0]
    cluster_ids = sorted(df["cluster_id"].unique())
    for cid in cluster_ids:
        sub = gdf_plot.loc[gdf_plot["cluster_id"] == cid]
        if sub.empty:
            continue
        gpd.GeoDataFrame(sub, crs=gdf.crs).plot(
            ax=ax_map,
            color=CLUSTER_PALETTE[cid % len(CLUSTER_PALETTE)],
            edgecolor="white", linewidth=0.5,
        )
    ax_map.set_axis_off()
    ax_map.set_title("Mapa de clusters comunales", fontsize=10.5)

    handles = [
        plt.Rectangle((0, 0), 1, 1,
                      color=CLUSTER_PALETTE[cid % len(CLUSTER_PALETTE)],
                      label=f"{cid}: {cluster_labels.get(cid, '?')}")
        for cid in cluster_ids
    ]
    ax_map.legend(handles=handles, loc="lower left", fontsize=8.5,
                  framealpha=0.9, title="Cluster ID : Label")

    ax_tab = axes[1]
    ax_tab.set_axis_off()
    rows: list[list[str]] = []
    for cid in cluster_ids:
        sub = df.loc[df["cluster_id"] == cid]
        n = len(sub)
        merged = sub.merge(ebi[["name", "ebi_score"]], on="name")
        top3 = (merged.nlargest(3, "ebi_score")["name"]
                .tolist() if n >= 3 else merged["name"].tolist())
        rows.append([str(cid), cluster_labels.get(cid, "?"),
                     str(n), ", ".join(top3)])
    table = ax_tab.table(
        cellText=rows,
        colLabels=["ID", "Label", "N", "Top-3 (por EBI)"],
        loc="center", cellLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1, 1.4)
    ax_tab.set_title("Top-3 comunas por cluster (orden por EBI)", fontsize=10)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    df = _load_master()
    ebi = pd.read_csv(DATA_DIR / "environmental_burden_index.csv")

    cols = [c for c, _ in CLUSTER_FEATURES if c in df.columns]
    if len(cols) != len(CLUSTER_FEATURES):
        missing = [c for c, _ in CLUSTER_FEATURES if c not in df.columns]
        raise ValueError(f"Missing feature cols: {missing}")
    sub = df[cols].copy()
    for col, sign in CLUSTER_FEATURES:
        if sign == -1:
            sub[col] = -sub[col]
    features = StandardScaler().fit_transform(sub.values)

    best_k, scores = _select_k(features)
    if scores[best_k] < SILHOUETTE_FLOOR:
        print(
            f"Best silhouette ({scores[best_k]:.3f}) < {SILHOUETTE_FLOOR}; "
            f"falling back to k={FALLBACK_K}"
        )
        best_k = FALLBACK_K
    print(f"Selected k={best_k}; silhouette={scores[best_k]:.3f}")

    km = KMeans(n_clusters=best_k, random_state=RANDOM_STATE, n_init=10)
    cluster_assignments = km.fit_predict(features).astype(int)
    df = pd.concat([
        df,
        pd.DataFrame({
            "cluster_id": cluster_assignments,
            "cluster_label": "",
            "cluster_size": 0,
            "silhouette_global": round(scores[best_k], 4),
        }, index=df.index),
    ], axis=1)
    cluster_labels = _label_clusters(df)
    df["cluster_label"] = df["cluster_id"].map(cluster_labels)
    cluster_sizes = df.groupby("cluster_id").size().to_dict()
    df["cluster_size"] = df["cluster_id"].map(cluster_sizes)

    out_csv = DATA_DIR / "commune_clusters.csv"
    df[["name", "cluster_id", "cluster_label",
        "cluster_size", "silhouette_global"]].to_csv(out_csv, index=False)
    print(f"Wrote: {out_csv} ({len(df)} rows)")

    geo = DATA_DIR / "santiago_exposome_master.geojson"
    if geo.exists():
        gdf = gpd.read_file(geo)
        _plot_clusters(
            gdf, df, cluster_labels, ebi,
            FIGURES_DIR / "commune_clusters_map.png",
        )

    summary_path = DATA_DIR / "cross_layer_summary.json"
    if summary_path.exists():
        with open(summary_path) as f:
            summary = json.load(f)
        summary["cluster_assignments"] = {
            "method": (
                f"K-means (k={best_k}) over 6 standardised features; "
                f"silhouette={scores[best_k]:.3f}; "
                f"random_state={RANDOM_STATE}."
            ),
            "features": [
                {"column": c, "sign": s} for c, s in CLUSTER_FEATURES
            ],
            "k_search_range": [K_MIN, K_MAX],
            "k_silhouette_scores": {str(k): round(v, 4) for k, v in scores.items()},
            "selected_k": int(best_k),
            "clusters": [
                {
                    "id": int(cid),
                    "label": cluster_labels.get(int(cid), "?"),
                    "size": int(cluster_sizes.get(int(cid), 0)),
                    "members": df.loc[df["cluster_id"] == cid, "name"].tolist(),
                }
                for cid in sorted(df["cluster_id"].unique())
            ],
            "created_utc": datetime.now(timezone.utc).isoformat(),
        }
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"Updated: {summary_path}")


if __name__ == "__main__":
    sys.exit(main())

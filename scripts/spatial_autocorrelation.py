"""Spatial autocorrelation analysis over the master exposome table.

Reads `data/processed/santiago_exposome_master.geojson` and computes
Moran's I (global) + LISA cluster maps (local) for the canonical
exposome indicators. This tells us whether each layer is **patchy**
(autocorrelation positive: nearby communes share similar values),
**dispersed** (negative: neighbors are dissimilar), or **random**
(autocorrelation ~ 0).

Outputs
-------
1. `data/processed/spatial_autocorrelation.json`
   For each of the 12 canonical indicators:
   {I, E_I, p_value, z_score, n_HH, n_LL, n_HL, n_LH, n_NS,
    interpretation}.
2. `figures/spatial_autocorrelation_lisa.png`
   4-panel LISA cluster map (HH, HL, LH, LL, NS) for the 4 layers
   with the highest significant global Moran's I.
3. `figures/spatial_autocorrelation_bar.png`
   1-panel bar chart of global Moran's I per layer (sorted), with
   significance indicated by marker color.

Method
------
- Spatial weights: Queen contiguity from `libpysal.weights.Queen`
  (communes are neighbors if they share at least one vertex).
- Row-standardization applied (common in PySAL workflows).
- Moran's I computed with `esda.Moran` (analytical inference,
  permutation-based p-value with 999 permutations).
- LISA computed with `esda.Moran_Local`; communes classified into
  HH, HL, LH, LL, or non-significant at p < 0.05.

Usage
-----
    python scripts/spatial_autocorrelation.py
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
from esda.moran import Moran, Moran_Local
from libpysal.weights import Queen

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

CANONICAL_LAYERS: list[tuple[str, str, str]] = [
    # (label, column, interpretation)
    ("PM2.5 (ACAG)", "pm25_mean", "ambient PM2.5 (chronic)"),
    ("NO2 surface (sat)", "no2_surface_ug_m3", "NO2 surface concentration"),
    ("O3 column (sat)", "o3_mean", "O3 total column"),
    ("Heavy metals index", "hm_index", "industrial metal emissions"),
    ("ALAN radiance", "alan_radiance_mean", "artificial light at night"),
    ("Noise combined %", "noise_combined_pct", "noise exposure"),
    ("Heat exposure", "heat_exposure_index", "heat exposure index"),
    ("Urban heat anomaly", "urban_heat_anomaly_c", "urban heat island"),
    ("Wind calm annual", "wind_calm_pct", "low-dispersion episodes"),
    ("Greenspace NDVI", "green_cover_pct_ndvi", "vegetation cover"),
    ("Walkability", "walk_index", "walkability index"),
    ("Transit", "transit_index", "transit accessibility"),
    ("Pobreza %", "pobreza_pct", "poverty rate"),
    ("NSE index", "nse_index", "socioeconomic level"),
]

PERMUTATIONS = 999
ALPHA = 0.05

LISA_COLORS = {
    "HH": "#d7191c",  # red — hot spot
    "LL": "#2c7bb6",  # blue — cold spot
    "HL": "#fdae61",  # orange — high outlier
    "LH": "#abd9e9",  # light blue — low outlier
    "NS": "#eeeeee",  # gray — not significant
}


def _load_geodata() -> tuple[gpd.GeoDataFrame, Queen]:
    geo = DATA_DIR / "santiago_exposome_master.geojson"
    if not geo.exists():
        raise FileNotFoundError(
            f"Master GeoJSON not found: {geo}. "
            "Run scripts/build_master_exposome.py first."
        )
    gdf = gpd.read_file(geo)
    w = Queen.from_dataframe(gdf, use_index=False)
    w.transform = "r"
    return gdf, w


def _classify_lisa(moran_local: Moran_Local, gdf: gpd.GeoDataFrame) -> pd.Series:
    """Classify each commune into HH/HL/LH/LL/NS.

    Quadrants:
      Q1 (HH): local value > mean, spatial lag > mean
      Q2 (LH): local value < mean, spatial lag > mean
      Q3 (LL): local value < mean, spatial lag < mean
      Q4 (HL): local value > mean, spatial lag < mean
    Significant at p < ALPHA.
    """
    sig = moran_local.p_sim < ALPHA
    q = moran_local.q
    labels = np.where(sig, "NS", "NS")
    labels[(q == 1) & sig] = "HH"
    labels[(q == 2) & sig] = "LH"
    labels[(q == 3) & sig] = "LL"
    labels[(q == 4) & sig] = "HL"
    return pd.Series(labels, index=gdf.index, name="lisa_class")


def _interpret(I: float, p: float) -> str:
    if p >= ALPHA:
        return "spatial_randomness"
    if I > 0.3:
        return "strong_positive_autocorrelation"
    if I > 0:
        return "weak_positive_autocorrelation"
    if I < -0.3:
        return "strong_negative_autocorrelation"
    return "weak_negative_autocorrelation"


def _compute_for_layer(
    gdf: gpd.GeoDataFrame, w: Queen, col: str,
) -> dict:
    """Compute Moran's I global + LISA for one column."""
    series = gdf[col].astype(float)
    if series.isna().any():
        series = series.fillna(series.median())
    arr = series.to_numpy()
    mi = Moran(arr, w, permutations=PERMUTATIONS)
    mi_local = Moran_Local(arr, w, permutations=PERMUTATIONS, seed=12345)
    classes = _classify_lisa(mi_local, gdf)
    counts = classes.value_counts().to_dict()
    return {
        "I": round(float(mi.I), 4),
        "E_I": round(float(mi.EI), 4),
        "z_score": round(float(mi.z_sim), 4),
        "p_value": round(float(mi.p_sim), 4),
        "n_HH": int(counts.get("HH", 0)),
        "n_LL": int(counts.get("LL", 0)),
        "n_HL": int(counts.get("HL", 0)),
        "n_LH": int(counts.get("LH", 0)),
        "n_NS": int(counts.get("NS", 0)),
        "interpretation": _interpret(float(mi.I), float(mi.p_sim)),
    }, classes


def _plot_lisa_panels(
    gdf: gpd.GeoDataFrame, results: dict, out: Path,
) -> None:
    """4-panel LISA map for the top-4 most autocorrelated layers."""
    ranked = sorted(
        ((label, r) for label, r in results.items()
         if r["p_value"] < ALPHA and r["I"] > 0),
        key=lambda x: -x[1]["I"],
    )[:4]
    if not ranked:
        ranked = list(results.items())[:4]
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle(
        "LISA cluster maps — comunas con autocorrelacion espacial significativa\n"
        "HH = hot spot (high surrounded by high), LL = cold spot, "
        "HL/LH = outliers espaciales",
        fontsize=11,
    )
    for ax, (label, _) in zip(axes.ravel(), ranked):
        classes_series = gdf[f"lisa_{label}"]
        for cls, color in LISA_COLORS.items():
            mask = classes_series == cls
            if mask.any():
                subset = gdf.loc[mask]
                gpd.GeoDataFrame(subset, crs=gdf.crs).plot(
                    ax=ax, color=color, edgecolor="white", linewidth=0.4,
                )
        ax.set_title(
            f"{label}  (I = {results[label]['I']:.2f}, p = {results[label]['p_value']:.3f})",
            fontsize=10,
        )
        ax.set_axis_off()
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=c, label=k)
        for k, c in LISA_COLORS.items()
    ]
    fig.legend(
        handles=handles, loc="lower center", ncol=5, fontsize=9,
        bbox_to_anchor=(0.5, 0.01), framealpha=0.9,
    )
    fig.tight_layout(rect=[0, 0.04, 1, 0.95])
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def _plot_bar(results: dict, out: Path) -> None:
    """1-panel bar chart of global Moran's I per layer, sorted."""
    items = sorted(results.items(), key=lambda x: -x[1]["I"])
    labels = [k for k, _ in items]
    Is = [r["I"] for _, r in items]
    pvals = [r["p_value"] for _, r in items]
    colors = ["#d7191c" if p < ALPHA and I > 0
              else "#2c7bb6" if p < ALPHA and I < 0
              else "#cccccc" for I, p in zip(Is, pvals)]
    fig, ax = plt.subplots(figsize=(10, 7))
    y_pos = np.arange(len(labels))
    ax.barh(y_pos, Is, color=colors, edgecolor="white")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.axvline(0, color="#333", lw=0.6)
    ax.set_xlabel("Moran's I (autocorrelacion espacial global)")
    ax.set_title(
        "Moran's I por capa — exposome Region Metropolitana de Santiago\n"
        "Rojo = positivo significativo (p<0.05); Azul = negativo significativo; "
        "Gris = no significativo",
        fontsize=10.5,
    )
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    gdf, w = _load_geodata()
    n_neighbors_mean = float(np.mean(list(w.cardinalities.values())))
    results: dict[str, dict] = {}
    for label, col, interp in CANONICAL_LAYERS:
        if col not in gdf.columns:
            print(f"  skip: column {col!r} not in master")
            continue
        stats, classes = _compute_for_layer(gdf, w, col)
        results[label] = stats
        gdf[f"lisa_{label}"] = classes
        results[label]["interpretation_text"] = interp
        print(
            f"  {label}: I={stats['I']:.3f}, "
            f"p={stats['p_value']:.3f}, "
            f"HH={stats['n_HH']}, LL={stats['n_LL']}, "
            f"HL={stats['n_HL']}, LH={stats['n_LH']}, NS={stats['n_NS']}"
        )
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "method": (
            "Global Moran's I + LISA (local Moran) using Queen contiguity "
            "weights (row-standardized), 999 permutations, p < 0.05 for "
            "significance."
        ),
        "n_communes": int(len(gdf)),
        "mean_neighbors": round(n_neighbors_mean, 2),
        "layers": results,
        "ranked_by_I": sorted(
            ({"label": k, **v} for k, v in results.items()),
            key=lambda r: -r["I"],
        ),
    }
    out_json = DATA_DIR / "spatial_autocorrelation.json"
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Wrote: {out_json}")

    _plot_lisa_panels(
        gdf, results, FIGURES_DIR / "spatial_autocorrelation_lisa.png",
    )
    _plot_bar(results, FIGURES_DIR / "spatial_autocorrelation_bar.png")


if __name__ == "__main__":
    sys.exit(main())

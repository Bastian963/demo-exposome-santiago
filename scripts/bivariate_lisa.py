"""Bivariate LISA: EBI x NSE co-location analysis.

Computes **Bivariate Local Moran's I** (Anselin 2010) for the
Environmental Burden Index (EBI) against the NSE (Socioeconomic
Level) index, using Queen contiguity weights from the master
GeoJSON. This identifies **environmental-justice clusters** at
the commune level:

- **HH** (High EBI - High NSE): rich communes with high burden
  (intra-rich inequality, or location-specific hot spots).
- **HL** (High EBI - Low NSE): the **classic environmental
  justice signal** — poor communes with high burden.
- **LH** (Low EBI - High NSE): rich communes with low burden
  (advantage clusters).
- **LL** (Low EBI - Low NSE): rural periphery with low burden
  and low NSE (low-impact clusters).

The Bivariate Moran's I is **not symmetric**: we use EBI as the
focus variable and NSE as the contextual variable (i.e., is
high EBI co-located with high or low NSE?). The two directions
are run separately for symmetry.

Outputs
-------
- ``data/processed/bivariate_lisa.json`` (summary)
- ``figures/bivariate_lisa_ebinse_map.png`` (2-panel:
  EBI x NSE direction + NSE x EBI direction)
- ``figures/bivariate_lisa_quadrants.png`` (bar of cluster sizes)

Usage
-----
    python scripts/bivariate_lisa.py
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
from esda.moran import Moran_Local_BV
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

PERMUTATIONS = 999
ALPHA = 0.05

LISA_COLORS = {
    "HH": "#d7191c",
    "LL": "#2c7bb6",
    "HL": "#fdae61",
    "LH": "#abd9e9",
    "NS": "#eeeeee",
}


def _load_data() -> tuple[pd.DataFrame, gpd.GeoDataFrame, Queen]:
    ebi = pd.read_csv(DATA_DIR / "environmental_burden_index.csv")
    geo = gpd.read_file(DATA_DIR / "santiago_exposome_master.geojson")
    merged = geo.merge(ebi[["name", "ebi_score"]], on="name", how="left")
    if merged["ebi_score"].isna().any():
        raise ValueError("EBI score missing for some communes")
    w = Queen.from_dataframe(merged, use_index=False)
    w.transform = "R"
    return ebi, merged, w


def _bivariate_lisa(
    x: np.ndarray, y: np.ndarray, w: Queen,
) -> tuple[Moran_Local_BV, np.ndarray]:
    """Run Moran_Local_BV with x as the focus, y as the contextual.

    Returns the Moran_Local_BV object and the array of quadrant
    codes (1=HH, 2=LH, 3=LL, 4=HL, 0=NS) at p < 0.05.
    """
    np.random.seed(42)
    lisa_bv = Moran_Local_BV(x, y, w, permutations=PERMUTATIONS)
    sig = lisa_bv.p_sim < ALPHA
    q = lisa_bv.q
    quad = np.where(sig, q, 0)
    return lisa_bv, quad


def _quadrants_to_labels(quad: np.ndarray) -> list[str]:
    """Map q (1..4) and 0 (NS) to HH/LH/LL/HL/NS labels."""
    mapping = {0: "NS", 1: "HH", 2: "LH", 3: "LL", 4: "HL"}
    return [mapping.get(int(q), "NS") for q in quad]


def _plot_map(
    gdf: gpd.GeoDataFrame,
    quad: np.ndarray,
    title: str,
    out_path: Path,
) -> None:
    """Single-panel LISA cluster map."""
    gdf = gdf.copy()
    gdf["quadrant"] = _quadrants_to_labels(quad)
    fig, ax = plt.subplots(figsize=(7, 8))
    for label, color in LISA_COLORS.items():
        sub = gdf[gdf["quadrant"] == label]
        if len(sub) == 0:
            continue
        sub.plot(
            ax=ax, color=color, edgecolor="white", linewidth=0.4,
            label=f"{label} (n={len(sub)})",
        )
    ax.legend(
        loc="lower right", fontsize=8, framealpha=0.9, title="LISA cluster",
    )
    ax.set_title(title, fontsize=11)
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def _plot_quadrants(
    quad_ebinse: np.ndarray, quad_nseebi: np.ndarray, out_path: Path,
) -> None:
    """Bar chart of cluster sizes for both directions."""
    labels_ebinse = _quadrants_to_labels(quad_ebinse)
    labels_nseebi = _quadrants_to_labels(quad_nseebi)
    counts_ebinse = pd.Series(labels_ebinse).value_counts()
    counts_nseebi = pd.Series(labels_nseebi).value_counts()
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    for ax, counts, title in zip(
        axes,
        [counts_ebinse, counts_nseebi],
        ["EBI x NSE (focus: EBI)", "NSE x EBI (focus: NSE)"],
    ):
        labels = ["HH", "HL", "LH", "LL", "NS"]
        vals = [counts.get(l, 0) for l in labels]
        colors = [LISA_COLORS[l] for l in labels]
        ax.bar(labels, vals, color=colors, edgecolor="white")
        for i, v in enumerate(vals):
            ax.text(
                i, v + 0.3, str(v), ha="center", va="bottom", fontsize=9,
            )
        ax.set_title(title, fontsize=10)
        ax.set_ylabel("# communes", fontsize=9)
    plt.suptitle("Bivariate LISA cluster sizes (p<0.05, 999 permutations)", y=1.02)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def _members(quad: np.ndarray, names: pd.Series, label: str) -> list[str]:
    qmap = {"HH": 1, "LH": 2, "LL": 3, "HL": 4, "NS": 0}
    q = qmap[label]
    return names[quad == q].tolist()


def main() -> None:
    print("Loading EBI + master GeoJSON + Queen weights...")
    ebi, gdf, w = _load_data()
    nse = gdf["nse_index"].to_numpy()
    ebi_arr = gdf["ebi_score"].to_numpy()
    names = gdf["name"]

    print("Direction 1: EBI x NSE (focus: EBI)...")
    lisa_ebinse, quad_ebinse = _bivariate_lisa(ebi_arr, nse, w)
    print("Direction 2: NSE x EBI (focus: NSE)...")
    lisa_nseebi, quad_nseebi = _bivariate_lisa(nse, ebi_arr, w)

    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "method": (
            "Bivariate Local Moran's I (Anselin 2010) using Queen "
            "contiguity weights, row-standardized, 999 permutations, "
            "p<0.05 for significance. Quadrants: HH = high focus + high "
            "context; HL = high focus + low context (env-justice signal); "
            "LH = low focus + high context; LL = low focus + low context; "
            "NS = not significant."
        ),
        "n_communes": int(len(gdf)),
        "mean_neighbors": float(np.mean([len(w.neighbors[i]) for i in w.neighbors])),
        "permutations": PERMUTATIONS,
        "alpha": ALPHA,
        "direction_ebinse": {
            "focus": "EBI",
            "context": "NSE",
            "I_bv_mean": float(lisa_ebinse.Is.mean()),
            "n_HH": int((quad_ebinse == 1).sum()),
            "n_LH": int((quad_ebinse == 2).sum()),
            "n_LL": int((quad_ebinse == 3).sum()),
            "n_HL": int((quad_ebinse == 4).sum()),
            "n_NS": int((quad_ebinse == 0).sum()),
            "members_HH": _members(quad_ebinse, names, "HH"),
            "members_HL": _members(quad_ebinse, names, "HL"),
            "members_LH": _members(quad_ebinse, names, "LH"),
            "members_LL": _members(quad_ebinse, names, "LL"),
        },
        "direction_nseebi": {
            "focus": "NSE",
            "context": "EBI",
            "I_bv_mean": float(lisa_nseebi.Is.mean()),
            "n_HH": int((quad_nseebi == 1).sum()),
            "n_LH": int((quad_nseebi == 2).sum()),
            "n_LL": int((quad_nseebi == 3).sum()),
            "n_HL": int((quad_nseebi == 4).sum()),
            "n_NS": int((quad_nseebi == 0).sum()),
            "members_HH": _members(quad_nseebi, names, "HH"),
            "members_HL": _members(quad_nseebi, names, "HL"),
            "members_LH": _members(quad_nseebi, names, "LH"),
            "members_LL": _members(quad_nseebi, names, "LL"),
        },
    }
    out = DATA_DIR / "bivariate_lisa.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Wrote: {out}")

    print("Plotting LISA maps + quadrant bars...")
    _plot_map(
        gdf, quad_ebinse,
        "Bivariate LISA: EBI x NSE (focus: EBI)",
        FIGURES_DIR / "bivariate_lisa_ebinse_map.png",
    )
    print(f"  Saved: {FIGURES_DIR / 'bivariate_lisa_ebinse_map.png'}")
    _plot_map(
        gdf, quad_nseebi,
        "Bivariate LISA: NSE x EBI (focus: NSE)",
        FIGURES_DIR / "bivariate_lisa_nseebi_map.png",
    )
    print(f"  Saved: {FIGURES_DIR / 'bivariate_lisa_nseebi_map.png'}")
    _plot_quadrants(
        quad_ebinse, quad_nseebi,
        FIGURES_DIR / "bivariate_lisa_quadrants.png",
    )
    print(f"  Saved: {FIGURES_DIR / 'bivariate_lisa_quadrants.png'}")
    print("Done.")


if __name__ == "__main__":
    main()

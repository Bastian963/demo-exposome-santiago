"""Publication-quality figure for the walkability exposome layer.

OSM street-network metrics per commune, Región Metropolitana de Santiago.

Produces a 4-panel figure:
  A) Choropleth: walk_index (0–100).
  B) Choropleth: intersection density (intersec/km²).
  C) Ranked bar chart of communes by walk_index.
  D) Socioeconomic gradient: NSE index vs walk_index (Spearman r).
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize
from scipy.stats import spearmanr

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

CMAP_INDEX = "RdYlGn"
CMAP_DENSITY = "YlGn"


def _load_data() -> gpd.GeoDataFrame:
    walk_geo = DATA_DIR / "santiago_walkability.geojson"
    if not walk_geo.exists():
        raise FileNotFoundError(f"Walkability GeoJSON not found: {walk_geo}")
    gdf = gpd.read_file(walk_geo)

    nse_csv = DATA_DIR / "socioeconomic_exposome_rm_santiago.csv"
    if nse_csv.exists():
        nse = pd.read_csv(nse_csv)[["name", "nse_index"]]
        gdf = gdf.merge(nse, on="name", how="left")
    else:
        gdf["nse_index"] = np.nan

    return gdf


def _choropleth(ax, gdf, col, cmap, title, unit, vmin=None, vmax=None):
    vals = gdf[col].astype(float)
    vmin = vmin if vmin is not None else vals.min()
    vmax = vmax if vmax is not None else vals.max()
    norm = Normalize(vmin=vmin, vmax=vmax)

    for _, row in gdf.iterrows():
        v = row[col]
        color = plt.get_cmap(cmap)(norm(v))
        gpd.GeoDataFrame([row], crs=gdf.crs).plot(
            ax=ax, color=color, edgecolor="white", linewidth=0.4
        )

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    plt.colorbar(sm, ax=ax, fraction=0.03, pad=0.02, label=unit)
    ax.set_title(title)
    ax.set_axis_off()


def _bar_chart(ax, gdf):
    df = gdf[["name", "walk_index"]].sort_values("walk_index", ascending=True)
    colors = plt.get_cmap("RdYlGn")(np.linspace(0.05, 0.95, len(df)))
    bars = ax.barh(df["name"], df["walk_index"], color=colors, edgecolor="none", height=0.8)
    ax.set_xlabel("Walk index (0–100)")
    ax.set_title("Ranking comunal de caminabilidad")
    ax.set_xlim(0, 105)
    ax.axvline(50, color="#999", lw=0.8, ls="--")

    # Annotate top 5 and bottom 5.
    for i, (_, row) in enumerate(df.iterrows()):
        if i >= len(df) - 5 or i < 5:
            ax.text(row["walk_index"] + 1.5, i, f"{row['walk_index']:.0f}",
                    va="center", fontsize=6.5, color="#333")
    ax.tick_params(axis="y", labelsize=6.2)


def _scatter(ax, gdf):
    valid = gdf.dropna(subset=["nse_index", "walk_index"])
    if len(valid) < 5:
        ax.text(0.5, 0.5, "NSE data not available", transform=ax.transAxes,
                ha="center", va="center")
        return

    x = valid["nse_index"].astype(float)
    y = valid["walk_index"].astype(float)
    r, p = spearmanr(x, y)

    colors = plt.get_cmap("RdYlGn")(np.linspace(0.1, 0.9, len(valid)))
    ax.scatter(x, y, c=colors, s=30, alpha=0.85, edgecolors="#444", linewidths=0.4)

    # Regression line.
    m, b = np.polyfit(x, y, 1)
    xr = np.linspace(x.min(), x.max(), 100)
    ax.plot(xr, m * xr + b, color="#e44", lw=1.2, ls="--", alpha=0.7)

    # Label extreme communes.
    for _, row in valid.iterrows():
        if row["walk_index"] > 85 or row["walk_index"] < 20:
            ax.annotate(
                row["name"], (row["nse_index"], row["walk_index"]),
                fontsize=6.2, xytext=(4, 2), textcoords="offset points", color="#333",
            )

    pstr = "< 0.001" if p < 0.001 else f"= {p:.3f}"
    ax.set_title(f"NSE vs caminabilidad  (Spearman r = {r:.2f}, p {pstr})")
    ax.set_xlabel("NSE index (mayor = mejor posición)")
    ax.set_ylabel("Walk index (0–100)")


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    gdf = _load_data()

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle(
        "Caminabilidad comunal — Región Metropolitana de Santiago\n"
        "Fuente: OpenStreetMap vía osmnx · Red vial completa (network_type='all')",
        fontsize=11,
    )

    _choropleth(
        axes[0, 0], gdf, "walk_index", CMAP_INDEX,
        "A)  Índice de caminabilidad (0–100)", "Walk index",
        vmin=0, vmax=100,
    )
    _choropleth(
        axes[0, 1], gdf, "walk_intersection_density", CMAP_DENSITY,
        "B)  Densidad de intersecciones (intersec/km²)", "intersec/km²",
    )
    _bar_chart(axes[1, 0], gdf)
    _scatter(axes[1, 1], gdf)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = FIGURES_DIR / "walkability_santiago_4panel.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()

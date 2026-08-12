"""Publication-quality figure for the food environment exposome layer.

OSM retail outlet metrics per commune, Region Metropolitana de Santiago.

Produces a 4-panel figure:
  A) Choropleth: food_index (0-100).
  B) Choropleth: food_n_supermarket (count).
  C) Choropleth: food_mean_dist_supermarket_m (km, log scale).
  D) Ranked bar chart of food_index with top/bottom 5 annotated.

NOTE: 4 of 5 OSM retail categories are empty in the current cache
(greengrocer, marketplace, fast_food, convenience). The figure
reflects this gap: only supermarket density and access distance
contribute meaningful signal. See
`data/processed/santiago_food_environment_metadata.json` under
`coverage_gap` for details.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm, Normalize

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
CMAP_COUNT = "YlGnBu"
CMAP_DIST = "YlOrRd"


def _load_data() -> gpd.GeoDataFrame:
    geo = DATA_DIR / "santiago_food_environment.geojson"
    if not geo.exists():
        raise FileNotFoundError(f"Food environment GeoJSON not found: {geo}")
    return gpd.read_file(geo)


def _choropleth(ax, gdf, col, cmap, title, unit, vmin=None, vmax=None, log=False) -> None:
    vals = gdf[col].astype(float)
    if log:
        vals_plot = vals.where(vals > 0)
        vmin_p = vals_plot[vals_plot > 0].min() if (vals_plot > 0).any() else 1.0
        norm = LogNorm(vmin=max(vmin_p, 1.0), vmax=vals_plot.max())
    else:
        if vmin is None:
            vmin = float(vals.min())
        if vmax is None:
            vmax = float(vals.max())
        norm = Normalize(vmin=vmin, vmax=vmax)
    for _, row in gdf.iterrows():
        v = float(row[col])
        if log and v <= 0:
            color = "0.85"
        else:
            color = plt.get_cmap(cmap)(norm(v)) if v > 0 else "0.85"
        gpd.GeoDataFrame([row], crs=gdf.crs).plot(
            ax=ax, color=color, edgecolor="white", linewidth=0.4
        )
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    plt.colorbar(sm, ax=ax, fraction=0.03, pad=0.02, label=unit)
    ax.set_title(title)
    ax.set_axis_off()


def _bar_chart(ax, gdf) -> None:
    df = gdf[["name", "food_index"]].sort_values("food_index", ascending=True)
    colors = plt.get_cmap(CMAP_INDEX)(np.linspace(0.05, 0.95, len(df)))
    ax.barh(df["name"], df["food_index"], color=colors, edgecolor="none", height=0.8)
    ax.set_xlabel("Food index (0-100)")
    ax.set_title("Ranking comunal de entorno alimentario (food_index)")
    ax.set_xlim(0, 105)
    ax.axvline(50, color="#999", lw=0.8, ls="--")
    for i, (_, row) in enumerate(df.iterrows()):
        if i >= len(df) - 5 or i < 5:
            ax.text(row["food_index"] + 1.5, i, f"{row['food_index']:.0f}",
                    va="center", fontsize=6.5, color="#333")
    ax.tick_params(axis="y", labelsize=6.2)


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    gdf = _load_data()

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle(
        "Entorno alimentario comunal - Region Metropolitana de Santiago\n"
        "Fuente: OpenStreetMap (596 supermercados; 0 en greengrocer/marketplace/fast_food/convenience)\n"
        "Cobertura OSM limitada para categorias no-supermercado - ver coverage_gap en metadata",
        fontsize=11,
    )

    _choropleth(
        axes[0, 0], gdf, "food_index", CMAP_INDEX,
        "A)  Food index (0-100) - supermercado + distancia",
        "Food index", vmin=0, vmax=100,
    )
    _choropleth(
        axes[0, 1], gdf, "food_n_supermarket", CMAP_COUNT,
        "B)  Numero de supermercados (n)",
        "supermercados",
    )
    _choropleth(
        axes[1, 0], gdf, "food_mean_dist_supermarket_m", CMAP_DIST,
        "C)  Distancia media al supermercado (m, escala log)",
        "metros (log)", log=True,
    )
    _bar_chart(axes[1, 1], gdf)

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out = FIGURES_DIR / "food_environment_santiago_4panel.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()

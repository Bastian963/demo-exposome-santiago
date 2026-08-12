"""Publication-quality figure for the public transport accessibility exposome layer.

OSM bus stops + metro stations per commune, Región Metropolitana de Santiago.

Panels:
  A) Choropleth: transit_index (0–100).
  B) Choropleth: transit_bus_density (paraderos/km²).
  C) Ranked bar chart of communes by transit_index.
  D) NSE vs transit_index scatter (does wealthier = better transit?).
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
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
CMAP_BUS = "YlOrRd"


def _load_data() -> gpd.GeoDataFrame:
    geo = DATA_DIR / "santiago_public_transport.geojson"
    if not geo.exists():
        raise FileNotFoundError(f"Not found: {geo}")
    gdf = gpd.read_file(geo)

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
        color = plt.get_cmap(cmap)(norm(float(row[col])))
        gpd.GeoDataFrame([row], crs=gdf.crs).plot(
            ax=ax, color=color, edgecolor="white", linewidth=0.4
        )
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    plt.colorbar(sm, ax=ax, fraction=0.03, pad=0.02, label=unit)
    ax.set_title(title)
    ax.set_axis_off()


def _bar_chart(ax, gdf):
    df = gdf[["name", "transit_index"]].sort_values("transit_index", ascending=True)
    colors = plt.get_cmap("RdYlGn")(np.linspace(0.05, 0.95, len(df)))
    ax.barh(df["name"], df["transit_index"], color=colors, edgecolor="none", height=0.8)
    ax.set_xlabel("Transit index (0–100)")
    ax.set_title("Ranking comunal de acceso a transporte público")
    ax.set_xlim(0, 110)
    ax.axvline(50, color="#999", lw=0.8, ls="--")
    for i, (_, row) in enumerate(df.iterrows()):
        if i >= len(df) - 5 or i < 5:
            ax.text(row["transit_index"] + 1.5, i, f"{row['transit_index']:.0f}",
                    va="center", fontsize=6.5, color="#333")
    ax.tick_params(axis="y", labelsize=6.2)


def _scatter(ax, gdf):
    valid = gdf.dropna(subset=["nse_index", "transit_index"])
    if len(valid) < 5:
        ax.text(0.5, 0.5, "NSE data not available", transform=ax.transAxes,
                ha="center", va="center")
        return

    x = valid["nse_index"].astype(float)
    y = valid["transit_index"].astype(float)
    r, p = spearmanr(x, y)

    colors = plt.get_cmap("RdYlGn")(np.linspace(0.1, 0.9, len(valid)))
    ax.scatter(x, y, c=colors, s=32, alpha=0.85, edgecolors="#444", linewidths=0.4)

    m, b = np.polyfit(x, y, 1)
    xr = np.linspace(x.min(), x.max(), 100)
    ax.plot(xr, m * xr + b, color="#e44", lw=1.2, ls="--", alpha=0.7)

    for _, row in valid.iterrows():
        if row["transit_index"] > 85 or row["transit_index"] < 30:
            ax.annotate(row["name"], (row["nse_index"], row["transit_index"]),
                        fontsize=6.2, xytext=(4, 2), textcoords="offset points",
                        color="#333")

    pstr = "< 0.001" if p < 0.001 else f"= {p:.3f}"
    ax.set_title(f"NSE vs acceso a transporte  (Spearman r = {r:.2f}, p {pstr})")
    ax.set_xlabel("NSE index (mayor = mejor posición socioeconómica)")
    ax.set_ylabel("Transit index (0–100)")


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    gdf = _load_data()

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle(
        "Accesibilidad a transporte público — Región Metropolitana de Santiago\n"
        "Fuente: OpenStreetMap (11 815 paraderos RED únicos + 137 estaciones Metro S.A.)",
        fontsize=11,
    )

    _choropleth(axes[0, 0], gdf, "transit_index", CMAP_INDEX,
                "A)  Índice de acceso a transporte público (0–100)", "Transit index",
                vmin=0, vmax=100)
    _choropleth(axes[0, 1], gdf, "transit_bus_density", CMAP_BUS,
                "B)  Densidad de paraderos (paraderos/km²)", "paraderos/km²")
    _bar_chart(axes[1, 0], gdf)
    _scatter(axes[1, 1], gdf)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = FIGURES_DIR / "public_transport_santiago_4panel.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()

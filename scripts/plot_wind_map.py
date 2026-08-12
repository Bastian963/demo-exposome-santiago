"""Publication-quality figure for the wind exposure layer (ERA5).

Reads `santiago_wind.csv` and produces a 4-panel figure showing the
wind-modulated dispersion environment of the Region Metropolitana.

Panels:
  A) Choropleth: mean 10-m wind speed [m/s].
  B) Choropleth: fraction of calm hours (wind < 2 m/s) [%].
  C) Choropleth: prevailing direction [degrees from N] (categorical 8-rose).
  D) Ranked bar chart of wind_speed_mean with top/bottom 5 annotated.

Wind is not a pollutant; it modulates the **effective exposure** to
all other air-quality indicators. High wind_calm_pct + high NO2/PM2.5
implies poor ventilation and higher local dose.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize

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

CMAP_SPEED = "YlGnBu"
CMAP_CALM = "YlOrRd"
# 8-direction rose categorical colormap.
DIR_BINS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
DIR_COLORS = [
    "#5e3c99", "#b2abd2", "#e7d4e8", "#fdb863",
    "#b35806", "#e6f5d0", "#1b7837", "#5aae61",
]
DIR_CMAP = {d: c for d, c in zip(DIR_BINS, DIR_COLORS)}


def _dir_to_8(deg: float) -> str:
    if pd.isna(deg):
        return "N"
    idx = int(((deg + 22.5) % 360) // 45)
    return DIR_BINS[idx]


def _load_data() -> gpd.GeoDataFrame:
    csv = DATA_DIR / "santiago_wind.csv"
    if not csv.exists():
        raise FileNotFoundError(f"Wind CSV not found: {csv}")
    df = pd.read_csv(csv)
    geo = DATA_DIR / "santiago_wind.geojson"
    gdf = gpd.read_file(geo)
    gdf = gdf[["name", "geometry"]].merge(df, on="name", how="left")
    gdf["wind_dir_8"] = gdf["wind_dir_prevailing"].apply(_dir_to_8)
    return gdf


def _choropleth(ax, gdf, col, cmap, title, unit, vmin=None, vmax=None) -> None:
    vals = gdf[col].astype(float)
    if vmin is None:
        vmin = float(vals.min())
    if vmax is None:
        vmax = float(vals.max())
    norm = Normalize(vmin=vmin, vmax=vmax)
    for _, row in gdf.iterrows():
        v = float(row[col])
        color = plt.get_cmap(cmap)(norm(v))
        gpd.GeoDataFrame([row], crs=gdf.crs).plot(
            ax=ax, color=color, edgecolor="white", linewidth=0.4
        )
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    plt.colorbar(sm, ax=ax, fraction=0.03, pad=0.02, label=unit)
    ax.set_title(title)
    ax.set_axis_off()


def _choropleth_categorical(ax, gdf, col, cmap_dict, title) -> None:
    for _, row in gdf.iterrows():
        cat = row[col]
        color = cmap_dict.get(cat, "#999999")
        gpd.GeoDataFrame([row], crs=gdf.crs).plot(
            ax=ax, color=color, edgecolor="white", linewidth=0.4
        )
    handles = [
        mpatches.Patch(facecolor=cmap_dict[d], edgecolor="white", label=d)
        for d in DIR_BINS
    ]
    ax.legend(handles=handles, loc="lower left", fontsize=7, framealpha=0.8,
              ncol=2, title="Direccion")
    ax.set_title(title)
    ax.set_axis_off()


def _bar_chart(ax, gdf) -> None:
    df = gdf[["name", "wind_speed_mean"]].sort_values("wind_speed_mean", ascending=True)
    colors = plt.get_cmap(CMAP_SPEED)(np.linspace(0.05, 0.95, len(df)))
    ax.barh(df["name"], df["wind_speed_mean"], color=colors, edgecolor="none", height=0.8)
    ax.set_xlabel("Wind speed mean [m/s]")
    ax.set_title("Ranking comunal de velocidad de viento media")
    median_speed = df["wind_speed_mean"].median()
    ax.axvline(median_speed, color="#999", lw=0.8, ls="--",
               label=f"mediana = {median_speed:.2f} m/s")
    ax.legend(loc="lower right", fontsize=8)
    for i, (_, row) in enumerate(df.iterrows()):
        if i >= len(df) - 5 or i < 5:
            ax.text(row["wind_speed_mean"] + 0.02, i, f"{row['wind_speed_mean']:.2f}",
                    va="center", fontsize=6.5, color="#333")
    ax.tick_params(axis="y", labelsize=6.2)


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    gdf = _load_data()

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle(
        "Exposicion a viento — Region Metropolitana de Santiago (ERA5 10-m, 2024)\n"
        "Wind modula la dispersion de PM2.5/NO2/O3: alta calma + alta emision = mayor dosis efectiva",
        fontsize=11,
    )

    _choropleth(
        axes[0, 0], gdf, "wind_speed_mean", CMAP_SPEED,
        "A)  Velocidad media del viento 10 m [m/s]",
        "m/s",
    )
    _choropleth(
        axes[0, 1], gdf, "wind_calm_pct", CMAP_CALM,
        "B)  Fraccion de horas en calma (v < 2 m/s) [%]",
        "fraccion",
    )
    _choropleth_categorical(
        axes[1, 0], gdf, "wind_dir_8", DIR_CMAP,
        "C)  Direccion predominante (8 categorias)",
    )
    _bar_chart(axes[1, 1], gdf)

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out = FIGURES_DIR / "wind_santiago_4panel.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()

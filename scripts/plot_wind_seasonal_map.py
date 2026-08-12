"""Publication-quality figure for the seasonal wind layer (ERA5).

Reads `santiago_wind.csv` and produces a 4-panel figure showing the
winter vs summer wind-modulated dispersion environment of the
Region Metropolitana.

Panels:
  A) Choropleth: mean 10-m wind speed in winter (Jun-Aug) [m/s].
  B) Choropleth: mean 10-m wind speed in summer (Dec-Feb) [m/s].
  C) Choropleth: prevailing direction in winter (8-rose).
  D) Choropleth: prevailing direction in summer (8-rose).

The contrast between A-B (and C-D) is the relevant signal:
winter stagnation is the worst air-quality season in Santiago.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

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
    gdf["wind_dir_winter_8"] = gdf["wind_dir_winter_mean"].apply(_dir_to_8)
    gdf["wind_dir_summer_8"] = gdf["wind_dir_summer_mean"].apply(_dir_to_8)
    return gdf


def _choropleth(ax, gdf, col, cmap, title, unit, vmin=None, vmax=None) -> None:
    from matplotlib.colors import Normalize

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


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    gdf = _load_data()

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle(
        "Viento estacional — Region Metropolitana de Santiago (ERA5 10-m, 2024)\n"
        "Invierno (Jun-Ago) vs Verano (Dic-Feb): contraste clave para dispersion de PM2.5/NO2/O3",
        fontsize=11,
    )

    vmin = min(
        float(gdf["wind_speed_mean_winter"].min()),
        float(gdf["wind_speed_mean_summer"].min()),
    )
    vmax = max(
        float(gdf["wind_speed_mean_winter"].max()),
        float(gdf["wind_speed_mean_summer"].max()),
    )

    _choropleth(
        axes[0, 0], gdf, "wind_speed_mean_winter", CMAP_SPEED,
        "A)  Velocidad media del viento — INVIERNO (Jun-Ago) [m/s]",
        "m/s", vmin=vmin, vmax=vmax,
    )
    _choropleth(
        axes[0, 1], gdf, "wind_speed_mean_summer", CMAP_SPEED,
        "B)  Velocidad media del viento — VERANO (Dic-Feb) [m/s]",
        "m/s", vmin=vmin, vmax=vmax,
    )
    _choropleth_categorical(
        axes[1, 0], gdf, "wind_dir_winter_8", DIR_CMAP,
        "C)  Direccion predominante — INVIERNO",
    )
    _choropleth_categorical(
        axes[1, 1], gdf, "wind_dir_summer_8", DIR_CMAP,
        "D)  Direccion predominante — VERANO",
    )

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out = FIGURES_DIR / "wind_santiago_seasonal.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()

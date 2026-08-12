"""Publication-quality figure for the air-quality satellite exposome layer.

Reads `santiago_air_quality_satellite_<year>.csv` and produces a 4-panel
figure showing the four satellite-derived pollutants.

Panels:
  A) Choropleth: NO2 surface concentration [µg/m^3] (Plan A+ conversion).
  B) Choropleth: O3 total column [mol/m^2] (S5P; ranking only).
  C) Choropleth: AOD at 470 nm (proxy for PM column).
  D) Choropleth: Angstrom Exponent 470-550 (fine-particle / BC proxy).

The figure focuses on **relative ranking** of communes rather than
absolute concentrations: the O3 column is total (mostly stratospheric,
not directly comparable to surface), and AOD/AE are column
quantities. v1.1 dropped the previous (incorrect) O3 surface
proxy; see docs/plan_a_plus_methodology.md section 7.1.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
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

CMAP_NO2 = "YlOrRd"
CMAP_O3 = "PuRd"
CMAP_AOD = "YlGn"
CMAP_AE = "viridis"


def _load_data() -> gpd.GeoDataFrame:
    csv = DATA_DIR / "santiago_air_quality_satellite_2024.csv"
    if not csv.exists():
        raise FileNotFoundError(f"Air-quality satellite CSV not found: {csv}")
    df = pd.read_csv(csv)
    geo = DATA_DIR / "santiago_air_quality_satellite_2024.geojson"
    gdf = gpd.read_file(geo)
    return gdf[["name", "geometry"]].merge(df, on="name", how="left")


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


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    gdf = _load_data()

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle(
        "Calidad del aire satelital — Region Metropolitana de Santiago (2024)\n"
        "NO2, O3, AOD y Angstrom Exponent via Google Earth Engine (S5P + MCD19A2 + ERA5 BLH)",
        fontsize=11,
    )

    _choropleth(
        axes[0, 0], gdf, "no2_surface_ug_m3", CMAP_NO2,
        "A)  NO2 superficie [µg/m^3] (Plan A+, S5P + ERA5 BLH)",
        "µg/m³",
    )
    _choropleth(
        axes[0, 1], gdf, "o3_mean", CMAP_O3,
        "B)  O3 columna total [mol/m^2] (S5P, ranking only)",
        "mol/m^2",
    )
    _choropleth(
        axes[1, 0], gdf, "aod_mean", CMAP_AOD,
        "C)  AOD 470 nm (MCD19A2, columna)",
        "unitless",
    )
    _choropleth(
        axes[1, 1], gdf, "ae_470_550_mean", CMAP_AE,
        "D)  Angstrom Exponent 470-550 nm (mayor = mas fino)",
        "AE (470-550)",
    )

    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out = FIGURES_DIR / "air_quality_satellite_santiago_4panel.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()

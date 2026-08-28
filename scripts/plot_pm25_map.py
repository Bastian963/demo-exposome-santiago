"""Publication-quality figure for the chronic PM2.5 (ACAG) layer.

Produces a 4-panel summary:
  A) Choropleth of population-weighted chronic PM2.5 (µg/m³).
  B) Ranking of the 52 communes by population-weighted PM2.5.
  C) Validation panel:
       - If a SINCA annual-mean CSV is available, ACAG vs SINCA ground monitors
         (ecological, by commune): Spearman ρ + mean bias.
       - Otherwise, construct validity vs surface NO2 (urban co-exposure).
  D) Socioeconomic gradient (environmental justice): NSE index vs PM2.5.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "processed"
# Optional ground-truth: annual-mean PM2.5 by SINCA station (station, lat, lon, pm25).
SINCA_CSV = REPO_ROOT / "data" / "raw" / "stations_sinca" / "sinca_pm25_annual.csv"

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "font.family": "STIXGeneral",
        "mathtext.fontset": "stix",
        "axes.titlesize": 11,
        "axes.labelsize": 10,
    }
)

CMAP = "YlOrRd"
PM_COL = "pm25_pop_weighted"
PM_LABEL = "PM$_{2.5}$ crónico ponderado por población [µg/m³]"
WHO_PM25 = 5.0


def _sinca_validation(gdf: gpd.GeoDataFrame) -> pd.DataFrame | None:
    """Join SINCA station annual means to communes for an ecological check.

    Returns a per-commune frame with observed (SINCA) and modelled (ACAG) PM2.5,
    or None when the optional SINCA CSV is absent.
    """
    if not SINCA_CSV.exists():
        return None
    obs = pd.read_csv(SINCA_CSV)
    needed = {"lat", "lon", "pm25"}
    if not needed.issubset(obs.columns):
        print(f"SINCA CSV missing columns {needed - set(obs.columns)}; skipping validation.")
        return None
    pts = gpd.GeoDataFrame(
        obs, geometry=gpd.points_from_xy(obs["lon"], obs["lat"]), crs="EPSG:4326"
    )
    joined = gpd.sjoin(pts, gdf[["name", "pm25_mean", "geometry"]], predicate="within")
    if joined.empty:
        return None
    # Average stations that fall in the same commune.
    return (
        joined.groupby("name")
        .agg(sinca_pm25=("pm25", "mean"), acag_pm25=("pm25_mean", "first"))
        .reset_index()
    )


def main() -> None:
    geo = DATA_DIR / "santiago_exposome_master.geojson"
    gdf = gpd.read_file(geo)

    out_dir = REPO_ROOT / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(15, 13))

    vmin = float(gdf[PM_COL].min())
    vmax = float(gdf[PM_COL].max())
    norm = plt.Normalize(vmin=vmin, vmax=vmax)

    # --- A) Choropleth (population-weighted chronic PM2.5) --------------- #
    ax = axes[0, 0]
    gdf.plot(
        column=PM_COL,
        cmap=CMAP,
        norm=norm,
        linewidth=0.4,
        edgecolor="0.4",
        ax=ax,
        legend=True,
        legend_kwds={"label": PM_LABEL, "shrink": 0.6},
    )
    ax.set_title(
        "A) PM$_{2.5}$ crónico por comuna\n"
        "(ACAG 2015–2022, ~1 km, ponderado por población)"
    )
    ax.axis("off")

    # --- B) Ranking bar chart -------------------------------------------- #
    ax = axes[0, 1]
    ranked = gdf.sort_values(PM_COL)
    colors = plt.get_cmap(CMAP)(norm(ranked[PM_COL].to_numpy()))
    ax.barh(ranked["name"], ranked[PM_COL], color=colors, edgecolor="0.3", linewidth=0.3)
    ax.axvline(WHO_PM25, color="#2166ac", ls="--", lw=1.2, label=f"Guía WHO 2021 ({WHO_PM25:.0f})")
    ax.set_xlabel(PM_LABEL)
    ax.set_title("B) Ranking de comunas por PM$_{2.5}$\n(mayor = más contaminación)")
    ax.tick_params(axis="y", labelsize=6.5)
    ax.margins(y=0.005)
    ax.legend(loc="lower right", fontsize=8)

    # --- C) Validation: SINCA ground monitors, else NO2 construct validity #
    ax = axes[1, 0]
    val = _sinca_validation(gdf)
    if val is not None and len(val) >= 3:
        rho, pval = spearmanr(val["acag_pm25"], val["sinca_pm25"])
        bias = float((val["acag_pm25"] - val["sinca_pm25"]).mean())
        lims = [0, max(val[["acag_pm25", "sinca_pm25"]].to_numpy().max() * 1.1, WHO_PM25)]
        ax.plot(lims, lims, color="0.6", ls="--", lw=1, label="1:1")
        ax.scatter(val["sinca_pm25"], val["acag_pm25"], s=36, c="#b2182b",
                   edgecolor="white", linewidth=0.5)
        ax.set_xlabel("PM$_{2.5}$ observado SINCA [µg/m³]")
        ax.set_ylabel("PM$_{2.5}$ ACAG (comuna) [µg/m³]")
        ax.set_title(
            f"C) Validación vs estaciones SINCA (n={len(val)} comunas)\n"
            f"Spearman ρ={rho:.3f} (p={pval:.1e}); sesgo medio={bias:+.1f} µg/m³"
        )
        ax.legend(loc="upper left", fontsize=8)
    else:
        rho, pval = spearmanr(gdf[PM_COL], gdf["no2_surface_ug_m3"])
        ax.scatter(gdf[PM_COL], gdf["no2_surface_ug_m3"], s=28, c="#2c7fb8",
                   edgecolor="white", linewidth=0.5)
        ax.set_xlabel(PM_LABEL)
        ax.set_ylabel("NO$_2$ superficie [µg/m³]")
        ax.set_title(
            f"C) Validez de constructo: PM$_{{2.5}}$ vs NO$_2$\n"
            f"Spearman ρ={rho:.3f} (p={pval:.1e}) → co-exposición urbana\n"
            "(deja sinca_pm25_annual.csv para validar contra monitores)"
        )

    # --- D) Socioeconomic gradient: NSE vs PM2.5 ------------------------- #
    ax = axes[1, 1]
    nse_col = "nse_index_pca" if "nse_index_pca" in gdf.columns else "nse_index"
    rho2, pval2 = spearmanr(gdf[nse_col], gdf[PM_COL])
    ax.scatter(gdf[nse_col], gdf[PM_COL], s=28, c="#d95f0e",
               edgecolor="white", linewidth=0.5)
    ax.set_xlabel("Índice NSE (PCA, z-score; mayor = mejor)")
    ax.set_ylabel(PM_LABEL)
    ax.set_title(
        f"D) Gradiente socioeconómico del PM$_{{2.5}}$\n"
        f"Spearman ρ={rho2:.3f} (p={pval2:.1e})"
    )

    fig.suptitle(
        "Exposoma de PM$_{2.5}$ crónico — Región Metropolitana de Santiago\n"
        "ACAG/van Donkelaar satelital ~1 km (media 2015–2022) + ponderación poblacional (WorldPop)",
        fontsize=14,
        fontweight="bold",
        y=0.99,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    out_path = out_dir / "pm25_santiago_4panel.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()

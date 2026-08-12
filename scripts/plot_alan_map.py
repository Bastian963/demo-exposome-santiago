"""Publication-quality figure for the ALAN (artificial light at night) layer.

Produces a 4-panel summary:
  A) Choropleth of population-weighted VIIRS DNB radiance (log scale).
  B) Ranking of the 52 communes by population-weighted radiance.
  C) Construct-validity scatter: ALAN vs surface NO2 (urban co-exposure).
  D) Socioeconomic gradient scatter: NSE index vs ALAN exposure.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LogNorm
from scipy.stats import spearmanr

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data" / "processed"

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "font.family": "STIXGeneral",
        "mathtext.fontset": "stix",
        "axes.titlesize": 11,
        "axes.labelsize": 10,
    }
)

CMAP = "inferno"
ALAN_COL = "alan_radiance_pop_weighted"
ALAN_LABEL = "Radiancia ALAN ponderada por población [nW/cm²/sr]"


def main() -> None:
    geo = DATA_DIR / "santiago_exposome_master.geojson"
    gdf = gpd.read_file(geo)

    out_dir = REPO_ROOT / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(15, 13))

    vmin = max(gdf[ALAN_COL].min(), 0.1)
    vmax = gdf[ALAN_COL].max()
    norm = LogNorm(vmin=vmin, vmax=vmax)

    # --- A) Choropleth (population-weighted radiance, log scale) ---------- #
    ax = axes[0, 0]
    gdf.plot(
        column=ALAN_COL,
        cmap=CMAP,
        norm=norm,
        linewidth=0.4,
        edgecolor="0.4",
        ax=ax,
        legend=True,
        legend_kwds={"label": ALAN_LABEL, "shrink": 0.6},
    )
    ax.set_title(
        "A) Luz artificial nocturna por comuna\n"
        "(VIIRS DNB 2024, ponderada por población; escala log)"
    )
    ax.axis("off")

    # --- B) Ranking bar chart -------------------------------------------- #
    ax = axes[0, 1]
    ranked = gdf.sort_values(ALAN_COL)
    colors = plt.get_cmap(CMAP)(norm(ranked[ALAN_COL].to_numpy()))
    ax.barh(ranked["name"], ranked[ALAN_COL], color=colors, edgecolor="0.3", linewidth=0.3)
    ax.set_xlabel(ALAN_LABEL)
    ax.set_title("B) Ranking de comunas por exposición a ALAN\n(mayor = más luz nocturna)")
    ax.tick_params(axis="y", labelsize=6.5)
    ax.margins(y=0.005)

    # --- C) Construct validity: ALAN vs surface NO2 ---------------------- #
    ax = axes[1, 0]
    rho, pval = spearmanr(gdf[ALAN_COL], gdf["no2_surface_ug_m3"])
    ax.scatter(
        gdf[ALAN_COL],
        gdf["no2_surface_ug_m3"],
        s=28,
        c="#2c7fb8",
        edgecolor="white",
        linewidth=0.5,
    )
    ax.set_xscale("log")
    ax.set_xlabel(ALAN_LABEL)
    ax.set_ylabel("NO$_2$ superficie [µg/m³]")
    ax.set_title(
        f"C) Validez de constructo: ALAN vs NO$_2$\n"
        f"Spearman ρ={rho:.3f} (p={pval:.1e}) → co-exposición urbana"
    )

    # --- D) Socioeconomic gradient: NSE vs ALAN -------------------------- #
    ax = axes[1, 1]
    nse_col = "nse_index_pca" if "nse_index_pca" in gdf.columns else "nse_index"
    rho2, pval2 = spearmanr(gdf[nse_col], gdf[ALAN_COL])
    ax.scatter(
        gdf[nse_col],
        gdf[ALAN_COL],
        s=28,
        c="#d95f0e",
        edgecolor="white",
        linewidth=0.5,
    )
    ax.set_yscale("log")
    ax.set_xlabel("Índice NSE (PCA, z-score; mayor = mejor)")
    ax.set_ylabel(ALAN_LABEL)
    ax.set_title(
        f"D) Gradiente socioeconómico de la luz nocturna\n"
        f"Spearman ρ={rho2:.3f} (p={pval2:.1e})"
    )

    fig.suptitle(
        "Exposoma de luz artificial nocturna (ALAN) — Región Metropolitana de Santiago\n"
        "VIIRS Day/Night Band 2024, estadísticas comunales + ponderación poblacional (WorldPop)",
        fontsize=14,
        fontweight="bold",
        y=0.99,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    out_path = out_dir / "alan_santiago_4panel.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()

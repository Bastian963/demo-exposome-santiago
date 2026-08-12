"""4-panel summary figure for the heavy metals (RETC) exposome layer.

Panels:
  A) Choropleth — log(Pb + 1) [kg/yr], population-weighted palette.
  B) Ranking of communes by raw Pb emissions (kg/yr).
  C) Scatter: Pb vs PM2.5 (do industrial and combustion sources co-locate?).
  D) Scatter: Pb vs NSE index (environmental justice gradient).
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

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "font.family": "STIXGeneral",
        "mathtext.fontset": "stix",
        "axes.titlesize": 11,
        "axes.labelsize": 10,
    }
)

CMAP = "YlOrBr"
PB_COL = "hm_pb_log"
PB_RAW = "hm_pb_kg"
PB_LABEL_LOG = "log(Pb + 1) [kg/yr, escala log]"
PB_LABEL_RAW = "Pb emisiones industriales [kg/yr]"


def main() -> None:
    geo = DATA_DIR / "santiago_exposome_master.geojson"
    gdf = gpd.read_file(geo)

    out_dir = REPO_ROOT / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(15, 13))

    vmin = float(gdf[PB_COL].min())
    vmax = float(gdf[PB_COL].max())
    norm = plt.Normalize(vmin=vmin, vmax=vmax)

    # --- A) Choropleth (log Pb) ------------------------------------------- #
    ax = axes[0, 0]
    gdf.plot(
        column=PB_COL,
        cmap=CMAP,
        norm=norm,
        linewidth=0.3,
        edgecolor="white",
        ax=ax,
        legend=True,
        legend_kwds={"label": PB_LABEL_LOG, "shrink": 0.6},
    )
    ax.set_title(
        "A) Emisiones industriales de Pb por comuna\n"
        "(RETC fuentes puntuales, media 2015–2022, escala log)"
    )
    ax.axis("off")

    # --- B) Ranking bar chart (raw Pb, top communes) ---------------------- #
    ax = axes[0, 1]
    ranked = gdf.nlargest(20, PB_RAW).sort_values(PB_RAW)
    colors = plt.get_cmap(CMAP)(norm(np.log1p(ranked[PB_RAW].to_numpy())))
    ax.barh(ranked["name"], ranked[PB_RAW], color=colors, edgecolor="0.3", linewidth=0.3)
    ax.set_xlabel(PB_LABEL_RAW)
    ax.set_title("B) Top 20 comunas por emisiones de Pb\n(fuentes industriales RETC)")
    ax.tick_params(axis="y", labelsize=8)
    ax.margins(y=0.01)

    # --- C) Pb vs PM2.5 --------------------------------------------------- #
    ax = axes[1, 0]
    rho, pval = spearmanr(gdf[PB_COL], gdf["pm25_pop_weighted"])
    ax.scatter(
        gdf[PB_COL], gdf["pm25_pop_weighted"],
        s=28, c="#b2182b", edgecolor="white", linewidth=0.5,
    )
    # Highlight Tiltil
    tiltil = gdf[gdf["name"] == "Tiltil"]
    if len(tiltil):
        ax.scatter(
            tiltil[PB_COL], tiltil["pm25_pop_weighted"],
            s=80, c="#d6604d", edgecolor="#67001f", linewidth=1.2,
            zorder=5, label="Tiltil",
        )
        ax.legend(fontsize=8)
    ax.set_xlabel(PB_LABEL_LOG)
    ax.set_ylabel("PM$_{2.5}$ crónico ponderado por población [µg/m³]")
    ax.set_title(
        f"C) Fuentes industriales (Pb) vs PM$_{{2.5}}$ ambiental\n"
        f"Spearman ρ={rho:.3f} (p={pval:.1e})"
        " → ¿co-localización de exposiciones?"
    )

    # --- D) NSE gradient -------------------------------------------------- #
    ax = axes[1, 1]
    nse_col = "nse_index_pca" if "nse_index_pca" in gdf.columns else "nse_index"
    rho2, pval2 = spearmanr(gdf[nse_col], gdf[PB_COL])
    ax.scatter(
        gdf[nse_col], gdf[PB_COL],
        s=28, c="#d95f0e", edgecolor="white", linewidth=0.5,
    )
    ax.set_xlabel("Índice NSE (PCA z-score; mayor = mejor posición)")
    ax.set_ylabel(PB_LABEL_LOG)
    ax.set_title(
        f"D) Gradiente socioeconómico de emisiones de Pb\n"
        f"Spearman ρ={rho2:.3f} (p={pval2:.1e})"
    )

    fig.suptitle(
        "Exposoma de metales pesados — Región Metropolitana de Santiago\n"
        "RETC / MMA: Emisiones al aire de fuentes puntuales (media 2015–2022)",
        fontsize=14,
        fontweight="bold",
        y=0.99,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    out_path = out_dir / "heavy_metals_santiago_4panel.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()

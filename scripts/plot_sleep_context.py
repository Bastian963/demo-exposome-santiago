"""Summary figure for the sleep-circadian context layer.

Produces a 3-panel diagnostic:
  A) Choropleth of the sleep-circadian context index.
  B) Ranking of communes by the index.
  C) ALAN vs warm-night exposure, coloured by the index.
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
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

INDEX_COL = "sleep_context_index"
ALAN_COL = "sleep_alan_log"
NIGHTS_COL = "sleep_tropical_nights_20c"
CMAP = "magma_r"


def main() -> None:
    geo = DATA_DIR / "santiago_sleep_context.geojson"
    gdf = gpd.read_file(geo)

    out_dir = REPO_ROOT / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(17, 8.5))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.1, 1.2, 1.0])

    # --- A) Choropleth ---------------------------------------------------- #
    ax = fig.add_subplot(gs[0, 0])
    gdf.plot(
        column=INDEX_COL,
        cmap=CMAP,
        vmin=0,
        vmax=100,
        linewidth=0.4,
        edgecolor="0.4",
        ax=ax,
        legend=True,
        legend_kwds={"label": "Índice sueño-circadiano (0-100)", "shrink": 0.65},
    )
    ax.set_title("A) Contexto sueño-circadiano\n(mayor = más riesgo ambiental)")
    ax.axis("off")

    # --- B) Ranking ------------------------------------------------------- #
    ax = fig.add_subplot(gs[0, 1])
    ranked = gdf.sort_values(INDEX_COL)
    colors = plt.get_cmap(CMAP)(ranked[INDEX_COL].to_numpy() / 100)
    ax.barh(ranked["name"], ranked[INDEX_COL], color=colors, edgecolor="0.35", linewidth=0.3)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Índice sueño-circadiano (0-100)")
    ax.set_title("B) Ranking comunal")
    ax.tick_params(axis="y", labelsize=6.5)
    ax.margins(y=0.005)

    # --- C) ALAN vs warm nights ----------------------------------------- #
    ax = fig.add_subplot(gs[0, 2])
    rho, pval = spearmanr(gdf[ALAN_COL], gdf[NIGHTS_COL])
    sc = ax.scatter(
        gdf[ALAN_COL],
        gdf[NIGHTS_COL],
        c=gdf[INDEX_COL],
        cmap=CMAP,
        vmin=0,
        vmax=100,
        s=45,
        edgecolor="white",
        linewidth=0.5,
    )
    ax.set_xlabel("log(1 + ALAN ponderada por población)")
    ax.set_ylabel("Noches tropicales >=20 C")
    ax.set_title(f"C) Co-exposición: luz y noches cálidas\nSpearman ρ={rho:.3f} (p={pval:.1e})")
    fig.colorbar(sc, ax=ax, label="Índice sueño-circadiano")

    fig.suptitle(
        "Contexto ambiental sueño-circadiano — Región Metropolitana de Santiago\n"
        "Proxy comunal basado en ALAN, noches cálidas, temperatura mínima de verano y vulnerabilidad social",
        fontsize=14,
        fontweight="bold",
        y=0.99,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.94])

    out_path = out_dir / "sleep_context_santiago.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()

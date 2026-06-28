"""Publication-quality figures for the socioeconomic (NSE) exposome layer.

Produces a 4-panel summary:
  A) Choropleth of the PCA-weighted NSE index (nse_index_pca).
  B) Ranking of the 52 communes, coloured by NSE quintile.
  C) Weighting-sensitivity scatter: equal-weight vs PCA index.
  D) External-validation scatter if available, otherwise PC1 component loadings.
"""
from __future__ import annotations

import json
import sys
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

QUINTILE_COLORS = ["#7b3294", "#c2a5cf", "#f7f7f7", "#a6dba0", "#008837"]


def _quintile_cmap(values: pd.Series):
    from matplotlib.colors import ListedColormap

    return ListedColormap(QUINTILE_COLORS), values.astype(int) - 1


def main() -> None:
    csv = DATA_DIR / "socioeconomic_exposome_rm_santiago.csv"
    geo = DATA_DIR / "socioeconomic_exposome_rm_santiago.geojson"
    meta_path = DATA_DIR / "socioeconomic_exposome_rm_santiago_metadata.json"

    df = pd.read_csv(csv)
    gdf = gpd.read_file(geo)
    meta = json.loads(meta_path.read_text())

    out_dir = REPO_ROOT / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(15, 13))

    # --- A) Choropleth of PCA NSE index ---------------------------------- #
    ax = axes[0, 0]
    gdf.plot(
        column="nse_index_pca",
        cmap="RdYlGn",
        linewidth=0.4,
        edgecolor="0.3",
        ax=ax,
        legend=True,
        legend_kwds={"label": "Índice NSE (PCA, z-score)", "shrink": 0.6},
    )
    ax.set_title("A) Nivel socioeconómico por comuna\n(PC1 multidimensional, mayor = mejor)")
    ax.axis("off")

    # --- B) Ranking bar chart -------------------------------------------- #
    ax = axes[0, 1]
    ranked = df.sort_values("nse_index_pca")
    cmap, q_idx = _quintile_cmap(ranked["nse_quintil"])
    colors = [QUINTILE_COLORS[i] for i in q_idx]
    ax.barh(ranked["name"], ranked["nse_index_pca"], color=colors, edgecolor="0.3", linewidth=0.3)
    ax.set_xlabel("Índice NSE (PCA, z-score)")
    ax.set_title("B) Ranking de comunas por NSE\n(color = quintil; 1 vulnerable → 5 acomodado)")
    ax.tick_params(axis="y", labelsize=6.5)
    ax.axvline(0, color="0.5", linewidth=0.8, linestyle="--")
    ax.margins(y=0.005)

    # --- C) Weighting-sensitivity scatter -------------------------------- #
    ax = axes[1, 0]
    rho, pval = spearmanr(df["nse_index"], df["nse_index_pca"])
    ax.scatter(df["nse_index"], df["nse_index_pca"], s=28, c="#2c7fb8", edgecolor="white", linewidth=0.5)
    lims = [
        min(df["nse_index"].min(), df["nse_index_pca"].min()) - 0.2,
        max(df["nse_index"].max(), df["nse_index_pca"].max()) + 0.2,
    ]
    ax.plot(lims, lims, color="0.6", linewidth=0.8, linestyle="--")
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.set_xlabel("NSE equiponderado (media de z-scores)")
    ax.set_ylabel("NSE por PCA (PC1)")
    ax.set_title(
        f"C) Sensibilidad a la ponderación\nSpearman ρ={rho:.3f} "
        f"(p={pval:.1e}) → ranking robusto"
    )

    # --- D) External validation OR PC1 loadings -------------------------- #
    ax = axes[1, 1]
    ok = [v for v in meta.get("external_validation", []) if v.get("status") == "ok"]
    if ok:
        v = ok[0]
        ax.text(
            0.5,
            0.95,
            f"D) Validación externa vs {v['source']}\n"
            f"Spearman ρ={v['spearman_rho']:.3f} (n={v['n_matched']})",
            ha="center",
            va="top",
            transform=ax.transAxes,
            fontsize=10,
        )
        ax.axis("off")
    else:
        loadings = meta["index"]["pca_loadings_pc1"]
        labels = {
            "ingreso": "Ingreso (+)",
            "escolaridad": "Escolaridad (+)",
            "pobreza_pct": "Pobreza ingresos (−)",
            "pobreza_multi_pct": "Pobreza multidim. (−)",
            "viv_materialidad_deficitaria_pct": "Vivienda deficitaria (−)",
            "hacinamiento_phh": "Hacinamiento (−)",
        }
        names = [labels.get(k, k) for k in loadings]
        vals = list(loadings.values())
        ax.barh(names, vals, color="#41b6c4", edgecolor="0.3", linewidth=0.3)
        ax.set_xlabel("Carga en PC1 (|loading|)")
        var = meta["index"]["pca_variance_explained_pc1"]
        ax.set_title(
            f"D) Estructura del índice (cargas PC1)\n"
            f"PC1 explica {var:.0%} de la varianza; 6 dimensiones contribuyen"
        )
        ax.invert_yaxis()

    fig.suptitle(
        "Exposoma socioeconómico — Región Metropolitana de Santiago\n"
        "Índice multidimensional (CASEN 2022 + pobreza SAE + Censo 2017)",
        fontsize=14,
        fontweight="bold",
        y=0.99,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    out_path = out_dir / "socioeconomic_santiago_4panel.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()

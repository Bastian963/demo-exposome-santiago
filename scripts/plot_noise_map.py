"""Publication-quality figure for the traffic noise exposome layer.

Mapa de Ruido Gran Santiago Urbano 2023 — MMA / April 2024.

Produces a 4-panel summary:
  A) Choropleth: % population exposed to daytime noise Ld > 65 dBA.
  B) Choropleth: % population exposed to nighttime noise Ln > 55 dBA.
  C) Ranked bar chart of communes by combined noise exposure %.
  D) Socioeconomic gradient: NSE index vs combined noise exposure.

Communes outside the GSU urban perimeter (noise_in_gsu_map = 0) are shown
in light grey with cross-hatching to signal "not modelled".
"""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.patches as mpatches
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

CMAP = "YlOrRd"
NO_DATA_COLOR = "#d0d0d0"
NO_DATA_HATCH = "////"


def _load_data() -> gpd.GeoDataFrame:
    """Load noise GeoJSON and optionally enrich with socioeconomic columns."""
    noise_geo = DATA_DIR / "santiago_noise_mma_2023.geojson"
    if not noise_geo.exists():
        raise FileNotFoundError(
            f"Noise GeoJSON not found: {noise_geo}\n"
            "Run: python scripts/run_noise.py"
        )
    gdf = gpd.read_file(noise_geo)

    # Try to add NSE index from master or socioeconomic layer for panel D.
    for src in [
        DATA_DIR / "santiago_exposome_master.geojson",
        DATA_DIR / "socioeconomic_exposome_rm_santiago.geojson",
        DATA_DIR / "socioeconomic_exposome_rm_santiago.csv",
    ]:
        if src.exists():
            nse_df = (
                gpd.read_file(src) if src.suffix == ".geojson" else pd.read_csv(src)
            )
            nse_col = "nse_index_pca" if "nse_index_pca" in nse_df.columns else "nse_index"
            if nse_col in nse_df.columns and "name" in nse_df.columns:
                gdf = gdf.merge(nse_df[["name", nse_col]], on="name", how="left")
                gdf = gdf.rename(columns={nse_col: "nse_index"})
                break

    return gdf


def _choropleth(
    ax: plt.Axes,
    gdf: gpd.GeoDataFrame,
    col: str,
    title: str,
    label: str,
    norm: Normalize,
) -> None:
    """Draw a choropleth handling not-modelled communes as hatched grey."""
    in_map = gdf[gdf["noise_in_gsu_map"] == 1]
    out_map = gdf[gdf["noise_in_gsu_map"] == 0]

    # Grey hatched background for communes outside the GSU perimeter.
    out_map.plot(ax=ax, color=NO_DATA_COLOR, linewidth=0.3, edgecolor="0.5")
    for geom in out_map.geometry:
        patch = mpatches.PathPatch(
            plt.matplotlib.path.Path.make_compound_path(
                *[
                    plt.matplotlib.path.Path(np.array(p.exterior.coords))
                    for p in (
                        [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
                    )
                ]
            ),
            hatch=NO_DATA_HATCH,
            facecolor="none",
            edgecolor="0.65",
            linewidth=0.2,
        )
        ax.add_patch(patch)

    # Coloured communes in the GSU map.
    in_map.plot(
        column=col,
        cmap=CMAP,
        norm=norm,
        linewidth=0.4,
        edgecolor="0.4",
        ax=ax,
        legend=True,
        legend_kwds={"label": label, "shrink": 0.55, "pad": 0.01},
    )

    ax.set_title(title)
    ax.axis("off")

    # Legend patch for no-data communes.
    no_data_patch = mpatches.Patch(
        facecolor=NO_DATA_COLOR,
        edgecolor="0.5",
        hatch=NO_DATA_HATCH,
        linewidth=0.5,
        label="Fuera del área GSU (no modelado)",
    )
    ax.legend(handles=[no_data_patch], loc="lower left", fontsize=7, framealpha=0.8)


def main() -> None:
    gdf = _load_data()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    in_map = gdf[gdf["noise_in_gsu_map"] == 1].copy()
    pct_max = max(
        gdf["noise_ld_pct_exposed"].max(),
        gdf["noise_ln_pct_exposed"].max(),
    )
    norm = Normalize(vmin=0, vmax=pct_max)

    fig, axes = plt.subplots(2, 2, figsize=(15, 13))

    # --- A) Choropleth Ld (daytime) --------------------------------------- #
    _choropleth(
        axes[0, 0],
        gdf,
        col="noise_ld_pct_exposed",
        title=(
            "A) Exposición al ruido diurno (Ld > 65 dBA)\n"
            "% de población comunal expuesta — OCDE umbral día"
        ),
        label="% población con Ld > 65 dBA",
        norm=norm,
    )

    # --- B) Choropleth Ln (nighttime) ------------------------------------- #
    _choropleth(
        axes[0, 1],
        gdf,
        col="noise_ln_pct_exposed",
        title=(
            "B) Exposición al ruido nocturno (Ln > 55 dBA)\n"
            "% de población comunal expuesta — OCDE umbral noche"
        ),
        label="% población con Ln > 55 dBA",
        norm=norm,
    )

    # --- C) Ranking bar chart --------------------------------------------- #
    ax = axes[1, 0]
    ranked = in_map.sort_values("noise_combined_pct")
    cmap_fn = plt.get_cmap(CMAP)
    colors = cmap_fn(norm(ranked["noise_combined_pct"].to_numpy()))

    bars = ax.barh(
        ranked["name"],
        ranked["noise_combined_pct"],
        color=colors,
        edgecolor="0.3",
        linewidth=0.3,
    )
    # Dual markers for Ld and Ln.
    ax.scatter(
        ranked["noise_ld_pct_exposed"],
        range(len(ranked)),
        marker="D",
        s=14,
        color="#e31a1c",
        zorder=3,
        label="Ld > 65 dBA (día)",
    )
    ax.scatter(
        ranked["noise_ln_pct_exposed"],
        range(len(ranked)),
        marker="o",
        s=14,
        color="#08519c",
        zorder=3,
        label="Ln > 55 dBA (noche)",
    )
    ax.set_xlabel("% población expuesta")
    ax.set_title(
        "C) Ranking de comunas por exposición combinada al ruido\n"
        "(media Ld+Ln; rombos = día, círculos = noche)"
    )
    ax.tick_params(axis="y", labelsize=6.5)
    ax.margins(y=0.005)
    ax.legend(fontsize=7.5, loc="lower right")

    # --- D) Socioeconomic gradient ---------------------------------------- #
    ax = axes[1, 1]
    if "nse_index" in gdf.columns and gdf["nse_index"].notna().any():
        valid = in_map.dropna(subset=["nse_index", "noise_combined_pct"])
        rho, pval = spearmanr(valid["nse_index"], valid["noise_combined_pct"])
        sc = ax.scatter(
            valid["nse_index"],
            valid["noise_combined_pct"],
            s=40,
            c=valid["noise_combined_pct"],
            cmap=CMAP,
            norm=norm,
            edgecolor="0.3",
            linewidth=0.5,
        )
        # Label the top 5 noisiest.
        for _, row in valid.nlargest(5, "noise_combined_pct").iterrows():
            ax.annotate(
                row["name"],
                xy=(row["nse_index"], row["noise_combined_pct"]),
                fontsize=6.5,
                ha="left",
                xytext=(4, 0),
                textcoords="offset points",
            )
        ax.set_xlabel("Índice NSE (mayor = mejor situación socioeconómica)")
        ax.set_ylabel("Exposición combinada ruido [% promedio Ld+Ln]")
        ax.set_title(
            f"D) Gradiente socioeconómico: NSE vs exposición al ruido\n"
            f"Spearman ρ={rho:.3f} (p={pval:.1e}) — 35 comunas GSU"
        )
    else:
        ax.text(
            0.5, 0.5,
            "NSE no disponible\n(ejecutar scripts/run_socioeconomic.py)",
            ha="center", va="center", transform=ax.transAxes, fontsize=10,
        )
        ax.set_title("D) Gradiente socioeconómico vs ruido")
        ax.axis("off")

    fig.suptitle(
        "Exposoma de ruido ambiental — Gran Santiago Urbano\n"
        "Mapa de Ruido GSU 2023 (MMA, abril 2024) · 35 comunas · "
        "Modelación tránsito vehicular, 13 590 km de red vial",
        fontsize=13,
        fontweight="bold",
        y=0.995,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.965])

    out_path = FIGURES_DIR / "noise_santiago_4panel.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()

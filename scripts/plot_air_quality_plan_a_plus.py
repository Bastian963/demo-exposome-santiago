"""Generate before/after comparison figure: CAMS 11 km vs satellite ~3 km.

Plan A+ version: includes surface-concentration conversion panel.
"""
from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Add repo root so `exposome` is importable
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from exposome import config  # noqa: E402


def main() -> None:
    cfg = config.load_config("santiago")
    out_dir = Path("figures")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load old CAMS data (Open-Meteo, ~11 km)
    old_csv = REPO_ROOT / "data" / "processed" / "air_quality_exposome_rm_santiago.csv"
    old_df = pd.read_csv(old_csv)

    # Load new satellite data (GEE, ~3 km) with surface conversion
    new_csv = REPO_ROOT / "data" / "processed" / "santiago_air_quality_satellite_2024.csv"
    new_df = pd.read_csv(new_csv)

    # Base geometry
    geo_path = REPO_ROOT / "data" / "processed" / "socioeconomic_exposome_rm_santiago.geojson"
    gdf = gpd.read_file(geo_path)[["name", "geometry"]]

    old_gdf = gdf.merge(old_df, on="name", how="left")
    new_gdf = gdf.merge(new_df, on="name", how="left")

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    cmap = "YlOrRd"

    # --- Left panel — CAMS 11 km (NO2 in µg/m³) ---
    ax = axes[0]
    vmin, vmax = old_gdf["no2_mean"].min(), old_gdf["no2_mean"].max()
    old_gdf.plot(
        column="no2_mean",
        cmap=cmap,
        linewidth=0.5,
        edgecolor="0.3",
        ax=ax,
        vmin=vmin,
        vmax=vmax,
        legend=True,
        legend_kwds={"label": "NO₂ [µg/m³]", "shrink": 0.6},
    )
    ax.set_title("A) CAMS reanálisis — Open-Meteo\nResolución ~11 km", fontsize=11)
    ax.axis("off")
    dup_val = old_gdf["no2_mean"].round(2).value_counts().idxmax()
    n_dup = (old_gdf["no2_mean"].round(2) == dup_val).sum()
    ax.annotate(
        f"{n_dup} comunas comparten\nel mismo valor ({dup_val} µg/m³)",
        xy=(0.03, 0.03),
        xycoords="axes fraction",
        fontsize=9,
        color="darkred",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
    )

    # --- Middle panel — Satellite column density (raw, mol/m²) ---
    ax = axes[1]
    vmin2, vmax2 = new_gdf["no2_mean"].min(), new_gdf["no2_mean"].max()
    new_gdf.plot(
        column="no2_mean",
        cmap=cmap,
        linewidth=0.5,
        edgecolor="0.3",
        ax=ax,
        vmin=vmin2,
        vmax=vmax2,
        legend=True,
        legend_kwds={"label": "NO₂ columna [mol/m²]", "shrink": 0.6},
    )
    ax.set_title("B) Satélite Sentinel-5P — GEE\nColumna troposférica (~3.5 km)", fontsize=11)
    ax.axis("off")
    ax.annotate(
        "Mayor detalle espacial,\npero unidad no comparable\ncon guías WHO",
        xy=(0.03, 0.03),
        xycoords="axes fraction",
        fontsize=9,
        color="darkblue",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
    )

    # --- Right panel — Satellite surface concentration (µg/m³) ---
    ax = axes[2]
    vmin3, vmax3 = new_gdf["no2_surface_ug_m3"].min(), new_gdf["no2_surface_ug_m3"].max()
    new_gdf.plot(
        column="no2_surface_ug_m3",
        cmap=cmap,
        linewidth=0.5,
        edgecolor="0.3",
        ax=ax,
        vmin=vmin3,
        vmax=vmax3,
        legend=True,
        legend_kwds={"label": "NO₂ superficie [µg/m³]", "shrink": 0.6},
    )
    ax.set_title("C) Plan A+ — Conversión física\nERA5 BLH → µg/m³ (~3.5 km)", fontsize=11)
    ax.axis("off")
    ax.annotate(
        f"Rango comparable con CAMS:\n{vmin3:.1f} – {vmax3:.1f} µg/m³\n"
        "Gradiente intra-urbano resuelto",
        xy=(0.03, 0.03),
        xycoords="axes fraction",
        fontsize=9,
        color="darkgreen",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
    )

    fig.suptitle(
        "Calidad del aire en Santiago: evolución de la resolución y las unidades",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    out_path = out_dir / "air_quality_plan_a_plus_3panel.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()

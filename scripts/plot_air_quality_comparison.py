"""Generate before/after comparison figure: CAMS 11 km vs satellite ~3 km."""
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

    # Load new satellite data (GEE, ~3 km)
    new_csv = REPO_ROOT / "data" / "processed" / "santiago_air_quality_satellite_2024.csv"
    new_df = pd.read_csv(new_csv)

    # Base geometry
    geo_path = REPO_ROOT / "data" / "processed" / "socioeconomic_exposome_rm_santiago.geojson"
    gdf = gpd.read_file(geo_path)[["name", "geometry"]]

    old_gdf = gdf.merge(old_df, on="name", how="left")
    new_gdf = gdf.merge(new_df, on="name", how="left")

    # For a fair visual comparison of spatial detail, normalise each to 0-1
    # (since units differ: CAMS = µg/m³ surface, satellite = mol/m² column)
    for g, col in [(old_gdf, "no2_mean"), (new_gdf, "no2_mean")]:
        g[f"{col}_norm"] = (g[col] - g[col].min()) / (g[col].max() - g[col].min())

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    cmap = "YlOrRd"

    # Left panel — CAMS 11 km
    ax = axes[0]
    old_gdf.plot(
        column="no2_mean_norm",
        cmap=cmap,
        linewidth=0.5,
        edgecolor="0.3",
        ax=ax,
        vmin=0,
        vmax=1,
        legend=True,
        legend_kwds={"label": "Normalised NO₂ (0 = min, 1 = max)", "shrink": 0.6},
    )
    ax.set_title("A) CAMS reanálisis — Open-Meteo\nResolución ~11 km", fontsize=12)
    ax.axis("off")
    # Annotate duplicate-value clusters
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

    # Right panel — Satellite ~3 km
    ax = axes[1]
    new_gdf.plot(
        column="no2_mean_norm",
        cmap=cmap,
        linewidth=0.5,
        edgecolor="0.3",
        ax=ax,
        vmin=0,
        vmax=1,
        legend=True,
        legend_kwds={"label": "Normalised column NO₂ (0 = min, 1 = max)", "shrink": 0.6},
    )
    ax.set_title("B) Satélite Sentinel-5P — GEE\nResolución ~3.5 km", fontsize=12)
    ax.axis("off")
    ax.annotate(
        "Gradiente intra-urbano visible:\n"
        "oriente (cordillera, limpio)\n"
        "vs poniente/sur (contaminado)",
        xy=(0.03, 0.03),
        xycoords="axes fraction",
        fontsize=9,
        color="darkgreen",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
    )

    fig.suptitle(
        "Calidad del aire en Santiago: antes vs después de integrar satélites",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    out_path = out_dir / "air_quality_before_after_satellite.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"Saved {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()

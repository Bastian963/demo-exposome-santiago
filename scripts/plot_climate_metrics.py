"""4-panel choropleth figure for the climate_openmeteo exposome layer.

Panels:
  A) Temperatura media anual (°C).
  B) Días calurosos ≥30 °C.
  C) Noches tropicales ≥20 °C.
  D) Amplitud estacional (°C).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "font.family": "STIXGeneral",
        "mathtext.fontset": "stix",
        "axes.titlesize": 11,
        "axes.labelsize": 10,
    }
)


def plot_climate_metrics_map(
    metrics_csv: Path = Path("data/processed/santiago_climate_metrics_annual.csv"),
    boundaries_geojson: Path = Path("cache/santiago_communes.geojson"),
    out_path: Path = Path("figures/climate_metrics_santiago.png"),
) -> None:
    """Create a 4-panel choropleth of the climate_openmeteo layer."""
    df = pd.read_csv(metrics_csv)
    gdf = gpd.read_file(boundaries_geojson)
    gdf = gdf.merge(df, on="name", how="left")

    metrics = [
        ("tmean_annual", "Temperatura media anual (°C)", "RdYlBu_r"),
        ("hot_days_30c", "Días calurosos ≥30 °C", "YlOrRd"),
        ("tropical_nights_20c", "Noches tropicales ≥20 °C", "magma"),
        ("seasonal_amplitude", "Amplitud estacional (°C)", "viridis"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(15, 13))

    for ax, (col, title, cmap) in zip(axes.flatten(), metrics):
        gdf.plot(
            column=col,
            cmap=cmap,
            linewidth=0.3,
            edgecolor="white",
            ax=ax,
            legend=True,
            legend_kwds={"shrink": 0.6},
        )
        ax.set_title(title, fontsize=11)
        ax.axis("off")

    fig.suptitle(
        "Exposoma climático Open-Meteo — Región Metropolitana de Santiago\n"
        "Open-Meteo Historical Weather Archive (2024, temperatura del aire a 2 m)",
        fontsize=14,
        fontweight="bold",
        y=0.99,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    plot_climate_metrics_map()

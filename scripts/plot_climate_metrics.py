"""Generate climate exposome comparison figures."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_climate_metrics_map(
    metrics_csv: Path = Path("data/processed/santiago_climate_metrics_annual.csv"),
    boundaries_geojson: Path = Path("cache/santiago_communes.geojson"),
    out_path: Path = Path("figures/climate_metrics_santiago.png"),
) -> None:
    """Create a multi-panel figure of key climate metrics."""
    df = pd.read_csv(metrics_csv)
    gdf = gpd.read_file(boundaries_geojson)
    gdf = gdf.merge(df, on="name", how="left")

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    axes = axes.flatten()

    metrics = [
        ("tmean_annual", "Temperatura media anual (°C)"),
        ("hot_days_30c", "Días calurosos ≥30°C"),
        ("tropical_nights_20c", "Noches tropicales ≥20°C"),
        ("heat_wave_days", "Días de ola de calor"),
        ("cold_spell_days", "Días de ola de frío"),
        ("seasonal_amplitude", "Amplitud estacional (°C)"),
    ]

    for ax, (col, title) in zip(axes, metrics):
        gdf.plot(column=col, ax=ax, cmap="RdYlBu_r", legend=True, legend_kwds={"shrink": 0.6})
        ax.set_title(title, fontsize=10)
        ax.axis("off")

    fig.suptitle("Exposoma Climático — Región Metropolitana de Santiago (2024)", fontsize=14, y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    plot_climate_metrics_map()

"""Generate a four-panel precipitation exposome figure."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt

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


def main() -> None:
    geojson = DATA_DIR / "santiago_precipitation_chirps_2015_2024.geojson"
    if not geojson.exists():
        raise FileNotFoundError(
            f"Missing {geojson}. Run scripts/run_precipitation.py first."
        )

    gdf = gpd.read_file(geojson)

    out_dir = REPO_ROOT / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    axes = axes.flatten()

    panels = [
        ("precip_annual_mean_mm", "A) Precipitación anual media [mm]", "Blues"),
        ("precip_wet_day_pct", "B) Días húmedos [%]", "PuBuGn"),
        ("precip_rx5day_mm", "C) Máximo anual de 5 días [mm]", "YlGnBu"),
        ("precip_extremes_index", "D) Índice de extremos de lluvia [0-100]", "magma"),
    ]

    for ax, (column, title, cmap) in zip(axes, panels):
        gdf.plot(
            column=column,
            cmap=cmap,
            linewidth=0.4,
            edgecolor="0.4",
            ax=ax,
            legend=True,
            legend_kwds={"shrink": 0.65},
        )
        ax.set_title(title)
        ax.axis("off")

    fig.suptitle(
        "Exposoma de precipitación — Región Metropolitana de Santiago\n"
        "CHIRPS diario 2015-2024, estadísticas comunales",
        fontsize=14,
        fontweight="bold",
        y=0.98,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.94])

    out_path = out_dir / "precipitation_santiago_4panel.png"
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
